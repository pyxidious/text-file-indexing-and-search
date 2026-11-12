"""Collezioni sintetiche deterministiche, con qrels derivati dalle etichette."""
import csv
import io
from pathlib import Path
import random

from .io import read_json, sha256, write_json

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "corpus"


def generate_dataset(output, count=600, seed=42):
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise ValueError("Il numero di documenti deve essere un intero positivo")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("Il seed deve essere intero")
    output = Path(output)
    docs = output / "documents"
    docs.mkdir(parents=True, exist_ok=True)
    # Nessuna cancellazione implicita: una collezione di diversa dimensione va in un'altra cartella.
    if (output / "manifest.json").exists():
        old = read_json(output / "manifest.json")
        if old["configuration"]["count"] != count or old["configuration"]["seed"] != seed:
            raise ValueError("Usare una directory diversa per count/seed differenti")
    source = read_json(SOURCE / "topics.json")
    queries = read_json(SOURCE / "queries.json")
    rng = random.Random(seed)  # Stato locale; nessuna dipendenza dal random globale.
    rows = []
    for i in range(count):
        topic = source["topics"][i % len(source["topics"]) ]
        heading = rng.choice(source["headings"])
        slug = topic["title"].replace(" ", "_")
        filename = f"{slug}_{heading.replace(' ', '_')}_{i + 1:06d}.txt"
        paragraphs = [rng.choice(source["openings"]).format(title=topic["title"])]
        for _ in range(rng.randint(3, 15)):
            # Il tema principale prevale; il lessico trasversale introduce ambiguità.
            if rng.random() < 0.70:
                paragraph = rng.choice(topic["sentences"])
            else:
                paragraph = rng.choice(source["shared"])
            paragraphs.append(paragraph)
        a, b, c = rng.sample(topic["terms"], 3)
        paragraphs.append(rng.choice(source["term_templates"]).format(a=a, b=b, c=c))
        (docs / filename).write_bytes(("\n\n".join(paragraphs) + "\n").encode("utf-8"))
        rows.append({"id": filename, "filename": filename, "topic": topic["id"]})
    actual = {p.name for p in docs.iterdir() if p.is_file()}
    if actual != {row["filename"] for row in rows}:
        raise ValueError("Directory documents con file estranei: usare una directory pulita")
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=["id", "filename", "topic"], lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    (output / "metadata.csv").write_bytes(buffer.getvalue().encode("utf-8"))
    write_json(output / "queries.json", queries)
    qrels = {q["id"]: {row["id"]: 1 for row in rows if row["topic"] == q["topic"]}
             for q in queries if q["kind"] == "thematic"}
    write_json(output / "qrels.json", qrels)
    files = sorted([p for p in docs.iterdir() if p.is_file()] +
                   [output / name for name in ("metadata.csv", "queries.json", "qrels.json")])
    manifest = {
        "format_version": 1,
        "configuration": {"seed": seed, "count": count, "generator_version": 1,
                          "topic_assignment": "round-robin", "encoding": "UTF-8", "newline": "LF"},
        "inputs": {name: sha256(SOURCE / name) for name in ("topics.json", "queries.json")},
        "files": {p.relative_to(output).as_posix(): sha256(p) for p in files},
    }
    write_json(output / "manifest.json", manifest)
    return manifest


def verify_dataset(output):
    output = Path(output).resolve()
    manifest = read_json(output / "manifest.json")
    for relative, expected in sorted(manifest["files"].items()):
        path = (output / relative).resolve()
        if output not in path.parents or sha256(path) != expected:
            raise ValueError(f"Hash o percorso non valido: {relative}")
    expected_docs = {name for name in manifest["files"] if name.startswith("documents/")}
    actual_docs = {p.relative_to(output).as_posix() for p in (output / "documents").rglob("*")
                   if p.is_file()}
    if actual_docs != expected_docs or len(actual_docs) != manifest["configuration"]["count"]:
        raise ValueError("Insieme dei documenti diverso dal manifest")
    return sha256(output / "manifest.json")
