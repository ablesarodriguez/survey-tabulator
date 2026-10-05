"""Checks of the tabulation against tables worked out by hand.

    python -m unittest discover tests
"""

import os
import string
import sys
import tempfile
import unittest
from unittest import mock

import pandas as pd
import pyreadstat

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools'))

from excel_export import write_excel
import i18n
from i18n import LANGUAGES, OUTPUT, UI, output_labels
from make_sample_data import build, build_library
from pdf_export import write_pdf
from tabulation import Cancelled, accumulate, build_variable_rows, compute_scale_statistics

# Eight interviews in two waves. Interviews 4 and 8 were done by telephone.
ROWS = pd.DataFrame({
    'YEAR':          [2024, 2024, 2024, 2024, 2025, 2025, 2025, 2025],
    'WEIGHT':        [1.5,  0.5,  1.0,  1.0,  2.0,  1.0,  0.5,  0.5],
    'WEIGHT_ONLINE': [1.0,  1.0,  1.0,  0.0,  1.5,  1.0,  0.5,  0.0],
    'ANSWER':        [1,    2,    1,    9999, 2,    2,    1,    1],
    'OWNER':         [1,    1,    2,    2,    1,    2,    2,    1],
    'FUEL':          [1,    2,    7777, 7777, 1,    7777, 7777, 2],
    'DEVICE':        [1,    2,    1,    4444, 2,    2,    1,    4444],
    'SCORE':         [0,    2,    4,    6,    8,    10,   10,   8888],
}).astype('float64')

VALUE_LABELS = {
    'ANSWER': {1.0: 'Yes', 2.0: 'No', 9999.0: 'No answer'},
    'OWNER': {1.0: 'Yes', 2.0: 'No'},
    'FUEL': {1.0: 'Petrol', 2.0: 'Diesel', 7777.0: 'Not asked (filter)'},
    'DEVICE': {1.0: 'Phone', 2.0: 'Computer', 4444.0: 'Not asked (telephone interview)'},
    'SCORE': {8888.0: "Don't know"},
}


class TabulationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = os.path.join(cls.tmp.name, 'tiny.sav')
        pyreadstat.write_sav(ROWS, cls.path, variable_value_labels=VALUE_LABELS)
        _, cls.meta = pyreadstat.read_sav(cls.path, metadataonly=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def tabulate(self, variable, excluded=(), years=(2024, 2025), chunk_size=50_000):
        data = accumulate(self.path, self.meta, [variable], list(excluded), list(years), chunk_size=chunk_size)
        return data, build_variable_rows(variable, data)

    def test_weighted_counts_per_year(self):
        data, (categories, rows, bases, label, filters) = self.tabulate('OWNER')
        self.assertEqual(data['years'], [2024, 2025])
        self.assertEqual(categories, ['Yes', 'No'])
        self.assertEqual(rows['Yes'], ({2024: 2, 2025: 2}, 4))   # 1.5 + 0.5 | 2.0 + 0.5 (rounded half to even)
        self.assertEqual(rows['No'], ({2024: 2, 2025: 2}, 4))    # 1.0 + 1.0 | 1.0 + 0.5
        self.assertEqual(bases, [8, 4, 4])
        self.assertEqual(label, 'Weighted base: Total')
        self.assertEqual(filters, set())

    def test_special_codes_go_last_and_can_be_excluded(self):
        _, (categories, rows, _, _, filters) = self.tabulate('ANSWER')
        self.assertEqual(categories, ['Yes', 'No', 'No answer'])
        self.assertEqual(filters, {'No answer'})
        self.assertEqual(rows['No answer'], ({2024: 1, 2025: 0}, 1))

        _, (categories, _, _, _, _) = self.tabulate('ANSWER', excluded=[9999.0])
        self.assertEqual(categories, ['Yes', 'No'])

    def test_filtered_question_reduces_the_base(self):
        _, (categories, rows, bases, label, filters) = self.tabulate('FUEL', excluded=[7777.0])
        self.assertEqual(categories, ['Petrol', 'Diesel'])
        # Each wave has 4 interviews; the routed ones weigh 2.0 in 2024 and 1.5 in 2025
        self.assertEqual(bases, [4, 2, 2])
        self.assertIn('Filtered question', label)

    def test_online_only_question_uses_the_online_weight(self):
        _, (categories, rows, bases, label, _) = self.tabulate('DEVICE', excluded=[4444.0])
        self.assertEqual(categories, ['Phone', 'Computer'])
        self.assertEqual(rows['Phone'], ({2024: 2, 2025: 0}, 2))      # 1.0 + 1.0 | 0.5
        self.assertEqual(rows['Computer'], ({2024: 1, 2025: 2}, 4))   # 1.0 | 1.5 + 1.0
        self.assertEqual(bases, [6, 3, 3])
        self.assertTrue(label.startswith('Weighted base: Online'))

    def test_year_filter(self):
        data, (_, rows, bases, _, _) = self.tabulate('OWNER', years=[2025])
        self.assertEqual(data['years'], [2025])
        self.assertEqual(data['total_rows'], 4)
        self.assertEqual(bases, [4, 4])

    def test_result_does_not_depend_on_the_block_size(self):
        for variable in ('ANSWER', 'FUEL', 'DEVICE', 'SCORE'):
            _, whole = self.tabulate(variable)
            for chunk_size in (1, 3, 5):
                _, in_blocks = self.tabulate(variable, chunk_size=chunk_size)
                self.assertEqual(whole, in_blocks, f"{variable}, blocks of {chunk_size}")

    def test_result_does_not_depend_on_the_number_of_processes(self):
        for variable in ('ANSWER', 'FUEL', 'DEVICE', 'SCORE'):
            one = accumulate(self.path, self.meta, [variable], [], [2024, 2025], chunk_size=3, workers=1)
            two = accumulate(self.path, self.meta, [variable], [], [2024, 2025], chunk_size=3, workers=2)
            self.assertEqual(two['workers'], 2)
            self.assertEqual(build_variable_rows(variable, one), build_variable_rows(variable, two), variable)

    def test_a_job_can_be_cancelled_from_the_progress_callback(self):
        def stop(stage, done, total, detail):
            raise Cancelled()

        for workers in (1, 2):
            with self.assertRaises(Cancelled):
                accumulate(self.path, self.meta, ['ANSWER'], [], [2024, 2025], chunk_size=2,
                           on_progress=stop, workers=workers)

    def test_scale_statistics(self):
        data, (categories, rows, _, _, _) = self.tabulate('SCORE', excluded=[8888.0])
        stats = compute_scale_statistics(categories, rows, data['years'])
        # 2024: scores 0, 2, 4, 6 weighted 1.5, 0.5, 1, 1 -> counts 2, 0, 1, 1
        self.assertAlmostEqual(stats['mean'][2024], (0 * 2 + 4 + 6) / 4)
        self.assertAlmostEqual(stats['std_dev'][2024], (((2.5 ** 2) * 2 + 1.5 ** 2 + 3.5 ** 2) / 3) ** 0.5)

        _, (categories, rows, _, _, _) = self.tabulate('OWNER')
        self.assertIsNone(compute_scale_statistics(categories, rows, data['years']))


class LanguageTest(unittest.TestCase):
    def test_every_language_has_every_text(self):
        for texts in (UI, OUTPUT):
            for language in LANGUAGES:
                self.assertEqual(set(texts[language]), set(texts['en']), language)
        for language in LANGUAGES:
            for key, text in UI['en'].items():
                # The same placeholders, so that a translation can never break a message
                fields = lambda s: sorted(name for _, name, _, _ in string.Formatter().parse(s) if name)
                self.assertEqual(fields(UI[language][key]), fields(text), f"{language}: {key}")

    def test_the_choice_is_remembered(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {'APPDATA': tmp}):
            for language in LANGUAGES:
                i18n.save_language(language)
                self.assertEqual(i18n.load_language(), language)

    def test_documents_are_written_in_the_chosen_language(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'survey.sav')
            df, column_labels, value_labels = build(800)
            pyreadstat.write_sav(df, path, column_labels=column_labels, variable_value_labels=value_labels)
            _, meta = pyreadstat.read_sav(path, metadataonly=True)
            variables = ['SEX', 'CAR_FUEL', 'SAT_WEBSITE']
            data = accumulate(path, meta, variables, [8888.0, 9999.0, 7777.0, 4444.0], [2022, 2023, 2024, 2025])

            for language, sheet, base in (('en', 'Frequencies', 'Weighted base: Total'),
                                          ('ca', 'Freqüències', 'Base pond: Total'),
                                          ('es', 'Frecuencias', 'Base pond: Total')):
                excel = os.path.join(tmp, f'{language}.xlsx')
                write_excel(data, meta, variables, excel, True, show_stats=True, language=language)
                write_pdf(data, meta, variables, os.path.join(tmp, f'{language}.pdf'), True,
                          show_stats=True, language=language)
                sheets = pd.read_excel(excel, sheet_name=None, header=None)
                self.assertIn(sheet, sheets)
                self.assertIn(base, sheets[sheet][0].tolist())
                _, _, _, label, _ = build_variable_rows('CAR_FUEL', data, output_labels(language))
                self.assertIn(output_labels(language)['filtered_question'], label)


class SampleFileTest(unittest.TestCase):
    """End-to-end run on the synthetic survey, including both exporters."""

    def test_tabulate_and_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'survey.sav')
            df, column_labels, value_labels = build(3000)
            pyreadstat.write_sav(df, path, column_labels=column_labels, variable_value_labels=value_labels)
            _, meta = pyreadstat.read_sav(path, metadataonly=True)
            variables = [c for c in meta.column_names if c != 'ID']
            excluded = [8888.0, 9999.0, 7777.0, 4444.0]

            whole = accumulate(path, meta, variables, excluded, [2022, 2023, 2024, 2025])
            in_blocks = accumulate(path, meta, variables, excluded, [2022, 2023, 2024, 2025], chunk_size=400)
            self.assertEqual(whole['total_rows'], 3000)

            for variable in variables:
                table = build_variable_rows(variable, whole)
                self.assertEqual(table, build_variable_rows(variable, in_blocks), variable)

                # With the non-substantive answers left out, every column adds up to its base
                _, rows, bases, _, _ = table
                if variable in ('YEAR', 'MODE', 'SEX', 'AGE_GROUP', 'DISTRICT'):
                    self.assertAlmostEqual(sum(total for _, total in rows.values()), bases[0], delta=len(rows))

            for show_total in (True, False):
                write_excel(whole, meta, variables, os.path.join(tmp, 'out.xlsx'), show_total, show_stats=True)
                write_pdf(whole, meta, variables, os.path.join(tmp, 'out.pdf'), show_total, show_stats=True)
                self.assertGreater(os.path.getsize(os.path.join(tmp, 'out.xlsx')), 5000)
                self.assertGreater(os.path.getsize(os.path.join(tmp, 'out.pdf')), 5000)

            # Single-wave layout
            one_year = accumulate(path, meta, variables, excluded, [2025])
            write_pdf(one_year, meta, variables, os.path.join(tmp, 'single.pdf'), False, show_stats=True)
            write_excel(one_year, meta, variables, os.path.join(tmp, 'single.xlsx'), False, show_stats=True)

    def test_file_without_waves_or_weights(self):
        """A file with none of the expected columns is tabulated as one unweighted block."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'library.sav')
            df, column_labels, value_labels = build_library()
            pyreadstat.write_sav(df, path, column_labels=column_labels, variable_value_labels=value_labels)
            _, meta = pyreadstat.read_sav(path, metadataonly=True)
            variables = [c for c in meta.column_names if c != 'CARD']

            data = accumulate(path, meta, variables, [5555.0, -1111.0], [0], chunk_size=200)
            self.assertEqual(data['years'], [0])
            self.assertEqual(data['total_rows'], len(df))

            categories, rows, bases, _, _ = build_variable_rows('BRANCH', data)
            self.assertEqual(categories, ['Central', 'Station Road', 'Hillside', 'Mobile library'])
            for category, code in zip(categories, (1, 2, 3, 4)):
                self.assertEqual(rows[category][1], int((df['BRANCH'] == code).sum()))
            self.assertEqual(bases, [len(df), len(df)])

            categories, rows, _, _, _ = build_variable_rows('RATE_STAFF', data)
            self.assertIsNotNone(compute_scale_statistics(categories, rows, data['years']))

            write_excel(data, meta, variables, os.path.join(tmp, 'out.xlsx'), False, show_stats=True)
            write_pdf(data, meta, variables, os.path.join(tmp, 'out.pdf'), False, show_stats=True)


if __name__ == '__main__':
    unittest.main()
