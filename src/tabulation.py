"""Weighted frequency tables from an SPSS .sav file, read in blocks.

The file is never loaded whole. Each block is reduced to a handful of weighted
sums per (variable, category, year) and then discarded, so memory use depends on
the block size and on the number of distinct categories, not on the number of
rows.
"""

import gc
import math
import re
from collections import defaultdict

import pandas as pd
import pyreadstat

from config import (
    DEFAULT_CHUNK_SIZE,
    FILTER_KEYWORDS,
    LABELS,
    ONLINE_ONLY_CODE,
    ONLINE_WEIGHT_COLUMN,
    SCALE_MIN_CATEGORIES,
    SPECIAL_CODES,
    WEIGHT_COLUMN,
    YEAR_COLUMN,
)


def format_category(category):
    if isinstance(category, float) and category.is_integer():
        return str(int(category))
    return str(category)


def is_filter_label(label):
    text = str(label).lower()
    return any(keyword in text for keyword in FILTER_KEYWORDS)


def is_special_code(value):
    return isinstance(value, (int, float)) and value in SPECIAL_CODES


# ============================================================
# STEP 1: ACCUMULATION IN BLOCKS
# ============================================================

def accumulate(path, meta, variables, excluded_codes, selected_years,
               chunk_size=DEFAULT_CHUNK_SIZE, on_progress=None):
    """Read the file block by block and return the weighted sums of every table.

    excluded_codes are dropped from the tables altogether. selected_years limits
    a longitudinal file to those waves; it is ignored for a single-wave file.
    """
    value_labels = {var: meta.variable_value_labels.get(var, {}) for var in variables}

    is_longitudinal = YEAR_COLUMN in meta.column_names
    base_columns = [WEIGHT_COLUMN, ONLINE_WEIGHT_COLUMN]
    if is_longitudinal:
        base_columns.append(YEAR_COLUMN)

    needed_columns = list(dict.fromkeys(variables + base_columns))
    needed_columns = [c for c in needed_columns if c in meta.column_names]

    rows_per_year = defaultdict(int)
    online_weight_per_year = defaultdict(float)
    total_rows = 0
    years_seen = set()

    # sums[variable][((value, label), year)] = [weighted sum, online weighted sum]
    sums = {var: defaultdict(lambda: [0.0, 0.0]) for var in variables}
    online_only = {var: False for var in variables}

    filter_codes = {
        var: [value for value, label in value_labels[var].items() if is_filter_label(label)]
        for var in variables
    }
    # Weight of the respondents routed past each question, per year
    filtered_weight = {var: defaultdict(lambda: [0.0, 0.0]) for var in variables}

    excluded = []
    for code in excluded_codes:
        try:
            excluded.append(float(code))
        except (TypeError, ValueError):
            pass

    estimated_rows = getattr(meta, 'number_rows', None)
    estimated_chunks = math.ceil(estimated_rows / chunk_size) if estimated_rows else None

    reader = pyreadstat.read_file_in_chunks(
        pyreadstat.read_sav, path, chunksize=chunk_size,
        usecols=needed_columns, user_missing=True
    )

    weight_columns = [WEIGHT_COLUMN, ONLINE_WEIGHT_COLUMN]

    for chunk_idx, (chunk, _) in enumerate(reader):
        if on_progress:
            on_progress(chunk_idx, estimated_chunks or (chunk_idx + 2), "Reading block")

        if is_longitudinal:
            chunk[YEAR_COLUMN] = pd.to_numeric(chunk[YEAR_COLUMN], errors='coerce').fillna(0).astype('int32')
            if selected_years and selected_years != [0]:
                chunk = chunk[chunk[YEAR_COLUMN].isin(selected_years)].copy()
                if chunk.empty:
                    continue
        else:
            chunk[YEAR_COLUMN] = 0

        # A file without weights is tabulated unweighted
        for column in weight_columns:
            if column in chunk.columns:
                chunk[column] = pd.to_numeric(chunk[column], errors='coerce').fillna(0).astype('float32')
            else:
                chunk[column] = 1.0

        total_rows += len(chunk)
        for year, count in chunk[YEAR_COLUMN].value_counts().items():
            rows_per_year[int(year)] += int(count)
            years_seen.add(int(year))
        for year, weight in chunk.groupby(YEAR_COLUMN)[ONLINE_WEIGHT_COLUMN].sum().items():
            online_weight_per_year[int(year)] += float(weight)

        for var in variables:
            series = chunk[var]
            if not online_only[var] and series.isin([ONLINE_ONLY_CODE]).any():
                online_only[var] = True

            if filter_codes[var]:
                mask_filter = series.isin(filter_codes[var])
                if mask_filter.any():
                    routed = chunk.loc[mask_filter].groupby(YEAR_COLUMN)[weight_columns].sum()
                    for year, row in routed.iterrows():
                        acc = filtered_weight[var][int(year)]
                        acc[0] += float(row[WEIGHT_COLUMN])
                        acc[1] += float(row[ONLINE_WEIGHT_COLUMN])

            keep = ~pd.to_numeric(series, errors='coerce').isin(excluded)

            # Group by the raw SPSS code and attach the label afterwards, so that
            # the sort order and the special codes can rely on the numeric value.
            grouped = (chunk.loc[keep, weight_columns]
                       .groupby([series[keep], chunk.loc[keep, YEAR_COLUMN]], observed=True)
                       .sum())

            labels = value_labels[var]
            acc = sums[var]
            for (value, year), row in grouped.iterrows():
                try:
                    value = float(value)
                except (TypeError, ValueError):
                    pass
                label = labels.get(value, value)
                cell = acc[((value, format_category(label)), int(year))]
                cell[0] += float(row[WEIGHT_COLUMN])
                cell[1] += float(row[ONLINE_WEIGHT_COLUMN])

            del grouped

        del chunk
        if chunk_idx % 5 == 0:
            gc.collect()

    years = sorted(years_seen)
    if not years:
        raise ValueError("No valid years were found in the filtered data.")

    return {
        'years': years,
        'rows_per_year': rows_per_year,
        'online_weight_per_year': online_weight_per_year,
        'total_rows': total_rows,
        'sums': sums,
        'online_only': online_only,
        'filtered_weight': filtered_weight,
    }


