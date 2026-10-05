"""Data conventions.

Everything that depends on how a particular survey file is laid out lives here,
so the tool can be pointed at another file layout without touching the
tabulation code. The texts shown on screen and printed in the documents are in
i18n.py.
"""

# Rows read from the .sav file per block. Memory use grows with this value,
# not with the size of the file.
DEFAULT_CHUNK_SIZE = 50_000

# Files with at least this many rows are split between several processes.
# Below it, starting the processes costs more than it saves.
PARALLEL_MIN_ROWS = 200_000

# Upper limit of worker processes. Each one holds a block in memory, so this
# also bounds the memory used; the actual number never exceeds half the logical
# processors of the machine.
MAX_WORKERS = 6

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
