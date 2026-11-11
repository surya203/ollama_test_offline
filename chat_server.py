#!/usr/bin/env python3
"""Chat on this PC. Everyday questions use llama3.2:3b. Live facts use OpenAI."""

import json
import os
import re
import socket
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = "127.0.0.1"
PORT = 8765
OLLAMA = "http://127.0.0.1:11434"
MODEL = "llama3.2:3b"
OPENAI_URL = "https://api.openai.com/v1/responses"
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.4-mini")
INDEX = Path(__file__).resolve().parent / "static" / "index.html"
MAX_BODY = 1_000_000
MAX_MESSAGES = 40
MAX_CONTENT = 16_000
SYSTEM_PROMPT = (
    "You are a local assistant running offline on this computer through Ollama "
    "(llama3.2:3b). Answer from your own knowledge. Do not claim you searched "
    "the web or used live internet data."
)
ONLINE_SYSTEM = (
    "Answer using current public information from web search. "
    "Give a direct answer, then cite the sources you used. "
    "If search does not contain the answer, say so."
)
URL_RE = re.compile(r"https?://[^\s)>\]]+")
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
LIVE_RE = re.compile(
    r"\b("
    r"weather|forecast|news|headlines?|"
    r"stock price|share price|exchange rate|"
    r"current price|price of|how much (?:is|does|do)|"
    r"scores?|standings|"
    r"right now|as of today|today'?s|"
    r"this morning|last night|yesterday|"
    r"latest|breaking|"
    r"temperature (?:in|at|for|today|now|outside)|"
    r"who is the (?:current )?(?:president|prime minister|ceo|champion)"
    r")\b",
    re.IGNORECASE,
)
CREATIVE_RE = re.compile(
    r"\b(write|draft|compose|poem|story|essay|code|function|script|debug|refactor)\b",
    re.IGNORECASE,
)
URGENT_RE = re.compile(
    r"\b(right now|currently|today|tonight|latest|current|yesterday|last night|"
    r"this week|price|score|news|forecast)\b",
    re.IGNORECASE,
)


def ollama_tags():
    request = urllib.request.Request(OLLAMA + "/api/tags", method="GET")
    with urllib.request.urlopen(request, timeout=3) as response:
        return json.loads(response.read().decode("utf-8"))


def load_env_file():
    path = Path(__file__).resolve().parent / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def openai_model():
    return os.environ.get("OPENAI_MODEL", OPENAI_MODEL).strip() or OPENAI_MODEL


def openai_configured():
    return bool(os.environ.get("OPENAI_API_KEY", "").strip())


def model_installed(payload):
    models = payload.get("models") or []
    for item in models:
        name = item.get("name") or item.get("model") or ""
        if name == MODEL or name.startswith(MODEL + "-"):
            return True
    return False


def validate_messages(payload):
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object.")
    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ValueError("Send a non-empty messages list.")
    if len(messages) > MAX_MESSAGES:
        raise ValueError(f"Keep the conversation to {MAX_MESSAGES} messages.")

    clean = []
    for item in messages:
        if not isinstance(item, dict):
            raise ValueError("Each message must be an object.")
        role = item.get("role")
        content = item.get("content")
        if role not in ("user", "assistant"):
            raise ValueError("Only user and assistant messages are accepted.")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Each message needs text.")
        if len(content) > MAX_CONTENT:
            raise ValueError(f"Each message must be under {MAX_CONTENT} characters.")
        clean.append({"role": role, "content": content})

    if clean[-1]["role"] != "user":
        raise ValueError("The latest message must be from the user.")
    return clean


def needs_live_data(text):
    if not LIVE_RE.search(text):
        return False
    if CREATIVE_RE.search(text) and not URGENT_RE.search(text):
        return False
    return True


