"""Confronto sul development, congelamento della scelta, singola valutazione test."""
from pathlib import Path
import statistics
from time import perf_counter_ns

from . import __version__
from .acquire import DEFAULT_LOCK
from .analyzers import ANALYZER_CONFIG
from .dataset import document_mapping, verify_dataset
from .engine import SearchEngine
from .experiment import (FUNCTIONAL_QUERIES, aggregate_metrics, annotate_results, check_functional,
                         check_mapping, csv_file, environment, qrels_by_query, sample,
                         summarize_timings, validate_config)
from .io import read_json, sha256, write_json
from .metrics import retrieval_metrics
from .protocol import coverage_and_split
from .strategies import STOPLIST_PATH


def summarize(rows, size):
    return {**aggregate_metrics(rows),
            "mean_candidates": statistics.mean(row["retrieved"] for row in rows),
            "median_candidates": statistics.median(row["retrieved"] for row in rows),
            "mean_retrieved_percent": statistics.mean(row["retrieved"] for row in rows) * 100 / size}


def evaluate_queries(engine, queries, ids, spec, mapping, qrels, phase):
    runs, rows = {}, []
    for qid in ids:
        query = queries[qid]
        results = engine.search("contenuto " + query["text"], spec["mode"], spec["minimum_should_match"])
        judgments = qrels.get(qid, {})
        relevant = {doc for doc, grade in judgments.items() if grade >= 1}
        if not relevant:
            raise ValueError("Una query senza positivi non deve entrare in development/test")
        annotated = annotate_results(results, mapping, judgments)
        runs[qid] = {**query, "results": annotated}
        rows.append({"phase": phase, "strategy": spec["id"], "query_id": qid,
                     "source_query_id": query["source_query_id"], "text": query["text"],
                     "explicit_negative_judgments": sum(g == -1 for g in judgments.values()),
                     "unjudged_documents": len(mapping) - len(judgments),
                     **retrieval_metrics([r["doc_id"] for r in annotated], relevant)})
    return rows, runs


def choose_strategy(table, specs):
    if [row["strategy"] for row in table] != [spec["id"] for spec in specs]:
        raise ValueError("Tabella non allineata all'ordine di spareggio dichiarato")
    index = max(range(len(table)), key=lambda i: (table[i]["f1_at_10"], table[i]["recall_at_10"],
                                                table[i]["map_at_10"], -i))
    return specs[index]


