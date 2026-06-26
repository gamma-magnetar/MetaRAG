"""L4 — generation. Gemini turns (system + context) into SQL.

NullLLM is used when no API key is set: it raises a friendly message pointing you to
`python rag.py search ...` (retrieval-only), so the rest of the system stays usable.
"""
from __future__ import annotations
import re


class LLM:
    def generate(self, system: str, user: str) -> str: ...


class NullLLM(LLM):
    def generate(self, system: str, user: str) -> str:
        raise RuntimeError(
            "No GEMINI_API_KEY set, so SQL generation is disabled.\n"
            "  • Add a key to .env to enable `ask`, or\n"
            "  • run `python rag.py search \"<question>\"` to see what retrieval returns.")


def _strip_fences(text: str) -> str:
    text = text.strip()
    m = re.search(r"```(?:sql)?\s*(.*?)```", text, re.S | re.I)
    return m.group(1).strip() if m else text


class GeminiLLM(LLM):
    def __init__(self, api_key: str, model: str, temperature: float = 0.1):
        from google import genai
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.temperature = temperature

    def generate(self, system: str, user: str) -> str:
        from google.genai import types
        resp = self.client.models.generate_content(
            model=self.model,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=self.temperature,
                max_output_tokens=1500,
            ),
        )
        return _strip_fences(resp.text or "")


def get_llm(settings) -> LLM:
    if settings.has_gemini:
        try:
            return GeminiLLM(settings.gemini_api_key, settings.generation_model,
                             settings.generation_temperature)
        except Exception as e:
            print(f"[llm] Gemini unavailable ({e}).")
    return NullLLM()
