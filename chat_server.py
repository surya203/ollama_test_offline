#!/usr/bin/env python3
"""Local offline chat. Serves a page on this PC and streams llama3.2:3b from Ollama."""

import json
import socket
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = "127.0.0.1"
PORT = 8765
OLLAMA = "http://127.0.0.1:11434"
MODEL = "llama3.2:3b"
INDEX = Path(__file__).resolve().parent / "static" / "index.html"
MAX_BODY = 1_000_000
MAX_MESSAGES = 40
MAX_CONTENT = 16_000
SYSTEM_PROMPT = (
    "You are a local assistant running offline on this computer through Ollama "
    "(llama3.2:3b). Answer from your own knowledge. Do not claim you searched "
    "the web or used live internet data."
)


def ollama_tags():
    request = urllib.request.Request(OLLAMA + "/api/tags", method="GET")
    with urllib.request.urlopen(request, timeout=3) as response:
        return json.loads(response.read().decode("utf-8"))


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

        self._json(200, {"ok": True, "ollama": "up", "model": MODEL})

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
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(detail).get("error", detail)
            except json.JSONDecodeError:
                pass
            self._json(502, {"ok": False, "error": detail or "Ollama rejected the chat request."})
            return
        except (urllib.error.URLError, TimeoutError, OSError):
            self._json(
                503,
                {
                    "ok": False,
                    "error": "Ollama is not running. Start Ollama, then try again.",
                },
            )
            return

        try:
            self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        try:
            with response:
                for line in response:
                    text = line.decode("utf-8", errors="replace").strip()
                    if not text:
                        continue
                    try:
                        event = json.loads(text)
                    except json.JSONDecodeError:
                        self._write_event({"error": "Ollama returned an unreadable chunk."})
                        break
                    if event.get("error"):
                        self._write_event({"error": str(event["error"])})
                        break
                    piece = (event.get("message") or {}).get("content") or ""
                    if piece:
                        self._write_event({"content": piece})
                    if event.get("done"):
                        self._write_event({"done": True})
                        break
                else:
                    self._write_event({"done": True})
            self._end_chunks()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return
        except Exception as exc:
            try:
                self._write_event({"error": "The reply stopped: %s" % exc})
                self._end_chunks()
            except OSError:
                return

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


def main():
    try:
        server = ThreadingHTTPServer((HOST, PORT), ChatHandler)
    except OSError as exc:
        print("Could not listen on http://%s:%s (%s)." % (HOST, PORT, exc))
        raise SystemExit(1) from exc

    print("Offline chat ready at http://%s:%s" % (HOST, PORT))
    print("Model: %s via %s" % (MODEL, OLLAMA))
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
