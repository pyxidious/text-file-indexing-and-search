"""Proposta, revisione e congelamento lessicale. Nessun import del motore."""
from pathlib import Path

from .dataset import corpus_identity, csv_rows, document_paths, write_csv
from .io import read_json, sha256, write_json
from .oracle import NORMALIZATION, expression, scan_document

DEFAULT_QUERIES = Path("evaluation/queries.csv")
DEFAULT_OUTPUT = Path("evaluation")
REVIEW_FIELDS = ["query_id", "query", "doc_id", "filename", "proposed_label", "excerpt",
                 "present_terms", "reviewed", "manual_label", "reason"]
POSITIVE_FIELDS = ["query_id", "doc_id"]


def load_queries(path=DEFAULT_QUERIES):
    queries = csv_rows(path)
    if len(queries) != 10 or len({q["query_id"] for q in queries}) != 10:
        raise ValueError("Richieste esattamente 10 query con ID univoci")
    for query in queries:
        if not query["query_id"].strip() or query["field"] not in ("nome", "contenuto"):
            raise ValueError("ID o campo non valido")
        expression(query["expression"], query["type"])
    return queries


def identity(documents, queries):
    return dict(corpus=corpus_identity(documents), queries_sha256=sha256(queries),
                normalization=NORMALIZATION,
                scanner_sha256=sha256(Path(__file__).with_name("oracle.py")),
                procedure_sha256=sha256(__file__))


def propose(documents, queries=DEFAULT_QUERIES, output=DEFAULT_OUTPUT):
    output = Path(output)
    if (output / "frozen.json").exists():
        raise ValueError("Ground truth congelata: usare una nuova directory per altre proposte")
    query_list = load_queries(queries)
    paths = document_paths(documents)
    current = identity(documents, queries)
    rows, positives, counts = [], [], {}
    root = Path(documents).resolve()
    for q in query_list:
        terms = expression(q["expression"], q["type"])
        count = 0
        for path in paths:
            doc_id = path.relative_to(root).as_posix()
            label, excerpt, present = scan_document(path, q["field"], terms, q["type"] == "phrase")
            rows.append(dict(query_id=q["query_id"], query=q["field"] + " " + q["expression"],
                             doc_id=doc_id, filename=path.name, proposed_label=label,
                             excerpt=excerpt, present_terms=present, reviewed="", manual_label="", reason=""))
            if label:
                positives.append(dict(query_id=q["query_id"], doc_id=doc_id))
                count += 1
        counts[q["query_id"]] = count
    # Mai sovrascrivere revisioni umane o una proposta proveniente da input diversi.
    review = output / "review.csv"
    if review.exists():
        previous = read_json(output / "proposed.json")
        if previous["identity"] != current:
            raise ValueError("Input cambiati: usare una nuova directory di revisione")
        existing = csv_rows(review)
        fixed = [k for k in REVIEW_FIELDS if k not in ("reviewed", "manual_label", "reason")]
        if len(existing) != len(rows) or any(any(a[k] != str(b[k]) for k in fixed)
                                           for a,b in zip(existing, rows)):
            raise ValueError("Le proposte nella revisione sono cambiate")
    else:
        write_csv(review, rows, REVIEW_FIELDS)
    write_csv(output / "proposed_positives.csv", positives, POSITIVE_FIELDS)
    report = dict(status="automatically_proposed_not_human_validated", identity=current,
                  documents=len(paths), checks=len(rows), positives=counts,
                  proposed_positives_sha256=sha256(output / "proposed_positives.csv"))
    write_json(output / "proposed.json", report)
    return report


def freeze(documents, queries=DEFAULT_QUERIES, output=DEFAULT_OUTPUT, *, reviewer, approval_note):
    output = Path(output)
    if not reviewer.strip() or not approval_note.strip():
        raise ValueError("Indicare revisore umano e nota di approvazione")
    if (output / "frozen.json").exists() or (output / "final_positives.csv").exists():
        raise ValueError("Congelamento esistente: nessuna sovrascrittura")
    proposal = read_json(output / "proposed.json")
    current = identity(documents, queries)
    if (proposal["identity"] != current or proposal["proposed_positives_sha256"] !=
            sha256(output / "proposed_positives.csv")):
        raise ValueError("Input o proposte diversi dalla scansione iniziale")
    qs = load_queries(queries)
    paths = document_paths(documents)
    expected = {(q["query_id"], p.relative_to(Path(documents).resolve()).as_posix())
                for q in qs for p in paths}
    proposed = {(r["query_id"],r["doc_id"]) for r in csv_rows(output / "proposed_positives.csv")}
    seen, positives = set(), []
    query_text = {q["query_id"]: q["field"] + " " + q["expression"] for q in qs}
    for r in csv_rows(output / "review.csv"):
        pair = r["query_id"], r["doc_id"]
        if pair not in expected or pair in seen:
            raise ValueError("Coppia duplicata o esterna al corpus/query")
        seen.add(pair)
        if (r["query"] != query_text[pair[0]] or r["filename"] != Path(pair[1]).name
                or r["proposed_label"] != str(int(pair in proposed))):
            raise ValueError("Identita o proposta alterata nel CSV di revisione")
        if r["reviewed"] != "1" or r["manual_label"] not in ("", "0", "1"):
            raise ValueError("Ogni coppia deve essere revisionata (reviewed=1); etichette solo 0/1")
        label = r["manual_label"] or r["proposed_label"]
        if label != r["proposed_label"] and not r["reason"].strip():
            raise ValueError("Ogni correzione richiede una motivazione lessicale")
        if label == "1":
            positives.append(dict(query_id=pair[0], doc_id=pair[1]))
    if seen != expected:
        raise ValueError("Revisione incompleta: mancano coppie query-documento")
    write_csv(output / "final_positives.csv", sorted(positives, key=lambda r:(r["query_id"],r["doc_id"])), POSITIVE_FIELDS)
    frozen = dict(status="human_validated_frozen", reviewer=reviewer, approval_note=approval_note,
                  identity=current, checks=len(seen),
                  review_sha256=sha256(output / "review.csv"),
                  final_positives_sha256=sha256(output / "final_positives.csv"))
    write_json(output / "frozen.json", frozen)
    return frozen


def load_frozen(documents, queries=DEFAULT_QUERIES, output=DEFAULT_OUTPUT):
    output = Path(output)
    if not (output / "frozen.json").exists():
        raise ValueError("Ground truth non validata: completare la revisione umana e freeze prima di valutare")
    frozen = read_json(output / "frozen.json")
    if (frozen["status"] != "human_validated_frozen" or frozen["identity"] != identity(documents, queries)
            or frozen["final_positives_sha256"] != sha256(output / "final_positives.csv")
            or frozen["review_sha256"] != sha256(output / "review.csv")):
        raise ValueError("Ground truth o input modificati dopo il congelamento")
    relevant = {q["query_id"]: set() for q in load_queries(queries)}
    for row in csv_rows(output / "final_positives.csv"):
        if row["query_id"] not in relevant or row["doc_id"] not in frozen["identity"]["corpus"]:
            raise ValueError("Positivo estraneo al corpus/query")
        if row["doc_id"] in relevant[row["query_id"]]:
            raise ValueError("Positivo duplicato")
        relevant[row["query_id"]].add(row["doc_id"])
    return relevant
