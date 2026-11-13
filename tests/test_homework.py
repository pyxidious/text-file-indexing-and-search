"""Test con aspettative esplicite; lo scanner non usa la ricerca come oracolo."""
import ast
from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from irhome.analyzers import ANALYZERS
from irhome.dataset import analyze, csv_rows, verify_corpus, write_csv
from irhome.engine import SearchEngine, parse_query
from irhome.evaluation import evaluate
from irhome.ground_truth import freeze, load_frozen, propose
from irhome.io import read_json
from irhome.metrics import macro_metrics, retrieval_metrics
from irhome.oracle import expression, inspect_text, scan_document

ROOT = Path(__file__).resolve().parents[1]


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.docs = self.root / "docs"
        self.docs.mkdir()
        for name, text in {"01_boundary_layer.TXT": "HEAT-transfer and pressure velocity. heat transfer",
                           "02_layer_boundary.txt": "heat slow transfer pressure",
                           "03_pressure.txt": "velocity temperature",
                           "ignored.md": "heat transfer"}.items():
            (self.docs / name).write_text(text, encoding="utf-8")
        self.engine = SearchEngine.build(self.docs)

    def ids(self, query, **kwargs):
        return {r["id"] for r in self.engine.search(query, **kwargs)}

    def test_count_persistence_and_fresh_build(self):
        self.assertEqual(len(self.engine.documents), 3)
        self.engine.save(self.root / "index.json")
        self.assertEqual(SearchEngine.load(self.root / "index.json").search("contenuto heat"),
                         self.engine.search("contenuto heat"))
        self.assertEqual(len(SearchEngine.build(self.docs).documents), 3)

    def test_analyzers_and_case(self):
        self.assertEqual(ANALYZERS["nome"]("X/01_BOUNDARY-layer.TXT"), ["01", "boundary", "layer"])
        self.assertEqual(ANALYZERS["contenuto"]("HEAT_transfer, cafe\u0301"), ["heat", "transfer", "caf\u00e9"])
        self.assertEqual(self.ids("contenuto HEAT"), self.ids("contenuto heat"))

    def test_field_single_and_and(self):
        self.assertEqual(self.ids("nome pressure"), {"03_pressure.txt"})
        self.assertEqual(self.ids("contenuto pressure velocity"), {"01_boundary_layer.TXT"})
        self.assertEqual(self.ids("nome boundary layer"), {"01_boundary_layer.TXT", "02_layer_boundary.txt"})
        self.assertEqual(self.ids("contenuto heat absentword"), set())
        self.assertEqual(self.ids("contenuto heat heat"), self.ids("contenuto heat"))
        self.assertEqual(self.ids("contenuto and"), {"01_boundary_layer.TXT"})

    def test_phrase_order_and_separators(self):
        self.assertEqual(self.ids('contenuto "heat transfer"'), {"01_boundary_layer.TXT"})
        self.assertEqual(self.ids('contenuto "transfer heat"'), set())
        self.assertEqual(self.ids('nome "boundary layer"'), {"01_boundary_layer.TXT"})
        self.assertEqual(self.ids('nome "layer boundary"'), {"02_layer_boundary.txt"})
        self.assertEqual(self.ids('contenuto "heat heat"'), set())

    def test_explicit_legacy_or(self):
        self.assertEqual(self.ids("contenuto pressure velocity", strategy="or"), set(self.engine.documents))

    def test_invalid_and_empty_queries(self):
        for query in ("", "titolo heat", "nome", 'contenuto "heat', 'nome x "y"', 'nome ""', "nome ___"):
            with self.subTest(query=query), self.assertRaises(ValueError):
                parse_query(query)
        self.assertEqual(self.ids("contenuto no_such_token"), set())
        with self.assertRaises(ValueError):
            SearchEngine.build(self.root / "missing")


