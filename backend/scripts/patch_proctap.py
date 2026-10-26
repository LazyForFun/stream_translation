"""
proc-tap 的原生模組只在 Windows build >= 20438 才啟用程序專屬擷取,
否則會悄悄退回整個系統擷取。但 process loopback 在 Windows 10 2004 (build 19041)
起就可用,所以把門檻改成 19041 並重新編譯,覆蓋 site-packages 裡的 .pyd。

需要 Visual Studio Build Tools (C++)。打包後端之前執行一次:
    python scripts/patch_proctap.py
"""
import re
import shutil
import subprocess
import sys
import sysconfig
import tempfile
from pathlib import Path

import proctap

OLD_BUILD = "20438"
NEW_BUILD = "19041"

VSWHERE = Path(r"C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe")


def find_vcvars() -> Path:
    if not VSWHERE.exists():
        sys.exit("找不到 vswhere.exe,請安裝 Visual Studio Build Tools (C++)")

    install = subprocess.run(
        [
            str(VSWHERE), "-latest", "-products", "*",
            "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
            "-property", "installationPath",
        ],
        capture_output=True, text=True, check=True,
    ).stdout.strip()

    vcvars = Path(install) / "VC" / "Auxiliary" / "Build" / "vcvars64.bat"
    if not vcvars.exists():
        sys.exit(f"找不到 {vcvars}")

    return vcvars


def main():
    pkg_dir = Path(proctap.__file__).parent
    source = (pkg_dir / "_native.cpp").read_text(encoding="utf-8")

    if f"dwBuildNumber = {OLD_BUILD};" not in source:
        sys.exit("_native.cpp 的版本檢查和預期不同(proc-tap 版本不是 1.1.1?),請手動確認")

    patched = source.replace(f"dwBuildNumber = {OLD_BUILD};", f"dwBuildNumber = {NEW_BUILD};")
    patched = re.sub(rf"Build {OLD_BUILD} or later", f"Build {NEW_BUILD} or later", patched)

    include = sysconfig.get_paths()["include"]
    libs = Path(sys.base_prefix) / "libs"
    pyd_name = next(pkg_dir.glob("_native*.pyd")).name

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "_native.cpp").write_text(patched, encoding="utf-8")

        build = tmp / "build.bat"
        build.write_text(
            f'@call "{find_vcvars()}" >nul\n'
            f'cl /nologo /LD /O2 /std:c++20 /EHsc /utf-8 /I"{include}" _native.cpp '
            f'/Fe:{pyd_name} /link /LIBPATH:"{libs}" ole32.lib uuid.lib propsys.lib\n',
            encoding="ascii",
        )

        subprocess.run(["cmd", "/c", str(build)], cwd=tmp, check=True)
        shutil.copyfile(tmp / pyd_name, pkg_dir / pyd_name)

    print(f"已更新 {pkg_dir / pyd_name}(門檻 {OLD_BUILD} -> {NEW_BUILD})")


if __name__ == "__main__":
    main()
