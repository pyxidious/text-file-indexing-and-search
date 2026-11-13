"""OR esplicito: unione dei posting, BM25 invariato e frasi posizionali."""
from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from irhome.dataset import csv_rows, write_csv
from irhome.engine import SearchEngine
from irhome.evaluation import evaluate
from irhome.io import sha256, read_json
from irhome.semantic import prepare, freeze
from scripts.compare_matching import compare


class OrEngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.docs = self.root / "docs"
        self.docs.mkdir()
        for name, text in {"01_alpha_beta.txt": "alpha beta beta", "02_alpha.txt": "alpha",
                           "03_beta.txt": "beta", "04_beta_alpha.txt": "beta alpha"}.items():
            (self.docs / name).write_text(text, encoding="utf-8")
        self.engine = SearchEngine.build(self.docs)

    def ids(self, query, strategy="or"):
        return {r["id"] for r in self.engine.search(query, strategy=strategy)}

    def test_union_in_both_fields_and_and_default(self):
        expected = {"01_alpha_beta.txt", "02_alpha.txt", "03_beta.txt", "04_beta_alpha.txt"}
        for field in ("nome", "contenuto"):
            query = field + " alpha beta"
            self.assertEqual(self.ids(query), expected)
            self.assertEqual({r["id"] for r in self.engine.search(query)},
                             {"01_alpha_beta.txt", "04_beta_alpha.txt"})
            self.assertEqual(self.engine.search(query), self.engine.search(query, strategy="and"))

    def test_absent_terms_and_single_term(self):
        self.assertEqual(self.ids("contenuto absent alpha"), {"01_alpha_beta.txt", "02_alpha.txt", "04_beta_alpha.txt"})
        self.assertEqual(self.ids("contenuto alpha absent"), self.ids("contenuto absent alpha"))
        self.assertEqual(self.ids("contenuto missing absent"), set())
        self.assertEqual(self.engine.search("contenuto alpha", "or"), self.engine.search("contenuto alpha", "and"))

    def test_phrase_order_adjacency_and_missing_term_unchanged(self):
        for field in ("nome", "contenuto"):
            for phrase in ('"alpha beta"', '"beta alpha"', '"alpha absent"', '"beta beta"'):
                query = field + " " + phrase
                self.assertEqual(self.engine.search(query, "or"), self.engine.search(query, "and"))
        self.assertEqual(self.ids('contenuto "alpha beta"'), {"01_alpha_beta.txt"})
        self.assertEqual(self.ids('contenuto "beta alpha"'), {"04_beta_alpha.txt"})

    def test_bm25_shared_scores_order_and_index_unchanged(self):
        self.engine.save(self.root / "before.json")
        left = {r["id"]: r["score"] for r in self.engine.search("contenuto alpha beta")}
        right = self.engine.search("contenuto alpha beta", "or")
        self.assertTrue(all(left[r["id"]] == r["score"] for r in right if r["id"] in left))
        self.assertEqual(right, sorted(right, key=lambda r: (-r["score"], r["id"])))
        self.engine.save(self.root / "after.json")
        self.assertEqual(sha256(self.root / "before.json"), sha256(self.root / "after.json"))


class OrEvaluationTests(unittest.TestCase):
    def setUp(self):
        OrEngineTests.setUp(self)
        self.queries = self.root / "queries.csv"
        qs = [dict(query_id=f"Q{i:02d}", field="contenuto", expression="alpha beta" if i <= 7 else '\"alpha beta\"',
                   type="and" if i <= 7 else "phrase") for i in range(1, 11)]
        write_csv(self.queries, qs, list(qs[0]))
        self.metadata = self.root / "metadata.csv"
        metadata = [dict(doc_id=p.stem[:2], filename=p.name, title=p.stem, sha256=sha256(p), size_bytes=p.stat().st_size)
                    for p in sorted(self.docs.iterdir())]
        write_csv(self.metadata, metadata, list(metadata[0]))
        self.truth = self.root / "truth"
        criteria = [dict(query_id=q["query_id"], field=q["field"], expression=q["expression"],
                         information_need="Synthetic known topic", relevant="Fixture positives", not_relevant="Fixture negatives") for q in qs]
        write_csv(self.truth / "criteria.csv", criteria, list(criteria[0]))
        prepare(self.docs, self.queries, self.truth, self.metadata, expected_documents=4)
        annotations = csv_rows(self.truth / "annotations.csv")
        for r in annotations:
            for q in qs:
                r[q["query_id"]] = "1" if r["doc_id"] in ("01_alpha_beta.txt", "02_alpha.txt") else "0"
        write_csv(self.truth / "annotations.csv", annotations, list(annotations[0]))
        freeze(self.docs, self.queries, self.truth, self.metadata, expected_documents=4,
               reviewer="Synthetic fixture", approval_note="Test only, not real human review")

    def run_evaluation(self, output, **kwargs):
        with redirect_stdout(io.StringIO()):
            return evaluate(self.docs, self.queries, self.truth, output, self.metadata,
                            expected_documents=4, **kwargs)

    def test_or_evaluation_and_comparison_preserve_baseline(self):
        baseline, candidate = self.root / "baseline", self.root / "or"
        a, _ = self.run_evaluation(baseline)
        protected = {p.name:sha256(p) for p in baseline.iterdir()}
        b, _ = self.run_evaluation(candidate, strategy="or")
        self.assertEqual((a[0]["retrieved"], a[0]["tp"], a[0]["fp"], a[0]["fn"]), (2, 1, 1, 1))
        self.assertEqual((b[0]["retrieved"], b[0]["tp"], b[0]["fp"], b[0]["fn"]), (4, 2, 2, 0))
        self.assertEqual(a[7:], b[7:])
        comparison, macro = compare(baseline, candidate, self.queries)
        self.assertEqual(comparison[0]["delta_recall"], .5)
        self.assertAlmostEqual(comparison[0]["delta_f1"], 1/6)
        self.assertEqual(read_json(candidate / "comparison.json")["phrase_queries_identical"], ["Q08", "Q09", "Q10"])
        self.assertEqual({p.name:sha256(p) for p in baseline.iterdir()}, protected)
        self.assertEqual(read_json(baseline / "evaluation.json")["strategy"], "and")
        self.assertEqual(read_json(candidate / "evaluation.json")["strategy"], "or")

    def test_invalid_strategy_and_existing_baseline_rejected(self):
        baseline = self.root / "baseline"
        self.run_evaluation(baseline)
        before = {p.name:sha256(p) for p in baseline.iterdir()}
        with self.assertRaisesRegex(ValueError, "configurazione diversa"):
            self.run_evaluation(baseline, strategy="or")
        with self.assertRaisesRegex(ValueError, "separata"):
            self.run_evaluation("artifacts/homework/results", strategy="or")
        with self.assertRaisesRegex(ValueError, "Strategia"):
            self.run_evaluation(self.root / "invalid", strategy="xor")
        self.assertEqual({p.name:sha256(p) for p in baseline.iterdir()}, before)

    def test_default_output_separates_or_and_and_without_writing_real_outputs(self):
        with patch("irhome.evaluation.write_csv") as writer, patch("irhome.evaluation.write_json"):
            self.run_evaluation(None, strategy="or")
            self.assertEqual(writer.call_args_list[0].args[0], Path("artifacts/homework/results_or/metrics.csv"))
            writer.reset_mock()
            self.run_evaluation(None)
            self.assertEqual(writer.call_args_list[0].args[0], Path("artifacts/homework/results/metrics.csv"))


if __name__ == "__main__":
    unittest.main()