# ============================================================
# STEP 2: ROWS OF ONE TABLE
# ============================================================

def build_variable_rows(variable, data):
    """Turn the accumulated sums of one variable into the rows of its table.

    Returns (categories, rows, base_values, base_label, filter_categories), where
    rows[category] = ({year: count}, total count) and base_values is the base of
    the total followed by the base of each year.
    """
    years = data['years']
    sums = data['sums'][variable]
    is_online_only = data['online_only'][variable]
    weight_idx = 1 if is_online_only else 0
    base_label = LABELS['weighted_base_online'] if is_online_only else LABELS['weighted_base']

    present = {key for (key, _year) in sums.keys()}

    def order(item):
        value, label = item
        if isinstance(value, (int, float)):
            # Special codes and filter categories go to the bottom of the table
            if is_special_code(value) or is_filter_label(label):
                return (2, float(value), '')
            return (0, float(value), '')
        if is_filter_label(label):
            return (2, 0, str(value))
        return (0, 0, str(value))

    ordered = sorted(present, key=order)
    categories = [label for (_value, label) in ordered]

    rows = {}
    for (value, label) in ordered:
        counts = {}
        total = 0.0
        for year in years:
            weighted = sums.get(((value, label), year), [0.0, 0.0])[weight_idx]
            counts[year] = int(round(weighted))
            total += weighted
        rows[label] = (counts, int(round(total)))

    years_present = [
        year for year in years
        if sum(sums.get((key, year), [0, 0])[weight_idx] for key in ordered) > 0
    ]

    filtered = data.get('filtered_weight', {}).get(variable, {})

    def year_base(year):
        if is_online_only:
            gross = data['online_weight_per_year'].get(year, 0)
        else:
            gross = data['rows_per_year'].get(year, 0)
        routed = filtered.get(year, [0.0, 0.0])[weight_idx]
        return max(0, int(round(gross - routed)))

    base_total = int(sum(year_base(year) for year in years_present))
    base_values = [base_total] + [year_base(year) if year in years_present else 0 for year in years]

    has_filter = any(
        filtered.get(year, [0.0, 0.0])[0] > 0 or filtered.get(year, [0.0, 0.0])[1] > 0
        for year in years
    )
    if has_filter:
        base_label = f"{base_label}  ·  {LABELS['filtered_question']}"

    # These categories are listed with their count but without a percentage
    filter_categories = {
        label for (value, label) in ordered
        if is_filter_label(label) or is_special_code(value)
    }

    return categories, rows, base_values, base_label, filter_categories


def percentage(count, base):
    return round(count / base * 100, 1) if base > 0 else 0


def compute_scale_statistics(categories, rows, years):
    """Mean and standard deviation of a 0-10 or 1-10 scale, total and per year.

    Returns None when the variable does not look like a rating scale.
    """
    scores = {}
    for category in categories:
        # Takes the number the category starts with: "[0] Very bad", "1", "10"
        m = re.match(r'^\[?(\d+)\]?', str(category).strip())
        if m:
            score = int(m.group(1))
            if 0 <= score <= 10:
                scores[category] = score

    if len(scores) < SCALE_MIN_CATEGORIES:
        return None

    def mean_and_sd(frequencies):
        n = sum(count for category, count in frequencies.items() if category in scores)
        if n == 0:
            return None, None
        mean = sum(count * scores[c] for c, count in frequencies.items() if c in scores) / n
        squares = sum(count * (scores[c] - mean) ** 2 for c, count in frequencies.items() if c in scores)
        variance = squares / (n - 1) if n > 1 else 0
        return mean, math.sqrt(variance)

    stats = {'mean': {}, 'std_dev': {}}
    stats['mean']['total'], stats['std_dev']['total'] = mean_and_sd({c: rows[c][1] for c in categories})
    for year in years:
        stats['mean'][year], stats['std_dev'][year] = mean_and_sd({c: rows[c][0][year] for c in categories})
    return stats
