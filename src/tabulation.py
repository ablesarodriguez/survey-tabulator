"""Weighted frequency tables from an SPSS .sav file, read in blocks.

The file is never loaded whole. Each block is reduced to a handful of weighted
sums per (variable, category, year) and then discarded, so memory use depends on
the block size and on the number of distinct categories, not on the number of
rows. Large files are split between several processes, each of which reads and
reduces its own blocks.
"""

import math
import os
import re
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np
import pandas as pd
import pyreadstat

from config import (
    DEFAULT_CHUNK_SIZE,
    FILTER_KEYWORDS,
    MAX_WORKERS,
    ONLINE_ONLY_CODE,
    ONLINE_WEIGHT_COLUMN,
    PARALLEL_MIN_ROWS,
    SCALE_MIN_CATEGORIES,
    SPECIAL_CODES,
    WEIGHT_COLUMN,
    YEAR_COLUMN,
)
from i18n import output_labels


class Cancelled(Exception):
    """Raised from a progress callback to stop a job that is under way."""


def format_category(category):
    if isinstance(category, float) and category.is_integer():
        return str(int(category))
    return str(category)


def is_filter_label(label):
    text = str(label).lower()
    return any(keyword in text for keyword in FILTER_KEYWORDS)


def is_special_code(value):
    return isinstance(value, (int, float)) and value in SPECIAL_CODES


def default_columns(column_names, preferred=None):
    """Which columns of a file hold the wave and the weights.

    For each role, the first of these that exists in the file: the name in
    preferred (what the user chose last time), then the default in config.py.
    A role with no match is None: no waves, or no weighting.
    """
    defaults = {'year': YEAR_COLUMN, 'weight': WEIGHT_COLUMN, 'online_weight': ONLINE_WEIGHT_COLUMN}
    columns = {}
    for role, default in defaults.items():
        candidates = [(preferred or {}).get(role), default]
        columns[role] = next((name for name in candidates if name and name in column_names), None)
    return columns


def scan_years(path, year_column):
    """The waves present in the file, from a single pass over the year column."""
    column, _ = pyreadstat.read_sav(path, usecols=[year_column])
    years = pd.to_numeric(column[year_column], errors='coerce').dropna().astype('int64').unique()
    return sorted(int(year) for year in years)


# ============================================================
# STEP 1: ACCUMULATION IN BLOCKS
# ============================================================

def _weights(chunk, column):
    # Without a weight column, every interview counts as one
    if column is None or column not in chunk.columns:
        return np.ones(len(chunk))
    return pd.to_numeric(chunk[column], errors='coerce').fillna(0).to_numpy(dtype='float64')


