"""Write a synthetic survey to an SPSS .sav file.

Every answer is drawn at random: the file only imitates the shape of a real
longitudinal survey (waves, weights, rating scales, filtered questions,
online-only questions and special codes), so that the application can be tried
and benchmarked without any real microdata.

    python tools/make_sample_data.py                       # data/sample_survey.sav, 6,000 rows
    python tools/make_sample_data.py --library             # data/sample_library.sav, a different layout
    python tools/make_sample_data.py --rows 2000000 --extra-variables 60 --out big.sav
"""

import argparse
import os

import numpy as np
import pandas as pd
import pyreadstat

DONT_KNOW = 8888
NO_ANSWER = 9999
NOT_ASKED_FILTER = 7777
NOT_ASKED_PHONE = 4444

YEARS = [2022, 2023, 2024, 2025]


def scale_labels(low, high, start=0):
    labels = {float(i): str(i) for i in range(start, 11)}
    labels[float(start)] = f"{start} {low}"
    labels[10.0] = f"10 {high}"
    labels[float(DONT_KNOW)] = "Don't know"
    labels[float(NO_ANSWER)] = "No answer"
    return labels


def choice_labels(*options, dont_know=True):
    labels = {float(i): text for i, text in enumerate(options, start=1)}
    if dont_know:
        labels[float(DONT_KNOW)] = "Don't know"
    labels[float(NO_ANSWER)] = "No answer"
    return labels


