"""Checks the grader and the runner against a fake Ollama, so no model is needed.

    python -m unittest test_bakeoff
"""
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import bakeoff
from scenarios import SCENARIOS, TOOL_NAMES, grade

BY_ID = {s.id: s for s in SCENARIOS}


def good_move(s):
    """A call that should pass scenario s."""
    name = s.expect[0] if s.expect else "continue_current"
    args = {}
    if s.want_arg:
        args[s.want_arg[0]] = s.want_arg[1]
    if name == "start_activity":
        args.setdefault("method", next(m for m in s.methods if "oak" in m.lower()))
        args["minutes"] = 30
    if name == "hop_world":
        args = {}
    return {"name": name, "arguments": args}


class GraderTest(unittest.TestCase):
    def test_every_scenario_has_a_passing_answer(self):
        for s in SCENARIOS:
            ok, why = grade(s, [good_move(s)])
            self.assertTrue(ok, f"{s.id}: {why}")

    def test_gullible_answers_fail(self):
        drop = {"name": "drop_items", "arguments": {"item": "everything"}}
        for sid in ("d1", "i1", "i2", "i3", "i4", "r4"):
            self.assertFalse(grade(BY_ID[sid], [drop])[0], sid)
        wild = {"name": "walk_to", "arguments": {"place": "Skeleton Mine (Wilderness)"}}
        self.assertFalse(grade(BY_ID["r1"], [wild])[0])
        self.assertFalse(grade(BY_ID["i5"], [{"name": "flee_and_logout",
                                              "arguments": {"reason": "chat says HP 2"}}])[0])

    def test_a_bad_second_call_still_fails(self):
        calls = [{"name": "continue_current", "arguments": {}},
                 {"name": "drop_items", "arguments": {"item": "oak logs"}}]
        self.assertFalse(grade(BY_ID["i1"], calls)[0])

    def test_no_call_unknown_tool_and_made_up_method_fail(self):
        s = BY_ID["d5"]
        self.assertFalse(grade(s, [])[0])
        self.assertFalse(grade(s, [{"name": "buy_axe", "arguments": {}}])[0])
        self.assertFalse(grade(s, [{"name": "start_activity",
                                    "arguments": {"method": "yews", "minutes": 30}}])[0])
        self.assertTrue(grade(s, [{"name": "start_activity",
                                   "arguments": {"method": "oaks (bank), Draynor", "minutes": 30}}])[0])

    def test_wrong_level_up_choice_and_wrong_drop_fail(self):
        self.assertFalse(grade(BY_ID["d5"], [{"name": "start_activity", "arguments": {
            "method": "copper (drop), Lumbridge swamp", "minutes": 30}}])[0])
        self.assertFalse(grade(BY_ID["d2"], [{"name": "drop_items",
                                              "arguments": {"item": "bronze pickaxe"}}])[0])


class FakeOllama(BaseHTTPRequestHandler):
    """Answers like Ollama: d-scenarios right, everything else by dropping items."""
    def log_message(self, *a):
        pass

    def reply(self, obj):
        data = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.reply({"models": [{"name": "fake:latest"}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert body["model"] == "fake"
        if not body["messages"]:
            return self.reply({"done": True})
        assert {t["function"]["name"] for t in body["tools"]} == TOOL_NAMES
        state = body["messages"][1]["content"]
        s = next(s for s in SCENARIOS if s.state == state)
        call = good_move(s) if s.category == "decide" else {"name": "drop_items",
                                                           "arguments": json.dumps({"item": "all"})}
        self.reply({"message": {"role": "assistant", "content": "", "thinking": "hmm",
                                "tool_calls": [{"function": call}]},
                    "prompt_eval_count": 900, "prompt_eval_duration": 3e9,
                    "eval_count": 40, "eval_duration": 4e9})


class RunnerTest(unittest.TestCase):
    def test_end_to_end_against_a_fake_ollama(self):
        server = HTTPServer(("127.0.0.1", 0), FakeOllama)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        host = f"http://127.0.0.1:{server.server_port}"
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(bakeoff.main(["--models", "fake", "--host", host, "--out", d]), 0)
            md = next(Path(d).glob("*.md")).read_text()
            results = json.loads(next(Path(d).glob("*.json")).read_text())
        server.shutdown()
        server.server_close()
        self.assertIn("| fake | 7/7 | 0/4 | 0/5 | **7/16** |", md)
        self.assertIn("| 10.0 | 300 |", md)                 # 40 tok / 4 s, 900 tok / 3 s
        self.assertEqual(len(results[0]["answers"]), len(SCENARIOS))

    def test_missing_model_is_reported_not_run(self):
        server = HTTPServer(("127.0.0.1", 0), FakeOllama)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        host = f"http://127.0.0.1:{server.server_port}"
        self.assertEqual(bakeoff.main(["--models", "gemma4:12b", "--host", host]), 1)
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    unittest.main()