def tabulate_chunk(chunk, variables, columns, selected_years):
    """Reduce one block of rows to its weighted sums.

    columns says which column is the wave and which are the weights (see
    default_columns). Returns (rows per year, online weight per year, cells),
    where cells[variable][(value, year)] = [weighted sum, online weighted sum].
    """
    if columns['year']:
        years = pd.to_numeric(chunk[columns['year']], errors='coerce').fillna(0).to_numpy(dtype='int64')
        if selected_years and selected_years != [0]:
            keep = np.isin(years, selected_years)
            chunk, years = chunk[keep], years[keep]
    else:
        years = np.zeros(len(chunk), dtype='int64')

    if not len(chunk):
        return {}, {}, {}

    weight = _weights(chunk, columns['weight'])
    online_weight = _weights(chunk, columns['online_weight'])

    year_codes, year_values = pd.factorize(years, sort=True)
    year_values = [int(year) for year in year_values]
    n_years = len(year_values)

    rows_per_year = dict(zip(year_values, np.bincount(year_codes, minlength=n_years).tolist()))
    online_per_year = dict(zip(year_values, np.bincount(year_codes, weights=online_weight, minlength=n_years).tolist()))

    cells = {}
    for variable in variables:
        # Every (category, year) pair becomes one integer, so that a block is
        # reduced with three bincounts instead of a group-by per variable.
        codes, categories = pd.factorize(chunk[variable].to_numpy())
        valid = codes >= 0          # missing values get the code -1
        if valid.all():
            keys, w, wo = codes * n_years + year_codes, weight, online_weight
        else:
            keys, w, wo = codes[valid] * n_years + year_codes[valid], weight[valid], online_weight[valid]

        size = len(categories) * n_years
        present = np.bincount(keys, minlength=size)
        sums = np.bincount(keys, weights=w, minlength=size)
        online_sums = np.bincount(keys, weights=wo, minlength=size)

        table = {}
        for idx in np.flatnonzero(present).tolist():
            value = categories[idx // n_years]
            if isinstance(value, np.generic):
                value = value.item()
            table[(value, year_values[idx % n_years])] = [float(sums[idx]), float(online_sums[idx])]
        cells[variable] = table

    return rows_per_year, online_per_year, cells


def _read_chunk(path, offset, limit, columns):
    chunk, _ = pyreadstat.read_sav(path, row_offset=offset, row_limit=limit, usecols=columns, user_missing=True)
    return chunk


def _process_block(task):
    """Entry point of the worker processes: read one block and reduce it."""
    path, offset, limit, usecols, variables, columns, selected_years = task
    chunk = _read_chunk(path, offset, limit, usecols)
    return tabulate_chunk(chunk, variables, columns, selected_years)


def default_workers(n_rows, chunk_size):
    """How many processes are worth starting for a file of this size."""
    if not n_rows or n_rows < PARALLEL_MIN_ROWS:
        return 1
    n_chunks = math.ceil(n_rows / chunk_size)
    return max(1, min(MAX_WORKERS, (os.cpu_count() or 2) // 2, n_chunks))


def accumulate(path, meta, variables, excluded_codes, selected_years,
               chunk_size=DEFAULT_CHUNK_SIZE, on_progress=None, workers=None, columns=None):
    """Read the file block by block and return the weighted sums of every table.

    excluded_codes are dropped from the tables altogether. selected_years limits
    a longitudinal file to those waves; it is ignored for a single-wave file.
    workers is the number of processes; by default it depends on the file size.
    columns names the wave and weight columns; by default, those of config.py.
    on_progress(stage, done, total, detail) is called after every block; it can
    raise Cancelled to stop the job.
    """
    if columns is None:
        columns = default_columns(meta.column_names)
    else:
        # An explicit choice is respected as it is, including "no such column"
        columns = {role: (columns.get(role) if columns.get(role) in meta.column_names else None)
                   for role in ('year', 'weight', 'online_weight')}
    usecols = [c for c in dict.fromkeys(list(variables) + list(columns.values())) if c in meta.column_names]

    n_rows = getattr(meta, 'number_rows', None)
    n_rows = n_rows if n_rows and n_rows > 0 else None
    if workers is None:
        workers = default_workers(n_rows, chunk_size)

    rows_per_year, online_weight_per_year = {}, {}
    cells = {variable: {} for variable in variables}

    def merge(result):
        block_rows, block_online, block_cells = result
        for year, count in block_rows.items():
            rows_per_year[year] = rows_per_year.get(year, 0) + count
        for year, weight in block_online.items():
            online_weight_per_year[year] = online_weight_per_year.get(year, 0.0) + weight
        for variable, table in block_cells.items():
            target = cells[variable]
            for key, (weight, online) in table.items():
                cell = target.get(key)
                if cell is None:
                    target[key] = [weight, online]
                else:
                    cell[0] += weight
                    cell[1] += online

    def report(done, total):
        if on_progress:
            on_progress('read', done, total, '')

    def read_sequentially():
        total = math.ceil(n_rows / chunk_size) if n_rows else None
        offset = done = 0
        while n_rows is None or offset < n_rows:
            chunk = _read_chunk(path, offset, chunk_size, usecols)
            if not len(chunk):
                break
            merge(tabulate_chunk(chunk, variables, columns, selected_years))
            del chunk
            offset += chunk_size
            done += 1
            report(done, total or done + 1)

    def read_in_parallel():
        tasks = [(path, offset, chunk_size, usecols, list(variables), columns, selected_years)
                 for offset in range(0, n_rows, chunk_size)]
        pool = ProcessPoolExecutor(max_workers=workers)
        try:
            futures = [pool.submit(_process_block, task) for task in tasks]
            for done, future in enumerate(as_completed(futures), start=1):
                merge(future.result())
                report(done, len(tasks))
        finally:
            # If the job is cancelled or fails, the blocks still waiting are
            # dropped; the workers finish the one they are on and exit, so that
            # none of them outlives the job.
            pool.shutdown(wait=True, cancel_futures=True)

    if workers > 1 and n_rows:
        try:
            read_in_parallel()
        except Cancelled:
            raise
        except Exception:
            # The workers could not start or one of them died (for instance, out
            # of memory): start again in this process, which only holds one
            # block at a time. A genuine error will simply show up again.
            rows_per_year.clear()
            online_weight_per_year.clear()
            for table in cells.values():
                table.clear()
            read_sequentially()
    else:
        read_sequentially()

    years = sorted(rows_per_year)
    if not years:
        raise ValueError("No valid years were found in the filtered data.")

    excluded = set()
    for code in excluded_codes:
        try:
            excluded.add(float(code))
        except (TypeError, ValueError):
            pass

    # sums[variable][((value, label), year)] = [weighted sum, online weighted sum]
    sums, online_only, filtered_weight = {}, {}, {}
    for variable in variables:
        labels = meta.variable_value_labels.get(variable, {})
        filter_codes = {value for value, label in labels.items() if is_filter_label(label)}
        table, routed = {}, {}
        online_only[variable] = False

        for (raw, year), (weight, online) in cells[variable].items():
            label = format_category(labels.get(raw, raw))
            try:
                value = float(raw)
            except (TypeError, ValueError):
                value = raw
            if value == ONLINE_ONLY_CODE:
                online_only[variable] = True
            if raw in filter_codes:
                # Weight of the respondents routed past the question
                acc = routed.setdefault(year, [0.0, 0.0])
                acc[0] += weight
                acc[1] += online
            if value in excluded:
                continue
            table[((value, label), year)] = [weight, online]

        sums[variable] = table
        filtered_weight[variable] = routed

    return {
        'years': years,
        'rows_per_year': rows_per_year,
        'online_weight_per_year': online_weight_per_year,
        'total_rows': sum(rows_per_year.values()),
        'sums': sums,
        'online_only': online_only,
        'filtered_weight': filtered_weight,
        'workers': workers,
    }


# ============================================================
# STEP 2: ROWS OF ONE TABLE
# ============================================================

def build_variable_rows(variable, data, labels=None):
    """Turn the accumulated sums of one variable into the rows of its table.

    Returns (categories, rows, base_values, base_label, filter_categories), where
    rows[category] = ({year: count}, total count) and base_values is the base of
    the total followed by the base of each year. labels are the output labels of
    the chosen language.
    """
    labels = labels or output_labels('en')
    years = data['years']
    sums = data['sums'][variable]
    is_online_only = data['online_only'][variable]
    weight_idx = 1 if is_online_only else 0
    base_label = labels['weighted_base_online'] if is_online_only else labels['weighted_base']

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
        base_label = f"{base_label}  ·  {labels['filtered_question']}"

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
