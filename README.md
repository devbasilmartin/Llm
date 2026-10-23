# Llm

**superbond2**: a local language model that plays Old School RuneScape on a private server
that allows bots. He learns the game as he goes, sets his own goals and makes his own
mistakes. Alongside him, a learning track: small language models built from scratch.

- [ROADMAP.md](ROADMAP.md): the decisions so far, and the build order.
- [`superbond2/`](superbond2/): the agent. So far his eyes, his hands and a simulated game.
- [`bench/`](bench/): the model bake-off, which picks superbond2's brain from the open models
  that run on a CPU.

[skillbot](https://github.com/devbasilmartin/RuneScape) is the rule-based bot this started
from; superbond2 uses it as a reference.
