"""Metriche binarie su ranking completi; None indica un rapporto non definito."""
from statistics import mean


def retrieval_metrics(ranked_ids, relevant):
    if len(ranked_ids) != len(set(ranked_ids)):
        raise ValueError("Il ranking contiene duplicati")
    relevant, retrieved = set(relevant), set(ranked_ids)
    tp = len(retrieved & relevant)
    fp, fn = len(retrieved - relevant), len(relevant - retrieved)
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    # Forma equivalente alla media armonica; zero con positivi ma nessun hit.
    f1 = 2 * tp / (2 * tp + fp + fn) if relevant else None
    hits10 = len(set(ranked_ids[:10]) & relevant)
    return dict(tp=tp, fp=fp, fn=fn, retrieved=len(retrieved), relevant=len(relevant),
                precision=precision, recall=recall, f1=f1,
                precision_at_10=hits10 / 10,
                recall_at_10=hits10 / len(relevant) if relevant else None)


def macro_metrics(rows):
    result = {}
    for key in ("precision", "recall", "f1", "precision_at_10", "recall_at_10"):
        values = [row[key] for row in rows if row[key] is not None]
        result[key] = mean(values) if values else None
        result[key + "_defined_queries"] = len(values)
    return result
