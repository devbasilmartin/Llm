"""Step 2 of the learning track: a tiny GPT, from scratch, in numpy.

    python -m learn.gpt train --steps 3000      # learns from learn/data/wiki.txt
    python -m learn.gpt sample --chars 500      # writes a fake wiki page

It reads text one character at a time and learns to guess the next character. That's the
whole trick behind every GPT: guess the next piece, over and over, and get a little less
wrong each time. Big models guess word-pieces with billions of numbers; this one guesses
letters with about two hundred thousand, small enough for a CPU.

Everything is written out by hand, the backward pass included, so you can read how it
learns. Each part has a forward (compute an answer) and a backward (work out how each
number should change to make the answer less wrong). tests/test_gpt.py checks every
backward against a slow numerical estimate.

The parts, in the order the text flows through them:
1. Tokenizer: characters <-> numbers.
2. Embeddings: each character (and each position) becomes a vector of numbers to learn.
3. Blocks, each with
   a. layer norm: rescales each vector so the numbers stay in a sane range;
   b. causal self-attention: each position looks back at the earlier ones and gathers
      what matters for guessing the next character ("causal": never at later ones);
   c. an MLP: a small network applied to each position on its own, to think about what
      attention gathered.
   Both add their result to what came in (a "residual"), so information can flow
   straight through.
4. A last layer norm and a linear layer: a score for every possible next character.
5. Loss: cross-entropy, how surprised the model was by the real next character.
6. Adam: nudges every number a little in the direction that lowers the loss.
7. Sampling: generate text by guessing a character, adding it, and guessing again.
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"


# --- 1. the tokenizer ----------------------------------------------------------------------
class Tokenizer:
    """Every character that appears in the training text gets a number."""

    def __init__(self, chars: str):
        self.chars = "".join(sorted(set(chars)))
        self.index = {c: i for i, c in enumerate(self.chars)}

    @property
    def size(self) -> int:
        return len(self.chars)

    def encode(self, text: str) -> np.ndarray:
        return np.array([self.index[c] for c in text if c in self.index], dtype=np.int64)

    def decode(self, ids) -> str:
        return "".join(self.chars[int(i)] for i in ids)


# --- the model's size ------------------------------------------------------------------------
@dataclass
class Config:
    vocab: int                  # how many different characters
    context: int = 64           # how many characters back it can look
    width: int = 64             # numbers per vector ("embedding size")
    heads: int = 4              # attention heads: separate ways of looking back
    layers: int = 2             # blocks stacked on top of each other


def init(cfg: Config, seed: int = 0, dtype=np.float32) -> dict[str, np.ndarray]:
    """Random starting numbers: small, so nothing is too loud at the start."""
    rng = np.random.default_rng(seed)
    C, V = cfg.width, cfg.vocab

    def w(*shape, scale=0.02):
        return (rng.standard_normal(shape) * scale).astype(dtype)
    p = {"tok": w(V, C), "pos": w(cfg.context, C)}
    for i in range(cfg.layers):
        p |= {f"{i}.ln1.g": np.ones(C, dtype), f"{i}.ln1.b": np.zeros(C, dtype),
              f"{i}.qkv.w": w(C, 3 * C), f"{i}.qkv.b": np.zeros(3 * C, dtype),
              f"{i}.proj.w": w(C, C, scale=0.02 / np.sqrt(2 * cfg.layers)),
              f"{i}.proj.b": np.zeros(C, dtype),
              f"{i}.ln2.g": np.ones(C, dtype), f"{i}.ln2.b": np.zeros(C, dtype),
              f"{i}.fc.w": w(C, 4 * C), f"{i}.fc.b": np.zeros(4 * C, dtype),
              f"{i}.out.w": w(4 * C, C, scale=0.02 / np.sqrt(2 * cfg.layers)),
              f"{i}.out.b": np.zeros(C, dtype)}
    p |= {"lnf.g": np.ones(C, dtype), "lnf.b": np.zeros(C, dtype),
          "head.w": w(C, V), "head.b": np.zeros(V, dtype)}
    return p


# --- 3a. layer norm --------------------------------------------------------------------------
EPS = 1e-5


def layernorm(x, g, b):
    mu = x.mean(-1, keepdims=True)
    var = x.var(-1, keepdims=True)
    inv = 1.0 / np.sqrt(var + EPS)
    xhat = (x - mu) * inv                   # each vector now has mean 0, spread 1
    return xhat * g + b, (xhat, inv, g)     # ...then a learned scale and shift


def layernorm_back(dy, cache):
    xhat, inv, g = cache
    dg = (dy * xhat).reshape(-1, xhat.shape[-1]).sum(0)
    db = dy.reshape(-1, dy.shape[-1]).sum(0)
    dxhat = dy * g
    n = xhat.shape[-1]
    # every input affects the mean and spread too, hence the two correction terms
    dx = inv / n * (n * dxhat - dxhat.sum(-1, keepdims=True)
                    - xhat * (dxhat * xhat).sum(-1, keepdims=True))
    return dx, dg, db


# --- linear layers ---------------------------------------------------------------------------
def linear(x, w, b):
    return x @ w + b, x


def linear_back(dy, x, w):
    dw = x.reshape(-1, x.shape[-1]).T @ dy.reshape(-1, dy.shape[-1])
    db = dy.reshape(-1, dy.shape[-1]).sum(0)
    return dy @ w.T, dw, db


# --- 3b. causal self-attention ---------------------------------------------------------------
def softmax(x):
    e = np.exp(x - x.max(-1, keepdims=True))   # minus the max: same answer, no overflow
    return e / e.sum(-1, keepdims=True)


def attention(x, p, i, heads):
    B, T, C = x.shape
    hs = C // heads
    qkv, x_in = linear(x, p[f"{i}.qkv.w"], p[f"{i}.qkv.b"])
    # each position makes a query ("what am I looking for?"), a key ("what do I have?")
    # and a value ("what I'll pass on"), split into heads
    q, k, v = (qkv[..., j * C:(j + 1) * C].reshape(B, T, heads, hs).transpose(0, 2, 1, 3)
               for j in range(3))
    scale = 1.0 / np.sqrt(hs)
    scores = q @ k.transpose(0, 1, 3, 2) * scale        # how well each query matches each key
    future = np.triu(np.ones((T, T), dtype=bool), 1)
    scores = np.where(future, -1e9, scores)             # no peeking at later characters
    att = softmax(scores)                               # match scores -> weights summing to 1
    y = (att @ v).transpose(0, 2, 1, 3).reshape(B, T, C)   # a weighted mix of the values
    out, y_in = linear(y, p[f"{i}.proj.w"], p[f"{i}.proj.b"])
    return out, (x_in, q, k, v, att, scale, y_in)


def attention_back(dout, cache, p, i, heads):
    x_in, q, k, v, att, scale, y_in = cache
    B, T, C = x_in.shape
    hs = C // heads
    dy, dpw, dpb = linear_back(dout, y_in, p[f"{i}.proj.w"])
    dy = dy.reshape(B, T, heads, hs).transpose(0, 2, 1, 3)
    datt = dy @ v.transpose(0, 1, 3, 2)
    dv = att.transpose(0, 1, 3, 2) @ dy
    # softmax backward: dscores = att * (datt - sum(datt * att))
    dscores = att * (datt - (datt * att).sum(-1, keepdims=True)) * scale
    dq = dscores @ k
    dk = dscores.transpose(0, 1, 3, 2) @ q
    dqkv = np.concatenate([d.transpose(0, 2, 1, 3).reshape(B, T, C) for d in (dq, dk, dv)], -1)
    dx, dw, db = linear_back(dqkv, x_in, p[f"{i}.qkv.w"])
    return dx, {f"{i}.qkv.w": dw, f"{i}.qkv.b": db, f"{i}.proj.w": dpw, f"{i}.proj.b": dpb}


# --- 3c. the MLP -----------------------------------------------------------------------------
GELU_C = np.sqrt(2.0 / np.pi)


def gelu(x):
    """A smooth ReLU: lets small negative numbers through a little."""
    t = np.tanh(GELU_C * (x + 0.044715 * x ** 3))
    return 0.5 * x * (1 + t), t


def gelu_back(dy, x, t):
    dt = GELU_C * (1 + 3 * 0.044715 * x ** 2)
    return dy * (0.5 * (1 + t) + 0.5 * x * (1 - t ** 2) * dt)


def mlp(x, p, i):
    h, x_in = linear(x, p[f"{i}.fc.w"], p[f"{i}.fc.b"])     # widen to 4x
    a, t = gelu(h)
    out, a_in = linear(a, p[f"{i}.out.w"], p[f"{i}.out.b"])  # and back
    return out, (x_in, h, t, a_in)


def mlp_back(dout, cache, p, i):
    x_in, h, t, a_in = cache
    da, dow, dob = linear_back(dout, a_in, p[f"{i}.out.w"])
    dh = gelu_back(da, h, t)
    dx, dfw, dfb = linear_back(dh, x_in, p[f"{i}.fc.w"])
    return dx, {f"{i}.fc.w": dfw, f"{i}.fc.b": dfb, f"{i}.out.w": dow, f"{i}.out.b": dob}


# --- the whole model: forward, loss, backward --------------------------------------------------
def forward(p, cfg: Config, ids):
    """Scores for the next character at every position: shape (batch, time, vocab)."""
    B, T = ids.shape
    x = p["tok"][ids] + p["pos"][:T]                    # 2. what it is + where it is
    caches = []
    for i in range(cfg.layers):                         # 3. the blocks
        a, c1 = layernorm(x, p[f"{i}.ln1.g"], p[f"{i}.ln1.b"])
        att, c2 = attention(a, p, i, cfg.heads)
        x = x + att                                     # residual: add, don't replace
        m, c3 = layernorm(x, p[f"{i}.ln2.g"], p[f"{i}.ln2.b"])
        f, c4 = mlp(m, p, i)
        x = x + f
        caches.append((c1, c2, c3, c4))
    f, cf = layernorm(x, p["lnf.g"], p["lnf.b"])        # 4. scores for each next character
    logits, f_in = linear(f, p["head.w"], p["head.b"])
    return logits, (ids, caches, cf, f_in)


def loss_and_grads(p, cfg: Config, ids, targets):
    """5. How surprised the model is by the real next characters, and, for every number in
    the model, which way to nudge it to be less surprised next time."""
    logits, (ids, caches, cf, f_in) = forward(p, cfg, ids)
    B, T, V = logits.shape
    probs = softmax(logits)
    picked = probs.reshape(-1, V)[np.arange(B * T), targets.reshape(-1)]
    loss = float(-np.log(picked + 1e-12).mean())        # cross-entropy
    # backward, in reverse order of the forward
    dlogits = probs
    dlogits.reshape(-1, V)[np.arange(B * T), targets.reshape(-1)] -= 1
    dlogits /= B * T
    g = {}
    df, g["head.w"], g["head.b"] = linear_back(dlogits, f_in, p["head.w"])
    dx, g["lnf.g"], g["lnf.b"] = layernorm_back(df, cf)
    for i in reversed(range(cfg.layers)):
        c1, c2, c3, c4 = caches[i]
        dm, gm = mlp_back(dx, c4, p, i)                 # the residual passes dx on unchanged,
        dmx, g[f"{i}.ln2.g"], g[f"{i}.ln2.b"] = layernorm_back(dm, c3)
        dx = dx + dmx                                   # ...plus what flowed through the MLP
        da, ga = attention_back(dx, c2, p, i, cfg.heads)
        dax, g[f"{i}.ln1.g"], g[f"{i}.ln1.b"] = layernorm_back(da, c1)
        dx = dx + dax
        g |= gm | ga
    g["pos"] = np.zeros_like(p["pos"])
    g["pos"][:T] = dx.sum(0)
    g["tok"] = np.zeros_like(p["tok"])
    np.add.at(g["tok"], ids, dx)                        # each character's vector, summed
    return loss, g


# --- 6. Adam: the nudging ----------------------------------------------------------------------
class Adam:
    """Nudge each number against its gradient, with momentum (keep going the way it's been
    going) and a per-number step size (smaller steps for numbers whose gradient jumps around)."""

    def __init__(self, p, lr=3e-3, betas=(0.9, 0.99)):
        self.lr, (self.b1, self.b2) = lr, betas
        self.m = {k: np.zeros_like(v) for k, v in p.items()}
        self.v = {k: np.zeros_like(v) for k, v in p.items()}
        self.t = 0

    def step(self, p, g, lr=None):
        self.t += 1
        lr = self.lr if lr is None else lr
        for k in p:
            self.m[k] = self.b1 * self.m[k] + (1 - self.b1) * g[k]
            self.v[k] = self.b2 * self.v[k] + (1 - self.b2) * g[k] ** 2
            m = self.m[k] / (1 - self.b1 ** self.t)
            v = self.v[k] / (1 - self.b2 ** self.t)
            p[k] -= lr * m / (np.sqrt(v) + 1e-8)


# --- training --------------------------------------------------------------------------------
def batches(data: np.ndarray, context: int, size: int, rng):
    """Random snippets of the text, and the same snippets one character later (the answers)."""
    while True:
        starts = rng.integers(0, len(data) - context - 1, size)
        x = np.stack([data[s:s + context] for s in starts])
        y = np.stack([data[s + 1:s + context + 1] for s in starts])
        yield x, y


def train(text: str, steps: int = 3000, cfg: Config | None = None, batch: int = 16,
          lr: float = 3e-3, seed: int = 0, log=print, every: int = 100):
    tok = Tokenizer(text)
    cfg = cfg or Config(vocab=tok.size)
    data = tok.encode(text)
    split = int(len(data) * 0.9)                        # the last 10%: never trained on
    train_data, held_out = data[:split], data[split:]
    rng = np.random.default_rng(seed)
    p = init(cfg, seed)
    opt = Adam(p, lr)
    stream = batches(train_data, cfg.context, batch, rng)
    started = time.monotonic()
    history = []
    for step in range(1, steps + 1):
        x, y = next(stream)
        loss, g = loss_and_grads(p, cfg, x, y)
        warm = min(1.0, step / 100)                     # start gently,
        decay = 0.5 * (1 + np.cos(np.pi * step / steps))   # and slow down towards the end
        opt.step(p, g, lr * warm * (0.1 + 0.9 * decay))
        if step % every == 0 or step == steps:
            hx, hy = next(batches(held_out, cfg.context, batch, rng)) if len(held_out) > \
                cfg.context + 1 else (x, y)
            held, _ = loss_and_grads(p, cfg, hx, hy)
            history.append((step, loss, held))
            log(f"step {step:5d}  loss {loss:.3f}  held-out {held:.3f}  "
                f"({time.monotonic() - started:.0f} s)")
    return p, cfg, tok, history


# --- 7. sampling -----------------------------------------------------------------------------
def sample(p, cfg: Config, tok: Tokenizer, start: str = "\n", chars: int = 300,
           temperature: float = 0.8, seed: int = 0) -> str:
    """Guess the next character, add it, and guess again. A lower temperature plays it
    safe; a higher one takes chances."""
    rng = np.random.default_rng(seed)
    ids = list(tok.encode(start)) or [0]
    for _ in range(chars):
        window = np.array([ids[-cfg.context:]])
        logits, _ = forward(p, cfg, window)
        probs = softmax(logits[0, -1] / temperature)
        ids.append(int(rng.choice(len(probs), p=probs)))
    return tok.decode(ids)


# --- saving ----------------------------------------------------------------------------------
def save(path: Path, p, cfg: Config, tok: Tokenizer) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(path, **p, _meta=np.array(json.dumps({"cfg": asdict(cfg), "chars": tok.chars})))


def load(path: Path):
    z = np.load(path)
    meta = json.loads(str(z["_meta"]))
    p = {k: z[k] for k in z.files if k != "_meta"}
    return p, Config(**meta["cfg"]), Tokenizer(meta["chars"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="A tiny GPT, trained on the OSRS Wiki.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("train")
    t.add_argument("--text", type=Path, default=DATA / "wiki.txt")
    t.add_argument("--steps", type=int, default=3000)
    t.add_argument("--width", type=int, default=64)
    t.add_argument("--layers", type=int, default=2)
    t.add_argument("--context", type=int, default=64)
    s = sub.add_parser("sample")
    s.add_argument("--chars", type=int, default=500)
    s.add_argument("--start", default="== ")
    s.add_argument("--temperature", type=float, default=0.8)
    args = ap.parse_args(argv)
    model = DATA / "gpt.npz"
    if args.cmd == "train":
        if not args.text.exists():
            print(f"No {args.text} yet: run `python -m learn.fetch_wiki` first.")
            return 1
        text = args.text.read_text(encoding="utf-8")
        tok = Tokenizer(text)
        cfg = Config(vocab=tok.size, context=args.context, width=args.width, layers=args.layers)
        n = sum(v.size for v in init(cfg).values())
        print(f"{len(text):,} characters of text, {tok.size} different ones; "
              f"{n:,} numbers to learn.")
        p, cfg, tok, _ = train(text, args.steps, cfg)
        save(model, p, cfg, tok)
        print(f"Saved {model}. Try: python -m learn.gpt sample")
    else:
        if not model.exists():
            print("No model yet: run `python -m learn.gpt train` first.")
            return 1
        p, cfg, tok = load(model)
        print(sample(p, cfg, tok, args.start, args.chars, args.temperature))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
