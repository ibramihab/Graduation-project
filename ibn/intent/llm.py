"""The LLM "brain". Every LLM has ONE method: ask_json(system, user, schema) -> dict.

To use a different LLM later, write a new class with the same method and
add it to get_llm(). Nothing else in the project has to change.
"""
import json

import anthropic
import requests

from .. import settings


class ClaudeLLM:
    """Cloud LLM, needs ANTHROPIC_API_KEY in your .env file."""

    def __init__(self, model: str = settings.CLAUDE_MODEL):
        self.model = model

    def ask_json(self, system: str, user: str, schema: dict) -> dict:
        client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY automatically
        response = client.beta.messages.create(
            model=self.model,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": user}],
            # Force the answer to be JSON that matches our schema.
            output_config={"format": {"type": "json_schema", "schema": schema}},
            # If the model declines a request, let Anthropic retry on a fallback model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("The LLM refused this request.")
        text = next(b.text for b in response.content if b.type == "text")
        return json.loads(text)


class OllamaLLM:
    """Local LLM running on your own PC with Ollama (https://ollama.com).
    No API key, no internet. Start it with:  ollama run llama3.1"""

    def __init__(self, url: str = settings.OLLAMA_URL, model: str = settings.OLLAMA_MODEL):
        self.url = url
        self.model = model

    def ask_json(self, system: str, user: str, schema: dict) -> dict:
        response = requests.post(f"{self.url}/api/chat", timeout=300, json={
            "model": self.model,
            "stream": False,
            "format": schema,  # Ollama also supports forcing a JSON schema
            # temperature 0 = no randomness: small models make fewer mistakes.
            # num_ctx = how much text the model can read at once. Ollama's default (2048)
            # silently cuts off our long prompts, so we raise it.
            "options": {"temperature": 0, "num_ctx": 8192},
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
        })
        response.raise_for_status()
        return json.loads(response.json()["message"]["content"])


def get_llm():
    if settings.LLM_PROVIDER == "ollama":
        return OllamaLLM()
    return ClaudeLLM()
