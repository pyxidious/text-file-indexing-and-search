"""Persistenza di giudizi semantici redatti da Codex; nessun classificatore lessicale."""
from pathlib import Path
from .dataset import csv_rows, document_paths
from .io import read_json, sha256, write_json
from .semantic import atomic_csv

NEGATIVE = {
1: "Il nome non rende riconoscibile uno studio sostanziale di flusso supersonico.",
2: "Il nome non identifica uno studio della distribuzione spaziale di pressione.",
3: "Il nome non identifica chiaramente uno strato limite laminare.",
4: "Il nome non pone lo strato limite al centro dello studio.",
5: "Il nome non indica accoppiamento fra campo magnetico e moto di fluido conduttore.",
6: "Il testo non analizza sostanzialmente un flusso riconoscibile come supersonico.",
7: "Il testo non analizza una relazione fra pressione e velocita.",
8: "Il testo non sviluppa un'analisi di apporto/scambio di calore e comportamento termico.",
9: "Il testo non studia sostanzialmente trasferimento di calore.",
10: "Il testo non studia effetti della comprimibilita o del regime relativo al suono."
}


def record_batch(start, records, output="evaluation/semantic/codex_proposals", documents="corpus/documents",
                 annotations="evaluation/semantic/annotations.csv", provenance="evaluation/semantic/provenance.csv"):
    """I record contengono decisioni individuali gia redatte dopo lettura integrale.

    mask assegna esplicitamente dieci giudizi; why motiva ogni positivo e ogni
    incertezza. Per i negativi chiari si rende la sintesi fattuale del campo
    letta da Codex insieme al criterio escluso. Nessun matching genera etichette.
    """
    output = Path(output)
    root = Path(documents).resolve()
    selected = document_paths(documents)[start-1:start-1+len(records)]
    rows = []
    for record, path in zip(records, selected):
        if path.name[:4] != record["id"]:
            raise ValueError("Ordine o documento errato")
        mask = record["mask"]
        if len(mask) != 10 or any(c not in "01" for c in mask):
            raise ValueError("Servono dieci decisioni binarie esplicite")
        for i, label in enumerate(mask, 1):
            qid = f"Q{i:02d}"
            conf = record.get("confidence", {}).get(qid, "alta")
            why = record.get("why", {}).get(qid)
            if (label == "1" or conf != "alta") and not why:
                raise ValueError("Positivi e incertezze richiedono motivazione individuale")
            if conf not in ("alta", "media", "bassa"):
                raise ValueError("Confidenza non valida")
            if not why:
                why = ("Dal solo basename: " + record["n"] if i <= 5 else
                       "Dal testo integrale: " + record["t"]) + ". " + NEGATIVE[i]
            rows.append(dict(doc_id=path.relative_to(root).as_posix(), query_id=qid,
                             proposed_label=label, confidence=conf, reason=why))
    if len(rows) != len(records)*10:
        raise ValueError("Blocco fuori corpus")
    complete = csv_rows(output / "complete_labels.csv")
    old = {(r["doc_id"], r["query_id"]): r for r in complete}
    for r in rows:
        pair = r["doc_id"], r["query_id"]
        if pair in old and old[pair] != r:
            raise ValueError("Proposta esistente diversa: nessuna sovrascrittura")
        old[pair] = r
    batch = output / "batches" / f"{start:03d}_{start+len(records)-1:03d}.json"
    if batch.exists() and read_json(batch)["records"] != records:
        raise ValueError("Blocco gia salvato con decisioni diverse")
    write_json(batch, dict(start=start, documents=len(records), records=records,
                          method="decisioni semantiche individuali Codex, non etichette lessicali"))
    complete = sorted(old.values(), key=lambda r: (r["doc_id"], r["query_id"]))
    matrix = csv_rows(annotations)
    for doc in matrix:
        for i in range(1, 11):
            qid = f"Q{i:02d}"
            pair = doc["doc_id"], qid
            if pair in old:
                value = old[pair]["proposed_label"]
                if doc[qid] not in ("", value):
                    raise ValueError("Conflitto con annotazione esistente: importazione bloccata")
                doc[qid] = value
    prov = csv_rows(provenance)
    known = {(r["doc_id"], r["query_id"]) for r in prov}
    for r in rows:
        pair = r["doc_id"], r["query_id"]
        if pair not in known:
            prov.append(dict(doc_id=r["doc_id"], query_id=r["query_id"], proposed_label=r["proposed_label"],
                             effective_label=r["proposed_label"], source="codex_full_classification",
                             preexisting_label="", human_confirmed="0", reviewer="", confirmation_date="",
                             review_type="not_individually_confirmed"))
    atomic_csv(output / "complete_labels.csv", complete, list(complete[0]))
    atomic_csv(provenance, sorted(prov, key=lambda r: (r["doc_id"], r["query_id"])), list(prov[0]))
    atomic_csv(annotations, matrix, list(matrix[0]))
    write_json(output / "progress.json", dict(classified_documents=len(complete)//10,
        judgments=len(complete), complete_labels_sha256=sha256(output / "complete_labels.csv"),
        annotations_sha256=sha256(annotations), provenance_sha256=sha256(provenance)))
    return len(complete)


