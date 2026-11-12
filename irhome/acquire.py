"""Acquisizione una tantum tramite ir_datasets; snapshot locale verificato offline."""
import hashlib
from importlib.metadata import PackageNotFoundError, version
import os
from pathlib import Path
import re

from .io import read_json, sha256, write_json

IR_DATASETS_VERSION = "0.5.11"
UPSTREAM_MD5 = "1730f7be572d95a5a4b56c59a7b900a5"
SOURCE_URL = "http://ir.dcs.gla.ac.uk/resources/test_collections/cran/cran.tar.gz"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE = ROOT / "artifacts" / "cranfield-source"
DEFAULT_LOCK = ROOT / "config" / "cranfield.lock.json"
COUNTS = {"documents": 1400, "queries": 225, "qrels": 1837}
LEVEL_COUNTS = {-1: 225, 1: 128, 2: 387, 3: 734, 4: 363}


def check_dependency():
    try:
        found = version("ir_datasets")
    except PackageNotFoundError as error:
        raise RuntimeError("Installare le dipendenze con python -m pip install -r requirements.txt") from error
    if found != IR_DATASETS_VERSION:
        raise RuntimeError(f"Richiesto ir_datasets=={IR_DATASETS_VERSION}, trovato {found}")
    return found


def validate_records(records):
    if {key: len(records[key]) for key in COUNTS} != COUNTS:
        raise ValueError("Conteggi Cranfield diversi da 1400/225/1837")
    doc_ids = [doc["doc_id"] for doc in records["documents"]]
    query_ids = [query["query_id"] for query in records["queries"]]
    if set(doc_ids) != {str(i) for i in range(1, 1401)} or len(set(doc_ids)) != 1400:
        raise ValueError("ID documento non validi o duplicati")
    if set(query_ids) != {str(i) for i in range(1, 226)} or len(set(query_ids)) != 225:
        raise ValueError("ID query non validi o duplicati")
    for doc in records["documents"]:
        if not all(isinstance(doc[key], str) for key in ("doc_id", "title", "text", "author", "bib")):
            raise ValueError("Campi documento non testuali")
    source_ids = [q["source_query_id"] for q in records["queries"]]
    if len(set(source_ids)) != 225 or any(not isinstance(q["text"], str) for q in records["queries"]):
        raise ValueError("Query originali non valide")
    pairs, levels = set(), {level: 0 for level in LEVEL_COUNTS}
    for row in records["qrels"]:
        pair = row["query_id"], row["doc_id"]
        if (pair in pairs or pair[0] not in query_ids or pair[1] not in doc_ids
                or type(row["relevance"]) is not int or row["relevance"] not in levels):
            raise ValueError("Qrel duplicato o non valido")
        pairs.add(pair)
        levels[row["relevance"]] += 1
    if levels != LEVEL_COUNTS:
        raise ValueError("Distribuzione dei giudizi Cranfield inattesa")


def cache_lock(cache):
    cache = Path(cache)
    return {"dataset": "cranfield", "ir_datasets_version": IR_DATASETS_VERSION,
            "counts": COUNTS, "source_manifest_sha256": sha256(cache / "source-manifest.json"),
            "records_sha256": sha256(cache / "records.json"),
            "archive_sha256": sha256(cache / "cran.tar.gz")}


def load_snapshot(cache=DEFAULT_CACHE, lock=DEFAULT_LOCK):
    """Nessun import di ir_datasets e nessun accesso alla rete in questo percorso."""
    cache = Path(cache)
    expected = read_json(lock)
    if cache_lock(cache) != expected:
        raise ValueError("Snapshot diverso dal lock versionato; non viene riscaricato né riparato")
    manifest = read_json(cache / "source-manifest.json")
    for name, digest in manifest["files"].items():
        if name not in ("records.json", "cran.tar.gz") or sha256(cache / name) != digest:
            raise ValueError(f"Snapshot corrotto: {name}")
    records = read_json(cache / "records.json")
    validate_records(records)
    return records


def acquire(cache=DEFAULT_CACHE, lock=DEFAULT_LOCK, offline=False):
    cache = Path(cache)
    if (cache / "source-manifest.json").exists():
        return load_snapshot(cache, lock)
    if offline:
        raise FileNotFoundError("Snapshot locale assente: eseguire una prima acquisizione online")
    if any((cache / name).exists() for name in ("records.json", "cran.tar.gz")):
        raise ValueError("Snapshot parziale: usare una nuova cache, nessuna sovrascrittura automatica")
    check_dependency()
    # Le cache del provider restano nel workspace; la variabile è impostata prima dell'import.
    os.environ["IR_DATASETS_HOME"] = str((cache / "provider").resolve())
    import ir_datasets

    dataset = ir_datasets.load("cranfield")
    documents = sorted((doc._asdict() for doc in dataset.docs_iter()), key=lambda d: int(d["doc_id"]))
    queries = sorted((query._asdict() for query in dataset.queries_iter()),
                     key=lambda q: int(q["query_id"]))
    # Cran.qry ha ID .I non contigui; il provider li riallinea ai qrels 1..225.
    # Conserviamo ANCHE gli ID nel file originale, evitando di perdere questa informazione.
    raw_queries = Path(dataset.queries_path()).read_text(encoding="utf-8")
    source_ids = re.findall(r"^\.I\s+(\d+)\s*$", raw_queries, flags=re.MULTILINE)
    if len(source_ids) != len(queries):
        raise ValueError("Impossibile associare gli ID originali delle query")
    for query, source_id in zip(queries, source_ids):
        query["source_query_id"] = source_id
    qrels = sorted((qrel._asdict() for qrel in dataset.qrels_iter()),
                   key=lambda r: (int(r["query_id"]), int(r["doc_id"]), r["iteration"]))
    records = {"documents": documents, "queries": queries, "qrels": qrels}
    validate_records(records)
    archive = cache / "provider" / "cranfield" / "cran.tar.gz"
    raw = archive.read_bytes()
    if hashlib.md5(raw).hexdigest() != UPSTREAM_MD5:
        raise ValueError("Archivio originale non conforme al checksum del provider")
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "cran.tar.gz").write_bytes(raw)
    write_json(cache / "records.json", records)
    write_json(cache / "source-manifest.json", {
        "dataset": "cranfield", "ir_datasets_version": IR_DATASETS_VERSION,
        "source_url": SOURCE_URL, "upstream_md5": UPSTREAM_MD5, "counts": COUNTS,
        "files": {name: sha256(cache / name) for name in ("cran.tar.gz", "records.json")}})
    # Solo il bootstrap di sviluppo usa lock=None; i comandi pubblici richiedono il lock.
    if lock is not None:
        return load_snapshot(cache, lock)
    return records
