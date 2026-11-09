#!/usr/bin/env python3
"""Generated inputs for the Windows build, all from files already in the repo.

    python packaging/windows/prepare.py

Writes, under packaging/windows/build/ (git-ignored):
    version_info.txt     the .exe version resource, from app/version.py
    version.nsh          !defines for the installer (APP_VERSION, APP_VERSION_NUM)
and packaging/windows/PrerollsMax_ICON/*.ico, from the web interface's icon
(frontend/public/icons/icon-512.png), so there is one icon source.

build.ps1 runs this first; the workflow writes build_info.json beside it.
"""
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BUILD = HERE / "build"
ICONS = HERE / "PrerollsMax_ICON"
ICON_SOURCE = ROOT / "frontend" / "public" / "icons" / "icon-512.png"
ICON_SIZES = [16, 24, 32, 48, 64, 128, 256]


def app_version() -> str:
    text = (ROOT / "app" / "version.py").read_text(encoding="utf-8-sig")
    match = re.search(r"""__version__\s*=\s*['"]([^'"]+)['"]""", text)
    if not match:
        sys.exit("app/version.py has no __version__")
    return match.group(1)


def numeric(version: str) -> tuple:
    """1.2.3-beta.4 -> (1, 2, 3, 4); a stable 1.2.3 -> (1, 2, 3, 0)."""
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)(?:-[A-Za-z]+\.?(\d+))?", version)
    if not match:
        sys.exit(f"Can't read version {version!r}")
    return tuple(int(g or 0) for g in match.groups())


VERSION_INFO = """VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={num},
    prodvers={num},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [StringStruct('CompanyName', 'Prerolls Max'),
         StringStruct('FileDescription', 'Prerolls Max'),
         StringStruct('FileVersion', '{dotted}'),
         StringStruct('InternalName', 'Prerolls Max'),
         StringStruct('OriginalFilename', 'PrerollsMax.exe'),
         StringStruct('ProductName', 'Prerolls Max'),
         StringStruct('ProductVersion', '{version}'),
         StringStruct('LegalCopyright', 'Prerolls Max, based on NeXroll by JFLXCLOUD. MIT licence.')]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def write_icons() -> None:
    from PIL import Image

    ICONS.mkdir(exist_ok=True)
    master = Image.open(ICON_SOURCE).convert("RGBA")
    # One multi-size icon for the exes, and the per-size names the installer
    # and the tray look for (icon_1758297097_<n>x<n>.ico, kept from NeXroll's layout).
    master.save(ICONS / "prerollsmax.ico", sizes=[(s, s) for s in ICON_SIZES])
    for size in ICON_SIZES:
        master.save(ICONS / f"icon_1758297097_{size}x{size}.ico", sizes=[(size, size)])


def main() -> None:
    version = app_version()
    num = numeric(version)
    BUILD.mkdir(exist_ok=True)
    (BUILD / "version_info.txt").write_text(
        VERSION_INFO.format(num=num, dotted=".".join(map(str, num)), version=version), encoding="utf-8")
    (BUILD / "version.nsh").write_text(
        f'!define APP_VERSION "{version}"\n!define APP_VERSION_NUM "{".".join(map(str, num))}"\n',
        encoding="utf-8")
    write_icons()
    print(f"Prepared the Windows build for Prerolls Max {version} ({'.'.join(map(str, num))})")


if __name__ == "__main__":
    main()
