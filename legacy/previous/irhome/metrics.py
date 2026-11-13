"""Metriche binarie; nessuna inferenza di rilevanza dai risultati."""


def retrieval_metrics(ranked_ids, relevant, k=10):
    if k <= 0:
        raise ValueError("k deve essere positivo")
    if len(ranked_ids) != len(set(ranked_ids)):
        raise ValueError("Il ranking non può contenere duplicati")
    relevant = set(relevant)
    hits = len(set(ranked_ids) & relevant)
    hits_k = len(set(ranked_ids[:k]) & relevant)
    precision = hits / len(ranked_ids) if ranked_ids else 0.0
    recall = hits / len(relevant) if relevant else None
    recall_k = hits_k / len(relevant) if relevant else None
    f1 = (2 * precision * recall / (precision + recall)
          if recall is not None and precision + recall else 0.0 if relevant else None)
    precision_k = hits_k / k
    f1_k = (2 * precision_k * recall_k / (precision_k + recall_k)
            if recall_k is not None and precision_k + recall_k else 0.0 if relevant else None)
    running, total, total_k = 0, 0.0, 0.0
    for rank, doc in enumerate(ranked_ids, 1):
        if doc in relevant:
            running += 1
            total += running / rank
            if rank <= k:
                total_k += running / rank
    return {"precision_at_10": precision_k, "recall_at_10": recall_k, "f1_at_10": f1_k,
            "precision": precision, "recall": recall, "f1": f1,
            "average_precision": total / len(relevant) if relevant else None,
            "ap_at_10": total_k / min(k, len(relevant)) if relevant else None,
            "retrieved": len(ranked_ids), "relevant": len(relevant)}
