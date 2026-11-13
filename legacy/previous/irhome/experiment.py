"""Preparazione Cranfield 300, statistiche e primitive del protocollo sperimentale."""
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
from .dataset import ROOT, prepare_dataset, verify_dataset
from .engine import SearchEngine
from .io import read_json, sha256, write_json
from .oracle import direct_scan
from .strategies import validate_strategy

FUNCTIONAL_QUERIES = ROOT / "corpus" / "functional_queries.json"


def validate_config(config):
    if config.get("dataset") != "cranfield" or config.get("main_size") != 300:
        raise ValueError("Il benchmark principale richiede il sottoinsieme di 300 documenti")
    sizes = config["sizes"]
    if (not isinstance(sizes, list) or not sizes or
            any(type(n) is not int or not 1 <= n <= 300 for n in sizes) or
            len(sizes) != len(set(sizes)) or 300 not in sizes):
        raise ValueError("Dimensioni distinte in 1..300, inclusa 300, richieste")
    if type(config["seed"]) is not int or type(config["query_split_seed"]) is not int:
        raise ValueError("Seed interi richiesti")
    if config["development_fraction"] != 0.2:
        raise ValueError("Protocollo fissato a development 20%")
    expected_rule = "max development macro F1@10; ties: Recall@10, MAP@10, declared strategy order"
    if config["selection_rule"] != expected_rule:
        raise ValueError("Criterio di selezione diverso dal protocollo implementato")
    if len({s["id"] for s in config["strategies"]}) != len(config["strategies"]):
        raise ValueError("Identificativi strategia duplicati")
    for spec in config["strategies"]:
        validate_strategy(spec["mode"], spec["minimum_should_match"])
    if config["strategies"][0]["mode"] != "or":
        raise ValueError("La prima strategia deve essere la baseline OR originale")
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
    identity = {"dataset": "cranfield", "protocol_version": 3}
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
            prepare_dataset(collection / "dataset", records, size, source_sha, config["seed"])
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


def check_functional(engine, dataset, strategies=None):
    checks = []
    specs = strategies or [{"id": "or_original", "mode": "or", "minimum_should_match": 0.5}]
    for spec in specs:
        for query in read_json(FUNCTIONAL_QUERIES):
            result = engine.search(query["query"], spec["mode"], spec["minimum_should_match"])
            oracle = direct_scan(Path(dataset) / "documents", query["query"],
                                 spec["mode"], spec["minimum_should_match"])
            if {row["id"] for row in result} != oracle:
                raise AssertionError(f"Scansione diretta discordante: {spec['id']}/{query['id']}")
            if spec["mode"] == "or" and bool(oracle) != (query["expect"] == "nonempty"):
                raise AssertionError(f"Aspettativa funzionale non soddisfatta: {query['id']}")
            checks.append({**query, "strategy": spec["id"], "oracle_match": True,
                           "retrieved": len(result), "engine_ids": sorted(oracle)})
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
    from .comparison import run_experiment
    return run_experiment(output, config, samples)
