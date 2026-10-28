# How a GPT works, using the tiny one in this folder

`gpt.py` is a real GPT, the same kind of thing as the models superbond2 thinks with, shrunk
down until a CPU can train one in minutes. This guide walks through it in plain words. Each
part has a matching section in the code, numbered the same.

## The whole idea in one line

**Guess the next piece of text, see how wrong you were, adjust a little, repeat.** That's
it. Everything below is how that guessing works and how the adjusting works.

Big models guess the next *word-piece* and have billions of adjustable numbers. Ours guesses
the next *letter* and has about 120,000. Same trick, smaller scale.

## 1. Turning text into numbers (the tokenizer)

A computer can't do maths on letters, so every character gets a number: `a` is 0, `b` is 1,
and so on, for all 141 characters that appear in the wiki text (letters, digits,
punctuation, a few odd symbols). "oak" becomes something like `[67, 53, 63]`.

Big models use word-pieces instead ("oak", " logs", "ing"), so they have far fewer steps
per sentence. Letters keep ours simple.

## 2. Giving each character a meaning (embeddings)

Each character gets a list of 64 numbers, its *embedding*. At the start they're random.
Training slowly moves them so that characters used in similar ways end up with similar
lists. Nobody tells it that vowels are alike; it works that out because that helps it guess.

Each *position* (1st character, 2nd, ... 64th) gets its own list too, added on top. Without
that, the model couldn't tell "dog bites man" from "man bites dog".

## 3. The blocks: looking back, then thinking

The model stacks a couple of identical *blocks*. Each block does two things.

**3b. Attention: looking back.** This is the famous part. To guess what comes after
"Dragon Sl", the model needs to look back at earlier characters. Every position makes three
things:
- a **query**: "what am I looking for?"
- a **key**: "what do I have?"
- a **value**: "what I'll pass on if you pick me"

Each position compares its query with every earlier key. A good match means "pay attention
to that one". It then takes a mix of those positions' values, weighted by how well they
matched. *Causal* means it can only look back, never ahead: no peeking at the answer.

It does this 4 times side by side (4 *heads*), so one head can track, say, "what word am I
in" while another tracks "was there a capital letter recently".

**3c. The MLP: thinking it over.** After gathering, each position runs what it gathered
through a small network: widen to 4× the numbers, bend them (the *GELU*, a smooth "keep the
positives, mostly drop the negatives"), squash back down. Attention moves information
around; the MLP works on it.

**3a. Layer norm** sits before both. It rescales each position's numbers so they stay in a
sensible range. Without it, numbers grow or shrink layer after layer until training falls
apart.

**Residuals.** Each part *adds* its result to what came in, instead of replacing it. So
the original information can flow straight through, and each part only has to add
something useful. This is why deep models train at all.

## 4. Scores for the next character

At the end, each position's 64 numbers become 141 scores, one for each possible next
character. *Softmax* turns scores into probabilities that add up to 100%: maybe "a" 31%,
"e" 12%, "o" 9%...

## 5. How wrong was it? (the loss)

We know the real next character, because it's in the text. The *loss* is how surprised the
model was by it: give the right character 90% and the loss is small (0.1); give it 1% and
the loss is big (4.6). Guessing blindly among 141 characters scores about 4.9.

**Our run:** it started near 4.9 and got down to about 1.7 in 6 minutes. In plain terms, it
went from "no idea" to usually having the right character among its top few guesses.

## The adjusting: gradients and backpropagation

Here's the clever bit. For each of the 120,000 numbers we can ask: "if this number were a
tiny bit bigger, would the loss go up or down, and by how much?" That's the number's
*gradient*.

Working it out one number at a time would take forever. *Backpropagation* gets them all in
one pass, backwards through the model: the loss tells the last layer how to change, which
tells the layer before it, and so on to the start. In `gpt.py`, every forward function
(compute) has a matching `_back` function (work out the gradients), written by hand.

`tests/test_gpt.py` checks every one the slow way: nudge a number up a hair, nudge it down,
see how the loss moves. If the hand-written maths and the slow check disagree, the test
fails.

## 6. Nudging the numbers (Adam)

With the gradients known, every number moves a small step the way that lowers the loss.
*Adam* is a smarter way to step:
- **Momentum:** keep going roughly the way you've been going, so it doesn't zig-zag.
- **Per-number step sizes:** take smaller steps for numbers whose gradient keeps flipping.

The step size starts small for 100 steps (a warm-up), then slowly shrinks towards the end,
so it settles instead of bouncing around.

One step looks at 16 random snippets of 64 characters. 3,000 steps is about 3 million
characters seen, a bit more than the whole wiki text once.

## Held-out text: is it learning or memorising?

10% of the text is kept back and never trained on. Every 100 steps we check the loss on it.
If the training loss kept falling while the held-out loss rose, the model would be
memorising instead of learning. Ours stayed close together (about 1.7 and 1.6–1.9), so it's
learning patterns, not pages. The held-out number jumps around because each check uses
only a small sample.

## 7. Writing (sampling)

To write, give it a start ("== "), let it score the next character, *pick one at random
according to those probabilities*, add it, and go again. The **temperature** sets how bold
it is: low (0.5) sticks to safe, common choices; high (1.2) takes chances and gets weird.

What it wrote after 6 minutes:

> == Ae Anndity 's nellance players damage. It is the statack that and by anots isstand
> times rovary, with trange tick to are it detail on event of advantial persay...

That's the right shape: wiki headings, real words ("players", "damage", "the location",
"required by"), sentence rhythm, made-up words in between. It knows how wiki text *looks*,
but not yet what anything *means*.

## Why it isn't ChatGPT (yet)

| | Ours | A model like gemma4:12b |
|---|---|---|
| Adjustable numbers | 120,000 | 12,000,000,000 (100,000× more) |
| Training text | 2 MB of wiki | trillions of characters |
| Looks back | 64 characters | thousands of word-pieces |
| Training | 6 minutes on a CPU | weeks on thousands of GPUs |
| Then | that's it | trained further to follow instructions and be helpful |

The parts are the same: embeddings, attention, MLP, layer norm, residuals, the loss,
backpropagation, Adam. What changes is size, data and time.

## Try it (in the VM)

```sh
python -m learn.fetch_wiki --pages 1500     # the wiki as text (about 2 MB, ~30 requests)
python -m learn.gpt train                   # about 10 minutes on the VM's 2 cores
python -m learn.gpt sample                  # a fake wiki page
python -m learn.gpt sample --temperature 1.2 --start "== Dragon"
```

Things to try, in order of how much they change:
- `--steps 10000`: train longer. Does the loss keep dropping? When does it flatten?
- `--layers 4 --width 128`: a bigger model. Slower, but does it write better?
- `--context 128`: let it look further back.
- Training only on quest pages (`fetch_wiki --start "Quest"`): does it start writing quest
  guides?
