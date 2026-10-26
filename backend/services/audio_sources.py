import comtypes
import psutil
from pycaw.pycaw import AudioUtilities

SESSION_STATE_ACTIVE = 1


def _root_pid(proc: psutil.Process) -> int:
    # 瀏覽器等程式的聲音來自子行程;process loopback 會包含整個行程樹,
    # 所以往上找同名的最上層行程,每個應用程式只列一次
    name = proc.name()
    root = proc

    while True:
        try:
            parent = root.parent()
        except psutil.Error:
            break

        if parent is None or parent.name() != name:
            break

        root = parent

    return root.pid


def list_audio_sources() -> list[dict]:
    sources: dict[int, dict] = {}

    # 在 FastAPI 的 thread pool 執行,該執行緒尚未初始化 COM
    comtypes.CoInitialize()
    try:
        sessions = AudioUtilities.GetAllSessions()
    finally:
        comtypes.CoUninitialize()

    for session in sessions:
        proc = session.Process

        if proc is None or session.ProcessId == 0:
            continue

        try:
            pid = _root_pid(proc)
            name = proc.name()
        except psutil.Error:
            continue

        active = session.State == SESSION_STATE_ACTIVE
        existing = sources.get(pid)

        if existing:
            existing["active"] = existing["active"] or active
            continue

        sources[pid] = {"pid": pid, "name": name, "active": active}

    return sorted(sources.values(), key=lambda s: (not s["active"], s["name"].lower()))
