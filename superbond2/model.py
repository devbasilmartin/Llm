"""Talking to the model: Ollama's chat API with tools, standard library only.

The model runs on the Windows host; from the VM it's at http://10.0.2.2:11434 (Ollama has to
listen on 0.0.0.0 for that, see bench/README.md).
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field


class ModelError(Exception):
    """The model couldn't be reached or answered with an error."""


@dataclass
class Reply:
    calls: list[dict] = field(default_factory=list)     # [{"name", "arguments"}]
    content: str = ""
    thinking: str = ""
    seconds: float = 0.0
    prompt_tokens: int = 0
    gen_tokens: int = 0


def parse_calls(message: dict) -> list[dict]:
    calls = []
    for c in message.get("tool_calls") or []:
        fn = c.get("function", {})
        args = fn.get("arguments") or {}
        if isinstance(args, str):               # some models send the arguments as a string
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {"raw": args}
        calls.append({"name": fn.get("name", ""), "arguments": args if isinstance(args, dict) else {}})
    return calls


class Ollama:
    def __init__(self, model: str, host: str = "http://localhost:11434", think=None,
                 temperature: float = 0.3, num_ctx: int = 8192, timeout: float = 600):
        self.model, self.host = model, host.rstrip("/")
        self.think = think                      # None: the model's default; True/False; or low/medium/high
        self.options = {"temperature": temperature, "num_ctx": num_ctx}
        self.timeout = timeout

    def chat(self, messages: list[dict], tools: list[dict]) -> Reply:
        body = {"model": self.model, "messages": messages, "tools": tools, "stream": False,
                "keep_alive": "30m", "options": self.options}
        if self.think is not None:
            body["think"] = self.think
        req = urllib.request.Request(self.host + "/api/chat", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        t = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise ModelError(f"HTTP {e.code}: {e.read().decode(errors='replace')[:300]}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise ModelError(f"can't reach {self.host}: {e}") from None
        msg = data.get("message", {})
        return Reply(parse_calls(msg), msg.get("content", ""), msg.get("thinking", ""),
                     time.monotonic() - t, data.get("prompt_eval_count", 0), data.get("eval_count", 0))
