"""A tiny fake OpenAI-compatible server (llama-server flavour) for LAB-A tests. MOCK only.

It parses the option list from the system prompt and answers deterministically from a
hash of the user text, returning OpenAI-style logprobs with leading-space/case variants.
Behaviour switches (class attributes) simulate broken servers.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

OPT_CODE = re.compile(r"^([A-Z])\) ([a-z_]+):", re.M)
OPT_JSON = re.compile(r"^- ([a-z_]+):", re.M)


def _h(text: str) -> int:
    return int(hashlib.sha1(text.encode()).hexdigest(), 16)


class FakeHandler(BaseHTTPRequestHandler):
    empty_logprobs = False
    invalid_json = False

    def log_message(self, *a):  # quiet
        pass

    def _send(self, code: int, obj: dict):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path.startswith("/props"):
            return self._send(200, {"build_info": "fake-0", "model_ftype": "Q4_K - Medium"})
        self._send(404, {})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        if not self.path.endswith("/chat/completions"):
            return self._send(404, {})
        sys_msg = body["messages"][0]["content"]
        user = body["messages"][-1]["content"]
        h = _h(user)
        if body.get("response_format"):
            labels = OPT_JSON.findall(sys_msg)
            lab = labels[h % len(labels)]
            content = "{oops" if self.invalid_json else json.dumps({"label": lab})
            toks = ['{"', "label", '":', ' "', lab, '"}'] if not self.invalid_json else ["{oops"]
            lps = [{"token": t, "logprob": math.log(0.8) if t == lab else -0.01, "top_logprobs": []} for t in toks]
        else:
            opts = OPT_CODE.findall(sys_msg)
            codes = [c for c, _ in opts]
            c = codes[h % len(codes)]
            other = codes[(h // 7) % len(codes)]
            tops = [(c, math.log(0.6)), (" " + c, math.log(0.1)), (other.lower(), math.log(0.15)), ("The", math.log(0.05))]
            seen, top_list = set(), []
            for t, lp in tops:
                if t not in seen:
                    seen.add(t)
                    top_list.append({"token": t, "logprob": lp})
            content = c
            lps = [{"token": c, "logprob": math.log(0.6), "top_logprobs": top_list}]
        logprobs = {"content": []} if self.empty_logprobs else {"content": lps}
        self._send(200, {
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "logprobs": logprobs, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 100 + len(user) // 4, "completion_tokens": len(lps)},
            "model": body.get("model"),
        })


class FakeServer:
    def __init__(self, **flags):
        handler = type("H", (FakeHandler,), dict(flags))
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self.httpd.server_address[1]
        self.base_url = f"http://127.0.0.1:{self.port}/v1"
        self.t = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.t.start()
        return self

    def __exit__(self, *a):
        self.httpd.shutdown()
        self.httpd.server_close()
