"""Offline test: a broken generation stream fails the step instead of crashing the run (no LM Studio)."""
import http.client
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "runner"))
import smoke  # noqa: E402

TOKEN = b'data: {"choices": [{"delta": {"content": "a"}}]}\n'
END = b'data: {"choices": [{"delta": {}, "finish_reason": "stop"}]}\n'


class StreamErrorTest(unittest.TestCase):
    def stream(self, lines, error=None):
        def body():
            yield from lines
            if error:
                raise error

        response = mock.MagicMock()
        response.__enter__.return_value = body()
        with mock.patch.object(smoke.urllib.request, "urlopen", return_value=response):
            return smoke.stream_chat("m", [], max_tokens=5, total_timeout=30)

    def test_complete_stream(self):
        self.assertEqual(self.stream([TOKEN, END, b"data: [DONE]\n"])["content"], "a")

    def test_broken_streams_are_step_failures(self):
        cases = {
            "connection reset": ([TOKEN], ConnectionResetError("reset")),
            "incomplete read": ([TOKEN], http.client.IncompleteRead(b"")),
            "garbled data": ([b"data: {not json\n"], None),
            "closed early": ([TOKEN], None),
        }
        for name, (lines, error) in cases.items():
            with self.subTest(name):
                with self.assertRaises(smoke.StepError) as caught:
                    self.stream(lines, error)
                self.assertEqual(caught.exception.kind, "fail")


if __name__ == "__main__":
    unittest.main()
