"""Command-line mode: the same tabulation without the window, for batch use.

    python src/app.py --input data/sample_survey.sav --output tables.xlsx
    python src/app.py --input survey.sav --output tables --format both --language ca --variables SEX,AGE_GROUP
"""

import argparse
import os

import pyreadstat

from config import DEFAULT_CHUNK_SIZE, SPECIAL_CODES
from excel_export import write_excel
from i18n import DEFAULT_LANGUAGE, LANGUAGES
from pdf_export import write_pdf
from tabulation import accumulate


def main(argv=None):
    parser = argparse.ArgumentParser(prog='survey-tabulator', description="Tabulate an SPSS .sav file to Excel and PDF.")
    parser.add_argument('--input', required=True, help='.sav file to read')
    parser.add_argument('--output', required=True, help='output file; its extension is replaced as needed')
    parser.add_argument('--variables', help='comma-separated list, in table order (default: every variable with value labels)')
    parser.add_argument('--format', choices=['excel', 'pdf', 'both'], default='excel')
    parser.add_argument('--language', choices=list(LANGUAGES), default=DEFAULT_LANGUAGE)
    parser.add_argument('--years', help='comma-separated waves to include (default: all)')
    parser.add_argument('--include-special', action='store_true',
                        help='keep the special codes (don\'t know, no answer...) in the tables')
    parser.add_argument('--no-total', action='store_true', help='leave out the overall Total column')
    parser.add_argument('--no-stats', action='store_true', help='no mean and standard deviation for rating scales')
    parser.add_argument('--chunk-size', type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument('--workers', type=int, help='number of processes (default: depends on the file size)')
    args = parser.parse_args(argv)

    _, meta = pyreadstat.read_sav(args.input, metadataonly=True)
    if args.variables:
        variables = [name.strip() for name in args.variables.split(',') if name.strip()]
        unknown = [name for name in variables if name not in meta.column_names]
        if unknown:
            parser.error(f"not in the file: {', '.join(unknown)}")
    else:
        variables = [name for name in meta.column_names if name in meta.variable_value_labels]

    years = [int(year) for year in args.years.split(',')] if args.years else []
    excluded = [] if args.include_special else SPECIAL_CODES

    def on_progress(stage, done, total, detail):
        print(f"\r{stage}: {done}/{total}   ", end='', flush=True)

    data = accumulate(args.input, meta, variables, excluded, years, chunk_size=args.chunk_size,
                      on_progress=on_progress, workers=args.workers)

    base, _ = os.path.splitext(args.output)
    options = dict(show_stats=not args.no_stats, on_progress=on_progress, language=args.language)
    written = []
    if args.format in ('excel', 'both'):
        write_excel(data, meta, variables, base + '.xlsx', not args.no_total, **options)
        written.append(base + '.xlsx')
    if args.format in ('pdf', 'both'):
        write_pdf(data, meta, variables, base + '.pdf', not args.no_total, **options)
        written.append(base + '.pdf')

    print(f"\r{data['total_rows']:,} rows, {len(variables)} variables, {data['workers']} process(es) -> {', '.join(written)}")
    return 0
