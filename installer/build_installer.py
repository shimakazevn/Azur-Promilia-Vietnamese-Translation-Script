# -*- coding: utf-8 -*-
"""Compile AzurPromilia-VI-Setup.exe using the built-in .NET Framework 4.x C# compiler."""
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SRC = HERE / "AzurPromiliaViInstaller.cs"
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
    OUT_EXE.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(csc),
        "/nologo",
        "/target:winexe",
        "/optimize+",
        "/platform:anycpu",
        "/codepage:65001",
        "/r:System.dll",
        "/r:System.Core.dll",
        "/r:System.Drawing.dll",
        "/r:System.Windows.Forms.dll",
        "/r:System.Web.Extensions.dll",
        "/r:System.IO.Compression.FileSystem.dll",
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
