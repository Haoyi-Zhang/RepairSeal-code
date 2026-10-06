"""Clean finite-study replay and exact evidence comparison (Linux, one worker).

The stages run serially IN THIS PROCESS so a separate controller does not add
another process to the native compiler's process tree. A sampling thread only
reads this process and its descendants' /proc resource counters. No software
fingerprint, checksum manifest, network request, or model call is made.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import resource
import sys
import threading
import time
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests')]
from budget import Budget, enforce_limits
import study
import regression
import null_control
import report as publication
from scientific_comparison import compare_evidence


def sample_tree(root):
    todo = [root]; seen = set(); rss = 0
    while todo:
        pid = todo.pop()
        if pid in seen:
            continue
        try:
            statm = (Path('/proc') / str(pid) / 'statm').read_text().split()
            current = int(statm[1]) * os.sysconf('SC_PAGE_SIZE')
            tasks = list((Path('/proc') / str(pid) / 'task').iterdir())
        except (OSError, ValueError, IndexError):
            continue
        seen.add(pid); rss += current
        for task in tasks:
            try:
                todo.extend(int(n) for n in (task / 'children').read_text().split())
            except (OSError, ValueError):
                pass
    return rss, len(seen)


class Sampler:
    def __init__(self):
        self.done = threading.Event(); self.peak_rss = 0; self.peak_count = 0
        self.thread = threading.Thread(target=self.watch, daemon=True)
    def watch(self):
        while not self.done.is_set():
            rss, count = sample_tree(os.getpid())
            self.peak_rss = max(self.peak_rss, rss); self.peak_count = max(self.peak_count, count)
            self.done.wait(0.005)
    def __enter__(self):
        self.thread.start(); return self
    def __exit__(self, *unused):
        self.done.set(); self.thread.join()


def cpu():
    own = resource.getrusage(resource.RUSAGE_SELF)
    children = resource.getrusage(resource.RUSAGE_CHILDREN)
    return own.ru_utime + own.ru_stime + children.ru_utime + children.ru_stime


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True, help='new empty output directory')
    args = p.parse_args(); out = args.output.resolve()
    if out.exists() and any(out.iterdir()):
        p.error('output must be empty; do not overwrite retained scientific evidence')
    if out == ROOT / 'results':
        p.error('use a separate output, not retained results')
    out.mkdir(parents=True, exist_ok=True); enforce_limits()
    partial = out / 'null-control.partial.json'; context = out / 'null-control.context.json'
    stages = []
    jobs = [
        ('study', 1_150_000, lambda b: study.study(out, b), 'study.json'),
        ('regression', 200_000, regression.run, 'regression.json'),
        ('null-control', 240_000, lambda b: null_control.run(b, out, partial, context), 'null-control.json'),
        ('publication', 25_000, lambda b: publication.build(out, out / 'publication', b), 'publication/report.json'),
    ]
    summary = {'outcome': 'FAILED', 'stages': stages}
    try:
        for name, cap, function, filename in jobs:
            started = time.monotonic(); before_cpu = cpu(); budget = Budget(cap)
            with Sampler() as sampler:
                data = function(budget)
            data['resources'] = budget.report()
            (out / filename).write_text(json.dumps(data, indent=2) + '\n')
            stage = {'stage': name, 'instrumented_resources': data['resources'],
                     'whole_stage_cpu_seconds': cpu() - before_cpu,
                     'wall_seconds': time.monotonic() - started,
                     'sampled_aggregate_peak_rss_bytes': sampler.peak_rss,
                     'sampled_aggregate_peak_processes': sampler.peak_count}
            stages.append(stage)
            if not data['outcome'].startswith('PASS_'):
                raise AssertionError(name + ': unsuccessful reported outcome')
            if sampler.peak_rss > 3_489_660_928 or sampler.peak_count > 4:
                raise RuntimeError(name + ': sampled resource ceiling exceeded')
            if stage['wall_seconds'] > 120:
                raise RuntimeError(name + ': stage wall-time ceiling exceeded')
            if sum(s['instrumented_resources']['work_events'] for s in stages) > 950_000:
                raise RuntimeError('reproduction event ceiling exceeded')
            if name == 'null-control':
                partial.unlink(missing_ok=True); context.unlink(missing_ok=True)
        names = ['study.json', 'regression.json', 'null-control.json', 'cases.json', 'holes.json', 'tampering.json',
                 'case-summary.csv', 'native-harness.c', 'native-compilers.json', 'native-outputs-gcc.csv', 'native-outputs-clang.csv',
                 'publication/summary.json', 'publication/report.json', 'publication/families.tex',
                 'publication/outcomes.tex', 'publication/null.tex']
        for dirname in ('certificates', 'controls', 'oracle'):
            expected = sorted(p.name for p in (ROOT / 'results' / dirname).iterdir() if p.is_file())
            actual = sorted(p.name for p in (out / dirname).iterdir() if p.is_file())
            assert actual == expected, (dirname, 'file set differs')
            names.extend(dirname + '/' + n for n in expected)
        for name in names:
            before = ROOT / 'results' / name; after = out / name
            compare_evidence(before, after, name)
        summary.update(outcome='PASS_CLEAN_REPRODUCTION', compared_files=len(names),
                       work_events=sum(s['instrumented_resources']['work_events'] for s in stages) + len(names),
                       reconciliation_events=len(names),
                       measured_stage_cpu_seconds=sum(s['whole_stage_cpu_seconds'] for s in stages),
                       resource_note='5ms /proc samples include the serial scientific process and compiler descendants. Sampling can miss short-lived peaks; summed RSS may double-count shared pages. Per-process rusage maxima are also retained. One scientific worker; one resource-only sampling thread.')
    finally:
        (out / 'reproduction.json').write_text(json.dumps(summary, indent=2) + '\n')
        print(json.dumps(summary, indent=2))
if __name__ == '__main__':
    main()
