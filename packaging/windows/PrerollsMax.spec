# -*- mode: python ; coding: utf-8 -*-
#
# Builds the three Windows programs into packaging/windows/dist:
#   PrerollsMax.exe          the server and web interface (app/backend/main.py)
#   PrerollsMaxService.exe   the Windows service that keeps PrerollsMax.exe running
#   PrerollsMaxTray.exe      the tray icon (open, start/stop the service, updates)
#
# Run build.ps1 rather than this directly: it builds the web interface and the
# plugins, runs prepare.py (version resource, icons) and then:
#   pyinstaller --noconfirm --clean --distpath dist --workpath build/pyinstaller PrerollsMax.spec

import glob
import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

spec_root = os.path.abspath(SPECPATH)
# packaging/windows -> project root
project_root = os.path.dirname(os.path.dirname(spec_root))
app_root = os.path.join(project_root, 'app')
frontend_build = os.path.join(project_root, 'frontend', 'dist')
generated = os.path.join(spec_root, 'build')
icons = os.path.join(spec_root, 'PrerollsMax_ICON')
version_file = os.path.join(generated, 'version_info.txt')
exe_icon = os.path.join(icons, 'prerollsmax.ico')

for required in (os.path.join(frontend_build, 'index.html'), version_file, exe_icon):
    if not os.path.exists(required):
        raise SystemExit(f'Missing {required}: run packaging/windows/build.ps1 (or prepare.py and the frontend build) first.')

# build_info.json (which GitHub repository built this copy: update checks and
# the project link). Written by the workflow; a local build without it simply
# has update checks off.
build_info = os.path.join(generated, 'build_info.json')
_build_info_datas = [(build_info, '.')] if os.path.exists(build_info) else []

# yt-dlp discovers PO-token plugins (bgutil) via the `yt_dlp_plugins` namespace
# package at runtime. In a frozen build those submodules aren't picked up
# automatically, so collect them explicitly — otherwise the installed app can't
# mint PO tokens and YouTube trailer downloads fall back to the bot wall.
_potoken_hidden = collect_submodules('yt_dlp_plugins')
# include_py_files=True is essential: yt-dlp discovers plugins by scanning the
# yt_dlp_plugins namespace package's path for modules. Without the .py files on
# disk a frozen build ships only the EMPTY namespace package, so the bgutil
# plugin never loads and PO-token downloads silently fail.
_potoken_datas = collect_data_files('yt_dlp_plugins', include_py_files=True)
try:
    _potoken_datas += copy_metadata('bgutil-ytdlp-pot-provider')
except Exception:
    pass

# The Prerolls Max Intros plugins, served from the Media Servers page
# (/jellyfin/plugin/download, /emby/plugin/download). Built by plugins/build.sh
# into plugins/out before this spec runs.
_plugin_datas = [(z, 'plugins') for z in glob.glob(os.path.join(project_root, 'plugins', 'out', 'PrerollsMax.Jellyfin*.zip'))]
_emby_dll = os.path.join(project_root, 'plugins', 'out', 'PrerollsMax.Emby.dll')
if os.path.exists(_emby_dll):
    _plugin_datas.append((_emby_dll, 'plugins'))

# --- PrerollsMax.exe ---------------------------------------------------------
app_a = Analysis(
    [os.path.join(app_root, 'backend', 'main.py')],
    pathex=[app_root],
    binaries=[],
    datas=[
        (frontend_build, 'frontend/build'),
        (os.path.join(app_root, 'CHANGELOG.md'), '.'),
        # Typefaces the video maker offers on every install (SIL OFL 1.1).
        (os.path.join(project_root, 'assets', 'fonts'), 'assets/fonts'),
    ] + _potoken_datas + _plugin_datas + _build_info_datas,
    hiddenimports=['backend.radarr_connector', 'backend.dynamic_preroll', 'backend.theme_backdrop',
                   'backend.build_info', 'backend.port_config', 'segno', 'PIL', 'PIL.Image', 'PIL.ImageDraw',
                   'PIL.ImageFilter', 'httpx', 'httpx._transports', 'httpx._transports.default', 'httpcore',
                   'h11', 'h2', 'hpack', 'hyperframe', 'yt_dlp', 'yt_dlp_plugins', 'yt_dlp_plugins.extractor',
                   'yt_dlp_plugins.extractor.getpot_bgutil', 'yt_dlp_plugins.extractor.getpot_bgutil_http',
                   'yt_dlp_plugins.extractor.getpot_bgutil_script'] + _potoken_hidden
                  + collect_submodules('backend'),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter'],
    noarchive=False,
    optimize=0,
)
app_pyz = PYZ(app_a.pure)
app_exe = EXE(
    app_pyz, app_a.scripts, app_a.binaries, app_a.datas, [],
    name='PrerollsMax',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX breaks Python 3.10+ builds (ordinal 380 errors)
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    version=version_file,
    icon=[exe_icon],
)

# --- PrerollsMaxService.exe --------------------------------------------------
service_a = Analysis(
    [os.path.join(app_root, 'scripts', 'windows_service.py')],
    pathex=[app_root],
    datas=_build_info_datas,
    hiddenimports=['win32timezone', 'win32serviceutil', 'win32service', 'win32event', 'servicemanager',
                   'pywintypes', 'backend.port_config'],
    # port_config only falls back to backend.database when no data folder is
    # given; the service always gives one, so keep the database code out.
    excludes=['tkinter', 'backend.database', 'sqlalchemy'],
)
service_pyz = PYZ(service_a.pure)
service_exe = EXE(
    service_pyz, service_a.scripts, service_a.binaries, service_a.datas, [],
    name='PrerollsMaxService',
    debug=False,
    strip=False,
    upx=False,
    console=True,  # pywin32 services run as console programs (install/start/stop/remove)
    version=version_file,
    icon=[exe_icon],
)

# --- PrerollsMaxTray.exe -----------------------------------------------------
tray_a = Analysis(
    [os.path.join(app_root, 'scripts', 'tray_app.py')],
    pathex=[app_root],
    datas=[(icons, 'PrerollsMax_ICON')] + _build_info_datas,
    hiddenimports=['pystray._win32', 'PIL.ImageWin', 'win32api', 'win32con', 'win32gui', 'win32ui',
                   'backend.port_config', 'backend.brand', 'backend.build_info'],
    excludes=['tkinter', 'backend.database', 'sqlalchemy'],
)
tray_pyz = PYZ(tray_a.pure)
tray_exe = EXE(
    tray_pyz, tray_a.scripts, tray_a.binaries, tray_a.datas, [],
    name='PrerollsMaxTray',
    debug=False,
    strip=False,
    upx=False,
    console=False,
    version=version_file,
    icon=[exe_icon],
)
