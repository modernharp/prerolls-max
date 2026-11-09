import sys
import os
import webbrowser
import threading
import time
import subprocess
import ctypes
import socket
import urllib.request
import json
from typing import Optional

# Third-party (packaged into the EXE)
from PIL import Image, ImageDraw
import pystray

# Single-instance mutex name
MUTEX_NAME = "Global\\PrerollsMaxTray_SingleInstance_Mutex"
_mutex_handle = None

def _acquire_single_instance():
    """Acquire a system-wide mutex to ensure only one tray instance runs.
    Returns True if this is the first instance, False if another is already running."""
    global _mutex_handle
    try:
        # CreateMutexW: create or open a named mutex
        kernel32 = ctypes.windll.kernel32
        ERROR_ALREADY_EXISTS = 183
        
        _mutex_handle = kernel32.CreateMutexW(None, True, MUTEX_NAME)
        last_error = kernel32.GetLastError()
        
        if last_error == ERROR_ALREADY_EXISTS:
            # Another instance is already running
            if _mutex_handle:
                kernel32.CloseHandle(_mutex_handle)
                _mutex_handle = None
            return False
        return True
    except Exception as e:
        # If mutex fails, allow running (fallback behavior)
        try:
            _log_tray(f"Mutex acquisition failed: {e}")
        except:
            pass
        return True

def _release_single_instance():
    """Release the mutex when exiting."""
    global _mutex_handle
    try:
        if _mutex_handle:
            ctypes.windll.kernel32.ReleaseMutex(_mutex_handle)
            ctypes.windll.kernel32.CloseHandle(_mutex_handle)
            _mutex_handle = None
    except Exception:
        pass


def _pmax_port() -> int:
    """The port Prerolls Max uses: PMAX_PORT, else startup.json in the data
    folder (written by Settings > Moving from NeXroll and by the installer's
    "Keep NeXroll running too"), else 9393. One reader for everything:
    backend/port_config.py, bundled into this EXE."""
    global _PORT_NOTE
    env = dict(os.environ)  # note: on Windows a copy has UPPER-CASE keys; read ProgramData from os.environ
    if not env.get("PMAX_DB_PATH") and not env.get("PMAX_DB_DIR"):
        # The installed app keeps its database (and startup.json) here.
        env["PMAX_DB_DIR"] = os.path.join(os.environ.get("ProgramData") or os.path.expanduser("~"), "Prerolls Max")
    try:
        from backend import port_config
        port, source = port_config.configured_port(env)
        _PORT_NOTE = f"from {source}"
        return port
    except Exception as e:  # never stop the tray over this; read the same file directly
        _PORT_NOTE = f"port_config unavailable ({type(e).__name__}: {e}); read startup.json directly"
    try:
        if env.get("PMAX_PORT"):
            return int(env["PMAX_PORT"])
        with open(os.path.join(env["PMAX_DB_DIR"], "startup.json"), "r", encoding="utf-8") as fh:
            port = int((json.load(fh) or {}).get("port") or 0)
        if 1024 <= port <= 65535:
            return port
    except Exception:
        pass
    return 9393


_PORT_NOTE = ""
PMAX_PORT = _pmax_port()
APP_PORT = PMAX_PORT
# The project link comes from build_info.json (the GitHub repository that built
# this copy), through backend/brand.py, bundled into the tray's EXE.
try:
    from backend import brand as _brand
    GITHUB_URL = _brand.PROJECT_URL or _brand.UPSTREAM_URL
    LATEST_RELEASE_API = _brand.release_api_url()
except Exception:
    GITHUB_URL = "https://github.com/JFLXCLOUD/NeXroll"
    LATEST_RELEASE_API = None
APP_URL = f"http://localhost:{PMAX_PORT}"
LATEST_RELEASE_URL = GITHUB_URL + "/releases" if LATEST_RELEASE_API else GITHUB_URL
APP_NAME = "Prerolls Max"

