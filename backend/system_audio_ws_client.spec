# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['system_audio_ws_client.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['proctap.backends.windows', 'proctap._native'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['scipy'],  # proc-tap 在原生格式已是 48kHz float32 時不需要 scipy
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='system_audio_ws_client',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
