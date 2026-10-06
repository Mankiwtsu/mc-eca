"""
check_llm(): a start-up check so a missing LLM gives a clear message instead of
"Connection error" on every chat message.

    client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
    check_llm(client, "gemma3:4b")

Works with any OpenAI-compatible client object; mceca itself doesn't depend on openai.
"""

from __future__ import annotations

import os


def check_llm(client, model: str) -> None:
    """Stop the script with an explanation if `model` can't be used with `client`.

    Ollama (a localhost:11434 client): checks that Ollama runs and the model is
    downloaded. OpenAI: checks that an API key was set (not the placeholder)."""
    base_url = str(getattr(client, "base_url", ""))
    if "11434" in base_url or "ollama" in base_url.lower():
        _check_ollama(client, model)
    else:
        _check_openai_key(client)


def _check_ollama(client, model: str) -> None:
    try:
        names = [m.id for m in client.models.list().data]
    except Exception:
        _fail(
            "Can't reach Ollama at http://localhost:11434.\n"
            "  Start it: open the Ollama app, or run `ollama serve` in another terminal\n"
            "  (macOS with Homebrew: `brew services start ollama`). Then run this script again."
        )
    wanted = {model, model if ":" in model else model + ":latest"}
    if not wanted & set(names):
        have = ", ".join(names) or "none"
        _fail(
            f"Ollama is running but doesn't have the model '{model}' (installed: {have}).\n"
            f"  Download it with:  ollama pull {model}"
        )


def _check_openai_key(client) -> None:
    key = getattr(client, "api_key", None) or os.environ.get("OPENAI_API_KEY", "")
    if not key or "paste" in key.lower() or "your-key" in key.lower():
        _fail(
            "No OpenAI API key found.\n"
            "  Copy .env.example to .env (in the repository folder) and put your group's key\n"
            "  after OPENAI_API_KEY= . Or switch the example to Ollama (BACKEND = \"ollama\")."
        )


def _fail(message: str) -> None:
    print(f"[mceca] LLM not ready: {message}", flush=True)
    raise SystemExit(1)
