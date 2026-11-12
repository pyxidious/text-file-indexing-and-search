"""Cranfield: benchmark IR completo e misure separate sui prefissi 100/300/1400."""
import csv
import io
from importlib import metadata
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
from time import perf_counter_ns

from . import __version__
from .acquire import DEFAULT_CACHE, DEFAULT_LOCK, acquire, check_dependency
from .analyzers import ANALYZER_CONFIG
from .dataset import ROOT, document_mapping, prepare_dataset, verify_dataset
from .engine import SearchEngine
from .io import read_json, sha256, write_json
from .metrics import retrieval_metrics
from .oracle import direct_scan

FUNCTIONAL_QUERIES = ROOT / "corpus" / "functional_queries.json"


def validate_config(config):
    if config.get("dataset") != "cranfield" or config.get("main_size") != 1400:
        raise ValueError("Il benchmark principale richiede Cranfield completo (1400)")
    sizes = config["sizes"]
    if (not isinstance(sizes, list) or not sizes or
            any(type(n) is not int or not 1 <= n <= 1400 for n in sizes) or
            len(sizes) != len(set(sizes)) or 1400 not in sizes):
        raise ValueError("Dimensioni distinte in 1..1400, inclusa 1400, richieste")
    if config.get("relevance_threshold") != 1:
        raise ValueError("Questa configurazione richiede la soglia relevance >= 1")
    if type(config["repetitions"]) is not int or config["repetitions"] < 5:
        raise ValueError("Sono richieste almeno 5 ripetizioni")
    SearchEngine(**config["bm25"])
    if sys.version_info < (3, 10):
        raise RuntimeError("Python >= 3.10 richiesto")


def csv_file(path, rows):
    if not rows:
        return
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(buffer.getvalue().encode("utf-8"))


def sample(samples, size, phase, repetition, elapsed, query_id=""):
    samples.append({"size": size, "phase": phase, "query_id": query_id,
                    "repetition": repetition + 1, "ns": elapsed})


def prepare_collections(output, config, cache=DEFAULT_CACHE, offline=False):
    validate_config(config)
    check_dependency()
    records = acquire(cache, offline=offline)  # Rete/acquisizione fuori da tutti i timer.
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    marker = output / "experiment-kind.json"
    identity = {"dataset": "cranfield", "protocol_version": 2}
    if marker.exists() and read_json(marker) != identity:
        raise ValueError("Destinazione di un altro esperimento")
    if not marker.exists() and any(output.iterdir()):
        raise ValueError("Destinazione non vuota: non mescolare risultati sintetici e Cranfield")
    write_json(marker, identity)
    source_sha = read_json(DEFAULT_LOCK)["records_sha256"]
    samples = []
    for size in sorted(config["sizes"]):
        collection = output / f"n{size}"
        previous = None
        for repetition in range(config["repetitions"]):
            start = perf_counter_ns()
            prepare_dataset(collection / "dataset", records, size, source_sha)
            elapsed = perf_counter_ns() - start
            digest = verify_dataset(collection / "dataset")
            if previous is not None and digest != previous:
                raise AssertionError("Preparazione TXT non deterministica")
            previous = digest
            sample(samples, size, "preparation", repetition, elapsed)
        print(f"TXT {size}: hash verificati su {config['repetitions']} preparazioni", flush=True)
    for size in sorted(config["sizes"]):
        collection = output / f"n{size}"
        previous = None
        for repetition in range(config["repetitions"]):
            start = perf_counter_ns()
            engine = SearchEngine.build(collection / "dataset" / "documents", **config["bm25"])
            built = perf_counter_ns()
            engine.save(collection / "index.json")
            saved = perf_counter_ns()
            for phase, ns in (("index_build", built - start), ("index_save", saved - built),
                              ("index_total", saved - start)):
                sample(samples, size, phase, repetition, ns)
            digest = sha256(collection / "index.json")
            if previous is not None and digest != previous:
                raise AssertionError("Indice non deterministico")
            previous = digest
        print(f"Indici {size}: costruzione e persistenza verificate", flush=True)
    return samples


def summarize_timings(samples):
    groups = {}
    for row in samples:
        key = (row["size"], row["phase"], row["query_id"])
        groups.setdefault(key, []).append(row["ns"])
    rows = []
    for (size, phase, query_id), values in sorted(groups.items()):
        quartiles = statistics.quantiles(values, n=4, method="inclusive")
        rows.append({"size": size, "phase": phase, "query_id": query_id,
                     "samples": len(values), "median_ns": statistics.median(values),
                     "min_ns": min(values), "max_ns": max(values),
                     "stdev_ns": statistics.pstdev(values), "iqr_ns": quartiles[2] - quartiles[0]})
    return rows


