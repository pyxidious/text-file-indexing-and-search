"""Annotazione semantica umana, indipendente da ricerca e scanner lessicale."""
import csv
import re
import os
from pathlib import Path

from .dataset import csv_rows, verify_corpus, write_csv
from .ground_truth import load_queries
from .io import read_json, sha256, write_json

DEFAULT_OUTPUT = "evaluation/semantic"
DEFAULT_METADATA = "corpus/metadata.csv"
STATUS = "semantic_ground_truth_human_annotated"


def atomic_csv(path, rows, fields):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        write_csv(temporary, rows, fields)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def inputs(documents, queries, output, metadata, expected_documents):
    entries = verify_corpus(documents, metadata)
    if len(entries) != expected_documents:
        raise ValueError(f"Richiesti {expected_documents} documenti, trovati {len(entries)}")
    qs = load_queries(queries)
    if any(not re.fullmatch(r"[A-Za-z0-9_-]+", q["query_id"]) for q in qs):
        raise ValueError("ID query non valido per i file dei positivi")
    criteria_path = Path(output) / "criteria.csv"
    criteria = csv_rows(criteria_path)
    if len(criteria) != len(qs) or {r["query_id"] for r in criteria} != {q["query_id"] for q in qs}:
        raise ValueError("Criteri mancanti o duplicati")
    by_id = {r["query_id"]: r for r in criteria}
    for q in qs:
        r = by_id[q["query_id"]]
        if (r["field"] != q["field"] or r["expression"] != q["expression"]
                or any(not r[k].strip() for k in ("information_need", "relevant", "not_relevant"))):
            raise ValueError("Criteri incompleti o diversi dalle query")
    identity = dict(corpus={r["filename"]: r["sha256"] for r in entries},
                    queries_sha256=sha256(queries), criteria_sha256=sha256(criteria_path),
                    metadata_sha256=sha256(metadata), documents=expected_documents)
    return entries, qs, by_id, identity


def fields(qs):
    return ["doc_id", "source_file", "title"] + [q["query_id"] for q in qs]


def checked_rows(output, entries, qs, complete=False):
    path = Path(output) / "annotations.csv"
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != fields(qs):
            raise ValueError("Colonne della matrice non valide")
        rows = list(reader)
    expected = {e["filename"]: e for e in entries}
    seen = set()
    for r in rows:
        doc_id = r["doc_id"]
        if doc_id not in expected or doc_id in seen:
            raise ValueError("Documento estraneo o duplicato")
        seen.add(doc_id)
        if (None in r or r["source_file"] != doc_id or r["title"] != expected[doc_id]["title"]):
            raise ValueError("Riferimento o titolo alterato")
        for q in qs:
            label = r[q["query_id"]]
            if label not in ("0", "1", "", "?"):
                raise ValueError("Etichetta non valida: usare 0, 1, vuoto oppure ?")
            if complete and label not in ("0", "1"):
                raise ValueError("Annotazioni incomplete: giudizi mancanti o dubbi")
    if seen != set(expected):
        raise ValueError("Matrice incompleta: documenti mancanti")
    return rows


def prepare(documents="corpus/documents", queries="evaluation/queries.csv", output=DEFAULT_OUTPUT,
            metadata=DEFAULT_METADATA, *, expected_documents=300):
    output = Path(output)
    if (output / "frozen.json").exists() or (output / "final_positives.csv").exists():
        raise ValueError("Ground truth congelata: usare una nuova directory")
    entries, qs, criteria, identity = inputs(documents, queries, output, metadata, expected_documents)
    manifest = output / "prepared.json"
    if manifest.exists():
        if read_json(manifest)["identity"] != identity:
            raise ValueError("Input modificati rispetto alla preparazione")
        checked_rows(output, entries, qs)
    else:
        if (output / "annotations.csv").exists():
            raise ValueError("Matrice esistente senza manifest: nessuna sovrascrittura")
        rows = [dict(doc_id=e["filename"], source_file=e["filename"], title=e["title"],
                     **{q["query_id"]: "" for q in qs}) for e in entries]
        atomic_csv(output / "annotations.csv", rows, fields(qs))
        write_json(manifest, dict(status="semantic_annotation_pending", identity=identity))
    return entries, qs, criteria, identity


