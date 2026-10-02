"""Resource accounting shared by the experiment driver, never by semantic engines."""
from __future__ import annotations
import collections
import resource
import time

class BudgetExceeded(RuntimeError):
    pass

class Budget:
    def __init__(self, operation_limit=1_000_000, seconds=110):
        self.limit = operation_limit; self.seconds = seconds
        self.counts = collections.Counter(); self.total = 0
        self.wall_start = time.monotonic()
        self.start_self = resource.getrusage(resource.RUSAGE_SELF)
        self.start_children = resource.getrusage(resource.RUSAGE_CHILDREN)

    def tick(self, category, n=1):
        self.counts[category] += n; self.total += n
        if self.total > self.limit: raise BudgetExceeded("counted operation budget exceeded")
        if self.total % 1024 == 0 and time.monotonic() - self.wall_start > self.seconds:
            raise BudgetExceeded("wall time budget exceeded")

    def report(self):
        now = resource.getrusage(resource.RUSAGE_SELF)
        children = resource.getrusage(resource.RUSAGE_CHILDREN)
        own = now.ru_utime + now.ru_stime - self.start_self.ru_utime - self.start_self.ru_stime
        child = children.ru_utime + children.ru_stime - self.start_children.ru_utime - self.start_children.ru_stime
        return {"work_events": self.total, "counts": dict(sorted(self.counts.items())),
                "wall_seconds": time.monotonic() - self.wall_start,
                "self_cpu_seconds": own, "child_cpu_seconds": child, "total_cpu_seconds": own + child,
                "self_peak_rss_kib": now.ru_maxrss, "largest_child_rss_kib": children.ru_maxrss,
                "workers": 1}

def enforce_limits():
    resource.setrlimit(resource.RLIMIT_AS, (3_489_660_928, 3_489_660_928))
    resource.setrlimit(resource.RLIMIT_CPU, (115, 120))
