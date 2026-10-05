"""Data conventions and output labels.

Everything that depends on how a particular survey file is laid out lives here,
so the tool can be pointed at another file layout (or another language) without
touching the tabulation code.
"""

# Rows read from the .sav file per block. Memory use grows with this value,
# not with the size of the file.
DEFAULT_CHUNK_SIZE = 50_000

# Column that holds the wave of each interview. A file that has it is treated
# as longitudinal and gets one column per year; a file without it is tabulated
# as a single block.
YEAR_COLUMN = 'YEAR'

# Weighting coefficients: the general one, and the one that only applies to
# interviews answered online.
WEIGHT_COLUMN = 'WEIGHT'
ONLINE_WEIGHT_COLUMN = 'WEIGHT_ONLINE'

# A variable that contains this code was only asked in online interviews, so it
# is tabulated with the online weight and the online base.
ONLINE_ONLY_CODE = 4444

# Value labels containing any of these words mark respondents who were routed
# past the question. They are subtracted from the base of that question.
FILTER_KEYWORDS = ['filter', 'filtre', 'filtro']

# Codes reserved for non-substantive answers (don't know, no answer, not
# asked...). They are listed at the bottom of each table, get no percentage and
# can be included or excluded one by one from the settings tab.
SPECIAL_CODES = [-8888, -7777, -3333, -1111, 1111, 2222, 3333, 4444, 5555, 6666, 7777, 8888, 9999]

# A variable with at least this many categories numbered between 0 and 10 is
# treated as a rating scale and gets a mean and a standard deviation.
SCALE_MIN_CATEGORIES = 5

DECIMAL_SEPARATOR = '.'

LABELS = {
    'sheet_frequencies': 'Frequencies',
    'sheet_percentages': 'Column %',
    'total': 'Total',
    'year': 'Year',
    'data': 'Data',
    'counts': 'Counts',
    'percentages': 'Column %',
    'total_base': 'TOTAL base',
    'weighted_base': 'Weighted base: Total',
    'weighted_base_online': 'Weighted base: Online',
    'filtered_question': 'Filtered question',
    'mean': 'Mean',
    'std_dev': 'Std. deviation',
    'pdf_frequency': 'Frequency',
    'pdf_percent': 'Percent',
    'pdf_cumulative': 'Cumulative %',
    'pdf_count': 'N',
    'pdf_title': 'Statistical tables',
}