def import_review(output="evaluation/semantic"):
    """Importa soltanto giudizi esplicitamente compilati da un revisore.

    Non compila campi di revisione, non conferma righe vuote e non modifica
    le proposte originali. Una correzione richiede corrected_label esplicito.
    """
    output = Path(output)
    if (output / "frozen.json").exists():
        raise ValueError("Ground truth congelata")
    proposals = output / "codex_proposals"
    manifest_path = proposals / "classification_manifest.json"
    manifest = read_json(manifest_path)
    if sha256(proposals / "complete_labels.csv") != manifest["proposals_sha256"]:
        raise ValueError("Proposte originali modificate")
    review = csv_rows(proposals / "final_review.csv")
    matrix = csv_rows(output / "annotations.csv")
    by_doc = {r["doc_id"]: r for r in matrix}
    provenance = csv_rows(output / "provenance.csv")
    by_pair = {(r["doc_id"], r["query_id"]): r for r in provenance}
    corrections = csv_rows(proposals / "human_corrections.csv")
    correction_fields = ["doc_id", "query_id", "previous_label", "corrected_label", "reviewer", "date", "source"]
    review_types = {}
    approval_path = proposals / "final_supervision.json"
    if approval_path.exists():
        approval = read_json(approval_path)
        for item in approval["pair_review_types"]:
            pair = item["doc_id"], item["query_id"]
            if pair in review_types or item["review_type"] not in (
                    "assisted_confirmation_after_discussion", "assisted_bulk_confirmation"):
                raise ValueError("Modalita di supervisione duplicata o non valida")
            review_types[pair] = item["review_type"]
    if review_types:
        pairs_in_queue = {(r["doc_id"], r["query_id"]) for r in review}
        if not set(review_types) <= pairs_in_queue or not set(review_types) <= set(by_pair):
            raise ValueError("Modalita di supervisione per coppia estranea")
        declared = (("new_discussed_pairs", "assisted_confirmation_after_discussion"),
                    ("new_bulk_pairs", "assisted_bulk_confirmation"))
        for key, mode in declared:
            if key in approval and approval[key] != sum(v == mode for v in review_types.values()):
                raise ValueError("Conteggio della modalita di supervisione incoerente")
        if "new_approved_pairs" in approval and approval["new_approved_pairs"] != len(review_types):
            raise ValueError("Numero delle approvazioni incoerente")
    seen, imported = set(), 0
    for r in review:
        pair = r["doc_id"], r["query_id"]
        if pair in seen or pair not in by_pair:
            raise ValueError("Coda duplicata o estranea")
        seen.add(pair)
        if not r["human_label"]:
            if any(r[k] for k in ("corrected_label", "human_reason", "reviewed_by", "reviewed_at")):
                raise ValueError("Revisione umana parziale senza etichetta")
            continue
        label = r["human_label"]
        if (label not in ("0", "1") or not all(r[k].strip() for k in
                ("human_reason", "reviewed_by", "reviewed_at"))):
            raise ValueError("Conferma senza etichetta, motivo, revisore o data")
        p = by_pair[pair]
        if r["proposed_label"] != p["proposed_label"]:
            raise ValueError("Proposta originale alterata nella coda")
        needed = "" if label == p["proposed_label"] else label
        if r["corrected_label"] != needed:
            raise ValueError("La correzione richiede corrected_label esplicito")
        old = by_doc[pair[0]][pair[1]]
        # Non riscrivere conferme di calibrazione gia registrate con gli stessi
        # dati. L'importazione ripetuta e idempotente e conta solo nuove decisioni.
        if (p["human_confirmed"] == "1" and p["effective_label"] == label
                and old == label and p["reviewer"] == r["reviewed_by"]
                and p["confirmation_date"] == r["reviewed_at"]):
            continue
        if old != label:
            corrections.append(dict(doc_id=pair[0], query_id=pair[1], previous_label=old,
                                    corrected_label=label, reviewer=r["reviewed_by"], date=r["reviewed_at"],
                                    source="Revisione mirata: " + r["human_reason"]))
        by_doc[pair[0]][pair[1]] = label
        p.update(effective_label=label, human_confirmed="1", reviewer=r["reviewed_by"],
                 confirmation_date=r["reviewed_at"],
                 review_type=review_types.get(pair, "targeted_assisted_confirmation"))
        imported += 1
    atomic_csv(output / "annotations.csv", matrix, list(matrix[0]))
    atomic_csv(output / "provenance.csv", provenance, list(provenance[0]))
    atomic_csv(proposals / "human_corrections.csv", corrections, correction_fields)
    manifest["annotations_sha256"] = sha256(output / "annotations.csv")
    manifest["provenance_sha256"] = sha256(output / "provenance.csv")
    counts = manifest.setdefault("counts", {})
    counts["human_confirmed_pairs"] = sum(r["human_confirmed"] == "1" for r in provenance)
    counts["not_individually_confirmed_pairs"] = len(provenance)-counts["human_confirmed_pairs"]
    counts["unconfirmed_pairs"] = counts["not_individually_confirmed_pairs"]
    counts["review_pending"] = sum(not r["human_label"] for r in review)
    counts["review_confirmed"] = sum(bool(r["human_label"]) for r in review)
    automatic = csv_rows(proposals / "complete_labels.csv")
    query_ids = sorted({r["query_id"] for r in automatic})
    counts["proposed_positive_by_query"] = {
        q: sum(r["query_id"] == q and r["proposed_label"] == "1" for r in automatic) for q in query_ids}
    counts["effective_positive_by_query"] = {q: sum(r[q] == "1" for r in matrix) for q in query_ids}
    counts["confirmed_review_types"] = {
        mode: sum(r["human_confirmed"] == "1" and r["review_type"] == mode for r in provenance)
        for mode in sorted({r["review_type"] for r in provenance if r["human_confirmed"] == "1"})}
    if approval_path.exists():
        calibration_pairs = {(r["doc_id"], r["query_id"]) for r in
                             csv_rows(proposals / "calibration_review.csv") if r["human_label"] in ("0", "1")}
        counts["assisted_confirmation_groups"] = {
            "calibration": sum(pair in calibration_pairs and r["human_confirmed"] == "1" for pair, r in by_pair.items()),
            "discussed": sum(by_pair[pair]["human_confirmed"] == "1" for pair, mode in review_types.items() if mode == "assisted_confirmation_after_discussion"),
            "bulk": sum(by_pair[pair]["human_confirmed"] == "1" for pair, mode in review_types.items() if mode == "assisted_bulk_confirmation")}
    manifest["positive_counts_note"] = "positive_by_query e proposed_positive_by_query sono proposte originali; effective_positive_by_query descrive la matrice corrente."
    review_manifest_path = proposals / "review_manifest.json"
    if review_manifest_path.exists():
        summary = read_json(review_manifest_path)
        summary.update(status="targeted_review_completed" if counts["review_pending"] == 0 else "targeted_review_pending",
                       pending=counts["review_pending"], confirmed_in_queue=counts["review_confirmed"])
        write_json(review_manifest_path, summary)
    manifest["output_sha256"] = {p.name: sha256(p) for p in proposals.iterdir()
                                 if p.is_file() and p.name != "classification_manifest.json"}
    write_json(manifest_path, manifest)
    return imported
