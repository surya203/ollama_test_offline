# Chat (local llama3.2:3b, OpenAI when needed)

The page runs on this computer and uses the Python standard library, so there is nothing to install with pip.

The local model decides each question:

- Explanations, code, math, and other stable questions stay on `llama3.2:3b`.
- News, weather, prices, scores, and other current facts go to OpenAI (`gpt-5.4-mini`), which searches the web.

Each reply is labeled Offline or Online. Online replies include source links. An online question, plus the recent messages needed to understand it, is sent to OpenAI. The API key stays on the server.

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

## OpenAI for live questions

Set your key in the same terminal before starting the server. Do not put the key in the page or in source code.

PowerShell:

```
$env:OPENAI_API_KEY = "your-key"
python chat_server.py
```

To use a different OpenAI model:

```
$env:OPENAI_MODEL = "gpt-5.4-mini"
```

You can also put `OPENAI_API_KEY` and `OPENAI_MODEL` in a `.env` file in this folder. That file is ignored by git. Restart the server after changing it.
