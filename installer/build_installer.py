# -*- coding: utf-8 -*-
"""Compile AzurPromilia-VI-Setup.exe using the built-in .NET Framework 4.x C# compiler."""
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SRC = HERE / "AzurPromiliaViInstaller.cs"
ASSETS_DIR = HERE / "assets"
OUT_EXE = REPO / "AzurPromilia-VI-Setup.exe"
DIST_EXE = REPO / "dist" / "AzurPromilia-VI-Setup.exe"

CSC_CANDIDATES = [
    Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"),
    Path(r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe"),
]


def main():
    csc = next((p for p in CSC_CANDIDATES if p.is_file()), None)
    if csc is None:
        raise FileNotFoundError("Could not find .NET Framework 4.x csc.exe")
    wpf_dir = csc.parent / "WPF"
    OUT_EXE.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(csc),
        "/nologo",
        "/target:winexe",
        "/optimize+",
        "/warn:4",
        "/platform:anycpu",
        "/codepage:65001",
        "/r:System.dll",
        "/r:System.Core.dll",
        "/r:System.Windows.Forms.dll",
        "/r:System.Web.Extensions.dll",
        "/r:System.IO.Compression.FileSystem.dll",
        "/r:System.Xaml.dll",
        f"/r:{wpf_dir / 'WindowsBase.dll'}",
        f"/r:{wpf_dir / 'PresentationCore.dll'}",
        f"/r:{wpf_dir / 'PresentationFramework.dll'}",
        f"/win32icon:{ASSETS_DIR / 'app.ico'}",
        f"/resource:{ASSETS_DIR / 'app.ico'},AzurPromiliaVI.app.ico",
        f"/resource:{ASSETS_DIR / 'kv-poster.jpg'},AzurPromiliaVI.kv-poster.jpg",
        f"/resource:{ASSETS_DIR / 'kv-loop.mp4'},AzurPromiliaVI.kv-loop.mp4",
        f"/resource:{ASSETS_DIR / 'bgm.mp3'},AzurPromiliaVI.bgm.mp3",
        f"/out:{OUT_EXE}",
        str(SRC),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(res.stdout)
        print(res.stderr, file=sys.stderr)
        sys.exit(res.returncode)
    DIST_EXE.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(OUT_EXE, DIST_EXE)
    print(f"Compiled {OUT_EXE} ({OUT_EXE.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
