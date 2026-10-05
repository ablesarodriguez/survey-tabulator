"""Excel output: one sheet with weighted counts and one with column percentages."""

import xlsxwriter

from i18n import output_labels
from tabulation import build_variable_rows, compute_scale_statistics, percentage


def write_excel(data, meta, variables, output_path, show_total, show_stats=False, on_progress=None, language='en'):
    LABELS = output_labels(language)
    variable_labels = meta.column_names_to_labels
    years = data['years']
    total_rows = data['total_rows']
    rows_per_year = data['rows_per_year']

    # constant_memory writes each row to disk as soon as the next one starts
    workbook = xlsxwriter.Workbook(output_path, {'constant_memory': True})
    ws_freq = workbook.add_worksheet(LABELS['sheet_frequencies'])
    ws_pct = workbook.add_worksheet(LABELS['sheet_percentages'])

    n_value_columns = len(years) + (1 if show_total else 0)
    for ws in (ws_freq, ws_pct):
        ws.set_column('A:A', 50)
        ws.set_column(1, n_value_columns, 12)

    format_cache = {}

    def get_format(bold=False, is_pct=False, left=1, right=0, top=0, bottom=0):
        key = (bold, is_pct, left, right, top, bottom)
        if key not in format_cache:
            props = {'bold': bold}
            if is_pct:
                props['num_format'] = '0.0'
            if left:
                props['left'] = left
            if right:
                props['right'] = right
            if top:
                props['top'] = top
            if bottom:
                props['bottom'] = bottom
            format_cache[key] = workbook.add_format(props)
        return format_cache[key]

    def write_row(ws, row_idx, values, bold_all=False, is_pct=False, top=0, bottom=0):
        last = len(values) - 1
        for col_idx, value in enumerate(values):
            bold = bold_all or col_idx <= 1
            left = 2 if (top or bottom) and col_idx == 0 else 1
            right = 2 if (top or bottom) and col_idx == last else (1 if col_idx == last else 0)
            fmt = get_format(bold=bold, is_pct=(is_pct and col_idx >= 1),
                             left=left, right=right, top=top, bottom=bottom)
            if value is None or value == ' ' or value == '':
                ws.write_blank(row_idx, col_idx, None, fmt)
            else:
                ws.write(row_idx, col_idx, value, fmt)

    year_headers = years if years != [0] else [LABELS['data']]
    year_totals = [int(rows_per_year.get(year, 0)) for year in years]
    # Cells that sit under the "Total" column, when it is shown
    total_blank = [' '] if show_total else []
    total_value = [total_rows] if show_total else []

    header = [' '] + ([LABELS['total']] if show_total else []) + [LABELS['year']] + [''] * (len(years) - 1)
    blank_row = [' '] * (n_value_columns + 1)
    total_row = [LABELS['total']] + total_value + year_totals
    base_row = [LABELS['total_base']] + total_value + year_totals

    # --- Header block, the same on both sheets ---
    row = {}
    for ws, title in ((ws_freq, LABELS['counts']), (ws_pct, LABELS['percentages'])):
        write_row(ws, 0, header, bold_all=True, top=1)
        if show_total:
            write_row(ws, 1, [title] + total_blank + year_headers, bold_all=True)
            write_row(ws, 2, total_row, bold_all=True, bottom=1)
            next_row = 3
        else:
            write_row(ws, 1, [title] + year_headers, bold_all=True, bottom=1)
            next_row = 2
        write_row(ws, next_row, blank_row)
        write_row(ws, next_row + 1, base_row)
        row[ws] = next_row + 2

    def append(ws, values, **kwargs):
        write_row(ws, row[ws], values, **kwargs)
        row[ws] += 1

    # --- One table per variable ---
    for idx, variable in enumerate(variables):
        if on_progress:
            on_progress('excel', idx + 1, len(variables), variable)

        title = variable_labels.get(variable) or variable
        categories, rows, base_values, base_label, filter_categories = build_variable_rows(variable, data, LABELS)
        stats = compute_scale_statistics(categories, rows, years) if show_stats else None
        bases = base_values if show_total else base_values[1:]

        stats_rows = []
        if stats:
            for key in ('mean', 'std_dev'):
                keys = (['total'] if show_total else []) + years
                stats_rows.append([LABELS[key]] + [
                    round(stats[key][k], 2) if stats[key][k] is not None else '' for k in keys
                ])

        for ws in (ws_freq, ws_pct):
            append(ws, [title] + [' '] * n_value_columns)
            append(ws, [base_label] + bases)

        for category in categories:
            counts, total = rows[category]
            values = ([total] if show_total else []) + [counts[year] for year in years]
            append(ws_freq, [category] + values)

            if category in filter_categories:
                append(ws_pct, [category] + [' '] * n_value_columns, is_pct=True)
            else:
                append(ws_pct, [category] + [percentage(v, b) for v, b in zip(values, bases)], is_pct=True)

        for ws in (ws_freq, ws_pct):
            for stats_row in stats_rows:
                append(ws, stats_row)
            append(ws, blank_row)

    workbook.close()
