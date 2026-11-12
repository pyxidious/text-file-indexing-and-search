"""Protocollo sperimentale: fasi distinte e separazione risultati/osservazioni."""
import csv
import io
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
from time import perf_counter_ns

from . import __version__
from .analyzers import ANALYZER_CONFIG
from .dataset import ROOT, generate_dataset, verify_dataset
from .engine import SearchEngine
from .io import read_json, sha256, write_json
from .metrics import retrieval_metrics
from .oracle import direct_scan


def validate_config(config):
    if not isinstance(config["seed"], int) or isinstance(config["seed"], bool):
        raise ValueError("Seed intero richiesto")
    sizes = config["sizes"]
    if (not isinstance(sizes, list) or not sizes or
            any(type(n) is not int or n < 1 for n in sizes) or len(sizes) != len(set(sizes))):
        raise ValueError("Dimensioni positive e distinte richieste")
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


def prepare_collections(output, config):
    """Generazione e costruzione ripetute; hash fuori dagli intervalli misurati."""
    validate_config(config)
    output = Path(output)
    samples = []
    for size in sorted(config["sizes"]):
        collection = output / f"n{size}"
        previous = None
        for repetition in range(config["repetitions"]):
            start = perf_counter_ns()
            generate_dataset(collection / "dataset", size, config["seed"])
            elapsed = perf_counter_ns() - start
            digest = verify_dataset(collection / "dataset")
            if previous is not None and digest != previous:
                raise AssertionError("Generazione non deterministica")
            previous = digest
            samples.append({"size": size, "phase": "generation", "query_id": "",
                            "repetition": repetition + 1, "ns": elapsed})
        print(f"Dataset {size}: hash verificati su {config['repetitions']} generazioni", flush=True)
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
                samples.append({"size": size, "phase": phase, "query_id": "",
                                "repetition": repetition + 1, "ns": ns})
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
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                                capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, check=True,
                                    capture_output=True, text=True).stdout.strip())
    except (OSError, subprocess.CalledProcessError):
        commit, dirty = None, None
    return {"python": sys.version, "implementation": platform.python_implementation(),
            "project_version": __version__, "git_commit": commit, "git_dirty": dirty,
            "os": platform.platform(), "machine": platform.machine(),
            "processor": platform.processor(), "logical_cpus": os.cpu_count(),
            "timer": "time.perf_counter_ns", "ram_bytes": None}


def evaluate_collections(output, config, samples):
    validate_config(config)
    output = Path(output)
    per_query, collections = [], []
    for size in sorted(config["sizes"]):
        collection = output / f"n{size}"
        dataset = collection / "dataset"
        dataset_hash = verify_dataset(dataset)
        queries = read_json(dataset / "queries.json")
        qrels = read_json(dataset / "qrels.json")
        for repetition in range(config["repetitions"]):
            start = perf_counter_ns()
            engine = SearchEngine.load(collection / "index.json")
            elapsed = perf_counter_ns() - start
            samples.append({"size": size, "phase": "load", "query_id": "",
                            "repetition": repetition + 1, "ns": elapsed})
        if engine.k1 != config["bm25"]["k1"] or engine.b != config["bm25"]["b"]:
            raise ValueError("BM25 dell'indice diverso dalla configurazione")
        runs = {}
        for query in queries:
            previous = None
            for repetition in range(config["repetitions"]):
                start = perf_counter_ns()
                results = engine.search(query["query"])
                elapsed = perf_counter_ns() - start
                samples.append({"size": size, "phase": "search", "query_id": query["id"],
                                "repetition": repetition + 1, "ns": elapsed})
                if previous is not None and results != previous:
                    raise AssertionError("Ranking non deterministico")
                previous = results
            ranked = [row["id"] for row in results]
            runs[query["id"]] = results
            # Oracle fuori dalla regione temporizzata e senza accedere all'indice.
            oracle = direct_scan(dataset / "documents", query["query"])
            if set(ranked) != oracle:
                raise AssertionError(f"Disaccordo con scansione diretta: {size}/{query['id']}")
            relevant = (set(qrels[query["id"]]) if query["kind"] == "thematic" else oracle)
            per_query.append({"size": size, "query_id": query["id"], "kind": query["kind"],
                              "query": query["query"], "oracle_match": True,
                              **retrieval_metrics(ranked, relevant)})
        aggregates = {}
        for kind in ("functional", "thematic"):
            rows = [row for row in per_query if row["size"] == size and row["kind"] == kind]
            means = {}
            for metric in ("precision_at_10", "recall_at_10", "precision", "recall", "f1", "ap_at_10"):
                values = [row[metric] for row in rows if row[metric] is not None]
                means["map_at_10" if metric == "ap_at_10" else metric] = (
                    statistics.mean(values) if values else None)
            means["queries"] = len(rows)
            means["queries_with_relevant"] = sum(row["relevant"] > 0 for row in rows)
            aggregates[kind] = means
        write_json(collection / "ranking.json", runs)
        collections.append({"size": size, "dataset_sha256": dataset_hash,
                            "index_sha256": sha256(collection / "index.json"),
                            "ranking_sha256": sha256(collection / "ranking.json"),
                            "index_bytes": (collection / "index.json").stat().st_size,
                            "aggregates": aggregates})
        print(f"Valutazione {size}: {len(queries)} query concordano con la scansione diretta", flush=True)
    deterministic = {"project_version": __version__, "configuration": config,
                     "analyzers": ANALYZER_CONFIG, "collections": collections, "per_query": per_query}
    write_json(output / "results" / "deterministic.json", deterministic)
    csv_file(output / "results" / "metrics.csv", per_query)
    timings = summarize_timings(samples)
    write_json(output / "results" / "observed.json",
               {"environment": environment(), "configuration": config, "analyzers": ANALYZER_CONFIG,
                "deterministic_results_sha256": sha256(output / "results" / "deterministic.json"),
                "dataset_hashes": {str(c["size"]): c["dataset_sha256"] for c in collections},
                "timing_protocol": "warm filesystem caches; ordered sequential repetitions; no warm-up; ns",
                "samples": samples, "timing_summary": timings})
    csv_file(output / "results" / "timing_samples.csv", samples)
    csv_file(output / "results" / "timing_summary.csv", timings)
    write_json(output / "results" / "checksums.json", {
        name: sha256(output / "results" / name) for name in ("deterministic.json", "metrics.csv")})
    return deterministic