def environment():
    try:
        # Opzione limitata a questi comandi: non modifica la configurazione Git globale.
        git = ["git", "-c", f"safe.directory={ROOT.as_posix()}"]
        commit = subprocess.run(git + ["rev-parse", "HEAD"], cwd=ROOT, check=True,
                                capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(git + ["status", "--porcelain"], cwd=ROOT, check=True,
                                    capture_output=True, text=True).stdout.strip())
    except (OSError, subprocess.CalledProcessError):
        commit, dirty = None, None
    return {"python": sys.version, "implementation": platform.python_implementation(),
            "project_version": __version__, "git_commit": commit, "git_dirty": dirty,
            "os": platform.platform(), "machine": platform.machine(),
            "processor": platform.processor(), "logical_cpus": os.cpu_count(),
            "timer": "time.perf_counter_ns", "ram_bytes": None,
            "installed_distributions": dict(sorted((d.metadata["Name"], d.version)
                                                   for d in metadata.distributions()))}


def check_mapping(engine, mapping):
    if set(engine.documents) != set(mapping) or len(mapping) != len(set(mapping.values())):
        raise ValueError("Mapping motore -> doc_id Cranfield incompleto o ambiguo")


def qrels_by_query(qrels):
    grouped = {}
    for row in qrels:
        judgments = grouped.setdefault(row["query_id"], {})
        if row["doc_id"] in judgments:
            raise ValueError("Giudizio duplicato")
        judgments[row["doc_id"]] = row["relevance"]
    return grouped


def annotate_results(results, mapping, judgments):
    rows = []
    for rank, result in enumerate(results, 1):
        doc_id = mapping[result["id"]]  # KeyError se anche un solo risultato non è mappabile.
        judgment = judgments.get(doc_id)
        status = ("unjudged" if judgment is None else
                  "judged_relevant" if judgment >= 1 else "judged_nonrelevant")
        rows.append({"rank": rank, "doc_id": doc_id, "engine_id": result["id"],
                     "filename": result["filename"], "score": result["score"],
                     "judgment": judgment, "judgment_status": status,
                     "binary_relevance_for_metrics": int(judgment is not None and judgment >= 1)})
    return rows


def check_functional(engine, dataset):
    checks = []
    for query in read_json(FUNCTIONAL_QUERIES):
        result = engine.search(query["query"])
        oracle = direct_scan(Path(dataset) / "documents", query["query"])
        if {row["id"] for row in result} != oracle:
            raise AssertionError(f"Scansione diretta discordante: {query['id']}")
        if bool(oracle) != (query["expect"] == "nonempty"):
            raise AssertionError(f"Aspettativa funzionale non soddisfatta: {query['id']}")
        checks.append({**query, "oracle_match": True, "retrieved": len(result),
                       "engine_ids": sorted(oracle)})
    return checks


def aggregate_metrics(rows):
    aggregates = {}
    for metric in ("precision_at_10", "recall_at_10", "f1_at_10", "precision", "recall",
                   "f1", "average_precision", "ap_at_10"):
        values = [row[metric] for row in rows if row[metric] is not None]
        name = {"average_precision": "map", "ap_at_10": "map_at_10"}.get(metric, metric)
        aggregates[name] = statistics.mean(values) if values else None
    aggregates["queries"] = len(rows)
    aggregates["queries_with_relevant"] = sum(row["relevant"] > 0 for row in rows)
    return aggregates


