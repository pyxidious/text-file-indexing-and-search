import csv
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from irhome.analyzers import ContentAnalyzer, FilenameAnalyzer
from irhome.acquire import DEFAULT_CACHE, acquire, load_snapshot, validate_records
from irhome.dataset import (document_filename, document_mapping, normalized_newlines,
                            prepare_dataset, verify_dataset)
from irhome.engine import SearchEngine, parse_query
from irhome.experiment import (aggregate_metrics, annotate_results, check_functional,
                               check_mapping, qrels_by_query, summarize_timings, validate_config)
from irhome.io import read_json, sha256
from irhome.metrics import retrieval_metrics
from irhome.oracle import direct_scan


class AnalyzerTests(unittest.TestCase):
    def test_filename_delimiters_extension_and_stopwords(self):
        self.assertEqual(FilenameAnalyzer()("Reti-di_calcolatori.TXT"),
                         ["reti", "di", "calcolatori"])

    def test_content_stopwords_and_numbers(self):
        self.assertEqual(ContentAnalyzer()("L'analisi di un TEST, 42!"),
                         ["l", "analisi", "di", "un", "test", "42"])

    def test_unicode_canonical_equivalence(self):
        self.assertEqual(ContentAnalyzer()("INTEGRITA\u0300"), ["integrità"])
        self.assertNotEqual(ContentAnalyzer()("è"), ContentAnalyzer()("e"))

    def test_basename(self):
        self.assertEqual(FilenameAnalyzer()(r"dir\La_rete.txt"), ["la", "rete"])

    def test_only_terminal_extension_removed(self):
        self.assertEqual(FilenameAnalyzer()("note.txt.backup"), ["note", "txt", "backup"])


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        files = {
            "database_relazionali.txt": "Reti neurali e reti neurali profonde. di un sistema. eco eco eco.",
            "sistemi_distribuiti.txt": "Neurali reti. Integrita\u0300 e dati.",
            "vuoto.txt": "",
            "nested/copia.TXT": "reti neurali",
        }
        for name, content in files.items():
            path = self.root / name
            path.parent.mkdir(exist_ok=True)
            path.write_text(content, encoding="utf-8")
        self.engine = SearchEngine.build(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def ids(self, query):
        return {row["id"] for row in self.engine.search(query)}

    def test_separate_indexes(self):
        self.assertIn("database", self.engine.filename_index)
        self.assertNotIn("database", self.engine.content_index)
        self.assertNotIn("neurali", self.engine.filename_index)
        self.assertEqual(self.ids("nome database"), {"database_relazionali.txt"})
        self.assertEqual(self.ids("contenuto database"), set())

    def test_postings_positions(self):
        self.assertEqual(self.engine.content_index["reti"]["database_relazionali.txt"], [0, 3])
        self.assertEqual(self.engine.filename_index["relazionali"]["database_relazionali.txt"], [1])

    def test_phrase_order_and_adjacency(self):
        self.assertEqual(self.ids('contenuto "reti neurali"'),
                         {"database_relazionali.txt", "nested/copia.TXT"})
        self.assertEqual(self.ids('contenuto "neurali reti"'), {"sistemi_distribuiti.txt"})
        self.assertEqual(self.ids('contenuto "reti profonde"'), set())

    def test_repeated_phrase_and_stopwords(self):
        self.assertEqual(self.ids('contenuto "eco eco eco"'), {"database_relazionali.txt"})
        self.assertEqual(self.ids('contenuto "eco eco eco eco"'), set())
        self.assertEqual(self.ids('contenuto "di un"'), {"database_relazionali.txt"})

    def test_filename_phrase(self):
        self.assertEqual(self.ids('nome "database relazionali"'), {"database_relazionali.txt"})
        self.assertEqual(self.ids('nome "relazionali database"'), set())

    def test_or(self):
        self.assertEqual(self.ids("contenuto profonde integrità"),
                         {"database_relazionali.txt", "sistemi_distribuiti.txt"})

    def test_normalized_query(self):
        self.assertEqual(self.ids("contenuto INTEGRITÀ"), {"sistemi_distribuiti.txt"})

    def test_invalid_queries(self):
        for text in ("", "nome", "titolo rete", 'nome ""', 'nome "rete',
                     'contenuto reti "neurali"', "contenuto ---"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_query(text)

    def test_persistence_and_deterministic_bytes(self):
        first, second = self.root / "one.json", self.root / "two.json"
        self.engine.save(first)
        loaded = SearchEngine.load(first)
        loaded.save(second)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertEqual(loaded.search('contenuto "reti neurali"'),
                         self.engine.search('contenuto "reti neurali"'))
        self.assertEqual(loaded.documents["nested/copia.TXT"]["path"], "nested/copia.TXT")

    def test_unknown_index_version(self):
        path = self.root / "bad.json"
        path.write_text('{"format_version":99}', encoding="utf-8")
        with self.assertRaises(ValueError):
            SearchEngine.load(path)

    def test_matches_independent_scan(self):
        for text in ("nome database sistemi", 'nome "sistemi distribuiti"',
                     "contenuto reti integrità", 'contenuto "eco eco"', "contenuto assente"):
            self.assertEqual(self.ids(text), direct_scan(self.root, text))

    def test_bm25_formula_and_length_normalization(self):
        rows = self.engine.search("contenuto reti")
        self.assertEqual(rows[0]["id"], "nested/copia.TXT")
        n = len(self.engine.documents)
        lengths = self.engine.lengths["contenuto"]
        expected = math.log(1 + (n - 3 + .5) / (3 + .5)) * 2.2 / (
            1 + 1.2 * (.25 + .75 * 2 / (sum(lengths.values()) / n)))
        self.assertAlmostEqual(rows[0]["score"], expected)

    def test_ties_and_empty_collection(self):
        empty = self.root / "empty"
        empty.mkdir()
        self.assertEqual(SearchEngine.build(empty).search("contenuto reti"), [])
        (empty / "b.txt").write_text("uguale", encoding="utf-8")
        (empty / "a.txt").write_text("uguale", encoding="utf-8")
        engine = SearchEngine.build(empty)
        self.assertEqual([r["id"] for r in engine.search("contenuto uguale")], ["a.txt", "b.txt"])

    def test_invalid_bm25(self):
        for k1, b in ((0, .5), (1, 2), (float("nan"), .5), (1, float("inf"))):
            with self.assertRaises(ValueError):
                SearchEngine(k1, b)


class MetricTests(unittest.TestCase):
    def test_hand_calculated_metrics(self):
        result = retrieval_metrics(["a", "x", "b", "c"], {"a", "b", "z"})
        self.assertEqual(result["precision_at_10"], .2)
        self.assertAlmostEqual(result["recall_at_10"], 2 / 3)
        self.assertEqual(result["precision"], .5)
        self.assertAlmostEqual(result["f1"], 4 / 7)
        self.assertAlmostEqual(result["ap_at_10"], 5 / 9)

    def test_ap_cutoff_and_denominator(self):
        result = retrieval_metrics([str(i) for i in range(20)], {str(i) for i in range(20)})
        self.assertEqual(result["ap_at_10"], 1)
        self.assertEqual(result["recall_at_10"], .5)

    def test_empty_results_and_no_relevant(self):
        self.assertEqual(retrieval_metrics([], {"a"})["f1"], 0)
        result = retrieval_metrics([], set())
        self.assertIsNone(result["recall"])
        self.assertIsNone(result["ap_at_10"])
        self.assertEqual(result["precision"], 0)

    def test_reject_duplicate_ranking(self):
        with self.assertRaises(ValueError):
            retrieval_metrics(["a", "a"], {"a"})

    def test_timing_summary(self):
        rows = [{"size": 100, "phase": "load", "query_id": "", "ns": n}
                for n in (1, 2, 3, 4, 100)]
        result = summarize_timings(rows)[0]
        self.assertEqual(result["median_ns"], 3)
        self.assertEqual(result["iqr_ns"], 2)
        self.assertEqual(result["samples"], 5)


class DatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cache = Path(os.environ.get("IRHOME_TEST_CACHE", str(DEFAULT_CACHE)))
        try:
            cls.records = load_snapshot(cls.cache)
        except FileNotFoundError:
            raise unittest.SkipTest("Acquisire lo snapshot Cranfield per i test di integrazione offline")

    def test_regenerate_twice_and_compare_all_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a", Path(tmp) / "b"
            first = prepare_dataset(a, self.records, 100)
            second = prepare_dataset(b, self.records, 100)
            self.assertEqual(first, second)
            self.assertEqual(verify_dataset(a), verify_dataset(b))
            before = sha256(a / "manifest.json")
            prepare_dataset(a, self.records, 100)
            self.assertEqual(before, verify_dataset(a))
            self.assertGreater(len({p.stat().st_size for p in (a / "documents").iterdir()}), 10)

    def test_original_ground_truth_and_all_functional_queries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare_dataset(root, self.records, 1400)
            with (root / "metadata.csv").open(encoding="utf-8", newline="") as stream:
                metadata = list(csv.DictReader(stream))
            queries, qrels = read_json(root / "queries.json"), read_json(root / "qrels.json")
            self.assertEqual(len(metadata), 1400)
            self.assertEqual(queries, self.records["queries"])
            self.assertEqual(qrels, self.records["qrels"])
            engine = SearchEngine.build(root / "documents")
            mapping = document_mapping(root)
            check_mapping(engine, mapping)
            self.assertEqual(set(mapping.values()), {str(i) for i in range(1, 1401)})
            self.assertGreaterEqual(len(check_functional(engine, root)), 10)
            for original, entry in zip(self.records["documents"], read_json(root / "manifest.json")["documents"]):
                self.assertEqual((root / entry["path"]).read_bytes(),
                                 normalized_newlines(original["text"]).encode("utf-8"))
                self.assertEqual(entry["title"], original["title"])
                self.assertEqual(entry["author"], original["author"])
                self.assertEqual(entry["bib"], original["bib"])

    def test_prefix_collections_and_original_qrels_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = (Path(tmp) / name for name in ("a", "b"))
            small = prepare_dataset(a, self.records, 12)
            large = prepare_dataset(b, self.records, 24)
            for name, digest in small["files"].items():
                if name.startswith("documents/"):
                    self.assertEqual(digest, large["files"][name])
            self.assertEqual([d["doc_id"] for d in small["documents"]], [str(i) for i in range(1, 13)])
            self.assertEqual(read_json(a / "qrels.json"), read_json(b / "qrels.json"))

    def test_tampering_and_extra_files_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare_dataset(root, self.records, 12)
            extra = root / "documents" / "extra.txt"
            extra.write_text("extra", encoding="utf-8")
            with self.assertRaises(ValueError):
                verify_dataset(root)
            extra.unlink()
            next((root / "documents").iterdir()).write_text("modificato", encoding="utf-8")
            with self.assertRaises(ValueError):
                verify_dataset(root)

    def test_invalid_generation_and_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                prepare_dataset(tmp, self.records, 0)
        with self.assertRaises(ValueError):
            validate_config({"dataset": "cranfield", "main_size": 1400, "relevance_threshold": 1,
                             "sizes": [100, 300, 1400], "repetitions": 4,
                             "bm25": {"k1": 1.2, "b": .75}})

    def test_snapshot_counts_levels_and_query_identifiers(self):
        validate_records(self.records)
        qrels = self.records["qrels"]
        self.assertEqual(len(qrels), 1837)
        self.assertEqual(sum(row["relevance"] == -1 for row in qrels), 225)
        self.assertEqual(sum(row["relevance"] >= 1 for row in qrels), 1612)
        queries = self.records["queries"]
        self.assertEqual(queries[2]["query_id"], "3")
        self.assertEqual(queries[2]["source_query_id"], "004")

    def test_offline_snapshot_never_opens_network(self):
        with patch("socket.socket", side_effect=AssertionError("Accesso rete vietato")):
            self.assertEqual(acquire(self.cache, offline=True), self.records)

    def test_missing_offline_snapshot_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                acquire(tmp, offline=True)


class CranfieldUnitTests(unittest.TestCase):
    def test_deterministic_filename_and_collisions(self):
        self.assertEqual(document_filename("42", "Aéròdynamic / Properties: of WINGS!"),
                         "0042_aerodynamic_properties_of_wings.txt")
        self.assertNotEqual(document_filename("1", "same"), document_filename("2", "same"))
        self.assertEqual(document_filename("42", "???"), "0042_untitled.txt")
        self.assertLessEqual(len(document_filename("1400", "a" * 300)), 89)

    def test_no_title_or_trailing_newline_added(self):
        # Fixture unitaria minimale; non è parte della collezione sperimentale.
        records = {"documents": [{"doc_id": "1", "title": "Title only",
                                  "text": "Abstract\r\nunchanged\rtext", "author": "A", "bib": "B"}],
                   "queries": [], "qrels": []}
        with tempfile.TemporaryDirectory() as tmp:
            manifest = prepare_dataset(tmp, records, 1)
            path = Path(tmp) / manifest["documents"][0]["path"]
            self.assertEqual(path.read_bytes(), b"Abstract\nunchanged\ntext")
            verify_dataset(tmp)

    def test_negative_and_unjudged_stay_distinct(self):
        results = [{"id": name, "filename": name, "score": 1.0} for name in ("a", "b", "c")]
        mapping = {"a": "1", "b": "2", "c": "3"}
        rows = annotate_results(results, mapping, {"1": -1, "2": 4})
        self.assertEqual([r["judgment"] for r in rows], [-1, 4, None])
        self.assertEqual([r["judgment_status"] for r in rows],
                         ["judged_nonrelevant", "judged_relevant", "unjudged"])
        self.assertEqual([r["binary_relevance_for_metrics"] for r in rows], [0, 1, 0])
        with self.assertRaises(KeyError):
            annotate_results(results, {"a": "1"}, {})

    def test_duplicate_judgments_rejected(self):
        row = {"query_id": "1", "doc_id": "2", "relevance": 4}
        with self.assertRaises(ValueError):
            qrels_by_query([row, row])

    def test_full_ap_is_not_truncated_ap(self):
        result = retrieval_metrics([str(i) for i in range(20)], {"0", "19", "absent"})
        self.assertAlmostEqual(result["average_precision"], (1 + 2 / 20) / 3)
        self.assertAlmostEqual(result["ap_at_10"], 1 / 3)
        self.assertAlmostEqual(result["f1_at_10"], 2 * .1 * (1 / 3) / (.1 + 1 / 3))
        means = aggregate_metrics([result, retrieval_metrics([], {"r"})])
        self.assertAlmostEqual(means["map"], result["average_precision"] / 2)
        self.assertAlmostEqual(means["map_at_10"], result["ap_at_10"] / 2)


if __name__ == "__main__":
    unittest.main()
