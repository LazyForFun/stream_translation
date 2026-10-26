from pydantic import BaseModel


class TranscribeTranslateResponse(BaseModel):
    original_text: str
    translated_text: str
    detected_language: str