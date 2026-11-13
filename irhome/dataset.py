"""Inventario e statistiche del corpus locale; nessun download o giudizio esterno."""
from collections import Counter, defaultdict
import csv
from pathlib import Path
import random

from .io import sha256, write_json

DEFAULT_DOCUMENTS = Path("corpus/documents")


def csv_rows(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path, rows, fields):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def document_paths(directory):
    directory = Path(directory).resolve()
    if not directory.is_dir():
        raise ValueError("Directory del corpus inesistente")
    paths = sorted((p for p in directory.rglob("*") if p.is_file() and p.suffix.lower() == ".txt"),
                   key=lambda p: p.relative_to(directory).as_posix())
    if not paths:
        raise ValueError("Corpus vuoto")
    return paths


def corpus_identity(directory):
    root = Path(directory).resolve()
    return {p.relative_to(root).as_posix(): sha256(p) for p in document_paths(root)}


def verify_corpus(directory=DEFAULT_DOCUMENTS, metadata="corpus/metadata.csv"):
    root = Path(directory).resolve()
    entries = csv_rows(metadata)
    actual = corpus_identity(root)
    if (len(entries) != len(actual) or len({e["doc_id"] for e in entries}) != len(entries)
            or len({e["filename"] for e in entries}) != len(entries)
            or actual != {e["filename"]: e["sha256"] for e in entries}):
        raise ValueError("Corpus diverso dai metadati congelati")
    for e in entries:
        if (root / e["filename"]).stat().st_size != int(e["size_bytes"]):
            raise ValueError("Dimensione documento incoerente")
    return entries


def analyze(directory=DEFAULT_DOCUMENTS, output="evaluation/dataset_analysis.json"):
    # La tokenizzazione statistica usa soltanto lo scanner indipendente.
    from .oracle import words
    entries = verify_corpus(directory)
    root = Path(directory)
    terms, pairs, document_frequency = Counter(), Counter(), Counter()
    duplicates = defaultdict(list)
    title_prefixes = 0
    for e in entries:
        text = (root / e["filename"]).read_text(encoding="utf-8")
        tokens = words(text)
        terms.update(tokens)
        document_frequency.update(set(tokens))
        pairs.update(" ".join(pair) for pair in zip(tokens, tokens[1:]))
        duplicates[e["sha256"]].append(e["filename"])
        title_prefixes += tokens[:len(words(e["title"]))] == words(e["title"])
    selected = list(range(1, 1401))
    random.Random(42).shuffle(selected)
    result = dict(documents=len(entries), bytes=sum(int(e["size_bytes"]) for e in entries),
                  tokens=sum(terms.values()), distinct_tokens=len(terms),
                  identical_content_groups=[v for v in duplicates.values() if len(v) > 1],
                  titles_present_in_metadata=sum(bool(e["title"].strip()) for e in entries),
                  content_starts_with_title_tokens=title_prefixes,
                  seed42_selected_ids_verified=sorted(selected[:300]) == sorted(int(e["doc_id"]) for e in entries),
                  most_frequent_terms=[dict(term=t, occurrences=n, documents=document_frequency[t])
                                       for t, n in terms.most_common(40)],
                  most_frequent_bigrams=[dict(expression=t, occurrences=n) for t,n in pairs.most_common(40)])
    write_json(output, result)
    return result
