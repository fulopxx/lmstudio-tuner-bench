"""Progress messages of long-running core operations (runs, resumes).

The core never prints. It hands progress lines to the sink set here; the command line sets a sink that prints them,
and a later API can collect or stream them instead. Without a sink the messages are dropped. While a run is going on,
every line is also appended to the run's progress log (IF-12).
"""
import threading

_sink = None
_log_path = None
_log_lock = threading.Lock()


def set_sink(fn):
    """fn(text) receives every progress line; None drops them."""
    global _sink
    _sink = fn


def set_log(path):
    """Every following line is also appended to this file (a run's progress.log); None ends that."""
    global _log_path
    _log_path = path


def emit(text):
    path = _log_path
    if path is not None:
        with _log_lock:  # the harness output arrives from reader threads
            try:
                with open(path, "a", encoding="utf-8") as f:
                    f.write("".join(line + "\n" for line in str(text).split("\n")))
            except OSError:
                pass  # the log must never stop a run
    if _sink is not None:
        _sink(text)


class CoreError(Exception):
    """A request the core cannot carry out (unknown model, no run to resume, ...); `code` is the CLI exit code."""

    def __init__(self, message, code=2):
        super().__init__(message)
        self.code = code