class ScannerTests(unittest.TestCase):
    def test_hand_labels_without_engine(self):
        self.assertEqual(inspect_text("HEAT-transfer", ["heat", "transfer"], True)[0], 1)
        self.assertEqual(inspect_text("heat\ntransfer", ["heat", "transfer"], True)[0], 1)
        self.assertEqual(inspect_text("transfer heat", ["heat", "transfer"], True)[0], 0)
        self.assertEqual(inspect_text("heat and transfer", ["heat", "transfer"], True)[0], 0)
        self.assertEqual(inspect_text("heat and transfer", ["heat", "transfer"], False)[0], 1)
        self.assertEqual(inspect_text("heating transfers", ["heat", "transfer"], False)[0], 0)
        self.assertEqual(inspect_text("caf\u00e9", ["caf\u00e9"], False)[0], 1)
        label, excerpt, present = inspect_text("heat only", ["heat", "transfer"], False)
        self.assertEqual((label, present), (0, "heat"))
        self.assertIn("heat", excerpt)

    def test_source_imports_independent(self):
        for name in ("oracle.py", "ground_truth.py", "dataset.py"):
            tree = ast.parse((ROOT / "irhome" / name).read_text(encoding="utf-8"))
            imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
            self.assertFalse(any(module in ("engine", "analyzers", "evaluation", "metrics") for module in imports))

    def test_expression_validation(self):
        self.assertEqual(expression('"heat transfer"', "phrase"), ["heat", "transfer"])
        for text, kind in (("heat", "and"), ('"heat"', "single"), ("heat", "phrase"), ("", "single")):
            with self.assertRaises(ValueError):
                expression(text, kind)


class MetricTests(unittest.TestCase):
    def test_hand_calculation(self):
        m = retrieval_metrics(["a", "b", "x"], {"a", "b", "c", "d"})
        self.assertEqual((m["tp"], m["fp"], m["fn"]), (2, 1, 2))
        self.assertAlmostEqual(m["precision"], 2 / 3)
        self.assertEqual(m["recall"], .5)
        self.assertAlmostEqual(m["f1"], 4 / 7)
        self.assertEqual(m["precision_at_10"], .2)
        self.assertEqual(m["recall_at_10"], .5)

    def test_zero_and_undefined(self):
        m = retrieval_metrics([], {"a"})
        self.assertIsNone(m["precision"])
        self.assertEqual((m["recall"], m["f1"]), (0, 0))
        for ranking in ([], ["x"]):
            m = retrieval_metrics(ranking, set())
            self.assertIsNone(m["recall"])
            self.assertIsNone(m["f1"])
        self.assertEqual(retrieval_metrics(["x"], set())["precision"], 0)
        with self.assertRaises(ValueError):
            retrieval_metrics(["x", "x"], {"x"})

    def test_macro_excludes_only_undefined_values(self):
        rows = [retrieval_metrics([], set()), retrieval_metrics(["a"], {"a"})]
        m = macro_metrics(rows)
        self.assertEqual(m["precision"], 1)
        self.assertEqual(m["recall"], 1)
        self.assertEqual(m["precision_defined_queries"], 1)
        self.assertEqual(m["precision_at_10_defined_queries"], 2)
        self.assertEqual(m["precision_at_10"], .05)

    def test_no_top10_truncation(self):
        ids = [str(i) for i in range(25)]
        m = retrieval_metrics(ids, set(ids))
        self.assertEqual((m["tp"], m["fn"], m["recall"]), (25, 0, 1))
        self.assertEqual(m["recall_at_10"], .4)


class GroundTruthWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.docs = self.root / "docs"
        self.docs.mkdir()
        for i in range(25):
            (self.docs / f"{i:02d}_heat.txt").write_text("HEAT-transfer", encoding="utf-8")
        self.queries = self.root / "queries.csv"
        rows = [dict(query_id=f"Q{i:02d}", field="contenuto", expression="heat" if i < 10 else "absent",
                     type="single", expected_match="Fixture") for i in range(1, 11)]
        write_csv(self.queries, rows, list(rows[0]))
        self.output = self.root / "truth"

    def propose(self):
        with patch.object(SearchEngine, "build", side_effect=AssertionError("Scanner must not build index")), \
             patch.object(SearchEngine, "search", side_effect=AssertionError("Scanner must not search")):
            return propose(self.docs, self.queries, self.output)

    def review(self):
        path = self.output / "review.csv"
        rows = csv_rows(path)
        for row in rows:
            row["reviewed"] = "1"  # Test fixture only; no actual human review asserted.
        write_csv(path, rows, list(rows[0]))

    def freeze(self):
        return freeze(self.docs, self.queries, self.output,
                      reviewer="unit-test fixture", approval_note="Synthetic test only")

    def test_exhaustive_independent_proposals_and_pending_gate(self):
        report = self.propose()
        self.assertEqual(report["checks"], 250)
        self.assertEqual(report["positives"]["Q01"], 25)
        self.assertEqual(report["positives"]["Q10"], 0)
        self.assertFalse((self.output / "final_positives.csv").exists())
        with patch.object(SearchEngine, "build", side_effect=AssertionError("Premature search")):
            with self.assertRaisesRegex(ValueError, "non validata"):
                evaluate(self.docs, self.queries, self.output, self.root / "results")
        with self.assertRaisesRegex(ValueError, "revisionata"):
            self.freeze()

    def test_review_preserved_and_freeze_then_complete_evaluation(self):
        self.propose()
        self.review()
        reviewed = (self.output / "review.csv").read_bytes()
        self.propose()
        self.assertEqual((self.output / "review.csv").read_bytes(), reviewed)
        self.freeze()
        with redirect_stdout(io.StringIO()):
            rows, macro = evaluate(self.docs, self.queries, self.output, self.root / "results")
        self.assertEqual((rows[0]["tp"], rows[0]["recall"], rows[0]["recall_at_10"]), (25, 1, .4))
        self.assertEqual(len(csv_rows(self.root / "results/results.csv")), 225)
        self.assertIsNone(rows[-1]["recall"])
        with self.assertRaises(ValueError):
            self.propose()
        with self.assertRaises(ValueError):
            self.freeze()
        (self.docs / "00_heat.txt").write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "modificati"):
            load_frozen(self.docs, self.queries, self.output)

    def test_manual_correction_requires_reason(self):
        self.propose()
        self.review()
        path = self.output / "review.csv"
        rows = csv_rows(path)
        rows[0]["manual_label"] = "0"
        write_csv(path, rows, list(rows[0]))
        with self.assertRaisesRegex(ValueError, "motivazione"):
            self.freeze()
        rows[0]["reason"] = "Synthetic correction for workflow test"
        write_csv(path, rows, list(rows[0]))
        self.freeze()
        self.assertEqual(len(load_frozen(self.docs, self.queries, self.output)["Q01"]), 24)

    def test_duplicate_or_missing_review_rejected(self):
        self.propose()
        self.review()
        path = self.output / "review.csv"
        rows = csv_rows(path)
        write_csv(path, rows[:-1], list(rows[0]))
        with self.assertRaisesRegex(ValueError, "incompleta"):
            self.freeze()
        write_csv(path, rows + rows[:1], list(rows[0]))
        with self.assertRaisesRegex(ValueError, "duplicata"):
            self.freeze()

    def test_query_tampering_rejected(self):
        self.propose()
        self.review()
        self.queries.write_bytes(self.queries.read_bytes().replace(b"Fixture", b"Changed"))
        with self.assertRaisesRegex(ValueError, "Input"):
            self.freeze()


class CorpusTests(unittest.TestCase):
    def test_frozen_documents_and_analysis(self):
        entries = verify_corpus(ROOT / "corpus/documents", ROOT / "corpus/metadata.csv")
        self.assertEqual(len(entries), 300)
        self.assertEqual(sum(int(e["size_bytes"]) for e in entries), 309724)

    def test_actual_scanner_all_pairs_without_engine(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(SearchEngine, "build", side_effect=AssertionError("No index")):
            report = propose(ROOT / "corpus/documents", ROOT / "evaluation/queries.csv", tmp)
            self.assertEqual(report["checks"], 3000)
            self.assertEqual(len(csv_rows(Path(tmp) / "review.csv")), 3000)
            self.assertTrue(all(count > 0 for count in report["positives"].values()))


if __name__ == "__main__":
    unittest.main()