def build(rows, seed=7, extra_variables=0):
    rng = np.random.default_rng(seed)
    columns, col_labels, value_labels = {}, {}, {}

    def add(name, label, values, labels=None):
        columns[name] = values
        col_labels[name] = label
        if labels:
            value_labels[name] = labels

    def pick(options, p=None):
        return rng.choice(np.asarray(options, dtype='float64'), size=rows, p=p)

    def with_nonresponse(values, dk=0.03, na=0.02):
        draw = rng.random(rows)
        values = values.copy()
        values[draw < dk] = DONT_KNOW
        values[(draw >= dk) & (draw < dk + na)] = NO_ANSWER
        return values

    def scale(mean, start=0):
        # Each wave drifts a little, so the per-year columns are not identical
        drift = (year - YEARS[0]) * 0.18
        raw = rng.normal(mean + drift, 2.1, size=rows)
        return np.clip(np.rint(raw), start, 10)

    year = rng.choice(YEARS, size=rows, p=[0.22, 0.24, 0.26, 0.28]).astype('float64')
    # Online interviewing grows from wave to wave
    online = rng.random(rows) < (0.45 + (year - YEARS[0]) * 0.09)

    weight = rng.gamma(shape=9.0, scale=1 / 9.0, size=rows)
    online_weight = np.where(online, rng.gamma(shape=9.0, scale=1 / 9.0, size=rows), 0.0)
    # Weights are scaled to add up to the sample size of each wave
    for y in YEARS:
        in_year = year == y
        weight[in_year] *= in_year.sum() / weight[in_year].sum()
        in_year_online = in_year & online
        if in_year_online.any():
            online_weight[in_year_online] *= in_year_online.sum() / online_weight[in_year_online].sum()

    add('ID', 'Interview number', np.arange(1, rows + 1, dtype='float64'))
    add('YEAR', 'Year of the wave', year)
    add('WEIGHT', 'Weighting coefficient', weight)
    add('WEIGHT_ONLINE', 'Weighting coefficient (online interviews only)', online_weight)
    add('MODE', 'Interview mode', np.where(online, 1.0, 2.0), {1.0: 'Online', 2.0: 'Telephone'})

    add('SEX', 'Sex', pick([1, 2, 3], [0.48, 0.51, 0.01]),
        {1.0: 'Man', 2.0: 'Woman', 3.0: 'Non-binary'})
    age = np.clip(np.rint(rng.normal(47, 17, size=rows)), 16, 95)
    add('AGE', 'Age', age)
    add('AGE_GROUP', 'Age group', np.digitize(age, [25, 35, 50, 65]) + 1.0,
        {1.0: '16 to 24', 2.0: '25 to 34', 3.0: '35 to 49', 4.0: '50 to 64', 5.0: '65 and over'})
    add('DISTRICT', 'District of residence', pick([1, 2, 3, 4, 5, 6], [0.24, 0.19, 0.17, 0.15, 0.14, 0.11]),
        {1.0: 'Old Town', 2.0: 'Harbour', 3.0: 'Riverside', 4.0: 'North Hills', 5.0: 'Eastfield', 6.0: 'Westgate'})
    add('EDUCATION', 'Highest level of education completed',
        with_nonresponse(pick([1, 2, 3, 4], [0.12, 0.31, 0.27, 0.30]), dk=0, na=0.01),
        choice_labels('Primary or less', 'Secondary', 'Vocational training', 'University', dont_know=False))
    add('EMPLOYMENT', 'Employment status',
        with_nonresponse(pick([1, 2, 3, 4, 5], [0.55, 0.08, 0.22, 0.09, 0.06]), dk=0, na=0.01),
        choice_labels('Employed', 'Unemployed', 'Retired', 'Student', 'Other', dont_know=False))

    satisfaction = [
        ('SAT_TRANSPORT', 'Satisfaction with public transport', 6.1),
        ('SAT_HEALTH', 'Satisfaction with health centres', 6.6),
        ('SAT_SCHOOLS', 'Satisfaction with schools', 6.3),
        ('SAT_CLEANING', 'Satisfaction with street cleaning', 5.2),
        ('SAT_SAFETY', 'Satisfaction with public safety', 5.8),
        ('SAT_PARKS', 'Satisfaction with parks and green areas', 6.9),
    ]
    for name, label, mean in satisfaction:
        add(name, label + ' (0 to 10)', with_nonresponse(scale(mean)),
            scale_labels('Very dissatisfied', 'Very satisfied'))

    add('TRUST_COUNCIL', 'Trust in the city council (0 to 10)', with_nonresponse(scale(4.6), dk=0.05),
        scale_labels('No trust at all', 'Complete trust'))
    add('RECOMMEND', 'How likely are you to recommend living in the city? (1 to 10)',
        with_nonresponse(scale(7.2, start=1)), scale_labels('Not at all likely', 'Extremely likely', start=1))

    add('MAIN_TRANSPORT', 'Main means of transport on a working day',
        with_nonresponse(pick([1, 2, 3, 4, 5, 6], [0.29, 0.21, 0.12, 0.08, 0.26, 0.04]), dk=0, na=0.015),
        choice_labels('Private car', 'Bus', 'Metro or tram', 'Bicycle or scooter', 'On foot', 'Other', dont_know=False))

    owns_car = with_nonresponse(pick([1, 2], [0.62, 0.38]), dk=0, na=0.01)
    add('OWNS_CAR', 'Is there a car in the household?', owns_car, choice_labels('Yes', 'No', dont_know=False))
    # Only households with a car are asked what it runs on
    fuel = with_nonresponse(pick([1, 2, 3, 4], [0.41, 0.33, 0.17, 0.09]), dk=0.01, na=0.01)
    fuel[owns_car != 1] = NOT_ASKED_FILTER
    fuel_labels = choice_labels('Petrol', 'Diesel', 'Hybrid', 'Electric')
    fuel_labels[float(NOT_ASKED_FILTER)] = 'Not asked (filter)'
    add('CAR_FUEL', 'What does the main car of the household run on?', fuel, fuel_labels)

    add('RECYCLES', 'How often do you separate waste for recycling?',
        with_nonresponse(pick([1, 2, 3, 4], [0.46, 0.30, 0.16, 0.08])),
        choice_labels('Always', 'Often', 'Rarely', 'Never'))
    add('HOUSING', 'Housing tenure',
        with_nonresponse(pick([1, 2, 3, 4], [0.38, 0.29, 0.27, 0.06]), dk=0, na=0.02),
        choice_labels('Owned outright', 'Owned with a mortgage', 'Rented', 'Other', dont_know=False))
    add('MAIN_PROBLEM', 'Main problem of the city today',
        with_nonresponse(pick([1, 2, 3, 4, 5, 6, 7], [0.24, 0.17, 0.15, 0.13, 0.12, 0.11, 0.08]), dk=0.04),
        choice_labels('Housing prices', 'Traffic and parking', 'Cleanliness', 'Safety',
                      'Unemployment', 'Noise', 'Other'))

    # Questions that are only part of the online questionnaire
    def online_only(values, labels):
        values = values.copy()
        values[~online] = NOT_ASKED_PHONE
        labels = dict(labels)
        labels[float(NOT_ASKED_PHONE)] = 'Not asked (telephone interview)'
        return values, labels

    add('DEVICE', 'Device used to answer the questionnaire',
        *online_only(pick([1, 2, 3], [0.58, 0.34, 0.08]),
                     {1.0: 'Mobile phone', 2.0: 'Computer', 3.0: 'Tablet'}))
    add('APP_USE', 'Have you used the city services app in the last year?',
        *online_only(with_nonresponse(pick([1, 2], [0.37, 0.63])), choice_labels('Yes', 'No')))
    add('SAT_WEBSITE', 'Satisfaction with the city council website (0 to 10)',
        *online_only(with_nonresponse(scale(5.9)), scale_labels('Very dissatisfied', 'Very satisfied')))

    agreement = choice_labels('Strongly agree', 'Agree', 'Neither agree nor disagree', 'Disagree', 'Strongly disagree')
    for i in range(1, extra_variables + 1):
        add(f'ITEM_{i:03d}', f'Agreement with statement {i}',
            with_nonresponse(pick([1, 2, 3, 4, 5], [0.18, 0.31, 0.24, 0.18, 0.09])), agreement)

    return pd.DataFrame(columns), col_labels, value_labels


