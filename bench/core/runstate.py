"""Per-run state files and the lock that allows one GPU run at a time (sweep or agent).

Every run has its own folder state/runs/<id>/ with
  status.json   state, phase, heartbeat, process; written by the run's own process only
  control.json  the last request to the run (`run`, `pause`, `stop`), its source (`cli`, `web`, `runner`) and time
  progress.log  the run's progress lines, appended while the run's process works on it
These files stay after the run ends; a new run never touches them. state/active.json names the run that holds the
GPU (run, kind, pid, pid_created). A lock whose process no longer exists counts as free. The shared
state/status.json of older versions is only read, for runs that have no status file of their own.
"""
import contextlib
import ctypes
import json
import os
import threading
import time
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

from . import progress
from .progress import CoreError

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "state"  # read at call time, so tests can point it to a temporary folder
ACTIVE_STATES = ("starting", "running", "paused")
HEARTBEAT_LATE_S = 20  # an older heartbeat is reported, and trusted only if the process still exists


# ---------------------------------------------------------------- files
def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False), encoding="utf-8")
    for attempt in range(30):  # Windows: replace fails while a reader has the file open
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 29:
                raise
            time.sleep(0.1)


def read_json(path, default=None):
    for _ in range(10):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return default
        except (PermissionError, json.JSONDecodeError):
            time.sleep(0.1)
    return default


def run_dir(run_id):
    return STATE / "runs" / str(run_id)


def status_path(run_id):
    return run_dir(run_id) / "status.json"


def control_path(run_id):
    return run_dir(run_id) / "control.json"


def log_path(run_id):
    return run_dir(run_id) / "progress.log"


def active_path():
    return STATE / "active.json"


def legacy_status_path():
    return STATE / "status.json"


def new_run_id():
    """A run id (start time, YYYYMMDD_HHMMSS) that no run has used yet; waits for the next second if needed."""
    for _ in range(30):
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        if not run_dir(run_id).exists():
            return run_id
        time.sleep(0.1)
    raise CoreError("no free run id; try again")


def new_run_dir(run_id):
    """Creates the folder of a new run; refuses an id that is already taken (two runs started in the same second)."""
    (STATE / "runs").mkdir(parents=True, exist_ok=True)
    try:
        run_dir(run_id).mkdir()
    except FileExistsError:
        raise CoreError(f"run {run_id} already exists; start again in a second") from None
    return run_dir(run_id)


def init_files(run_id):
    """At the start and at every restart of a run: no pending request, and a progress log to append to."""
    send(run_id, "run")
    log_path(run_id).touch()


@contextlib.contextmanager
def logging_to(run_id):
    """While inside, every progress line is also appended to the run's progress.log."""
    progress.set_log(log_path(run_id))
    try:
        yield
    finally:
        progress.set_log(None)


def read_status(run_id):
    """The run's own status file; for runs written before per-run state, the shared file if it names this run."""
    if not run_id:
        return None
    st = read_json(status_path(run_id))
    if st is None:
        legacy = read_json(legacy_status_path())
        if legacy and legacy.get("run") == run_id:
            return legacy
    return st


# ---------------------------------------------------------------- control channel
SOURCES = ("cli", "web", "runner")  # who asked: a user through the command line or the web, or the run itself


def send(run_id, cmd, now=False, source="runner"):
    """Writes a request to the run (IF-14: with its source and time; the last request wins)."""
    if source not in SOURCES:
        raise CoreError(f"unknown request source {source!r}; expected one of {', '.join(SOURCES)}")
    write_json(control_path(run_id), {"cmd": cmd, "now": now, "source": source, "ts": time.time()})


def control(run_id):
    return read_json(control_path(run_id), {"cmd": "run", "now": False})


# ---------------------------------------------------------------- processes
def process_created(pid):
    """Creation time of a running process as an integer; None if there is no such process. Together with
    the PID it identifies one process, even if Windows reuses the PID later (for example after a reboot)."""
    if os.name != "nt" or not pid:
        return None
    k = ctypes.WinDLL("kernel32")
    k.OpenProcess.argtypes, k.OpenProcess.restype = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE
    k.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    k.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        code = wintypes.DWORD()
        if not k.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value != 259:  # STILL_ACTIVE
            return None
        times = [wintypes.FILETIME() for _ in range(4)]
        if not k.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
            return None
        return (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
    finally:
        k.CloseHandle(handle)


def same_process_alive(record):
    created = (record or {}).get("pid_created")
    return created is not None and process_created(record.get("pid")) == created


def runner_alive(st):
    """An active run counts as alive while its heartbeat is fresh, or while the very process that wrote it
    still exists: a late heartbeat alone must not end the status view or allow a second runner."""
    if not st or st.get("state") not in ACTIVE_STATES:
        return False
    if time.time() - st.get("heartbeat", 0) < HEARTBEAT_LATE_S:
        return True
    return same_process_alive(st)


# ---------------------------------------------------------------- one GPU run at a time
def active():
    """The run holding the GPU lock ({run, kind, pid, pid_created, started}), or None. A lock whose process is gone
    counts as free."""
    lock = read_json(active_path())
    return lock if lock and same_process_alive(lock) else None


def acquire(run_id, kind):
    """Takes the GPU lock for this process; raises CoreError naming the active run if another one holds it."""
    path = active_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    me = {"run": run_id, "kind": kind, "pid": os.getpid(), "pid_created": process_created(os.getpid()),
          "started": time.time()}
    for _ in range(20):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            held = read_json(path)
            if held is None and path.exists():  # being written right now
                time.sleep(0.1)
                continue
            if held and same_process_alive(held):
                raise CoreError(f"another run is active: {held.get('kind')} run {held.get('run')} "
                                f"(PID {held.get('pid')}); see `bench status`, or stop it first")
            if read_json(path) == held:  # still the same stale lock: remove it and try again
                try:
                    os.remove(path)
                except (FileNotFoundError, PermissionError):
                    time.sleep(0.1)
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(me, f, indent=1)
        return me
    raise CoreError("could not take the run lock (state/active.json); try again")


def release(run_id):
    """Gives the lock back if this process holds it for this run."""
    held = read_json(active_path())
    if held and held.get("run") == run_id and held.get("pid") == os.getpid():
        try:
            os.remove(active_path())
        except FileNotFoundError:
            pass


# ---------------------------------------------------------------- status writer
class Status:
    """The status file of one run, rewritten on every update and every 2 s (heartbeat) by a background thread."""

    def __init__(self, run_id, base):
        self.path = status_path(run_id)
        self.data = dict(base, run=run_id, heartbeat=time.time(), pid=os.getpid(),
                         pid_created=process_created(os.getpid()))
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self.update()
        self._thread = threading.Thread(target=self._beat, daemon=True)
        self._thread.start()

    def update(self, **kw):
        with self._lock:
            self.data.update(kw, heartbeat=time.time())
            try:
                write_json(self.path, self.data)
            except OSError:
                pass  # status display must never kill a run

    def _beat(self):
        while not self._stop.wait(2):
            self.update()

    def close(self, **kw):
        self._stop.set()
        self._thread.join(timeout=5)
        self.update(**kw)