def run_experiment(output, config, samples):
    validate_config(config)
    output = Path(output)
    results_dir = output / "results"
    engines, collections = {}, []
    for size in sorted(config["sizes"]):
        collection = output / f"n{size}"
        digest = verify_dataset(collection / "dataset")
        for repetition in range(config["repetitions"]):
            start = perf_counter_ns()
            engine = SearchEngine.load(collection / "index.json")
            elapsed = perf_counter_ns() - start
            sample(samples, size, "load", repetition, elapsed)
        mapping = document_mapping(collection / "dataset")
        check_mapping(engine, mapping)
        if {"k1": engine.k1, "b": engine.b} != config["bm25"]:
            raise ValueError("BM25 diverso dalla configurazione")
        engines[size] = engine
        collections.append({"size": size, "purpose": "main_ir" if size == 300 else "performance_only",
                            "dataset_sha256": digest, "index_sha256": sha256(collection / "index.json"),
                            "index_bytes": (collection / "index.json").stat().st_size})
    dataset = output / "n300/dataset"
    manifest = read_json(dataset / "manifest.json")
    query_list = read_json(dataset / "queries.json")
    qrel_list = read_json(dataset / "qrels.json")
    coverage, splits = coverage_and_split(query_list, qrel_list, manifest["selected_doc_ids"],
                                          config["query_split_seed"], config["development_fraction"])
    write_json(results_dir / "coverage.json", coverage)
    write_json(results_dir / "splits.json", splits)
    queries = {q["query_id"]: q for q in query_list}
    qrels = qrels_by_query(qrel_list)
    mapping = document_mapping(dataset)
    engine = engines[300]
    functional = check_functional(engine, dataset, config["strategies"])
    write_json(results_dir / "functional_checks.json", functional)
    print(f"Query funzionali: {len(functional)} controlli (12 per configurazione)", flush=True)

    development_rows, table, runs = [], [], {}
    for spec in config["strategies"]:
        rows, ranked = evaluate_queries(engine, queries, splits["development"], spec, mapping, qrels, "development")
        development_rows.extend(rows)
        runs[spec["id"]] = ranked
        summary = {"strategy": spec["id"], **summarize(rows, 300)}
        table.append(summary)
        print("Development:", summary, flush=True)
    write_json(results_dir / "development_runs.json", runs)
    csv_file(results_dir / "development_metrics.csv", development_rows)
    csv_file(results_dir / "development_comparison.csv", table)

    chosen = choose_strategy(table, config["strategies"])
    selection = {"rule": config["selection_rule"], "strategy": chosen,
                 "dataset_sha256": verify_dataset(dataset), "splits_sha256": sha256(results_dir / "splits.json"),
                 "stoplist_sha256": sha256(STOPLIST_PATH),
                 "development_comparison_sha256": sha256(results_dir / "development_comparison.csv"),
                 "development_query_ids": splits["development"],
                 "test_used_for_selection": False}
    selection_path = results_dir / "selection.json"
    if selection_path.exists() and read_json(selection_path) != selection:
        raise ValueError("La scelta congelata è cambiata: non sovrascrivere una valutazione test precedente")
    write_json(selection_path, selection)
    print("Scelta congelata PRIMA del test:", chosen, flush=True)
    # Un solo calcolo delle metriche sul test, per l'unica configurazione scelta.
    test_rows, test_runs = evaluate_queries(engine, queries, splits["test"], chosen, mapping, qrels, "test")
    test_summary = {"strategy": chosen["id"], **summarize(test_rows, 300)}
    write_json(results_dir / "test_runs.json", test_runs)
    csv_file(results_dir / "test_metrics.csv", test_rows)
    csv_file(results_dir / "test_summary.csv", [test_summary])
    print("Test finale:", test_summary, flush=True)

    # Solo le query DEVELOPMENT sono rigiocate cinque volte per i tempi.
    # Nessun altro uso del test e nessuna metrica sui subset da 100/200.
    for size, timed_engine in sorted(engines.items()):
        for qid in splits["development"]:
            previous = None
            for repetition in range(config["repetitions"]):
                start = perf_counter_ns()
                result = timed_engine.search("contenuto " + queries[qid]["text"],
                                             chosen["mode"], chosen["minimum_should_match"])
                elapsed = perf_counter_ns() - start
                sample(samples, size, "search", repetition, elapsed, qid)
                if previous is not None and result != previous:
                    raise AssertionError("Risultati non deterministici")
                previous = result
        print(f"Benchmark {size}: {len(splits['development'])} query development x{config['repetitions']}", flush=True)
    deterministic = {"project_version": __version__, "configuration": config,
                     "source_lock": read_json(DEFAULT_LOCK), "analyzers": ANALYZER_CONFIG,
                     "stoplist_sha256": sha256(STOPLIST_PATH), "functional_queries_sha256": sha256(FUNCTIONAL_QUERIES),
                     "metric_convention": {"relevant": "original relevance >= 1",
                                           "unjudged": "0 for metrics, null judgment and unjudged status",
                                           "ap_denominator": "all known relevant in the 300 documents",
                                           "ap_at_10_denominator": "min(10, known relevant in subset)",
                                           "averaging": "macro per eligible query; phases kept separate"},
                     "collections": collections, "coverage": coverage, "splits": splits,
                     "development_comparison": table, "selection": selection, "test_summary": test_summary}
    write_json(results_dir / "deterministic.json", deterministic)
    deterministic_names = ["deterministic.json", "coverage.json", "splits.json", "selection.json",
                           "functional_checks.json", "development_runs.json", "development_metrics.csv",
                           "development_comparison.csv", "test_runs.json", "test_metrics.csv", "test_summary.csv"]
    write_json(results_dir / "checksums.json", {name: sha256(results_dir / name) for name in deterministic_names})
    timings = summarize_timings(samples)
    performance = []
    for collection in collections:
        size = collection["size"]
        summary = {r["phase"]: r for r in timings if r["size"] == size and not r["query_id"]}
        query_times = [r["median_ns"] for r in timings if r["size"] == size and r["phase"] == "search"]
        performance.append({"size": size, "index_bytes": collection["index_bytes"],
                            **{phase + "_median_ns": summary[phase]["median_ns"]
                               for phase in ("index_build", "index_save", "load")},
                            "median_of_query_medians_ns": statistics.median(query_times)})
    write_json(results_dir / "observed.json", {"environment": environment(), "configuration": config,
               "selection": selection, "source_lock": read_json(DEFAULT_LOCK),
               "deterministic_results_sha256": sha256(results_dir / "deterministic.json"),
               "timing_protocol": "selected strategy; development queries only; no cache flush or warm-up; ns; acquisition excluded",
               "performance_comparison": performance, "samples": samples, "timing_summary": timings})
    csv_file(results_dir / "performance.csv", performance)
    csv_file(results_dir / "timing_samples.csv", samples)
    csv_file(results_dir / "timing_summary.csv", timings)
    return deterministic
