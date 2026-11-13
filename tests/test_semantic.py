"""Aspettative sintetiche fissate a priori; nessun giudizio sul corpus reale."""
from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from irhome.dataset import csv_rows, write_csv
from irhome.engine import SearchEngine
from irhome.evaluation import evaluate
from irhome.io import sha256
from irhome.semantic import (prepare, annotate, checked_rows, freeze, load_frozen,
                             progress, STATUS)


class SemanticTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.docs = self.root / "docs"
        self.docs.mkdir()
        metadata = []
        for i in range(12):
            name = f"{i:02d}_study.txt"
            p = self.docs / name
            p.write_text("heat" if i < 11 else "thermal energy exchange by convection", encoding="utf-8")
            metadata.append(dict(doc_id=str(i), filename=name, title=f"Study {i}",
                                 sha256=sha256(p), size_bytes=p.stat().st_size))
        self.metadata = self.root / "metadata.csv"
        write_csv(self.metadata, metadata, list(metadata[0]))
        self.queries = self.root / "queries.csv"
        queries = [dict(query_id=f"Q{i:02d}", field="contenuto", expression="heat", type="single")
                   for i in range(1, 11)]
        write_csv(self.queries, queries, list(queries[0]))
        self.out = self.root / "semantic"
        criteria = [dict(query_id=q["query_id"], field=q["field"], expression=q["expression"],
                         information_need="Thermal exchange", relevant="Studies thermal exchange",
                         not_relevant="Incidental mention") for q in queries]
        write_csv(self.out / "criteria.csv", criteria, list(criteria[0]))
        self.params = dict(documents=self.docs, queries=self.queries, output=self.out,
                           metadata=self.metadata, expected_documents=12)
        prepare(**self.params)

    def rows(self):
        return csv_rows(self.out / "annotations.csv")

    def save(self, rows):
        write_csv(self.out / "annotations.csv", rows, list(rows[0]))

    def complete(self):
        rows = self.rows()
        for i, r in enumerate(rows):
            for k in list(r)[3:]:
                # A priori fixture: first document only mentions heat; last is a synonym FN.
                r[k] = "0" if i == 0 else "1"
        self.save(rows)

    def freeze(self):
        return freeze(**self.params, reviewer="synthetic fixture", approval_note="Test only")

    def evaluate(self, output):
        with redirect_stdout(io.StringIO()):
            return evaluate(self.docs, self.queries, self.out, output, self.metadata,
                            expected_documents=12)

    def test_prepare_is_blank_independent_and_preserves_edits(self):
        with patch.object(SearchEngine, "build", side_effect=AssertionError("No search")):
            entries, qs, _, _ = prepare(**self.params)
        self.assertEqual(progress(self.rows(), qs), dict(total=120, complete=0, missing=120, doubtful=0))
        rows = self.rows()
        rows[0].update(Q01="1", Q02="0", Q03="?", Q04="")
        self.save(rows)
        previous = (self.out / "annotations.csv").read_bytes()
        prepare(**self.params)
        self.assertEqual((self.out / "annotations.csv").read_bytes(), previous)
        self.assertEqual(progress(rows, qs)["doubtful"], 1)
        rows[0]["Q01"] = "2"
        self.save(rows)
        with self.assertRaisesRegex(ValueError, "Etichetta"):
            prepare(**self.params)

    def test_console_save_resume_edit_and_title_display(self):
        answers = iter(["10?_______", "q"])
        displayed = []
        annotate(**self.params, input_fn=lambda _: next(answers), print_fn=displayed.append)
        self.assertEqual([self.rows()[0][f"Q{i:02d}"] for i in range(1, 5)], ["1", "0", "?", ""])
        self.assertTrue(any("Titolo: Study 0" in s for s in displayed))
        displayed.clear()
        answers = iter(["g 1", "0000000000", "q"])
        annotate(**self.params, input_fn=lambda _: next(answers), print_fn=displayed.append)
        self.assertTrue(any("Documento 1/12" in s for s in displayed))
        self.assertEqual(self.rows()[0]["Q01"], "0")
        self.assertEqual(self.rows()[0]["Q03"], "0")
        # Complete first row: next invocation resumes at document two.
        displayed.clear()
        annotate(**self.params, input_fn=lambda _: "q", print_fn=displayed.append)
        self.assertTrue(any("Documento 2/12" in s for s in displayed))

    def test_incomplete_doubtful_and_premature_evaluation_rejected(self):
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.freeze()
        self.complete()
        rows = self.rows()
        rows[-1]["Q10"] = "?"
        self.save(rows)
        with self.assertRaisesRegex(ValueError, "dubbi"):
            self.freeze()
        with patch.object(SearchEngine, "build", side_effect=AssertionError("Premature search")):
            with self.assertRaisesRegex(ValueError, "non congelata"):
                self.evaluate(self.root / "results")
        self.assertFalse((self.root / "results").exists())

    def test_freeze_and_semantic_false_negative_reproducibility(self):
        self.complete()
        self.assertEqual(self.freeze()["status"], STATUS)
        rows, macro = self.evaluate(self.root / "results")
        for r in rows:
            self.assertEqual((r["tp"], r["fp"], r["fn"]), (10, 1, 1))
            self.assertAlmostEqual(r["precision"], 10/11)
            self.assertAlmostEqual(r["recall"], 10/11)
            self.assertAlmostEqual(r["f1"], 10/11)
            self.assertAlmostEqual(r["precision_at_10"], .9)
            self.assertAlmostEqual(r["recall_at_10"], 9/11)
        self.assertEqual(len(csv_rows(self.root / "results/results.csv")), 110)
        errors = csv_rows(self.root / "results/errors.csv")
        self.assertIn(dict(query_id="Q01", error="FN", doc_id="11_study.txt"), errors)
        self.assertIn(dict(query_id="Q01", error="FP", doc_id="00_study.txt"), errors)
        self.assertEqual(macro["recall_defined_queries"], 10)
        self.assertEqual(self.evaluate(self.root / "again"), (rows, macro))
        for p in (self.root / "results").iterdir():
            self.assertEqual(p.read_bytes(), (self.root / "again" / p.name).read_bytes())
        with self.assertRaises(ValueError):
            self.freeze()
        with self.assertRaises(ValueError):
            annotate(**self.params, input_fn=lambda _: "q")

    def test_tampering_detected_for_every_input_and_frozen_file(self):
        self.complete()
        self.freeze()
        paths = [self.docs / "00_study.txt", self.queries, self.metadata,
                 self.out / "criteria.csv", self.out / "annotations.csv",
                 self.out / "prepared.json", self.out / "final_positives.csv",
                 self.out / "positives_Q01.csv"]
        for path in paths:
            with self.subTest(path=path.name):
                original = path.read_bytes()
                path.write_bytes(original + b"\n")
                try:
                    with self.assertRaises(ValueError):
                        load_frozen(**self.params)
                finally:
                    path.write_bytes(original)
        self.assertEqual(len(load_frozen(**self.params)["Q01"]), 11)

    def test_matrix_identity_count_and_duplicates(self):
        rows = self.rows()
        for changed in (rows[:-1], rows + rows[:1], [dict(rows[0], title="Altered")] + rows[1:]):
            self.save(changed)
            with self.assertRaises(ValueError):
                prepare(**self.params)
        self.save(rows)
        params = dict(self.params, expected_documents=300)
        with self.assertRaisesRegex(ValueError, "300"):
            prepare(**params)
        self.queries.write_bytes(self.queries.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "Input modificati"):
            prepare(**self.params)


if __name__ == "__main__":
    unittest.main()