def _get_install_dir():
    """Get the Prerolls Max installation directory."""
    try:
        # Try registry first
        install_dir = _reg_get_value("Software\\Prerolls Max", "InstallDir")
        if install_dir and os.path.exists(install_dir):
            return install_dir
            
        # Then try executable directory
        if getattr(sys, "frozen", False):
            exe_dir = os.path.dirname(sys.executable)
            if os.path.exists(os.path.join(exe_dir, "PrerollsMax.exe")):
                return exe_dir
                
        # Finally try Program Files
        program_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
        nexroll_dir = os.path.join(program_files, "Prerolls Max")
        if os.path.exists(os.path.join(nexroll_dir, "PrerollsMax.exe")):
            return nexroll_dir
            
    except Exception as e:
        _log_tray(f"Error getting install dir: {e}")
    
    return os.path.dirname(sys.executable)

def _tray_log_dir():
    try:
        base = (
            os.environ.get("PROGRAMDATA")
            or os.environ.get("ProgramData")
            or os.environ.get("ALLUSERSPROFILE")
            or os.environ.get("LOCALAPPDATA")
            or os.environ.get("APPDATA")
            or os.path.dirname(sys.executable)
        )
        d = os.path.join(base, "Prerolls Max", "logs")
        os.makedirs(d, exist_ok=True)
        return d
    except Exception:
        try:
            d = os.path.join(os.path.dirname(sys.executable), "logs")
            os.makedirs(d, exist_ok=True)
            return d
        except Exception:
            return os.getcwd()

def _log_tray(msg: str):
    try:
        log_dir = _tray_log_dir()
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(os.path.join(log_dir, "tray.log"), "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


def _message_box(title: str, text: str):
    # Show a topmost, foreground info dialog on a background thread to avoid blocking the tray UI
    def _show():
        try:
            MB_OK = 0x00000000
            MB_ICONINFORMATION = 0x00000040
            MB_SETFOREGROUND = 0x00010000
            MB_TOPMOST = 0x00040000
            MB_TASKMODAL = 0x00002000
            flags = MB_OK | MB_ICONINFORMATION | MB_SETFOREGROUND | MB_TOPMOST | MB_TASKMODAL
            # Allow the MessageBox to take focus from background process
            try:
                ctypes.windll.user32.AllowSetForegroundWindow(-1)
            except Exception:
                pass
            ctypes.windll.user32.MessageBoxW(None, text, title, flags)
        except Exception:
            pass
    try:
        t = threading.Thread(target=_show, daemon=True)
        t.start()
    except Exception:
        # Fallback to synchronous display
        try:
            ctypes.windll.user32.MessageBoxW(None, text, title, 0x00000040)
        except Exception:
            pass


def _reg_get_value(subkey: str, value_name: str) -> Optional[str]:
    """Read a registry value from HKLM in both 64-bit and 32-bit views (handles NSIS x86 writes)."""
    try:
        if not sys.platform.startswith("win"):
            return None
        import winreg
        # Try 64-bit view first, then 32-bit (Wow6432Node)
        for access in (
            winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0),
            winreg.KEY_READ | getattr(winreg, "KEY_WOW64_32KEY", 0),
        ):
            try:
                key = winreg.OpenKeyEx(winreg.HKEY_LOCAL_MACHINE, subkey, 0, access)
                try:
                    val, _ = winreg.QueryValueEx(key, value_name)
                    s = str(val).strip() if val is not None else ""
                    if s:
                        return s
                finally:
                    winreg.CloseKey(key)
            except Exception:
                continue
    except Exception:
        pass
    return None


def _reg_install_dir() -> Optional[str]:
    return _reg_get_value(r"Software\Prerolls Max", "InstallDir")


def _paths():
    inst = _reg_install_dir() or os.path.dirname(sys.executable)
    svc = os.path.join(inst, "PrerollsMaxService.exe")
    app = os.path.join(inst, "PrerollsMax.exe")
    return inst, svc, app


def _is_listening(port: int = PMAX_PORT, host: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.5):
            return True
    except Exception:
        return False


def _nexroll_holds_port() -> bool:
    """NeXroll answers on our port (both use 9393 by default)."""
    try:
        with urllib.request.urlopen(f"{APP_URL}/", timeout=2.0) as resp:
            return b"<title>NeXroll" in resp.read(65536)
    except Exception:
        return False


