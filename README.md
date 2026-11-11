# Offline chat (llama3.2:3b)

Local chat page that talks only to Ollama on this computer. It uses the Python standard library, so there is nothing to install with pip. Requests stay on `127.0.0.1`.

The model is `llama3.2:3b`, which is already installed.

## Start

1. Start Ollama (open the Ollama app, or run `ollama serve`).
2. From this folder, run:

```
python chat_server.py
```

3. Open http://127.0.0.1:8765

The server listens on `127.0.0.1` only, so other machines cannot reach it. Stop it with Ctrl+C.

## If the page says Ollama is not running

Start Ollama, then refresh the page.

Confirm the model is present:

```
ollama list
```

You should see `llama3.2:3b`.
