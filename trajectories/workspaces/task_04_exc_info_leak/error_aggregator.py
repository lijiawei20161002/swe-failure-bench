"""
Exception aggregator for deferred error reporting.

Collects exceptions from a batch of operations and reports them together
after all operations have run. Used in batch processing pipelines where
you want to continue despite errors and report a summary at the end.

Public API:
    agg = ErrorAggregator()

    with agg.capture("op1"):
        might_fail()

    agg.report()   # prints all collected errors

    agg.clear()
"""

from __future__ import annotations

import gc
import sys
import traceback
from contextlib import contextmanager
from typing import Any


class ErrorAggregator:
    """
    Captures exceptions from multiple operations and reports them together.
    Operations run to completion even if some fail.
    """

    def __init__(self):
        # Each entry: (label, exc_type, exc_value, exc_tb)
        # BUG: storing exc_tb (the traceback object) keeps the entire call
        # stack alive. Each traceback frame references the frame object
        # (tb.tb_frame), which holds all local variables for that call.
        # Any objects referenced in the failing function's locals stay alive
        # as long as this aggregator exists, even after the caller has
        # released its references and expects them to be collected.
        #
        # Fix: do NOT store the raw traceback. Instead convert it to a
        # formatted string immediately and store that:
        #     tb_str = "".join(traceback.format_tb(exc_tb))
        #     self._errors.append((label, exc_type, exc_value, tb_str))
        # or simply clear the tb reference:
        #     self._errors.append((label, exc_type, exc_value, None))
        self._errors: list[tuple] = []

    @contextmanager
    def capture(self, label: str):
        """Run the body; if it raises, capture the exception for later."""
        try:
            yield
        except Exception:
            exc_type, exc_value, exc_tb = sys.exc_info()
            # Fix: format traceback immediately and do not keep the raw traceback
            tb_str = "".join(traceback.format_tb(exc_tb)) if exc_tb else ""
            # Clear traceback on exception value to release frame references
            if exc_value is not None:
                exc_value.__traceback__ = None
            self._errors.append((label, exc_type, exc_value, tb_str))

    def report(self) -> list[str]:
        """Return formatted error strings for all captured exceptions."""
        lines = []
        for label, exc_type, exc_value, exc_tb in self._errors:
            if isinstance(exc_tb, str):
                tb_text = exc_tb
            else:
                tb_text = "".join(traceback.format_tb(exc_tb)) if exc_tb else ""
            lines.append(f"[{label}] {exc_type.__name__}: {exc_value}\n{tb_text}")
        return lines

    def clear(self):
        """Discard all captured exceptions."""
        self._errors.clear()

    def __len__(self):
        return len(self._errors)