def _probe_health(url: str = f"{APP_URL}/health", timeout: float = 2.5) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def _service_installed() -> bool:
    """Return True if the Windows service 'PrerollsMaxService' is installed."""
    try:
        # 'sc query' returns 0 if service exists, non-zero otherwise
        rc = subprocess.run(
            ["sc", "query", "PrerollsMaxService"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        return getattr(rc, "returncode", 1) == 0
    except Exception:
        return False


def _start_service_blocking(wait_seconds: int = 20) -> bool:
    """Attempt to start the service quickly; fall back to app if not installed or fails."""
    inst, svc, _ = _paths()
    if not os.path.exists(svc):
        return False
    # If the service is not installed, do not wait
    if not _service_installed():
        return False
    try:
        r = subprocess.run(
            [svc, "start"],
            cwd=inst,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        # If start failed, do not wait for long health timeout
        if getattr(r, "returncode", 1) != 0:
            return False
    except Exception:
        return False

    # Short health wait (reduce tray startup delay when service cannot become healthy)
    start = time.time()
    while time.time() - start < wait_seconds:
        if _probe_health() or _is_listening():
            return True
        time.sleep(1.0)
    return False


def _start_app_blocking(wait_seconds: int = 20) -> bool:
    inst, _, app = _paths()
    if not os.path.exists(app):
        _log_tray("start_app: app executable not found at " + app)
        return False
    try:
        # Best-effort: ensure no prior instances are locking the port
        try:
            subprocess.run(
                ["taskkill", "/F", "/IM", "PrerollsMax.exe", "/T"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
        except Exception:
            pass
        subprocess.Popen(
            [app],
            cwd=inst,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        _log_tray("start_app: launched PrerollsMax.exe from " + inst)
    except Exception as e:
        _log_tray(f"start_app: failed to launch PrerollsMax.exe: {e}")
        return False
    start = time.time()
    while time.time() - start < wait_seconds:
        if _probe_health() or _is_listening():
            return True
        time.sleep(1.0)
    return False


def ensure_backend_running():
    _log_tray("ensure_backend_running: invoked")
    if _nexroll_holds_port():
        msg = (f"Port {PMAX_PORT} is already in use, probably by NeXroll. Stop NeXroll, "
               "or set PMAX_PORT (or pick another port in Settings > Moving from NeXroll).")
        _log_tray("ensure_backend_running: " + msg)
        _message_box("Prerolls Max can't start", msg)
        return
    # If already good, nothing to do
    if _probe_health() or _is_listening():
        _log_tray("ensure_backend_running: backend already healthy")
        return
    # Try to start service first; if fails (e.g., no admin rights), fall back to app
    _log_tray("ensure_backend_running: attempting to start service")
    if _start_service_blocking():
        _log_tray("ensure_backend_running: service reported healthy")
        return
    _log_tray("ensure_backend_running: service not available, trying portable app")
    ok = _start_app_blocking()
    if ok:
        _log_tray("ensure_backend_running: portable app reported healthy")
    else:
        _log_tray("ensure_backend_running: portable app did not reach healthy state")


def start_service(icon: Optional[object] = None, item: Optional[object] = None) -> None:
    _log_tray("start_service: invoked")
    ok = _start_service_blocking()
    if ok:
        _log_tray("start_service: service reported healthy")
        return
    _log_tray("start_service: service not available; attempting portable app")
    _message_box("Prerolls Max Service", "Failed to start service (may require admin). "
                 "Attempting to start app instead.")
    if not _start_app_blocking():
        _log_tray("start_service: portable app launch failed")
        _message_box("Prerolls Max", "Could not start Prerolls Max. Please run PrerollsMax.exe manually.")
    else:
        _log_tray("start_service: portable app reported healthy")


def stop_service(icon: Optional[object] = None, item: Optional[object] = None) -> None:
    _log_tray("stop_service: invoked")
    inst, svc, _ = _paths()
    if not os.path.exists(svc):
        _log_tray("stop_service: service executable not found")
        _message_box("Prerolls Max Service", "Service executable not found.")
        return
    try:
        subprocess.run([svc, "stop"], cwd=inst, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        _log_tray("stop_service: stop command issued")
    except Exception as e:
        _log_tray(f"stop_service: error: {e}")
        _message_box("Prerolls Max Service", f"Failed to stop service: {e}")


def restart_service(icon: Optional[object] = None, item: Optional[object] = None) -> None:
    _log_tray("restart_service: invoked")
    stop_service()
    time.sleep(1.5)
    start_service()


def start_app(icon: Optional[object] = None, item: Optional[object] = None) -> None:
    _log_tray("start_app: invoked")
    if not _start_app_blocking():
        _log_tray("start_app: failed to start portable app")
        _message_box("Prerolls Max", "Failed to start Prerolls Max application.")
    else:
        _log_tray("start_app: portable app reported healthy")


def open_app(icon: Optional[object] = None, item: Optional[object] = None) -> None:
    try:
        _log_tray(f"open_app: opening {APP_URL}")
        webbrowser.open(APP_URL)
    except Exception as e:
        _log_tray(f"open_app: error: {e}")
        _message_box("Open Prerolls Max", f"Could not open {APP_URL}")


def open_github(icon: Optional[object] = None, item: Optional[object] = None) -> None:
    try:
        _log_tray(f"open_github: opening {GITHUB_URL}")
        webbrowser.open(GITHUB_URL)
    except Exception as e:
        _log_tray(f"open_github: error: {e}")
        _message_box("Open GitHub", f"Could not open {GITHUB_URL}")


def rebuild_thumbnails(icon: Optional[object] = None, item: Optional[object] = None) -> None:
    _log_tray("rebuild_thumbnails: POST /thumbnails/rebuild?force=true")
    try:
        req = urllib.request.Request(f"{APP_URL}/thumbnails/rebuild?force=true", method="POST")
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        msg = (
            "Rebuild complete.\n"
            f"Processed: {data.get('processed')}\n"
            f"Generated: {data.get('generated')}\n"
            f"Skipped: {data.get('skipped')}\n"
            f"Failures: {data.get('failures')}"
        )
        _log_tray(f"rebuild_thumbnails: done processed={data.get('processed')} generated={data.get('generated')} skipped={data.get('skipped')} failures={data.get('failures')}")
    except Exception as e:
        msg = f"Rebuild failed: {e}"
        _log_tray(f"rebuild_thumbnails: error: {e}")
    _message_box("Rebuild Thumbnails", msg)

def _reg_version() -> Optional[str]:
    # Read HKLM\Software\Prerolls Max\Version from both 64-bit and 32-bit views
    return _reg_get_value(r"Software\Prerolls Max", "Version")


def _backend_version() -> Optional[str]:
    """Fallback: query the backend /system/version endpoint for installed/api version."""
    try:
        req = urllib.request.Request(
            f"{APP_URL}/system/version",
            headers={"User-Agent": "PrerollsMaxTray/1.0", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            if getattr(resp, "status", 200) == 200:
                import json as _json
                data = _json.loads(resp.read().decode("utf-8"))
                # Prefer registry_version if provided by backend, else api_version
                ver = data.get("registry_version") or data.get("api_version") or ""
                ver = str(ver).strip()
                return ver if ver else None
    except Exception:
        return None
    return None


def _parse_version(s: str) -> tuple[int, int, int]:
    if not s:
        return (0, 0, 0)
    try:
        s = s.strip()
        if s and (s[0] == "v" or s[0] == "V"):
            s = s[1:]
        parts = s.split(".")
        nums = []
        for p in parts:
            # keep digits only
            digits = "".join(ch for ch in p if ch.isdigit())
            nums.append(int(digits) if digits else 0)
        while len(nums) < 3:
            nums.append(0)
        return tuple(nums[:3])
    except Exception:
        return (0, 0, 0)


def check_for_updates(icon: Optional[object] = None, item: Optional[object] = None) -> None:
    # Prefer registry version, then backend-reported version, else 0.0.0
    if not LATEST_RELEASE_API:
        _message_box("Prerolls Max Update", "Update checks aren't set up for this copy of Prerolls Max.")
        return
    current = _reg_version() or _backend_version() or "0.0.0"
    latest_tag = None
    try:
        req = urllib.request.Request(
            LATEST_RELEASE_API,
            headers={"User-Agent": "PrerollsMaxTray/1.0", "Accept": "application/vnd.github+json"},
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            latest_tag = data.get("tag_name") or data.get("name")
    except Exception as e:
        latest_tag = None
        _log_tray(f"check_for_updates: error contacting GitHub: {e}")

    if not latest_tag:
        _log_tray("check_for_updates: latest release not resolved; opening releases page")
        _message_box("Prerolls Max Update", "Could not check for updates. Opening releases page.")
        try:
            webbrowser.open(LATEST_RELEASE_URL)
        except Exception:
            pass
        return

    _log_tray(f"check_for_updates: installed={current} latest={latest_tag}")

    curr_v = _parse_version(current)
    latest_v = _parse_version(latest_tag)

    if latest_v > curr_v:
        _message_box("Prerolls Max Update", f"New version available: {latest_tag} (installed: {current}). Opening download page.")
        try:
            webbrowser.open(LATEST_RELEASE_URL)
        except Exception:
            pass
    else:
        _message_box("Prerolls Max Update", f"You are up to date.\nInstalled: {current}\nLatest: {latest_tag}")


def about(icon: Optional[object] = None, item: Optional[object] = None) -> None:
    _message_box(
        "About Prerolls Max",
        "Prerolls Max\n\nPlex Preroll Management System\n\n"
        f"Web UI: {APP_URL}\n"
        "Project: " + GITHUB_URL
    )


def on_exit(icon: Optional[object] = None, item: Optional[object] = None) -> None:
    try:
        if icon:
            icon.visible = False  # type: ignore
            icon.stop()  # type: ignore
    except Exception:
        pass
    time.sleep(0.2)
    os._exit(0)


def _build_icon_image():
    size = (16, 16)
    img = Image.new("RGBA", size, color=(0, 0, 0, 0))  # type: ignore
    draw = ImageDraw.Draw(img)
    draw.ellipse((0, 0, 15, 15), fill=(30, 144, 255, 255))
    draw.line((4, 11, 4, 4), fill=(255, 255, 255, 255), width=2)
    draw.line((4, 4, 11, 11), fill=(255, 255, 255, 255), width=2)
    draw.line((11, 11, 11, 4), fill=(255, 255, 255, 255), width=2)
    return img


def resource_path(rel_path: str) -> str:
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(__file__))
    return os.path.join(base_path, rel_path)


def get_tray_image():
    try:
        install_dir = _get_install_dir()
        _log_tray(f"Looking for icon in install directory: {install_dir}")
        
        # First try the bundled resources directory (packaged with exe)
        if getattr(sys, "frozen", False):
            # When frozen, check the _MEIPASS directory for bundled resources
            resource_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
            icon_path = os.path.join(resource_dir, "resources", "icon_1758297097_16x16.ico")
            _log_tray(f"Checking bundled icon at: {icon_path}")
            if os.path.exists(icon_path):
                _log_tray(f"Found bundled icon at: {icon_path}")
                img = Image.open(icon_path).convert("RGBA")
                return img
        
        # Try the embedded icon (when running as packaged exe)
        if getattr(sys, "frozen", False):
            try:
                import win32api
                import win32con
                import win32gui
                
                # Always use the current executable (PrerollsMaxTray.exe)
                exe_path = sys.executable
                    
                _log_tray(f"Extracting icon from: {exe_path}")
                large_icons, small_icons = win32gui.ExtractIconEx(exe_path, 0)  # type: ignore

                if small_icons:
                    hicon = small_icons[0]
                    import win32ui
                    from PIL import ImageWin

                    dc = win32ui.CreateDCFromHandle(win32gui.GetDC(0))
                    bmp = win32ui.CreateBitmap()
                    bmp.CreateCompatibleBitmap(dc, 16, 16)
                    memdc = dc.CreateCompatibleDC()
                    memdc.SelectObject(bmp)
                    memdc.DrawIcon((0, 0), hicon)

                    bmpinfo = bmp.GetInfo()
                    bmpstr = bmp.GetBitmapBits(True)
                    img = Image.frombuffer(
                        'RGB',
                        (bmpinfo['bmWidth'], bmpinfo['bmHeight']),
                        bmpstr, 'raw', 'BGRX', 0, 1
                    )
                    img = img.convert("RGBA")
                    _log_tray("Successfully extracted icon from exe")
                    return img
            except Exception as e:
                _log_tray(f"Failed to extract embedded icon: {e}")
        
        # Try the resources directory
        tray_icon = os.path.join(install_dir, "resources", "tray.ico")
        if os.path.exists(tray_icon):
            _log_tray(f"Found tray icon at: {tray_icon}")
            img = Image.open(tray_icon).convert("RGBA")
            if max(img.size) > 32:
                img = img.resize((16, 16))
            return img
            
        # Next try the packaged executable's embedded icon (fallback)
        if getattr(sys, "frozen", False):
            try:
                import win32api
                import win32con
                import win32gui
                
                # Use current executable as fallback
                exe_path = sys.executable
                    
                _log_tray(f"Extracting icon from: {exe_path} (fallback)")
                large_icons, small_icons = win32gui.ExtractIconEx(exe_path, 0)  # type: ignore

                if small_icons:
                    hicon = small_icons[0]
                    import win32ui
                    from PIL import ImageWin

                    dc = win32ui.CreateDCFromHandle(win32gui.GetDC(0))
                    bmp = win32ui.CreateBitmap()
                    bmp.CreateCompatibleBitmap(dc, 16, 16)
                    memdc = dc.CreateCompatibleDC()
                    memdc.SelectObject(bmp)
                    memdc.DrawIcon((0, 0), hicon)

                    bmpinfo = bmp.GetInfo()
                    bmpstr = bmp.GetBitmapBits(True)
                    img = Image.frombuffer(
                        'RGB',
                        (bmpinfo['bmWidth'], bmpinfo['bmHeight']),
                        bmpstr, 'raw', 'BGRX', 0, 1
                    )
                    img = img.convert("RGBA")
                    _log_tray("Successfully extracted icon from exe")
                    return img
            except Exception as e:
                _log_tray(f"Failed to extract embedded icon: {e}")

        # Try PrerollsMax_ICON directory
        icon_paths = [
            os.path.join(install_dir, "PrerollsMax_ICON"),  # Installed location
            os.path.join(os.path.dirname(install_dir), "PrerollsMax_ICON"),  # Parent of install dir
            resource_path("PrerollsMax_ICON")  # Resource path
        ]
        
        for icon_dir in icon_paths:
            _log_tray(f"Checking icon directory: {icon_dir}")
            if os.path.isdir(icon_dir):
                # Try icon files in order of preference
                for size in ["16x16", "32x32", "64x64"]:
                    for ext in [".ico", ".png"]:
                        icon_path = os.path.join(icon_dir, f"icon_1758297097_{size}{ext}")
                        if os.path.exists(icon_path):
                            _log_tray(f"Found icon at: {icon_path}")
                            img = Image.open(icon_path).convert("RGBA")
                            if max(img.size) > 32:
                                img = img.resize((16, 16))
                            return img

        # Fallbacks
        candidates = [
            resource_path(os.path.join("frontend", "favicon.ico")),
            resource_path("favicon.ico"),
            resource_path("PrerollsMax.ico"),
        ]
        for p in candidates:
            if os.path.exists(p):
                img = Image.open(p).convert("RGBA")
                if max(img.size) > 32:
                    img = img.resize((16, 16))
                return img
    except Exception:
        pass
    return _build_icon_image()


def run_tray():
    _log_tray(f"PrerollsMaxTray starting (port {PMAX_PORT}, {_PORT_NOTE})")
    menu = pystray.Menu(
        pystray.MenuItem("Open", open_app, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Start Service", start_service),
        pystray.MenuItem("Stop Service", stop_service),
        pystray.MenuItem("Restart Service", restart_service),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Rebuild Thumbnails", rebuild_thumbnails),
        pystray.MenuItem("Check for updates", check_for_updates),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("About", about),
        pystray.MenuItem("Project page", open_github),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Exit", on_exit)
    )

    icon = pystray.Icon("PrerollsMaxTray", get_tray_image(), APP_NAME, menu)
    t = threading.Thread(target=ensure_backend_running, daemon=True)
    t.start()
    icon.run()


if __name__ == "__main__":
    # Single-instance check - prevent multiple tray apps from running
    if not _acquire_single_instance():
        # Another instance is already running - just exit silently
        sys.exit(0)
    
    # Install a global excepthook to capture unhandled exceptions to ProgramData\Prerolls Max\logs\tray.log
    def _tray_excepthook(exc_type, exc, tb):
        try:
            import traceback
            lines = "".join(traceback.format_exception(exc_type, exc, tb))
            _log_tray(f"Unhandled exception: {lines}")
        except Exception:
            pass
        # Also show a minimal message box to surface fatal errors when running interactively
        try:
            _message_box("Prerolls Max Tray Error", f"{exc_type.__name__}: {exc}")
        except Exception:
            pass
    try:
        sys.excepthook = _tray_excepthook
    except Exception:
        pass
    
    try:
        # Run as GUI app (no console when packaged)
        run_tray()
    finally:
        # Release mutex on exit
        _release_single_instance()