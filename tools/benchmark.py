"""Time and peak memory of tabulating every categorical variable of a .sav file.

Compares the block-by-block reader of this project, with one process and with
several, against simply loading the whole file into a DataFrame, which is the
least any load-everything tool has to do. Each measurement runs in its own
process, and memory is the peak of that process and all its workers together.

    python tools/make_sample_data.py --rows 2000000 --extra-variables 72 --out big.sav
    python tools/benchmark.py big.sav
"""

import argparse
import os
import subprocess
import sys
import tempfile
import threading
import time

import psutil
import pyreadstat

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


class MemoryMonitor(threading.Thread):
    """Samples the memory of this process and its children until stopped."""

    def __init__(self):
        super().__init__(daemon=True)
        self.peak = 0
        self._stop_event = threading.Event()

    def run(self):
        me = psutil.Process()
        while not self._stop_event.wait(0.05):
            total = 0
            for process in [me] + me.children(recursive=True):
                try:
                    total += process.memory_info().rss
                except psutil.Error:
                    pass
            self.peak = max(self.peak, total)

    def stop(self):
        self._stop_event.set()
        self.join()
        return self.peak / 1e6


def run_blocks(path, chunk_size, workers):
    from excel_export import write_excel
    from tabulation import accumulate

    _, meta = pyreadstat.read_sav(path, metadataonly=True)
    # Identifiers and weights are not tabulated: only the variables with value labels
    variables = [c for c in meta.column_names if c in meta.variable_value_labels]
    data = accumulate(path, meta, variables, [], [], chunk_size=chunk_size, workers=workers)
    with tempfile.TemporaryDirectory() as tmp:
        write_excel(data, meta, variables, os.path.join(tmp, 'tables.xlsx'), True, show_stats=True)
    return meta.number_rows, len(variables), data['workers']


def run_whole(path):
    df, meta = pyreadstat.read_sav(path, user_missing=True)
    return len(df), df.shape[1], 1


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('path')
    parser.add_argument('--chunk-size', type=int, default=50_000)
    parser.add_argument('--mode', choices=['one', 'auto', 'whole'], help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.mode:
        monitor = MemoryMonitor()
        monitor.start()
        start = time.perf_counter()
        if args.mode == 'whole':
            rows, columns, workers = run_whole(args.path)
        else:
            rows, columns, workers = run_blocks(args.path, args.chunk_size, 1 if args.mode == 'one' else None)
        seconds = time.perf_counter() - start
        print(f"{rows} {columns} {workers} {seconds:.1f} {monitor.stop():.0f}")
        return

    print(f"{args.path}: {os.path.getsize(args.path) / 1e6:.0f} MB on disk, blocks of {args.chunk_size:,} rows")
    for mode, title in (('one', 'Tabulate + Excel, one process'),
                        ('auto', 'Tabulate + Excel, default number of processes'),
                        ('whole', 'Only load the whole file into memory')):
        result = subprocess.run(
            [sys.executable, '-W', 'ignore', __file__, args.path, '--chunk-size', str(args.chunk_size), '--mode', mode],
            capture_output=True, text=True)
        if result.returncode != 0:
            print(f"{title}: failed\n{result.stderr.strip().splitlines()[-1]}")
            continue
        rows, columns, workers, seconds, memory = result.stdout.split()
        print(f"{title}: {int(rows):,} rows x {columns} variables, {workers} process(es), "
              f"{seconds} s, peak memory {memory} MB")


if __name__ == '__main__':
    main()
