from faster_whisper import WhisperModel
import traceback
from pathlib import Path


class Transcriber:
    def __init__(self, model_name: str = "large-v3-turbo"):
        self.model = None

        try:
            print("=== Trying GPU (CUDA) ===")
            self.model = WhisperModel(
                model_name,
                device="cuda",
                compute_type="float16"
            )
            print("=== Whisper using GPU ===")

        except Exception as e:
            print("=== GPU init FAILED ===")
            print(str(e))
            print(traceback.format_exc())

            try:
                print("=== Fallback to CPU ===")
                self.model = WhisperModel(
                    model_name,
                    device="cpu",
                    compute_type="int8"
                )
                print("=== Whisper using CPU ===")
            except Exception as cpu_e:
                print("=== CPU init FAILED ===")
                print(str(cpu_e))
                print(traceback.format_exc())
                raise

    def transcribe(self, file_path: str) -> dict:
        if self.model is None:
            raise RuntimeError("Transcriber model is not initialized")

        p = Path(file_path)

        if not p.exists():
            raise FileNotFoundError(f"Audio file not found: {file_path}")

        segments, info = self.model.transcribe(
            file_path,
            beam_size=3,
            language="ko"
        )
        text = "".join(segment.text for segment in segments).strip()

        return {
            "text": text,
            "language": info.language,
            "language_probability": info.language_probability,
        }