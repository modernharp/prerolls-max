import os
import sys
import time
import signal
import socket
import subprocess
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
# Import win32timezone directly from the package
from win32timezone import TimeZoneInfo
import win32event
import win32service
import win32serviceutil
import servicemanager
import pywintypes


class PrerollsMaxService(win32serviceutil.ServiceFramework):
    _svc_name_ = "PrerollsMaxService"
    _svc_display_name_ = "Prerolls Max Background Service"
    _svc_description_ = "Runs the Prerolls Max FastAPI backend as a Windows service."
    _svc_deps_ = []  # No dependencies required

    def __init__(self, args):
        try:
            super().__init__(args)
            # Event to listen for stop requests
            self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
            self.proc = None
            self.stopping = False
            self.startup_checkpoint = 0
            # track recent restart timestamps to avoid rapid thrashing
            self._restart_history = []
            self.log_dir = self._get_log_dir()
            try:
                os.makedirs(self.log_dir, exist_ok=True)
            except Exception:
                pass
            # Install global logging early so any startup exceptions are captured
            try:
                self._install_global_logging()
            except Exception:
                pass
            self._log("info", f"Service initialized. log_dir={self.log_dir}, install_dir={self._get_install_dir()}")
        except Exception as e:
            import traceback
            print(f"Service init error: {e}\n{traceback.format_exc()}", file=sys.stderr)
            raise

    def _get_install_dir(self) -> str:
        """Get the installation directory with frontend path validation."""
        try:
            # Start with service executable directory
            if getattr(sys, "frozen", False):
                service_dir = os.path.dirname(sys.executable)
                self._log("info", f"Service executable directory: {service_dir}")
                
                # Look for frontend in various locations relative to service
                frontend_paths = [
                    os.path.join(service_dir, "frontend", "build"),
                    os.path.join(os.path.dirname(service_dir), "frontend", "build"),
                    os.path.join(service_dir, "frontend", "build", "static"),
                ]
                
                for path in frontend_paths:
                    self._log("info", f"Checking frontend path: {path}")
                    if os.path.exists(os.path.join(path, "index.html")):
                        self._log("info", f"Found frontend build at: {path}")
                        return os.path.dirname(os.path.dirname(path))  # Return Prerolls Max root dir
                
            # Check standard Program Files location
            program_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
            nexroll_dir = os.path.join(program_files, "Prerolls Max")
            
            if os.path.exists(os.path.join(nexroll_dir, "frontend", "build", "index.html")):
                self._log("info", f"Found Prerolls Max in Program Files: {nexroll_dir}")
                return nexroll_dir
            
            # Development/fallback paths
            paths_to_check = [
                os.path.dirname(os.path.abspath(__file__)),  # Script directory
                os.getcwd(),  # Current working directory
                os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."),  # Parent of script dir
            ]
            
            for path in paths_to_check:
                frontend_build = os.path.join(path, "frontend", "build", "index.html")
                if os.path.exists(frontend_build):
                    self._log("info", f"Found frontend in development path: {path}")
                    return path
                
            self._log("warning", "No frontend build found in any expected location")
            return service_dir if getattr(sys, "frozen", False) else os.getcwd()
            
        except Exception as e:
            self._log("error", f"Error in _get_install_dir: {e}")
            return os.getcwd()

    def _get_log_dir(self) -> str:
        try:
            # First, try programdata location
            prog_data = os.environ.get("ProgramData", "")
            if prog_data:
                log_dir = os.path.join(prog_data, "Prerolls Max", "logs")
                try:
                    os.makedirs(log_dir, exist_ok=True)
                    return log_dir
                except Exception:
                    pass

            # Fallback: temp directory
            temp = os.environ.get("TEMP", os.environ.get("TMP", ""))
            if temp:
                log_dir = os.path.join(temp, "Prerolls Max", "logs")
                try:
                    os.makedirs(log_dir, exist_ok=True)
                    return log_dir
                except Exception:
                    pass

            # Last resort: next to the exe
            exe_dir = self._get_install_dir()
            log_dir = os.path.join(exe_dir, "logs")
            try:
                os.makedirs(log_dir, exist_ok=True)
            except Exception:
                pass
            return log_dir
        except Exception as e:
            print(f"Error getting log dir: {e}", file=sys.stderr)
            return os.getcwd()

    def _install_global_logging(self):
        """Install a global excepthook and tee stdout/stderr into the service log."""
        def log_error(msg):
            self._log("error", msg)
        servicemanager.LogErrorMsg = log_error
        
        # Install exception hook
        try:
            import traceback
            def _hook(exc_type, exc, tb):
                try:
                    lines = "".join(traceback.format_exception(exc_type, exc, tb))
                    self._log("error", f"Unhandled exception: {lines}")
                except Exception:
                    pass
            sys.excepthook = _hook
        except Exception:
            pass
            
        # Redirect std streams as best-effort
        try:
            self._redirect_std_streams()
        except Exception:
            pass

    def _build_launch_command(self):
        inst_dir = self._get_install_dir()
        nexroll_exe = os.path.join(inst_dir, "PrerollsMax.exe")

        self._log("info", f"Looking for PrerollsMax.exe in: {nexroll_exe}")
        
        # Prefer the packaged executable
        if os.path.exists(nexroll_exe):
            self._log("info", f"Found PrerollsMax.exe at {nexroll_exe}")
            return {"cmd": [nexroll_exe], "cwd": inst_dir}

        # Fall back to Python (system) if available
        python = None
        for cand in ["python", "python3", sys.executable]:
            try:
                # Hide any flash of console windows when probing python
                si = None
                try:
                    si = subprocess.STARTUPINFO()
                    si.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 0)
                except Exception:
                    si = None
                completed = subprocess.run(
                    [cand, "--version"],
                    capture_output=True,
                    startupinfo=si,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                if completed.returncode == 0:
                    python = cand
                    break
            except Exception:
                continue

        if python:
            # Note: In installed layout, backend sources are not present; this fallback
            # is best-effort for developer installs only.
            return {
                "cmd": [python, "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", str(self._get_port())],
                "cwd": inst_dir,
            }

        # Last resort: try the venv if present
        venv_python = os.path.join(inst_dir, "venv", "Scripts", "python.exe")
        if os.path.exists(venv_python):
            return {
                "cmd": [venv_python, "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", str(self._get_port())],
                "cwd": inst_dir,
            }

        # If nothing found, return None
        return None

    def _redirect_std_streams(self):
        try:
            log_path = os.path.join(self.log_dir, "service.log")
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            lf = open(log_path, "a", encoding="utf-8", buffering=1)
            class _Tee:
                def __init__(self, orig, fh):
                    self._orig = orig
                    self._fh = fh
                def write(self, s):
                    try:
                        if self._orig:
                            self._orig.write(s)
                    except Exception:
                        pass
                    try:
                        if self._fh:
                            self._fh.write(s)
                    except Exception:
                        pass
                def flush(self):
                    try:
                        if self._orig:
                            self._orig.flush()
                    except Exception:
                        pass
                    try:
                        if self._fh:
                            self._fh.flush()
                    except Exception:
                        pass
            try:
                sys.stdout = _Tee(getattr(sys, "stdout", None), lf)
                sys.stderr = _Tee(getattr(sys, "stderr", None), lf)
            except Exception:
                pass
        except Exception:
            pass

    def _log(self, level: str, msg: str):
        # Write to Windows Event Log and file
        text = f"PrerollsMaxService: {msg}"
        try:
            if level.lower() == "error":
                servicemanager.LogErrorMsg(text)
            else:
                servicemanager.LogInfoMsg(text)
        except Exception:
            pass

        try:
            log_path = os.path.join(self.log_dir, "service.log")
            with open(log_path, "a", encoding="utf-8") as f:
                ts = time.strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"[{ts}] [{level.upper()}] {msg}\n")
        except Exception:
            pass

    def _is_port_open(self, host: str, port: int, timeout: float = 1.5) -> bool:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except Exception:
            return False

    def _get_port(self) -> int:
        """PMAX_PORT, else startup.json in the data folder (Settings > Moving from
        NeXroll, or the installer's "Keep NeXroll running too"), else 9393. The
        same reader as PrerollsMax.exe: backend/port_config.py, bundled in."""
        env = dict(os.environ)
        if not env.get("PMAX_DB_PATH") and not env.get("PMAX_DB_DIR"):
            env["PMAX_DB_DIR"] = os.path.join(os.environ.get("ProgramData") or os.path.expanduser("~"), "Prerolls Max")
        try:
            from backend import port_config
            return port_config.configured_port(env)[0]
        except Exception as e:  # never stop the service over this; read the same file directly
            if not getattr(self, "_port_note_logged", False):
                self._port_note_logged = True
                self._log("warning", f"port_config unavailable ({type(e).__name__}: {e}); reading startup.json directly")
        try:
            if env.get("PMAX_PORT"):
                return int(env["PMAX_PORT"])
            import json
            with open(os.path.join(env["PMAX_DB_DIR"], "startup.json"), "r", encoding="utf-8") as fh:
                port = int((json.load(fh) or {}).get("port") or 0)
            if 1024 <= port <= 65535:
                return port
        except Exception:
            pass
        return 9393

    def _who_is_on(self, port: int) -> str:
        """"NeXroll" when NeXroll's page answers on this port, else ""."""
        try:
            req = Request(f"http://127.0.0.1:{port}/", headers={"User-Agent": "PrerollsMaxService/1.0"})
            with urlopen(req, timeout=2) as resp:
                return "NeXroll" if b"<title>NeXroll" in resp.read(65536) else ""
        except Exception:
            return ""

    def _wait_for_health(self, timeout: int = 60) -> bool:
        """Wait until the backend reports healthy or port 9393 is open."""
        start = time.time()
        last_log = 0.0
        port = self._get_port()
        url = f"http://127.0.0.1:{port}/health"

        while not self.stopping and (time.time() - start) < timeout:
            # Try HTTP health
            try:
                req = Request(url, headers={"User-Agent": "PrerollsMaxService/1.0"})
                with urlopen(req, timeout=2) as resp:
                    if getattr(resp, "status", 200) == 200:
                        return True
            except (URLError, HTTPError, TimeoutError, Exception):
                pass

            # Fallback to port check
            if self._is_port_open("127.0.0.1", port, timeout=1.0):
                return True

            # Periodically tell SCM we're still starting
            self.ReportServiceStatus(win32service.SERVICE_START_PENDING)
            # Log every 5 seconds while waiting
            if time.time() - last_log > 5.0:
                self._log("info", f"Waiting for backend health on {url} ...")
                last_log = time.time()

            # Wait or break if stop requested
            rc = win32event.WaitForSingleObject(self.hWaitStop, 1000)
            if rc == win32event.WAIT_OBJECT_0:
                break

        return False

    def _start_backend(self):
        launch = self._build_launch_command()
        if not launch:
            self._log("error", "No suitable runtime found to start Prerolls Max (missing PrerollsMax.exe and Python).")
            return None

        # Verify frontend build assets exist when running from packaged install
        try:
            inst_dir = self._get_install_dir()
            frontend_build = os.path.join(inst_dir, 'frontend', 'build', 'index.html')
            if not os.path.exists(frontend_build):
                self._log("warning", f"Frontend build not found at {frontend_build}. The web UI may be unavailable. Ensure frontend/build is packaged into the installer.")
        except Exception:
            pass

        # Prevent starting if the configured port is already in use. This avoids
        # multiple concurrent backends fighting for the same socket and rapid
        # restart loops that make SCM unable to start the service.
        port = self._get_port()
        try:
            if self._is_port_open("127.0.0.1", port):
                if self._who_is_on(port) == "NeXroll" or port == 9393:
                    self._log("error", f"Port {port} is already in use, probably by NeXroll. Stop NeXroll, or set "
                                       "PMAX_PORT (or pick another port in Settings > Moving from NeXroll).")
                else:
                    self._log("error", f"Port {port} already in use; will not start backend. Ensure no other Prerolls Max instance is running.")
                return None
        except Exception:
            pass

        # If another PrerollsMax.exe is already running, do not launch another one.
        try:
            # Use tasklist to detect running image name on Windows
            if sys.platform.startswith("win"):
                try:
                    completed = subprocess.run(["tasklist", "/FI", "IMAGENAME eq PrerollsMax.exe", "/FO", "CSV"], capture_output=True, text=True)
                    out = (completed.stdout or "").strip().splitlines()
                    # tasklist returns header and possibly rows. If more than 1 line, there are matches.
                    if len(out) > 1:
                        self._log("info", f"Detected existing PrerollsMax.exe processes; skipping launch ({len(out)-1} instances found).")
                        return None
                except Exception:
                    pass
        except Exception:
            pass

        creationflags = 0
        try:
            # On Windows, hide console window for background service
            if hasattr(subprocess, "CREATE_NO_WINDOW"):
                creationflags |= subprocess.CREATE_NO_WINDOW
        except Exception:
            pass

        try:
            self._log("info", f"Launching backend: {' '.join(launch['cmd'])} cwd={launch['cwd']}")
            proc = subprocess.Popen(
                launch["cmd"],
                cwd=launch["cwd"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
                creationflags=creationflags,
            )
            self._log("info", f"Started backend with PID {proc.pid} (cmd: {' '.join(launch['cmd'])})")
            return proc
        except Exception as e:
            self._log("error", f"Failed to start backend: {e}")
            return None

    def SvcDoRun(self):
        self._log("info", "Service starting...")
        self.ReportServiceStatus(win32service.SERVICE_START_PENDING)

        healthy = False
        attempts = 0
        max_attempts = 3

        while attempts < max_attempts and not self.stopping:
            if attempts > 0:
                self._log("info", f"Retrying backend start (attempt {attempts + 1}/{max_attempts})...")
                # back off a bit longer between attempts to allow any leftover
                # sockets to be released and to avoid hot loops
                time.sleep(5)

            self.proc = self._start_backend()
            if not self.proc:
                break

            # Keep START_PENDING while probing readiness
            self.ReportServiceStatus(win32service.SERVICE_START_PENDING)
            healthy = self._wait_for_health(timeout=45)

            if healthy:
                break

            # Not healthy, terminate this attempt and try again
            self._log("error", "Backend failed readiness probe. Restarting...")
            self._terminate_backend()
            attempts += 1

        # Move to RUNNING to avoid SCM timeout; continue monitoring even if unhealthy
        self.ReportServiceStatus(win32service.SERVICE_RUNNING)
        if healthy:
            self._log("info", "Service running (backend healthy).")
        else:
            self._log("error", "Service running but backend did not become healthy; will monitor/restart if needed.")

        # Main loop: wait for stop event, monitor child process
        try:
            while True:
                # Wait for stop signal for up to 2 seconds
                rc = win32event.WaitForSingleObject(self.hWaitStop, 2000)
                # If stop event is signaled, break
                if rc == win32event.WAIT_OBJECT_0:
                    break

                # If child exited unexpectedly while not stopping, attempt a restart
                if self.proc and self.proc.poll() is not None and not self.stopping:
                    exit_code = self.proc.returncode
                    now = time.time()
                    # record this restart attempt
                    self._restart_history.append(now)
                    # keep only recent history (last 60s)
                    window = 60.0
                    self._restart_history = [t for t in self._restart_history if now - t <= window]
                    if len(self._restart_history) > 5:
                        self._log("error", f"Backend restart rate too high ({len(self._restart_history)} restarts in {int(window)}s); aborting to avoid thrash.")
                        break

                    self._log("error", f"Backend exited unexpectedly with code {exit_code}. Attempting restart...")
                    # short backoff before restart
                    time.sleep(3)
                    self.proc = self._start_backend()
                    if not self.proc:
                        self._log("error", "Restart failed; stopping service loop.")
                        break

        except Exception as e:
            self._log("error", f"Service run loop exception: {e}")
        finally:
            # Ensure backend is stopped on service exit
            self._terminate_backend()
            self._log("info", "Service stopped.")
            self.ReportServiceStatus(win32service.SERVICE_STOPPED)

    def _terminate_backend(self):
        if not self.proc:
            return
            
        try:
            # Store pid before termination attempts
            proc_pid = self.proc.pid
            
            # Log termination attempt
            self._log("info", f"Attempting to terminate backend process {proc_pid}")
            
            # Try graceful termination first
            self.proc.terminate()
            
            # Give the process a chance to exit gracefully
            try:
                if self.proc.wait(timeout=5) is not None:
                    self._log("info", f"Backend process {proc_pid} terminated gracefully")
                    self.proc = None
                    return
            except subprocess.TimeoutExpired:
                self._log("warning", f"Backend process {proc_pid} did not terminate gracefully, forcing kill")
                
            # If still running, force kill
            try:
                if self.proc:  # Check if proc still exists
                    self.proc.kill()
                    self.proc.wait(timeout=5)
                    self._log("info", f"Backend process {proc_pid} was forcefully terminated")
            except Exception as e:
                self._log("error", f"Failed to kill backend process {proc_pid}: {e}")
        except Exception as e:
            self._log("error", f"Error during backend process termination: {e}")
        finally:
            self.proc = None
            
        # Double check for any leftover Prerolls Max processes
        try:
            if sys.platform.startswith("win"):
                subprocess.run(
                    ["taskkill", "/F", "/IM", "PrerollsMax.exe"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
        except Exception:
            pass

    def SvcStop(self):
        self._log("info", "Stop requested.")
        self.stopping = True
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)
        self._terminate_backend()


if __name__ == "__main__":
    # This allows standard pywin32 service commands:
    # windows_service.exe install
    # windows_service.exe start
    # windows_service.exe stop
    # windows_service.exe remove
    # With no arguments the Service Control Manager is starting the frozen
    # PrerollsMaxService.exe: host the service in this process. (Without this a
    # PyInstaller build can be installed but never starts: error 1053.)
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(PrerollsMaxService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(PrerollsMaxService)