def evaluate_collections(output, config, samples):
    validate_config(config)
    output = Path(output)
    per_query, collections, functional = [], [], []
    main_aggregates = None
    for size in sorted(config["sizes"]):
        collection = output / f"n{size}"
        dataset = collection / "dataset"
        dataset_hash = verify_dataset(dataset)
        queries = read_json(dataset / "queries.json")
        judgments_by_query = qrels_by_query(read_json(dataset / "qrels.json"))
        mapping = document_mapping(dataset)
        for repetition in range(config["repetitions"]):
            start = perf_counter_ns()
            engine = SearchEngine.load(collection / "index.json")
            elapsed = perf_counter_ns() - start
            sample(samples, size, "load", repetition, elapsed)
        check_mapping(engine, mapping)
        if {"k1": engine.k1, "b": engine.b} != config["bm25"]:
            raise ValueError("BM25 dell'indice diverso dalla configurazione")
        is_main = size == config["main_size"]
        if is_main:
            functional = check_functional(engine, dataset)
            print(f"Correttezza lessicale: {len(functional)} query funzionali verificate", flush=True)
        runs = {}
        for number, query in enumerate(queries, 1):
            line = "contenuto " + query["text"]
            previous = None
            for repetition in range(config["repetitions"]):
                start = perf_counter_ns()
                results = engine.search(line)
                elapsed = perf_counter_ns() - start
                sample(samples, size, "search", repetition, elapsed, query["query_id"])
                if previous is not None and results != previous:
                    raise AssertionError("Ranking non deterministico")
                previous = results
            if any(row["id"] not in mapping for row in results):
                raise ValueError("Risultato non associabile a Cranfield")
            if is_main:
                judgments = judgments_by_query.get(query["query_id"], {})
                annotated = annotate_results(results, mapping, judgments)
                ranked_ids = [row["doc_id"] for row in annotated]
                relevant = {doc for doc, judgment in judgments.items() if judgment >= 1}
                per_query.append({"query_id": query["query_id"],
                                  "source_query_id": query["source_query_id"], "text": query["text"],
                                  "judged_relevant": len(relevant),
                                  "judged_nonrelevant": sum(v == -1 for v in judgments.values()),
                                  "unjudged_in_collection": 1400 - len(judgments),
                                  "retrieved_unjudged": sum(r["judgment"] is None for r in annotated),
                                  **retrieval_metrics(ranked_ids, relevant)})
                runs[query["query_id"]] = {**query, "results": annotated}
            if number % 25 == 0 or number == len(queries):
                print(f"Query {size}: {number}/{len(queries)} (x{config['repetitions']})", flush=True)
        record = {"size": size, "purpose": "main_ir" if is_main else "performance_only",
                  "dataset_sha256": dataset_hash, "index_sha256": sha256(collection / "index.json"),
                  "index_bytes": (collection / "index.json").stat().st_size}
        if is_main:
            main_aggregates = aggregate_metrics(per_query)
            write_json(collection / "ranking.json", runs)
            record["ranking_sha256"] = sha256(collection / "ranking.json")
        collections.append(record)
    deterministic = {"project_version": __version__, "configuration": config,
                     "source_lock": read_json(DEFAULT_LOCK), "analyzers": ANALYZER_CONFIG,
                     "functional_queries_sha256": sha256(FUNCTIONAL_QUERIES),
                     "metric_convention": {"relevant": "original relevance >= 1",
                                           "unjudged": "treated as 0 for metrics; status preserved",
                                           "ap_denominator": "all known relevant documents",
                                           "ap_at_10_denominator": "min(10, all known relevant documents)"},
                     "collections": collections, "main_aggregates": main_aggregates,
                     "per_query": per_query, "functional_checks": functional}
    results_dir = output / "results"
    write_json(results_dir / "deterministic.json", deterministic)
    csv_file(results_dir / "metrics.csv", per_query)
    csv_file(results_dir / "aggregate_metrics.csv", [main_aggregates])
    write_json(results_dir / "functional_checks.json", functional)
    timings = summarize_timings(samples)
    # Mediana delle mediane delle 225 query: riepilogo compatto, non latenza di una query specifica.
    performance = []
    for collection in collections:
        size = collection["size"]
        summary = {row["phase"]: row for row in timings if row["size"] == size and not row["query_id"]}
        query_medians = [row["median_ns"] for row in timings if row["size"] == size and row["phase"] == "search"]
        performance.append({"size": size, "index_bytes": collection["index_bytes"],
                            **{phase + "_median_ns": summary[phase]["median_ns"]
                               for phase in ("index_build", "index_save", "load")},
                            "median_of_query_medians_ns": statistics.median(query_medians)})
    write_json(results_dir / "observed.json", {
        "environment": environment(), "configuration": config, "analyzers": ANALYZER_CONFIG,
        "deterministic_results_sha256": sha256(results_dir / "deterministic.json"),
        "source_lock": read_json(DEFAULT_LOCK), "performance_comparison": performance,
        "timing_protocol": "sequential; no cache flushing, no warm-up; download excluded; ns",
        "samples": samples, "timing_summary": timings})
    csv_file(results_dir / "timing_samples.csv", samples)
    csv_file(results_dir / "timing_summary.csv", timings)
    csv_file(results_dir / "performance.csv", performance)
    write_json(results_dir / "checksums.json", {name: sha256(results_dir / name) for name in
               ("deterministic.json", "metrics.csv", "aggregate_metrics.csv", "functional_checks.json")})
    print("Metriche aggregate Cranfield completo:", main_aggregates, flush=True)
    return deterministic
