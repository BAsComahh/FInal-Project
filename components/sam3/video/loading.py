"""Observe weight-loading progress through Transformers' supported tqdm hook."""

from contextlib import contextmanager
from threading import get_ident


class _WeightProgress:
    def __init__(self, bar, report):
        self.bar, self.report = bar, report

    def __iter__(self):
        total = getattr(self.bar, "total", None)
        self.report(("Loading weights", 0, total))
        for completed, item in enumerate(self.bar, 1):
            yield item
            self.report(("Loading weights", completed, total))

    def __getattr__(self, name):
        return getattr(self.bar, name)


@contextmanager
def weight_loading_progress(report):
    from transformers.utils import logging

    thread_id = get_ident()

    def hook(factory, args, kwargs):
        bar = previous(factory, args, kwargs) if previous is not None else factory(*args, **kwargs)
        if get_ident() == thread_id and kwargs.get("desc") == "Loading weights":
            return _WeightProgress(bar, report)
        return bar

    previous = logging.set_tqdm_hook(hook)
    try:
        yield
    finally:
        logging.set_tqdm_hook(previous)
