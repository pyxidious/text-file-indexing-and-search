"""Evidenza minima della conversione Cranfield, non una pipeline di acquisizione.

Funzioni estratte senza modifica dalla sorgente storica identificata in
cranfield_origin.json. document_bytes riprende l'operazione originale di export.
Nessun accesso a query o giudizi ufficiali; nessun download.
"""
import csv
import hashlib
import json
from pathlib import Path
import random
import re
import unicodedata

IR_DATASETS_VERSION = "0.5.11"
SOURCE_URL = "http://ir.dcs.gla.ac.uk/resources/test_collections/cran/cran.tar.gz"
UPSTREAM_MD5 = "1730f7be572d95a5a4b56c59a7b900a5"

def normalized_newlines(text):
    return text.replace("\r\n", "\n").replace("\r", "\n")

def document_filename(doc_id, title):
    if not isinstance(doc_id, str) or not doc_id.isdecimal() or int(doc_id) < 1:
        raise ValueError("ID documento numerico positivo richiesto")
    title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "_", title).strip("_")[:80].rstrip("_") or "untitled"
    return f"{int(doc_id):04d}_{slug}.txt"

def select_documents(documents, count=300, seed=42):
    """Permutazione uniforme, indipendente da query, giudizi e risultati."""
    if type(seed) is not int or type(count) is not int or not 1 <= count <= len(documents):
        raise ValueError("Seed intero e dimensione valida richiesti")
    ordered = sorted(documents, key=lambda d: int(d["doc_id"]))
    if len({d["doc_id"] for d in ordered}) != len(ordered):
        raise ValueError("ID documento duplicati")
    random.Random(seed).shuffle(ordered)
    return sorted(ordered[:count], key=lambda d: int(d["doc_id"]))


def document_bytes(doc):
    # Operazione ripresa da prepare_dataset, senza titolo, strip o newline aggiunti.
    content = normalized_newlines(doc["text"]).encode("utf-8")
    return content


def verify_local():
    root = Path(__file__).resolve().parents[1]
    with (root / "corpus/metadata.csv").open(encoding="utf-8", newline="") as stream:
        entries = list(csv.DictReader(stream))
    expected = select_documents([dict(doc_id=str(i)) for i in range(1, 1401)])
    if [int(e["doc_id"]) for e in entries] != [int(e["doc_id"]) for e in expected]:
        raise ValueError("Selezione diversa da Random(42).shuffle e primi300")
    for e in entries:
        if e["filename"] != document_filename(e["doc_id"], e["title"]):
            raise ValueError("Filename diverso dalla conversione storica")
        raw = (root / "corpus/documents" / e["filename"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != e["sha256"] or len(raw) != int(e["size_bytes"]):
            raise ValueError("Hash o dimensione incoerenti")
        if document_bytes(dict(text=raw.decode("utf-8"))) != raw:
            raise ValueError("Il testo locale non e UTF-8 con newline LF")
    return dict(documents=len(entries), selection_verified=True, filenames_verified=True, hashes_verified=True)


if __name__ == "__main__":
    print(json.dumps(verify_local(), indent=2))