def progress(rows, qs):
    labels = [r[q["query_id"]] for r in rows for q in qs]
    return dict(total=len(labels), complete=sum(v in ("0", "1") for v in labels),
                missing=labels.count(""), doubtful=labels.count("?"))


def annotate(documents="corpus/documents", queries="evaluation/queries.csv", output=DEFAULT_OUTPUT,
             metadata=DEFAULT_METADATA, *, expected_documents=300, input_fn=input, print_fn=print):
    entries, qs, criteria, _ = prepare(documents, queries, output, metadata,
                                        expected_documents=expected_documents)
    rows = checked_rows(output, entries, qs)
    qids = [q["query_id"] for q in qs]
    index = next((i for i, r in enumerate(rows) if any(r[k] in ("", "?") for k in qids)), 0)
    while True:
        print_fn(str(progress(rows, qs)))
        r = rows[index]
        print_fn(f"Documento {index + 1}/{len(rows)} | ID/nome: {r['doc_id']}\nTitolo: {r['title']}")
        print_fn((Path(documents) / r["source_file"]).read_text(encoding="utf-8"))
        for q in qs:
            c = criteria[q["query_id"]]
            print_fn(f"{q['query_id']} [{q['field']}] {q['expression']}: {c['information_need']}\n"
                     f"  1: {c['relevant']}\n  0: {c['not_relevant']}")
        print_fn("Per nome giudicare SOLO il basename senza estensione, mai il titolo dei metadati; per contenuto usare il testo. Nessun vincolo di termini esatti.")
        print_fn("Attuali: " + " ".join(r[k] or "_" for k in qids))
        try:
            answer = input_fn("10 etichette (01?_ compatte o separate; _=vuoto, -=mantieni); n/p; g NUMERO o ID; q: ").strip()
        except (EOFError, KeyboardInterrupt):
            print_fn("Progresso salvato ai documenti confermati precedenti.")
            return
        if answer == "q":
            return
        if answer in ("n", "p"):
            index = (index + (1 if answer == "n" else -1)) % len(rows)
            continue
        if answer.startswith("g "):
            target = answer[2:].strip()
            found = next((i for i, row in enumerate(rows) if row["doc_id"] == target), None)
            if found is None and target.isdecimal() and 1 <= int(target) <= len(rows):
                found = int(target) - 1
            if found is None:
                print_fn("Documento non trovato")
            else:
                index = found
            continue
        labels = answer.split() if len(answer.split()) > 1 else list(answer)
        if len(labels) != len(qids) or any(v not in "01?_-" or len(v) != 1 for v in labels):
            print_fn("Inserire esattamente dieci etichette valide")
            continue
        for k, v in zip(qids, labels):
            if v != "-":
                r[k] = "" if v == "_" else v
        atomic_csv(Path(output) / "annotations.csv", rows, fields(qs))
        print_fn("Salvato. " + str(progress(rows, qs)))
        if index == len(rows) - 1:
            return
        index += 1


