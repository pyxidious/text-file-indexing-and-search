"""Trasformazione deterministica di Cranfield in file TXT, senza dipendenze IR."""
import csv
import io
from pathlib import Path
import re
import unicodedata

from .io import read_json, sha256, write_json

ROOT = Path(__file__).resolve().parents[1]
FILENAME_RULE = "NFKD ASCII lower; non [a-z0-9] -> _; trim; first 80 chars; ID padded to 4"


def normalized_newlines(text):
    return text.replace("\r\n", "\n").replace("\r", "\n")


def document_filename(doc_id, title):
    if not isinstance(doc_id, str) or not doc_id.isdecimal() or int(doc_id) < 1:
        raise ValueError("ID documento numerico positivo richiesto")
    title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "_", title).strip("_")[:80].rstrip("_") or "untitled"
    return f"{int(doc_id):04d}_{slug}.txt"


def prepare_dataset(output, records, count=1400, source_sha256=None):
    if type(count) is not int or not 1 <= count <= len(records["documents"]):
        raise ValueError("Numero documenti non valido")
    output = Path(output)
    docs = output / "documents"
    selected = sorted(records["documents"], key=lambda d: int(d["doc_id"]))[:count]
    ids = [doc["doc_id"] for doc in selected]
    if len(ids) != len(set(ids)):
        raise ValueError("ID documento duplicati")
    entries = []
    for doc in selected:
        filename = document_filename(doc["doc_id"], doc["title"])
        entries.append({"doc_id": doc["doc_id"], "engine_id": filename, "filename": filename,
                        "path": f"documents/{filename}", "title": doc["title"],
                        "author": doc["author"], "bib": doc["bib"]})
    filenames = [entry["filename"] for entry in entries]
    if len(set(filenames)) != count:
        raise ValueError("Collisione nei filename")
    docs.mkdir(parents=True, exist_ok=True)
    actual = {p.relative_to(docs).as_posix() for p in docs.rglob("*") if p.is_file()}
    if actual - set(filenames):
        raise ValueError("File estranei nella destinazione; usare una nuova directory")
    for doc, entry in zip(selected, entries):
        # Nessun titolo aggiunto, strip, traduzione o newline finale aggiunto.
        content = normalized_newlines(doc["text"]).encode("utf-8")
        (output / entry["path"]).write_bytes(content)
        entry["sha256"] = sha256(output / entry["path"])
    buffer = io.StringIO(newline="")
    fields = ["doc_id", "engine_id", "filename", "path", "title", "author", "bib", "sha256"]
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(entries)
    (output / "metadata.csv").write_bytes(buffer.getvalue().encode("utf-8"))
    # Anche nei subset conserviamo tutti i giudizi originali; non vi calcoliamo metriche IR.
    queries = sorted(records["queries"], key=lambda q: int(q["query_id"]))
    qrels = sorted(records["qrels"], key=lambda r: (int(r["query_id"]), int(r["doc_id"]), r["iteration"]))
    write_json(output / "queries.json", queries)
    write_json(output / "qrels.json", qrels)
    paths = [output / entry["path"] for entry in entries]
    paths += [output / name for name in ("metadata.csv", "queries.json", "qrels.json")]
    manifest = {"format_version": 2, "dataset": "cranfield", "source_records_sha256": source_sha256,
                "configuration": {"count": count, "selection": "first N by numeric original doc_id",
                                  "filename_rule": FILENAME_RULE, "encoding": "UTF-8",
                                  "content": "text only; CRLF/CR -> LF; no added trailing newline"},
                "documents": entries, "queries_count": len(queries), "qrels_count": len(qrels),
                "qrels_scope": "full original collection, also for performance-only subsets",
                "files": {p.relative_to(output).as_posix(): sha256(p) for p in sorted(paths)}}
    write_json(output / "manifest.json", manifest)
    return manifest


def verify_dataset(output):
    output = Path(output).resolve()
    manifest = read_json(output / "manifest.json")
    if manifest["format_version"] != 2 or manifest["dataset"] != "cranfield":
        raise ValueError("Dataset incompatibile: atteso Cranfield formato 2")
    for relative, expected in sorted(manifest["files"].items()):
        path = (output / relative).resolve()
        if output not in path.parents or sha256(path) != expected:
            raise ValueError(f"Hash o percorso non valido: {relative}")
    entries = manifest["documents"]
    paths = {entry["path"] for entry in entries}
    actual = {p.relative_to(output).as_posix() for p in (output / "documents").rglob("*") if p.is_file()}
    if (actual != paths or len(paths) != manifest["configuration"]["count"] or
            len({entry["doc_id"] for entry in entries}) != len(entries) or
            len({entry["engine_id"] for entry in entries}) != len(entries)):
        raise ValueError("Documenti o mapping non conformi al manifest")
    for entry in entries:
        if (entry["path"] != "documents/" + entry["engine_id"] or
                manifest["files"].get(entry["path"]) != entry["sha256"]):
            raise ValueError("Mapping/hash documento incoerente")
    return sha256(output / "manifest.json")


def document_mapping(dataset):
    verify_dataset(dataset)
    return {entry["engine_id"]: entry["doc_id"]
            for entry in read_json(Path(dataset) / "manifest.json")["documents"]}