def classify_route(messages):
    latest = messages[-1]["content"]
    if needs_live_data(latest):
        return "online"

    prior = []
    for item in messages[-5:-1]:
        prior.append("%s: %s" % (item["role"], item["content"][:400]))
    question = latest
    if prior:
        question = "Recent conversation:\n%s\n\nLatest question:\n%s" % (
            "\n".join(prior),
            latest,
        )
    prompt = (
        "Classify the question. Reply with exactly one word: online or offline.\n"
        "online = needs live web data such as news, weather, prices, scores, or current events.\n"
        "offline = coding, math, writing, or knowledge that does not change.\n"
        "Question: %s\n"
        "Route:" % question
    )
    body = json.dumps(
        {
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0, "num_predict": 3, "stop": ["\n"]},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        OLLAMA + "/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        text = json.loads(response.read().decode("utf-8")).get("response") or ""
    if re.search(r"\bonline\b", text.lower()):
        return "online"
    return "offline"


def citation_sources(*chunks):
    found = []
    seen = set()

    def add(url, title):
        url = (url or "").strip().rstrip(".,;)")
        title = (title or "").strip()
        if url.lower().startswith(("http://", "https://")):
            if url in seen:
                return
            seen.add(url)
            found.append({"title": title or url, "url": url})
            return
        label = {
            "oai-weather": "Weather data",
            "oai-sports": "Sports data",
            "oai-finance": "Finance data",
        }.get(title, title)
        if label and label not in seen:
            seen.add(label)
            found.append({"title": label, "url": ""})

    for chunk in chunks:
        if isinstance(chunk, str):
            for title, url in MARKDOWN_LINK_RE.findall(chunk):
                add(url, title)
            for url in URL_RE.findall(chunk):
                add(url, "")
            continue
        if not isinstance(chunk, list):
            continue
        for item in chunk:
            if not isinstance(item, dict):
                continue
            nested = item.get("url_citation") if isinstance(item.get("url_citation"), dict) else item
            add(
                nested.get("url") or item.get("url"),
                nested.get("title") or item.get("title") or item.get("name"),
            )
    return found


class ChatHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self._serve_index()
        elif path == "/api/health":
            self._health()
        else:
            self._json(404, {"ok": False, "error": "Not found."})

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path != "/api/chat":
            self._json(404, {"ok": False, "error": "Not found."})
            return
        self._chat()

    def _serve_index(self):
        if not INDEX.is_file():
            self._json(500, {"ok": False, "error": "Chat page is missing."})
            return
        body = INDEX.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _health(self):
        try:
            tags = ollama_tags()
        except (urllib.error.URLError, TimeoutError, OSError):
            self._json(
                503,
                {
                    "ok": False,
                    "ollama": "down",
                    "model": MODEL,
                    "error": "Ollama is not running. Start Ollama, then refresh this page.",
                },
            )
            return

        if not model_installed(tags):
            self._json(
                503,
                {
                    "ok": False,
                    "ollama": "up",
                    "model": MODEL,
                    "error": "llama3.2:3b is not installed in Ollama.",
                },
            )
            return

        self._json(
            200,
            {
                "ok": True,
                "ollama": "up",
                "model": MODEL,
                "openai": "configured" if openai_configured() else "missing",
                "openaiModel": openai_model(),
            },
        )

    def _chat(self):
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0 or length > MAX_BODY:
            self._json(400, {"ok": False, "error": "Chat request is empty or too large."})
            return
        raw = self.rfile.read(length)
        try:
            messages = validate_messages(json.loads(raw.decode("utf-8")))
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            message = str(exc) if isinstance(exc, ValueError) else "Request body must be JSON."
            self._json(400, {"ok": False, "error": message})
            return

        if not self._begin_sse():
            return

        try:
            self._write_event({"status": "choosing"})
            try:
                route = classify_route(messages)
            except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
                self._write_event(
                    {
                        "error": "Ollama is not running, so this question could not be routed.",
                    }
                )
                self._end_chunks()
                return

            print("Route: %s" % route, flush=True)
            if route == "online":
                if not openai_configured():
                    self._write_event(
                        {
                            "error": (
                                "This question needs current information, so it uses OpenAI. "
                                "Set OPENAI_API_KEY and restart the chat server."
                            )
                        }
                    )
                    self._end_chunks()
                    return
                self._write_event(
                    {"route": "online", "model": openai_model(), "status": "searching"}
                )
                self._stream_openai(messages)
            else:
                self._write_event({"route": "offline", "model": MODEL})
                self._stream_ollama(messages)
            self._end_chunks()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return
        except Exception as exc:
            try:
                self._write_event({"error": "The reply stopped: %s" % exc})
                self._end_chunks()
            except OSError:
                return

    def _begin_sse(self):
        try:
            self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        return True

    def _stream_ollama(self, messages):
        body = json.dumps(
            {
                "model": MODEL,
                "messages": [{"role": "system", "content": SYSTEM_PROMPT}, *messages],
                "stream": True,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            OLLAMA + "/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            response = urllib.request.urlopen(request, timeout=300)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            detail = "Ollama is not running. Start Ollama, then try again."
            if isinstance(exc, urllib.error.HTTPError):
                detail = _read_error(exc) or "Ollama rejected the chat request."
            self._write_event({"error": detail})
            return

        with response:
            for line in response:
                text = line.decode("utf-8", errors="replace").strip()
                if not text:
                    continue
                try:
                    event = json.loads(text)
                except json.JSONDecodeError:
                    self._write_event({"error": "Ollama returned an unreadable chunk."})
                    return
                if event.get("error"):
                    self._write_event({"error": str(event["error"])})
                    return
                piece = (event.get("message") or {}).get("content") or ""
                if piece:
                    self._write_event({"content": piece})
                if event.get("done"):
                    self._write_event({"done": True})
                    return
        self._write_event({"done": True})

    def _stream_openai(self, messages):
        key = os.environ.get("OPENAI_API_KEY", "").strip()
        try:
            response = _open_openai(messages, key, with_reasoning=True)
        except urllib.error.HTTPError as exc:
            detail = _read_error(exc)
            if exc.code == 400 and "reasoning" in detail.lower():
                try:
                    response = _open_openai(messages, key, with_reasoning=False)
                except urllib.error.HTTPError as retry_exc:
                    self._write_event({"error": _openai_failure(retry_exc)})
                    return
                except (urllib.error.URLError, TimeoutError, OSError):
                    self._write_event({"error": "Could not reach OpenAI."})
                    return
            else:
                self._write_event({"error": _failure_text(exc.code, detail)})
                return
        except (urllib.error.URLError, TimeoutError, OSError):
            self._write_event({"error": "Could not reach OpenAI."})
            return

        with response:
            try:
                payload = json.loads(response.read().decode("utf-8"))
            except json.JSONDecodeError:
                self._write_event({"error": "OpenAI returned an unreadable reply."})
                return
        if payload.get("error"):
            message = payload["error"]
            if isinstance(message, dict):
                message = message.get("message") or "OpenAI could not answer."
            self._write_event({"error": str(message)})
            return
        reply, sources = read_openai_response(payload)
        if reply:
            self._write_event({"content": reply})
        if sources:
            self._write_event({"sources": sources})
        if not reply:
            self._write_event({"error": "OpenAI returned an empty reply."})
            return
        self._write_event({"done": True})

    def _write_event(self, payload):
        data = ("data: " + json.dumps(payload) + "\n\n").encode("utf-8")
        self.wfile.write(("%X\r\n" % len(data)).encode("ascii"))
        self.wfile.write(data)
        self.wfile.write(b"\r\n")
        self.wfile.flush()

    def _end_chunks(self):
        self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()

    def _json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def read_openai_response(payload):
    texts = []
    annotations = []
    named = []
    for item in payload.get("output") or []:
        if item.get("type") == "web_search_call":
            action = item.get("action") or {}
            for source in action.get("sources") or []:
                if isinstance(source, dict):
                    named.append(source)
        if item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if part.get("type") != "output_text":
                continue
            texts.append(part.get("text") or "")
            extra = part.get("annotations") or []
            if isinstance(extra, list):
                annotations.extend(extra)
    reply = "".join(texts).strip()
    sources = citation_sources(reply, annotations, named)
    return reply, sources


def _open_openai(messages, key, with_reasoning):
    payload = {
        "model": openai_model(),
        "instructions": ONLINE_SYSTEM,
        "input": messages,
        "tools": [{"type": "web_search", "search_context_size": "low"}],
        "tool_choice": "required",
        "include": ["web_search_call.action.sources"],
    }
    if with_reasoning:
        payload["reasoning"] = {"effort": "low"}
    request = urllib.request.Request(
        OPENAI_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + key,
        },
        method="POST",
    )
    return urllib.request.urlopen(request, timeout=180)


def _read_error(exc):
    detail = exc.read().decode("utf-8", errors="replace")
    try:
        payload = json.loads(detail)
        err = payload.get("error", detail)
        if isinstance(err, dict):
            detail = err.get("message") or detail
        elif isinstance(err, str):
            detail = err
    except json.JSONDecodeError:
        pass
    return " ".join(detail.split())[:300]


def _failure_text(code, detail):
    if code == 401:
        return "OpenAI rejected the API key."
    if code == 429:
        return "OpenAI is busy. Wait a moment and try again."
    return detail or "OpenAI could not answer."


def _openai_failure(exc):
    return _failure_text(exc.code, _read_error(exc))


def main():
    load_env_file()
    global OPENAI_MODEL
    OPENAI_MODEL = openai_model()
    try:
        server = ThreadingHTTPServer((HOST, PORT), ChatHandler)
    except OSError as exc:
        print("Could not listen on http://%s:%s (%s)." % (HOST, PORT, exc))
        raise SystemExit(1) from exc

    print("Chat ready at http://%s:%s" % (HOST, PORT), flush=True)
    print("Offline model: %s via %s" % (MODEL, OLLAMA), flush=True)
    if openai_configured():
        print("Online model: %s" % openai_model(), flush=True)
    else:
        print("Online model: set OPENAI_API_KEY to enable OpenAI.", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