def freeze(documents="corpus/documents", queries="evaluation/queries.csv", output=DEFAULT_OUTPUT,
           metadata=DEFAULT_METADATA, *, reviewer, approval_note, expected_documents=300):
    if not reviewer.strip() or not approval_note.strip():
        raise ValueError("Indicare revisore e nota reali")
    entries, qs, _, identity = prepare(documents, queries, output, metadata,
                                       expected_documents=expected_documents)
    rows = checked_rows(output, entries, qs, complete=True)
    output = Path(output)
    protocol_status, supervision, provenance_hashes = STATUS, None, {}
    if ((output / "provenance.csv").exists() or
            (output / "codex_proposals/classification_manifest.json").exists()):
        from .assisted_freeze import snapshot, STATUS as ASSISTED_STATUS
        supervision, provenance_hashes = snapshot(output, rows, qs, identity)
        protocol_status = ASSISTED_STATUS
    positives = [dict(query_id=q["query_id"], doc_id=r["doc_id"])
                 for q in qs for r in sorted(rows, key=lambda r: r["doc_id"]) if r[q["query_id"]] == "1"]
    atomic_csv(output / "final_positives.csv", positives, ["query_id", "doc_id"])
    per_query = {}
    for q in qs:
        path = output / f"positives_{q['query_id']}.csv"
        atomic_csv(path, [r for r in positives if r["query_id"] == q["query_id"]], ["query_id", "doc_id"])
        per_query[path.name] = sha256(path)
    frozen = dict(status=protocol_status, identity=identity, reviewer=reviewer, approval_note=approval_note,
                  supervision=supervision, provenance_sha256=provenance_hashes,
                  per_query_positives_sha256=per_query,
                  checks=len(rows)*len(qs), annotations_sha256=sha256(output / "annotations.csv"),
                  prepared_sha256=sha256(output / "prepared.json"),
                  final_positives_sha256=sha256(output / "final_positives.csv"))
    write_json(output / "frozen.json", frozen)
    return frozen


def load_frozen(documents, queries="evaluation/queries.csv", output=DEFAULT_OUTPUT,
                metadata=DEFAULT_METADATA, *, expected_documents=300):
    output = Path(output)
    if not (output / "frozen.json").exists():
        raise ValueError("Ground truth semantica non congelata: completare annotazioni e freeze")
    frozen = read_json(output / "frozen.json")
    entries, qs, _, identity = inputs(documents, queries, output, metadata, expected_documents)
    from .assisted_freeze import STATUS as ASSISTED_STATUS
    if (frozen["status"] not in (STATUS, ASSISTED_STATUS) or frozen["identity"] != identity
            or read_json(output / "prepared.json")["identity"] != identity
            or any(frozen[key + "_sha256"] != sha256(output / filename) for key, filename in
                   (("annotations", "annotations.csv"), ("prepared", "prepared.json"),
                    ("final_positives", "final_positives.csv")))):
        raise ValueError("Ground truth o input modificati dopo il congelamento")
    rows = checked_rows(output, entries, qs, complete=True)
    if frozen["status"] == ASSISTED_STATUS:
        from .assisted_freeze import snapshot
        supervision, hashes = snapshot(output, rows, qs, identity)
        if supervision != frozen["supervision"] or hashes != frozen["provenance_sha256"]:
            raise ValueError("Provenienza modificata dopo il congelamento")
    elif ((output / "provenance.csv").exists() or
            (output / "codex_proposals/classification_manifest.json").exists()):
        raise ValueError("Protocollo assistito non dichiarato nel congelamento")
    relevant = {q["query_id"]: {r["doc_id"] for r in rows if r[q["query_id"]] == "1"} for q in qs}
    expected = [dict(query_id=q["query_id"], doc_id=d) for q in qs for d in sorted(relevant[q["query_id"]])]
    per_query = frozen["per_query_positives_sha256"]
    if set(per_query) != {f"positives_{q['query_id']}.csv" for q in qs}:
        raise ValueError("File dei positivi per query mancanti")
    for q in qs:
        name = f"positives_{q['query_id']}.csv"
        if (sha256(output / name) != per_query[name] or csv_rows(output / name) !=
                [r for r in expected if r["query_id"] == q["query_id"]]):
            raise ValueError("Positivi per query modificati dopo il congelamento")
    if csv_rows(output / "final_positives.csv") != expected:
        raise ValueError("Positivi incoerenti con le annotazioni")
    return relevant
