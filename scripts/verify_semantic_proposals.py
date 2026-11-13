"""Verifica sola lettura di proposte, conferme, matrice e hash; nessuna metrica."""
import json
from collections import Counter
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from irhome.dataset import csv_rows, verify_corpus, corpus_identity
from irhome.io import read_json, sha256


def verify():
    root = Path("evaluation/semantic")
    output = root / "codex_proposals"
    manifest = read_json(output / "classification_manifest.json")
    initial = read_json(output / "run_inputs.json")
    entries = verify_corpus()
    if len(entries) != 300 or corpus_identity("corpus/documents") != initial["corpus"]:
        raise ValueError("Corpus alterato")
    for path, key in (("evaluation/queries.csv", "queries_sha256"),
                      (root / "criteria.csv", "criteria_sha256"),
                      ("corpus/metadata.csv", "metadata_sha256")):
        if sha256(path) != initial[key]:
            raise ValueError("Input alterato: " + str(path))
    for path, digest in initial["protected"].items():
        if Path(path).name not in ("semantic.py", "evaluation.py") and sha256(path) != digest:
            raise ValueError("Componente protetto alterato: " + path)
    for name, digest in manifest["output_sha256"].items():
        if sha256(output / name) != digest:
            raise ValueError("Output diverso dal manifest: " + name)
    for name, digest in manifest["batch_sha256"].items():
        if sha256(output / name) != digest:
            raise ValueError("Blocco alterato: " + name)
    rows = csv_rows(output / "complete_labels.csv")
    queries = [q["query_id"] for q in csv_rows("evaluation/queries.csv")]
    expected = {(e["filename"], q) for e in entries for q in queries}
    lookup = {(r["doc_id"], r["query_id"]): r for r in rows}
    if len(rows) != 3000 or len(lookup) != 3000 or set(lookup) != expected:
        raise ValueError("Copertura query-documento non valida")
    if any(r["proposed_label"] not in ("0", "1") or not r["reason"].strip()
           or r["confidence"] not in ("alta", "media", "bassa") for r in rows):
        raise ValueError("Giudizio non valido")
    matrix = csv_rows(root / "annotations.csv")
    values = {(r["doc_id"], q): r[q] for r in matrix for q in queries}
    if len(matrix) != 300 or set(values) != expected:
        raise ValueError("Matrice non valida")
    provenance = csv_rows(root / "provenance.csv")
    prov = {(r["doc_id"], r["query_id"]): r for r in provenance}
    if len(provenance) != 3000 or set(prov) != expected:
        raise ValueError("Provenienza incompleta o duplicata")
    for pair in expected:
        if (values[pair] not in ("0", "1") or prov[pair]["effective_label"] != values[pair]
                or prov[pair]["proposed_label"] != lookup[pair]["proposed_label"]):
            raise ValueError("Matrice/provenienza/proposta incoerenti")
    for name, path in (("annotations_sha256", root / "annotations.csv"),
                       ("provenance_sha256", root / "provenance.csv")):
        if sha256(path) != manifest[name]:
            raise ValueError("Hash di matrice o provenienza cambiato")
    baseline = csv_rows(output / "history/v2_before_human_confirmation/annotations_before_import.csv")
    for r in baseline:
        for q in queries:
            if r[q] and values[r["doc_id"], q] != r[q]:
                correction = any(c["doc_id"] == r["doc_id"] and c["query_id"] == q
                                 and c["corrected_label"] == values[r["doc_id"], q]
                                 for c in csv_rows(output / "human_corrections.csv"))
                if not correction:
                    raise ValueError("Etichetta preesistente cambiata senza correzione registrata")
    calibration = csv_rows(output / "calibration_labels.csv")
    if len(calibration) != 200 or any(lookup[r["doc_id"], r["query_id"]] != r for r in calibration):
        raise ValueError("Proposte di calibrazione alterate")
    confirmations = csv_rows(output / "calibration_review.csv")
    if len(confirmations) != 38 or any(r["human_label"] != r["proposed_label"]
            or r["corrected_label"] or r["reviewed_by"] != "utente_chat"
            or r["reviewed_at"] != "2026-11-13" for r in confirmations):
        raise ValueError("Conferme di calibrazione incoerenti")
    review = csv_rows(output / "final_review.csv")
    review_pairs = {(r["doc_id"], r["query_id"]) for r in review}
    required = {(r["doc_id"], r["query_id"]) for r in read_json(output / "review_manifest.json")["required_pairs"]}
    if len(review_pairs) != len(review) or review_pairs != required:
        raise ValueError("Coda di revisione alterata")
    uncertain = {(r["doc_id"], r["query_id"]) for r in rows if r["confidence"] != "alta"}
    if not uncertain <= review_pairs:
        raise ValueError("Casi incerti esclusi dalla coda")
    return dict(documents=300, judgments=3000,
        positive_by_query={q:sum(r["proposed_label"] == "1" for r in rows if r["query_id"] == q) for q in queries},
        confidence=dict(Counter(r["confidence"] for r in rows)),
        human_confirmed_pairs=sum(r["human_confirmed"] == "1" for r in provenance),
        review_queue=len(review), review_pending=sum(not r["human_label"] for r in review),
        frozen=(root / "frozen.json").exists())


if __name__ == "__main__":
    try:
        print(json.dumps(verify(), ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError) as error:
        raise SystemExit(str(error))
