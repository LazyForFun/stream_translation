import os
from openai import OpenAI

class Translator:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()

    def set_api_key(self, api_key: str):
        self.api_key = api_key.strip()

    def clear_api_key(self):
        self.api_key = ""

    def has_api_key(self) -> bool:
        return bool(self.api_key)

    def translate_to_zh_tw(
        self,
        text: str,
        source_language: str | None = None,
        context_lines: list[str] | None = None
    ) -> str:
        if not text.strip():
            return ""

        if not self.api_key:
            return f"[未翻譯] {text}"

        client = OpenAI(api_key=self.api_key)

        context_text = ""
        if context_lines:
            cleaned_context = [line.strip() for line in context_lines if line.strip()]
            if cleaned_context:
                context_text = "\n".join(cleaned_context)

        system_prompt = (
            "將句子翻譯成合理且通順的中文"
            "只要輸出翻譯後的結果就好"
        )

        user_parts = []
        if source_language:
            user_parts.append(f"來源語言：{source_language}")

        if context_text:
            user_parts.append(f"前文：\n{context_text}")

        user_parts.append(f"當前句子：\n{text}")
        user_text = "\n\n".join(user_parts)

        response = client.responses.create(
            model="gpt-5.4-mini",
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text}
            ]
        )

        return response.output_text.strip()