def build_library(rows=1500, seed=11):
    """A second, unrelated file: one wave, no weights and a different set of codes.

    It is there to show that nothing in the application is tied to one
    questionnaire: the same window adapts to whatever the dictionary declares.
    """
    rng = np.random.default_rng(seed)
    columns, col_labels, value_labels = {}, {}, {}
    not_applicable, refused = 5555.0, -1111.0

    def add(name, label, options, p, extra=None, scale=False):
        values = rng.choice(np.arange(len(p), dtype='float64') + (0 if scale else 1), size=rows, p=p)
        labels = dict(options)
        for code, text, share in (extra or []):
            values[rng.random(rows) < share] = code
            labels[code] = text
        columns[name], col_labels[name], value_labels[name] = values, label, labels

    def options(*texts):
        return {float(i): text for i, text in enumerate(texts, start=1)}

    columns['CARD'] = np.arange(1, rows + 1, dtype='float64')
    col_labels['CARD'] = 'Library card number (anonymised)'

    add('BRANCH', 'Branch visited most often',
        options('Central', 'Station Road', 'Hillside', 'Mobile library'), [0.46, 0.27, 0.19, 0.08])
    add('VISITS', 'Visits in the last three months',
        options('None', '1 to 3', '4 to 10', 'More than 10'), [0.14, 0.41, 0.31, 0.14],
        extra=[(refused, 'Prefers not to say', 0.03)])
    add('MEMBER_SINCE', 'Member since',
        options('Less than a year', '1 to 5 years', 'More than 5 years'), [0.21, 0.37, 0.42])
    add('MAIN_USE', 'Main reason for the visit',
        options('Borrowing books', 'Studying', 'Computers and wifi', 'Activities for children', 'Other'),
        [0.44, 0.23, 0.14, 0.13, 0.06], extra=[(refused, 'Prefers not to say', 0.02)])
    add('EBOOKS', 'Uses the e-book lending platform', options('Yes', 'No'), [0.31, 0.69])
    for name, label, mean in (('RATE_STAFF', 'Rating of the staff', 8.1),
                              ('RATE_CATALOGUE', 'Rating of the catalogue', 6.7),
                              ('RATE_HOURS', 'Rating of the opening hours', 5.9)):
        weights = np.exp(-0.5 * ((np.arange(11) - mean) / 1.9) ** 2)
        labels = {float(i): str(i) for i in range(11)}
        labels[0.0], labels[10.0] = '0 Very poor', '10 Excellent'
        add(name, label + ' (0 to 10)', labels, weights / weights.sum(), scale=True,
            extra=[(not_applicable, 'Not applicable', 0.06), (refused, 'Prefers not to say', 0.02)])

    return pd.DataFrame(columns), col_labels, value_labels


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--library', action='store_true',
                        help='write the second sample instead: a single-wave, unweighted library survey')
    parser.add_argument('--rows', type=int, default=6000)
    parser.add_argument('--extra-variables', type=int, default=0, help='additional agreement items, to widen the file')
    parser.add_argument('--seed', type=int, default=7)
    parser.add_argument('--out', default=os.path.join(os.path.dirname(__file__), '..', 'data', 'sample_survey.sav'))
    args = parser.parse_args()

    if args.library:
        df, col_labels, value_labels = build_library()
        if args.out == parser.get_default('out'):
            args.out = os.path.join(os.path.dirname(args.out), 'sample_library.sav')
    else:
        df, col_labels, value_labels = build(args.rows, args.seed, args.extra_variables)
    out = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    pyreadstat.write_sav(df, out, file_label='Synthetic survey',
                         column_labels=col_labels, variable_value_labels=value_labels, compress=True)
    print(f"{out}: {len(df):,} rows, {df.shape[1]} variables, {os.path.getsize(out) / 1e6:.1f} MB")


if __name__ == '__main__':
    main()
