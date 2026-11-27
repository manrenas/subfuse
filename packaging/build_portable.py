from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
BUILD = ROOT / "build" / "portable"


def main() -> int:
    if sys.platform not in {"win32", "darwin"}:
        raise SystemExit("Portable ZIP builds are supported on Windows and macOS.")
    architecture = platform.machine().lower()
    if architecture in {"amd64", "x64"}:
        architecture = "x86_64"
    elif architecture in {"aarch64", "arm64"}:
        architecture = "arm64"
    if sys.platform == "win32" and architecture != "x86_64":
        raise SystemExit("The Windows release target is x86_64.")
    if sys.platform == "darwin" and architecture not in {"x86_64", "arm64"}:
        raise SystemExit(f"Unsupported macOS architecture: {architecture}")

    shutil.rmtree(BUILD, ignore_errors=True)
    DIST.mkdir(parents=True, exist_ok=True)
    BUILD_DIST = BUILD / "dist"
    data_separator = os.pathsep
    icon = ROOT / "legenda_app" / "assets" / "subfuse-icone.png"
    icon_notice = ROOT / "legenda_app" / "assets" / "ICON-NOTICE.txt"
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        "SubFuse",
        "--distpath",
        str(BUILD_DIST),
        "--workpath",
        str(BUILD / "work"),
        "--specpath",
        str(BUILD),
        "--add-data",
        f"{icon}{data_separator}assets",
        "--add-data",
        f"{icon_notice}{data_separator}assets",
        str(ROOT / "embutir_legendas.py"),
    ]
    subprocess.run(command, cwd=ROOT, check=True)

    from legenda_app import __version__

    target = "windows" if sys.platform == "win32" else "macos"
    archive = DIST / f"SubFuse-{__version__}-{target}-{architecture}.zip"
    app_directory = (
        BUILD_DIST / "SubFuse.app"
        if sys.platform == "darwin"
        else BUILD_DIST / "SubFuse"
    )
    executable = (
        app_directory / "Contents" / "MacOS" / "SubFuse"
        if sys.platform == "darwin"
        else app_directory / "SubFuse.exe"
    )
    subprocess.run([str(executable), "--version"], cwd=ROOT, check=True)
    archive.unlink(missing_ok=True)

    if sys.platform == "darwin":
        subprocess.run(
            [
                "ditto",
                "-c",
                "-k",
                "--sequesterRsrc",
                "--keepParent",
                str(app_directory),
                str(archive),
            ],
            check=True,
        )
    else:
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
            for path in sorted(app_directory.rglob("*")):
                if path.is_file():
                    archive_path = Path("SubFuse") / path.relative_to(app_directory)
                    output.write(path, archive_path)
    print(f"Created {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
