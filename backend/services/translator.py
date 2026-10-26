import os
import httpx
from openai import OpenAI

PROVIDERS = ("openai", "gemini")

OPENAI_MODEL = "gpt-5.4-mini"
GEMINI_MODEL = "gemini-3.5-flash-lite"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

SYSTEM_PROMPT = (
    "將句子翻譯成合理且通順的中文"
    "只要輸出翻譯後的結果就好"
)


class Translator:
    def __init__(self):
        self.provider = "openai"
        self.api_keys = {
            "openai": os.getenv("OPENAI_API_KEY", "").strip(),
            "gemini": os.getenv("GEMINI_API_KEY", "").strip(),
        }

    def set_provider(self, provider: str):
        if provider not in PROVIDERS:
            raise ValueError(f"Unknown provider: {provider}")
        self.provider = provider

    def set_api_key(self, api_key: str, provider: str | None = None):
        self.api_keys[provider or self.provider] = api_key.strip()

    def clear_api_key(self, provider: str | None = None):
        self.api_keys[provider or self.provider] = ""

    def has_api_key(self, provider: str | None = None) -> bool:
        return bool(self.api_keys[provider or self.provider])

    def translate_to_zh_tw(
        self,
        text: str,
        source_language: str | None = None,
        context_lines: list[str] | None = None
    ) -> str:
        if not text.strip():
            return ""

        if not self.has_api_key():
            return f"[未翻譯] {text}"

        context_text = ""
        if context_lines:
            cleaned_context = [line.strip() for line in context_lines if line.strip()]
            if cleaned_context:
                context_text = "\n".join(cleaned_context)

        user_parts = []
        if source_language:
            user_parts.append(f"來源語言：{source_language}")

        if context_text:
            user_parts.append(f"前文：\n{context_text}")

        user_parts.append(f"當前句子：\n{text}")
        user_text = "\n\n".join(user_parts)

        if self.provider == "gemini":
            return self._translate_gemini(user_text)
        return self._translate_openai(user_text)

    def _translate_openai(self, user_text: str) -> str:
        client = OpenAI(api_key=self.api_keys["openai"])
        response = client.responses.create(
            model=OPENAI_MODEL,
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text}
            ]
        )
        return response.output_text.strip()

    def _translate_gemini(self, user_text: str) -> str:
        response = httpx.post(
            GEMINI_URL.format(model=GEMINI_MODEL),
            headers={"x-goog-api-key": self.api_keys["gemini"]},
            json={
                "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                "contents": [{"role": "user", "parts": [{"text": user_text}]}],
                "generationConfig": {"thinkingConfig": {"thinkingLevel": "minimal"}},
            },
            timeout=30,
        )
        response.raise_for_status()
        parts = response.json()["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts).strip()
