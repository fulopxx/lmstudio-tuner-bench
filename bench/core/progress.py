"""Progress messages of long-running core operations (runs, resumes).

The core never prints. It hands progress lines to the sink set here; the command line sets a sink that prints them,
and a later API can collect or stream them instead. Without a sink the messages are dropped.
"""

_sink = None


def set_sink(fn):
    """fn(text) receives every progress line; None drops them."""
    global _sink
    _sink = fn


def emit(text):
    if _sink is not None:
        _sink(text)


class CoreError(Exception):
    """A request the core cannot carry out (unknown model, no run to resume, ...); `code` is the CLI exit code."""

    def __init__(self, message, code=2):
        super().__init__(message)
        self.code = code
