"""Valutazione consentita solo dopo congelamento della ground truth validata."""
from pathlib import Path

from .dataset import write_csv
from .ground_truth import load_frozen, load_queries
from .io import sha256, write_json
from .metrics import macro_metrics, retrieval_metrics


def evaluate(documents="corpus/documents", queries="evaluation/queries.csv",
             ground_truth="evaluation", output="artifacts/homework/results"):
    # Il controllo precede costruzione dell'indice, query e metriche.
    relevant = load_frozen(documents, queries, ground_truth)
    from .engine import SearchEngine
    engine = SearchEngine.build(documents)
    rows, runs = [], []
    for q in load_queries(queries):
        query = q["field"] + " " + q["expression"]
        results = engine.search(query)  # Ranking COMPLETO: nessun top-k per TP/FP/FN.
        ids = [r["id"] for r in results]
        rows.append(dict(query_id=q["query_id"], query=query,
                         **retrieval_metrics(ids, relevant[q["query_id"]])))
        for rank, r in enumerate(results, 1):
            runs.append(dict(query_id=q["query_id"], rank=rank, doc_id=r["id"],
                             score=r["score"], relevant=int(r["id"] in relevant[q["query_id"]])))
    output = Path(output)
    write_csv(output / "metrics.csv", rows, list(rows[0]))
    write_csv(output / "results.csv", runs, ["query_id", "rank", "doc_id", "score", "relevant"])
    summary = macro_metrics(rows)
    write_csv(output / "macro.csv", [summary], list(summary))
    write_json(output / "evaluation.json", dict(status="evaluated_against_human_validated_lexical_truth",
               frozen_sha256=sha256(Path(ground_truth) / "frozen.json"),
               engine_sha256=sha256(Path(__file__).with_name("engine.py")), macro=summary))
    for row in rows:
        def fmt(value):
            return "non definita" if value is None else f"{value:.6f}"
        print(f"{row['query_id']}: TP={row['tp']} FP={row['fp']} FN={row['fn']} "
              f"P={fmt(row['precision'])} R={fmt(row['recall'])} F1={fmt(row['f1'])} "
              f"P@10={fmt(row['precision_at_10'])} R@10={fmt(row['recall_at_10'])}")
    print("Macro (solo valori definiti):", summary)
    return rows, summary
