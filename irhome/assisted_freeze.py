"""Controlli di provenienza per il congelamento del protocollo assistito."""
from pathlib import Path
from .dataset import csv_rows
from .io import read_json, sha256

STATUS = "semantic_ground_truth_codex_assisted_partially_supervised"


def snapshot(output, rows, qs, identity):
    output = Path(output)
    proposals = output / "codex_proposals"
    manifest = read_json(proposals / "classification_manifest.json")
    if manifest["identity"] != identity:
        raise ValueError("Input diversi dal protocollo assistito")
    label_path = proposals / "complete_labels.csv"
    if sha256(label_path) != manifest["proposals_sha256"]:
        raise ValueError("Proposte Codex modificate")
    expected = {(r["doc_id"], q["query_id"]): r[q["query_id"]] for r in rows for q in qs}
    automatic = {}
    for r in csv_rows(label_path):
        pair = r["doc_id"], r["query_id"]
        if pair in automatic or pair not in expected or r["proposed_label"] not in ("0", "1"):
            raise ValueError("Proposte duplicate o estranee")
        automatic[pair] = r["proposed_label"]
    if set(automatic) != set(expected):
        raise ValueError("Proposte incomplete")
    seen, confirmed = set(), set()
    for r in csv_rows(output / "provenance.csv"):
        pair = r["doc_id"], r["query_id"]
        if pair in seen or pair not in expected:
            raise ValueError("Provenienza duplicata o estranea")
        seen.add(pair)
        if (r["proposed_label"] != automatic[pair] or r["effective_label"] != expected[pair]
                or r["human_confirmed"] not in ("0", "1")):
            raise ValueError("Provenienza incoerente con proposte o matrice")
        if r["human_confirmed"] == "1":
            if not r["reviewer"].strip() or not r["confirmation_date"].strip():
                raise ValueError("Conferma senza revisore o data")
            confirmed.add(pair)
        elif expected[pair] != automatic[pair]:
            raise ValueError("Correzione priva di conferma umana")
    if seen != set(expected):
        raise ValueError("Provenienza incompleta")
    review_manifest = read_json(proposals / "review_manifest.json")
    required_list = [(r["doc_id"], r["query_id"]) for r in review_manifest["required_pairs"]]
    required = set(required_list)
    if len(required_list) != len(required) or not required <= set(expected):
        raise ValueError("Manifest revisione non valido")
    review = csv_rows(proposals / "final_review.csv")
    review_pairs = [(r["doc_id"], r["query_id"]) for r in review]
    if len(review_pairs) != len(set(review_pairs)) or set(review_pairs) != required:
        raise ValueError("Coda di revisione incompleta o alterata")
    for r in review:
        pair = r["doc_id"], r["query_id"]
        if r["proposed_label"] != automatic[pair]:
            raise ValueError("Proposta alterata nella coda")
        if (r["human_label"] not in ("0", "1") or not r["reviewed_by"].strip()
                or not r["reviewed_at"].strip() or not r["human_reason"].strip()):
            raise ValueError("Revisione mirata incompleta: confermare i casi pendenti prima del freeze")
        if r["human_label"] != expected[pair]:
            raise ValueError("Conferma della coda diversa dalla matrice: riconciliare esplicitamente")
        correction = "" if automatic[pair] == expected[pair] else expected[pair]
        if r["corrected_label"] != correction:
            raise ValueError("Correzione umana incoerente nella coda")
        confirmed.add(pair)
    # Questi hash congelano le attestazioni effettive, senza trasformarle in
    # una dichiarazione di revisione manuale dell'intero corpus.
    paths = [output / "provenance.csv", proposals / "classification_manifest.json", label_path,
             proposals / "final_review.csv", proposals / "review_manifest.json",
             proposals / "supervision.json", proposals / "human_corrections.csv",
             proposals / "calibration_review.csv"]
    hashes = {p.relative_to(output).as_posix(): sha256(p) for p in paths}
    return dict(protocol=STATUS, human_confirmed_pairs=len(confirmed),
                unconfirmed_pairs=len(expected)-len(confirmed), total_pairs=len(expected),
                full_manual_validation=False,
                description="Ground truth semantica proposta mediante Codex e parzialmente supervisionata da un revisore umano"), hashes
