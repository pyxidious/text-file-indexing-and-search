"""Accordo su qrels noti, senza trasformare i non giudicati in negativi."""
import csv
import io
from pathlib import Path

from .data import csv_bytes, load_study, text_hash, value_hash
from .provider import validate_judgment
from .runner import atomic_json, load_annotations, now
from ..io import read_json


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def agreement(gold, annotations):
    """gold: pair_id -> grado originale; annotations può contenere coppie esterne."""
    assessed, abstentions, missing = [], [], []
    matrix = [[0] * 5 for _ in range(5)]
    tp = fp = fn = tn = 0
    for pid, grade in sorted(gold.items()):
        annotation = annotations.get(pid)
        if annotation is None:
            missing.append(pid)
            continue
        if annotation["assessment"] == "unassessable":
            abstentions.append(pid)
            continue
        predicted = annotation["relevance"]
        actual = 0 if grade == -1 else grade  # Solo vista metrica, non riscrive i qrels.
        matrix[actual][predicted] += 1
        assessed.append(pid)
        tp += actual >= 1 and predicted >= 1
        fn += actual >= 1 and predicted == 0
        fp += actual == 0 and predicted >= 1
        tn += actual == 0 and predicted == 0
    n = len(assessed)
    accuracy, sensitivity, specificity = ratio(tp + tn, n), ratio(tp, tp + fn), ratio(tn, tn + fp)
    precision = ratio(tp, tp + fp)
    expected = ((tp + fn) * (tp + fp) + (tn + fp) * (tn + fn)) / n ** 2 if n else None
    kappa = (accuracy - expected) / (1 - expected) if n and expected != 1 else None
    marg_gold = [sum(row) for row in matrix]
    marg_pred = [sum(matrix[i][j] for i in range(5)) for j in range(5)]
    observed_disagreement = sum((i - j) ** 2 * matrix[i][j] for i in range(5) for j in range(5))
    expected_disagreement = (sum((i - j) ** 2 * marg_gold[i] * marg_pred[j]
                                  for i in range(5) for j in range(5)) / n if n else 0)
    return {"expected_pairs": len(gold), "annotated_pairs": n + len(abstentions), "assessed_pairs": n,
            "missing_pairs": missing, "unassessable_pairs": abstentions,
            "unassessable_original_positive": sum(gold[p] >= 1 for p in abstentions),
            "unassessable_original_negative": sum(gold[p] == -1 for p in abstentions),
            "assessed_coverage": ratio(n, len(gold)),
            "confusion_matrix": {"TP": tp, "FP": fp, "FN": fn, "TN": tn} if n else None,
            "accuracy": accuracy, "precision": precision, "recall_sensitivity": sensitivity,
            "specificity": specificity,
            "balanced_accuracy": (sensitivity + specificity) / 2 if sensitivity is not None and specificity is not None else None,
            "f1": ratio(2 * tp, 2 * tp + fp + fn) if n else None, "cohen_kappa": kappa,
            "graded_exploratory": {"matrix_gold_rows_model_columns_0_to_4": matrix if n else None,
                                   "exact_agreement": ratio(sum(matrix[i][i] for i in range(5)), n),
                                   "mean_absolute_error": ratio(sum(abs(i - j) * matrix[i][j]
                                                               for i in range(5) for j in range(5)), n),
                                   "quadratic_weighted_kappa": 1 - observed_disagreement / expected_disagreement
                                   if expected_disagreement else None,
                                   "caveat": "original -1 -> 0 only for comparison; scales not proven equivalent"}}


def study_metrics(dataset, output):
    identity, documents, queries, qrels, plans = load_study(dataset, output)
    annotations = load_annotations(output, identity, documents, plans)
    gold = {p["pair_id"]: next(r["relevance"] for r in qrels if
            r["query_id"] == p["query_id"] and r["doc_id"] == p["doc_id"]) for p in plans["pilot"]}
    scores = agreement(gold, annotations)
    examples = {"agreement": [], "disagreement": []}
    lookup = {p["pair_id"]: p for p in plans["pilot"]}
    for pid in sorted(gold):
        annotation = annotations.get(pid)
        if not annotation or annotation["assessment"] == "unassessable":
            continue
        group = "agreement" if (gold[pid] >= 1) == (annotation["relevance"] >= 1) else "disagreement"
        if len(examples[group]) < 3:
            p = lookup[pid]
            examples[group].append({"pair_id": pid, "query_text": queries[p["query_id"]],
                                    "document_excerpt": annotation["evidence"][0] if annotation["evidence"] else documents[p["doc_id"]][:300],
                                    "original_relevance": gold[pid], "silver_relevance": annotation["relevance"],
                                    "explanation": annotation["explanation"]})
    return scores, examples, annotations, plans


def import_manual_review(dataset, output, csv_path):
    identity, documents, queries, _, plans = load_study(dataset, output)
    allowed = {p["pair_id"]: p for p in plans["unjudged"]}
    raw = Path(csv_path).read_bytes()
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline="")))
    seen, reviewed = set(), []
    for row in rows:
        pid = row["pair_id"]
        if pid in seen or pid not in allowed:
            raise ValueError("Coppia umana duplicata o fuori dal campione cieco")
        seen.add(pid)
        pair = allowed[pid]
        if (row["query_id"] != pair["query_id"] or row["doc_id"] != pair["doc_id"] or
                row["query_text"] != queries[pair["query_id"]] or row["document_text"] != documents[pair["doc_id"]]):
            raise ValueError("ID o testi modificati nel CSV umano")
        if not row["assessment"].strip():
            if any(row[name].strip() for name in ("relevance", "explanation", "evidence", "reviewer_id")):
                raise ValueError("Revisione umana compilata parzialmente")
            continue
        if not row["reviewer_id"].strip():
            raise ValueError("Identificativo revisore obbligatorio")
        value = {"assessment": row["assessment"], "relevance": int(row["relevance"]) if row["relevance"] else None,
                 "confidence": 0, "explanation": row["explanation"],
                 "evidence": [row["evidence"]] if row["evidence"] else []}
        validate_judgment(value, documents[pair["doc_id"]])
        del value["confidence"]  # Nessuna confidence umana inventata.
        reviewed.append({**{k: pair[k] for k in ("pair_id", "query_id", "doc_id")}, **value,
                         "source": "manual_review", "reviewer_id": row["reviewer_id"],
                         "study_sha256": value_hash(identity)})
    batch_id = text_hash(raw.decode("utf-8-sig"))
    dest = Path(output) / "manual_reviews" / (batch_id + ".json")
    if not dest.exists():
        atomic_json(dest, {"csv_sha256": batch_id, "timestamp_utc": now(), "reviews": reviewed})
    return {"batch_id": batch_id, "reviews_imported": len(reviewed), "source": "manual_review"}
