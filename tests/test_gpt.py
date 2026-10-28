"""The tiny GPT: every hand-written backward checked against a numerical estimate, and it
actually learns."""
import numpy as np

from learn.gpt import Config, Tokenizer, init, load, loss_and_grads, sample, save, train


def test_the_tokenizer_round_trips():
    tok = Tokenizer("oak logs")
    assert tok.size == 7 and tok.decode(tok.encode("logs oak")) == "logs oak"


def test_every_gradient_matches_a_numerical_estimate():
    """Nudge one number a tiny bit up and down, see how the loss moves: that's its gradient
    the slow way. The backward pass must agree, for every kind of parameter."""
    cfg = Config(vocab=7, context=5, width=8, heads=2, layers=2)
    p = init(cfg, seed=1, dtype=np.float64)
    for k in p:                                     # bigger numbers: a sharper test
        p[k] = p[k] + np.random.default_rng(2).standard_normal(p[k].shape) * 0.3
    rng = np.random.default_rng(3)
    x, y = rng.integers(0, 7, (2, 5)), rng.integers(0, 7, (2, 5))
    _, g = loss_and_grads(p, cfg, x, y)
    for name in p:
        flat = p[name].reshape(-1)
        for j in rng.choice(flat.size, min(4, flat.size), replace=False):
            old, h = flat[j], 1e-5
            flat[j] = old + h
            up, _ = loss_and_grads(p, cfg, x, y)
            flat[j] = old - h
            down, _ = loss_and_grads(p, cfg, x, y)
            flat[j] = old
            numeric = (up - down) / (2 * h)
            got = g[name].reshape(-1)[j]
            assert abs(numeric - got) <= 1e-6 + 1e-4 * abs(numeric), (name, j, numeric, got)


def test_it_learns_a_pattern_and_samples_it(tmp_path):
    text = "chop oak, bank logs. " * 200
    cfg = Config(vocab=len(set(text)), context=16, width=32, heads=4, layers=1)
    p, cfg, tok, history = train(text, steps=300, cfg=cfg, batch=8, log=lambda s: None)
    first, last = history[0][1], history[-1][1]
    assert last < 0.3 and last < first / 2           # from guessing to nearly knowing
    out = sample(p, cfg, tok, "chop ", chars=40, temperature=0.5)
    assert "oak" in out and "bank" in out
    save(tmp_path / "m.npz", p, cfg, tok)
    p2, cfg2, tok2 = load(tmp_path / "m.npz")
    assert cfg2 == cfg and tok2.chars == tok.chars
    assert sample(p2, cfg2, tok2, "chop ", chars=40, temperature=0.5) == out
