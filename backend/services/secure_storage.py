import base64
import ctypes
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

API_KEY_FILE = APP_DIR / "api_key.bin"


def save_api_key_encrypted(api_key: str) -> None:
    encrypted = _protect(api_key.encode("utf-8"))
    API_KEY_FILE.write_bytes(base64.b64encode(encrypted))


def load_api_key_encrypted() -> str | None:
    if not API_KEY_FILE.exists():
        return None

    raw = API_KEY_FILE.read_bytes()
    if not raw:
        return None

    encrypted = base64.b64decode(raw)
    decrypted = _unprotect(encrypted)
    value = decrypted.decode("utf-8").strip()
    return value or None


def clear_saved_api_key() -> None:
    if API_KEY_FILE.exists():
        API_KEY_FILE.unlink()