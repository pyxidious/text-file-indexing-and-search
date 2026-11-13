"""Copertura e split deterministici: nessun accesso al motore o ai suoi punteggi."""
from collections import Counter
import random


def coverage_and_split(queries, qrels, doc_ids, seed=42, development_fraction=0.2):
    if not 0 < development_fraction < 1 or type(seed) is not int:
        raise ValueError("Seed e frazione di sviluppo non validi")
    doc_ids = set(doc_ids)
    query_ids = sorted((q["query_id"] for q in queries), key=int)
    positive = {qid: set() for qid in query_ids}
    negative = {qid: set() for qid in query_ids}
    pairs = set()
    for row in qrels:
        qid, doc = row["query_id"], row["doc_id"]
        if qid not in positive or doc not in doc_ids or (qid, doc) in pairs:
            raise ValueError("Qrel duplicato o esterno alla collezione/query")
        pairs.add((qid, doc))
        if row["relevance"] >= 1:
            positive[qid].add(doc)
        elif row["relevance"] == -1:
            negative[qid].add(doc)
        else:
            raise ValueError("Grado Cranfield non valido")
    eligible = [qid for qid in query_ids if positive[qid]]
    if len(eligible) < 2:
        raise ValueError("Servono almeno due query valutabili per development/test")
    shuffled = eligible.copy()
    random.Random(seed).shuffle(shuffled)
    ndev = min(len(eligible) - 1, max(1, int(len(eligible) * development_fraction + 0.5)))
    development = sorted(shuffled[:ndev], key=int)
    test = sorted(shuffled[ndev:], key=int)
    excluded = [qid for qid in query_ids if not positive[qid]]
    judged_docs = {doc for _, doc in pairs}
    positive_per_doc = Counter(doc for group in positive.values() for doc in group)
    coverage = {"documents": len(doc_ids), "original_queries": len(query_ids),
                "eligible_queries": len(eligible), "excluded_queries": len(excluded),
                "exclusion_reason": "no known positive judgment in the selected corpus",
                "positive_judgments": sum(map(len, positive.values())),
                "explicit_negative_judgments": sum(map(len, negative.values())),
                "judged_query_document_pairs": len(pairs),
                "unjudged_query_document_pairs": len(query_ids) * len(doc_ids) - len(pairs),
                "documents_never_judged_for_any_query": len(doc_ids - judged_docs),
                "positive_documents_per_query": {q: len(positive[q]) for q in query_ids},
                "positive_count_histogram": dict(sorted(Counter(map(len, positive.values())).items())),
                "documents_with_positive_judgment": len(positive_per_doc),
                "positive_queries_per_document": {doc: positive_per_doc[doc] for doc in sorted(doc_ids, key=int)},
                "queries_without_positive_ids": excluded}
    split = {"seed": seed, "development_fraction": development_fraction,
             "method": "sort numeric eligible IDs; Random(seed).shuffle; round half up n*fraction",
             "development": development, "test": test, "excluded": excluded,
             "exclusion_reason": coverage["exclusion_reason"]}
    return coverage, split
