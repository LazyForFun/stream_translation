import re
import time

# 句尾標點：英文標點需後接空白/結尾（避免切到 3.5 這種小數），中日標點直接切
_SENTENCE_RE = re.compile(r".+?(?:[.!?…]+(?=\s|$)|[。！？]+)", re.DOTALL)

_CLAUSE_BREAKS = ",，、"

# 韓文句尾常見收尾字（Whisper 沒給標點時的備援）
_KOREAN_END_CHARS = "요다까죠네군"


class SentenceSegmenter:
    """把 Whisper 每個 chunk 的片段累積起來，依句尾標點 / 韓文句尾 / 停頓 / 長度切成完整句子。"""

    def __init__(
        self,
        max_chars: int = 70,
        pause_seconds: float = 1.2,
        min_chars: int = 4,
    ):
        self.max_chars = max_chars
        self.pause_seconds = pause_seconds
        self.min_chars = min_chars
        self.buffer = ""
        self.last_feed_ts = time.monotonic()

    def feed(self, text: str, now: float | None = None) -> list[str]:
        text = text.strip()
        if not text:
            return []

        self.last_feed_ts = time.monotonic() if now is None else now
        self.buffer = f"{self.buffer} {text}".strip()

        sentences, tail = self._split_sentences(self.buffer)

        # 太長仍沒結束：在子句邊界強制切開
        while len(tail) > self.max_chars:
            head, tail = self._cut_long(tail)
            sentences.append(head)

        # 沒有標點時，用韓文句尾判斷（太短的不算，避免誤切）
        if len(tail) >= self.min_chars * 2 and self._ends_like_korean(tail):
            sentences.append(tail)
            tail = ""

        self.buffer = tail
        return sentences

    def poll(self, now: float | None = None) -> list[str]:
        """停頓夠久就把剩下的 buffer 全部吐出。"""
        if not self.buffer.strip():
            return []

        now = time.monotonic() if now is None else now
        if now - self.last_feed_ts >= self.pause_seconds:
            return self.flush()
        return []

    def flush(self) -> list[str]:
        text = self.buffer.strip()
        self.buffer = ""
        return [text] if text else []

    def _split_sentences(self, text: str) -> tuple[list[str], str]:
        sentences: list[str] = []
        pending = ""
        consumed = 0

        for match in _SENTENCE_RE.finditer(text):
            consumed = match.end()
            piece = f"{pending} {match.group()}".strip()

            # 「네.」這種太短的句子先併到下一句，避免單獨翻譯
            if len(piece) < self.min_chars:
                pending = piece
            else:
                sentences.append(piece)
                pending = ""

        tail = f"{pending} {text[consumed:].strip()}".strip()
        return sentences, tail

    @staticmethod
    def _ends_like_korean(text: str) -> bool:
        stripped = text.rstrip(" ,，、")
        return bool(stripped) and stripped[-1] in _KOREAN_END_CHARS

    def _cut_long(self, text: str) -> tuple[str, str]:
        window = text[: self.max_chars]

        idx = max(window.rfind(c) for c in _CLAUSE_BREAKS)
        if idx < self.min_chars:
            idx = window.rfind(" ")
        if idx < self.min_chars:
            return window.strip(), text[self.max_chars:].strip()

        return text[: idx + 1].strip(), text[idx + 1:].strip()
