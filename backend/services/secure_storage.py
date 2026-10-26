import base64
import ctypes
import json
import os
from pathlib import Path
from ctypes import wintypes


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


crypt32 = ctypes.windll.crypt32
kernel32 = ctypes.windll.kernel32

CryptProtectData = crypt32.CryptProtectData
CryptProtectData.argtypes = [
    ctypes.POINTER(DATA_BLOB),
    wintypes.LPCWSTR,
    ctypes.POINTER(DATA_BLOB),
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(DATA_BLOB),
]
CryptProtectData.restype = wintypes.BOOL

CryptUnprotectData = crypt32.CryptUnprotectData
CryptUnprotectData.argtypes = [
    ctypes.POINTER(DATA_BLOB),
    ctypes.POINTER(wintypes.LPWSTR),
    ctypes.POINTER(DATA_BLOB),
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(DATA_BLOB),
]
CryptUnprotectData.restype = wintypes.BOOL


def _bytes_to_blob(data: bytes) -> DATA_BLOB:
    buffer = ctypes.create_string_buffer(data)
    blob = DATA_BLOB()
    blob.cbData = len(data)
    blob.pbData = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))
    blob._buffer = buffer
    return blob


def _blob_to_bytes(blob: DATA_BLOB) -> bytes:
    if not blob.cbData:
        return b""
    ptr = ctypes.cast(blob.pbData, ctypes.POINTER(ctypes.c_char))
    return ctypes.string_at(ptr, blob.cbData)


def _protect(data: bytes) -> bytes:
    in_blob = _bytes_to_blob(data)
    out_blob = DATA_BLOB()

    if not CryptProtectData(
        ctypes.byref(in_blob),
        "StreamTranslate API Key",
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    ):
        raise ctypes.WinError()

    try:
        return _blob_to_bytes(out_blob)
    finally:
        if out_blob.pbData:
            kernel32.LocalFree(out_blob.pbData)


def _unprotect(data: bytes) -> bytes:
    in_blob = _bytes_to_blob(data)
    out_blob = DATA_BLOB()
    description = wintypes.LPWSTR()

    if not CryptUnprotectData(
        ctypes.byref(in_blob),
        ctypes.byref(description),
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    ):
        raise ctypes.WinError()

    try:
        return _blob_to_bytes(out_blob)
    finally:
        if out_blob.pbData:
            kernel32.LocalFree(out_blob.pbData)


APP_DIR = Path(os.getenv("APPDATA", ".")) / "StreamTranslate"
APP_DIR.mkdir(parents=True, exist_ok=True)

PROVIDERS = ("openai", "gemini")
DEFAULT_PROVIDER = "openai"

# openai 沿用舊檔名，升級後不用重新輸入 key
API_KEY_FILES = {
    "openai": APP_DIR / "api_key.bin",
    "gemini": APP_DIR / "gemini_api_key.bin",
}
SETTINGS_FILE = APP_DIR / "settings.json"


def save_api_key_encrypted(api_key: str, provider: str = DEFAULT_PROVIDER) -> None:
    encrypted = _protect(api_key.encode("utf-8"))
    API_KEY_FILES[provider].write_bytes(base64.b64encode(encrypted))


def load_api_key_encrypted(provider: str = DEFAULT_PROVIDER) -> str | None:
    path = API_KEY_FILES[provider]
    if not path.exists():
        return None

    raw = path.read_bytes()
    if not raw:
        return None

    encrypted = base64.b64decode(raw)
    decrypted = _unprotect(encrypted)
    value = decrypted.decode("utf-8").strip()
    return value or None


def clear_saved_api_key(provider: str = DEFAULT_PROVIDER) -> None:
    path = API_KEY_FILES[provider]
    if path.exists():
        path.unlink()


def save_provider(provider: str) -> None:
    SETTINGS_FILE.write_text(json.dumps({"provider": provider}), encoding="utf-8")


def load_provider() -> str:
    try:
        provider = json.loads(SETTINGS_FILE.read_text(encoding="utf-8")).get("provider")
    except (OSError, ValueError):
        return DEFAULT_PROVIDER
    return provider if provider in PROVIDERS else DEFAULT_PROVIDER
