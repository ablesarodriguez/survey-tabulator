"""Time and peak memory of tabulating every categorical variable of a .sav file.

Compares the block-by-block reader of this project with simply loading the whole
file into a DataFrame, which is the least any load-everything tool has to do.
Each measurement runs in its own process so that the peaks do not mix.

    python tools/make_sample_data.py --rows 2000000 --extra-variables 72 --out big.sav
    python tools/benchmark.py big.sav
"""

import argparse
import os
import subprocess
import sys
import tempfile
import time

import psutil
import pyreadstat

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


def peak_memory_mb():
    info = psutil.Process().memory_info()
    return getattr(info, 'peak_wset', info.rss) / 1e6


def run_blocks(path, chunk_size):
    from excel_export import write_excel
    from tabulation import accumulate

    _, meta = pyreadstat.read_sav(path, metadataonly=True)
    # Identifiers and weights are not tabulated: only the variables with value labels
    variables = [c for c in meta.column_names if c in meta.variable_value_labels]
    data = accumulate(path, meta, variables, [], [], chunk_size=chunk_size)
    with tempfile.TemporaryDirectory() as tmp:
        write_excel(data, meta, variables, os.path.join(tmp, 'tables.xlsx'), True, show_stats=True)
    return meta.number_rows, len(variables)


def run_whole(path):
    df, meta = pyreadstat.read_sav(path, user_missing=True)
    return len(df), df.shape[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('path')
    parser.add_argument('--chunk-size', type=int, default=50_000)
    parser.add_argument('--mode', choices=['blocks', 'whole'], help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.mode:
        start = time.perf_counter()
        rows, columns = run_blocks(args.path, args.chunk_size) if args.mode == 'blocks' else run_whole(args.path)
        print(f"{rows} {columns} {time.perf_counter() - start:.1f} {peak_memory_mb():.0f}")
        return

    print(f"{args.path}: {os.path.getsize(args.path) / 1e6:.0f} MB on disk")
    for mode, title in (('blocks', f'Tabulate the categorical variables in blocks of {args.chunk_size:,} rows + Excel'),
                        ('whole', 'Only load the whole file into memory')):
        result = subprocess.run(
            [sys.executable, '-W', 'ignore', __file__, args.path, '--chunk-size', str(args.chunk_size), '--mode', mode],
            capture_output=True, text=True)
        if result.returncode != 0:
            print(f"{title}: failed\n{result.stderr.strip().splitlines()[-1]}")
            continue
        rows, columns, seconds, memory = result.stdout.split()
        print(f"{title}: {int(rows):,} rows x {columns} variables, {seconds} s, peak memory {memory} MB")


if __name__ == '__main__':
    main()
