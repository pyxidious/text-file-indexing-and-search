import csv
import math
from pathlib import Path
import tempfile
import unittest

from irhome.analyzers import ContentAnalyzer, FilenameAnalyzer
from irhome.dataset import generate_dataset, verify_dataset
from irhome.engine import SearchEngine, parse_query
from irhome.experiment import summarize_timings, validate_config
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
    def test_regenerate_twice_and_compare_all_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a", Path(tmp) / "b"
            first = generate_dataset(a, 100, 42)
            second = generate_dataset(b, 100, 42)
            self.assertEqual(first, second)
            self.assertEqual(verify_dataset(a), verify_dataset(b))
            before = sha256(a / "manifest.json")
            generate_dataset(a, 100, 42)
            self.assertEqual(before, verify_dataset(a))
            self.assertGreater(len({p.stat().st_size for p in (a / "documents").iterdir()}), 10)

    def test_ground_truth_from_labels_and_all_queries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_dataset(root, 36)
            with (root / "metadata.csv").open(encoding="utf-8", newline="") as stream:
                metadata = list(csv.DictReader(stream))
            queries, qrels = read_json(root / "queries.json"), read_json(root / "qrels.json")
            self.assertEqual(len({r["topic"] for r in metadata}), 12)
            self.assertGreaterEqual(sum(q["kind"] == "thematic" for q in queries), 20)
            self.assertGreaterEqual(sum(q["kind"] == "functional" for q in queries), 10)
            engine = SearchEngine.build(root / "documents")
            for query in queries:
                with self.subTest(query=query["id"]):
                    if query["kind"] == "thematic":
                        expected = {r["id"] for r in metadata if r["topic"] == query["topic"]}
                        self.assertEqual(set(qrels[query["id"]]), expected)
                    self.assertEqual({r["id"] for r in engine.search(query["query"])},
                                     direct_scan(root / "documents", query["query"]))

    def test_prefix_collections_and_different_seed(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b, c = (Path(tmp) / name for name in ("a", "b", "c"))
            small = generate_dataset(a, 12, 42)
            large = generate_dataset(b, 24, 42)
            different = generate_dataset(c, 12, 43)
            for name, digest in small["files"].items():
                if name.startswith("documents/"):
                    self.assertEqual(digest, large["files"][name])
            self.assertNotEqual(small["files"], different["files"])

    def test_tampering_and_extra_files_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_dataset(root, 12)
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
                generate_dataset(tmp, 0)
        with self.assertRaises(ValueError):
            validate_config({"seed": 42, "sizes": [100], "repetitions": 4,
                             "bm25": {"k1": 1.2, "b": .75}})


if __name__ == "__main__":
    unittest.main()
