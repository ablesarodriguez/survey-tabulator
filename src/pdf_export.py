"""PDF output: counts and percentages side by side, one table per variable.

A single-wave file is laid out in portrait with a cumulative percentage; a
longitudinal one in landscape, with a count and a percentage column per year.
"""

from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape, portrait
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

from config import DECIMAL_SEPARATOR, LABELS
from tabulation import build_variable_rows, compute_scale_statistics, percentage


def format_number(value, decimals=1):
    return f"{value:.{decimals}f}".replace('.', DECIMAL_SEPARATOR)


def write_pdf(data, meta, variables, output_path, show_total, title=None, show_stats=False, on_progress=None):
    variable_labels = meta.column_names_to_labels
    years = data['years']
    total_rows = data['total_rows']
    rows_per_year = data['rows_per_year']

    is_single = (len(years) == 1)
    pagesize = portrait(A4) if is_single else landscape(A4)

    doc = SimpleDocTemplate(
        output_path, pagesize=pagesize,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm, topMargin=1.5 * cm, bottomMargin=1.5 * cm,
        title=title or LABELS['pdf_title']
    )

    styles = getSampleStyleSheet()
    variable_style = ParagraphStyle(
        'Variable', parent=styles['Normal'], fontSize=9,
        fontName='Helvetica-Bold', textColor=colors.black, leading=11
    )

    story = []
    hundred = format_number(100)

    # --- Column headers and widths ---
    if is_single:
        header = ['', LABELS['pdf_frequency'], LABELS['pdf_percent'], LABELS['pdf_cumulative']]
        widths = [doc.width * 0.55, doc.width * 0.15, doc.width * 0.15, doc.width * 0.15]
    else:
        # Each group (the total and every year) spans a count and a percentage column
        groups = ([LABELS['total']] if show_total else []) + [str(year) for year in years]
        header = ['']
        for group in groups:
            header += [group] * 2
        widths = [doc.width * 0.28] + [(doc.width * 0.72) / (2 * len(groups))] * (2 * len(groups))

    def base_style():
        return [
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('LEFTPADDING', (0, 0), (-1, -1), 2),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
        ]

    # --- 1. Header table with the totals ---
    header_rows = [header]
    header_style = base_style()

    if is_single:
        if show_total:
            header_rows.append([LABELS['total'], str(total_rows), hundred, hundred])
        header_rows.append([LABELS['total_base'], str(total_rows), hundred, hundred])
    else:
        header_rows.append([''] + [LABELS['pdf_count'], '%'] * len(groups))

        year_cells = []
        for year in years:
            year_cells += [str(int(rows_per_year.get(year, 0))), hundred]
        total_cells = [str(total_rows), hundred] if show_total else []

        if show_total:
            header_rows.append([LABELS['total']] + total_cells + year_cells)
        header_rows.append([LABELS['total_base']] + total_cells + year_cells)

        for i in range(len(groups)):
            header_style.append(('SPAN', (1 + 2 * i, 0), (2 + 2 * i, 0)))
            header_style.append(('ALIGN', (1 + 2 * i, 0), (2 + 2 * i, 0), 'CENTER'))

    header_style.append(('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'))
    header_style.append(('LINEABOVE', (0, 0), (-1, 0), 1, colors.black))
    header_style.append(('LINEBELOW', (0, -1), (-1, -1), 1, colors.black))

    header_table = Table(header_rows, colWidths=widths)
    header_table.setStyle(TableStyle(header_style))
    story.append(header_table)

    # --- 2. One table per variable ---
    for idx, variable in enumerate(variables):
        if on_progress:
            on_progress(idx, len(variables), f"PDF: building tables ({variable})")

        label = variable_labels.get(variable) or variable
        categories, rows, base_values, base_label, filter_categories = build_variable_rows(variable, data)
        bases = base_values if (show_total or is_single) else base_values[1:]

        table_rows = []
        table_style = base_style()

        table_rows.append([Paragraph(f"<b>{escape(str(label))}</b>", variable_style)] + [''] * (len(header) - 1))
        table_style.append(('SPAN', (0, 0), (-1, 0)))
        table_style.append(('LINEABOVE', (0, 0), (-1, 0), 1, colors.black))

        if is_single:
            table_rows.append([base_label, str(base_values[0]), hundred, format_number(0)])
        else:
            base_row = [base_label]
            for base in bases:
                base_row += [str(base), hundred]
            table_rows.append(base_row)
        table_style.append(('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'))

        cumulative = 0.0
        for category in categories:
            counts, total = rows[category]
            is_filter = category in filter_categories

            if is_single:
                if is_filter:
                    table_rows.append([category, str(total), '—', '—'])
                    continue
                pct = percentage(total, base_values[0])
                cumulative += pct
                # Rounding each row to one decimal can leave the last one at 99.9 or 100.1
                shown = 100 if cumulative > 99.9 else cumulative
                table_rows.append([category, str(total), format_number(pct), format_number(shown)])
            else:
                values = ([total] if show_total else []) + [counts[year] for year in years]
                row = [category]
                for value, base in zip(values, bases):
                    row += [str(value), '—' if is_filter else format_number(percentage(value, base))]
                table_rows.append(row)

        if show_stats:
            stats = compute_scale_statistics(categories, rows, years)
            if stats:
                if is_single:
                    keys, padding = ['total'], ['', '']
                else:
                    keys, padding = (['total'] if show_total else []) + years, []
                for key in ('mean', 'std_dev'):
                    row = [LABELS[key]]
                    for k in keys:
                        value = stats[key][k]
                        row += [format_number(value, 2) if value is not None else '', '']
                    table_rows.append(row[:len(header) - len(padding)] + padding)

        table_style.append(('LINEBELOW', (0, -1), (-1, -1), 1, colors.black))

        table = Table(table_rows, colWidths=widths)
        table.setStyle(TableStyle(table_style))
        story.append(table)

    if on_progress:
        on_progress(len(variables), len(variables), "Rendering PDF (writing to disk...)")

    doc.build(story)
