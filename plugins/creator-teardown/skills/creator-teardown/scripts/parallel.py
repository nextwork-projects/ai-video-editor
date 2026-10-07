"""Measure several videos at once. Stdlib only.

    python3 parallel.py demo     self-check
"""
import os
import sys


def jobs(n_items, cores=None, env=None):
    """How many videos to measure at once: CT_JOBS, else a quarter of the cores (each worker is itself
    multi-threaded), 1 to 4. ponytail: a core count, not a memory check; CT_JOBS=1 on a small laptop."""
    env = os.environ if env is None else env
    n = int(env.get("CT_JOBS") or 0) or min(4, max(1, (cores or os.cpu_count() or 2) // 4))
    return max(1, min(n, n_items))


def pmap(fn, items, threads=False):
    """fn over items, several at once, results in order. fn must be a top-level function (processes).
    threads=True for work that is a subprocess already (whisper, yt-dlp)."""
    items = list(items)
    n = jobs(len(items))
    if n == 1:
        return [fn(x) for x in items]
    from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
    with (ThreadPoolExecutor if threads else ProcessPoolExecutor)(n) as ex:
        return list(ex.map(fn, items))


def demo():
    assert jobs(5, cores=14, env={}) == 3 and jobs(5, cores=8, env={}) == 2 and jobs(5, cores=2, env={}) == 1
    assert jobs(2, cores=64, env={}) == 2 and jobs(5, cores=14, env={"CT_JOBS": "1"}) == 1
    assert pmap(abs, [-1, -2, 3], threads=True) == [1, 2, 3]
    print("parallel demo ok")


if __name__ == "__main__":
    sys.exit(demo() if sys.argv[1:] == ["demo"] else print(__doc__))
