"""Confronta corse AND/OR sulla stessa ground truth, senza rieseguire la baseline."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from irhome.dataset import csv_rows, write_csv
from irhome.ground_truth import load_queries
from irhome.io import read_json, write_json, sha256

METRICS = ("precision", "recall", "f1")


def number(value):
    return None if value == "" else float(value)


def delta(a, b):
    return None if a is None or b is None else b-a


def compare(baseline="artifacts/homework/results", candidate="artifacts/homework/results_or",
            queries="evaluation/queries.csv", output=None):
    baseline, candidate = Path(baseline), Path(candidate)
    output = candidate if output is None else Path(output)
    if output.resolve() == baseline.resolve() or baseline.resolve() in output.resolve().parents:
        raise ValueError("Il confronto deve preservare la directory della baseline")
    a_meta, b_meta = (read_json(p / "evaluation.json") for p in (baseline, candidate))
    if a_meta.get("strategy", "and") != "and" or b_meta.get("strategy") != "or":
        raise ValueError("Richieste una corsa AND e una OR")
    for key in ("frozen_sha256", "engine_sha256", "ground_truth_status"):
        if a_meta[key] != b_meta[key]:
            raise ValueError("Input o motore diversi fra le configurazioni: " + key)
    qs = load_queries(queries)
    a_rows, b_rows = (csv_rows(p / "metrics.csv") for p in (baseline, candidate))
    a, b = ({r["query_id"]: r for r in rows} for rows in (a_rows, b_rows))
    qids = {q["query_id"] for q in qs}
    if len(a_rows) != len(qs) or len(b_rows) != len(qs) or set(a) != qids or set(b) != qids:
        raise ValueError("Query mancanti o duplicate nei risultati")
    a_runs, b_runs = (csv_rows(p / "results.csv") for p in (baseline, candidate))
    if any(r["query_id"] not in qids for r in a_runs+b_runs):
        raise ValueError("Risultato di query estranea")
    comparisons, monotonic, phrases = [], [], []
    for q in qs:
        qid = q["query_id"]
        left, right = a[qid], b[qid]
        query = q["field"] + " " + q["expression"]
        if left["query"] != query or right["query"] != query or left["relevant"] != right["relevant"]:
            raise ValueError("Query o riferimenti diversi")
        ar = [r for r in a_runs if r["query_id"] == qid]
        br = [r for r in b_runs if r["query_id"] == qid]
        ai, bi = ({r["doc_id"] for r in rows} for rows in (ar, br))
        if len(ai) != len(ar) or len(bi) != len(br):
            raise ValueError("Ranking duplicato")
        for metric, ranking in ((left, ar), (right, br)):
            tp = sum(int(r["relevant"]) for r in ranking)
            if (len(ranking) != int(metric["retrieved"]) or tp != int(metric["tp"])
                    or len(ranking)-tp != int(metric["fp"])
                    or int(metric["relevant"])-tp != int(metric["fn"])):
                raise ValueError("Ranking e conteggi incoerenti")
        if q["type"] == "phrase":
            if ar != br or left != right:
                raise ValueError("Comportamento phrase modificato")
            phrases.append(qid)
        else:
            if not ai <= bi:
                raise ValueError("OR non contiene tutti i risultati AND")
            if number(left["recall"]) is not None and number(right["recall"]) < number(left["recall"]):
                raise ValueError("Recall OR inferiore alla baseline")
            monotonic.append(qid)
        row = dict(query_id=qid, query=query, type=q["type"], relevant=int(left["relevant"]))
        for prefix, metric in (("and", left), ("or", right)):
            row.update({prefix+"_"+k: int(metric[k]) for k in ("retrieved", "tp", "fp", "fn")})
            row.update({prefix+"_"+k: number(metric[k]) for k in METRICS})
        row.update({"delta_"+k: delta(number(left[k]), number(right[k])) for k in METRICS})
        comparisons.append(row)
    macro_rows = []
    for k in METRICS:
        av, bv = a_meta["macro"][k], b_meta["macro"][k]
        macro_rows.append(dict(metric=k, and_value=av, or_value=bv, delta=delta(av, bv),
                               and_defined_queries=a_meta["macro"][k+"_defined_queries"],
                               or_defined_queries=b_meta["macro"][k+"_defined_queries"]))
    write_csv(output / "comparison.csv", comparisons, list(comparisons[0]))
    write_csv(output / "comparison_macro.csv", macro_rows, list(macro_rows[0]))
    metadata = dict(baseline_strategy="and", candidate_strategy="or",
                    frozen_sha256=a_meta["frozen_sha256"], engine_sha256=a_meta["engine_sha256"],
                    baseline_files_sha256={p.name:sha256(p) for p in baseline.iterdir() if p.is_file()},
                    candidate_run_sha256={name:sha256(candidate / name) for name in
                                          ("metrics.csv", "results.csv", "macro.csv", "errors.csv", "evaluation.json")},
                    non_phrase_recall_monotonic=monotonic, phrase_queries_identical=phrases,
                    delta_definition="OR meno AND, differenza sulla scala della metrica; non variazione relativa percentuale")
    write_json(output / "comparison.json", metadata)
    def fmt(v):
        return "n/d" if v is None else f"{v:.6f}"
    lines = ["# Confronto sperimentale AND / OR", "",
             "Stesso motore, analyzer, BM25 e ground truth congelata. AND predefinito; OR esplicito per termini non quotati.", "",
             "| Query | P AND | P OR | Delta P | R AND | R OR | Delta R | F1 AND | F1 OR | Delta F1 |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in comparisons:
        vals = [r["query_id"]]
        for k in METRICS:
            vals.extend(fmt(r[p+"_"+k]) for p in ("and", "or", "delta"))
        lines.append("| " + " | ".join(vals) + " |")
    lines += ["", "| Metrica macro | AND | OR | Delta |", "|---|---:|---:|---:|"]
    lines += ["| " + " | ".join([r["metric"], fmt(r["and_value"]), fmt(r["or_value"]), fmt(r["delta"])]) + " |" for r in macro_rows]
    lines += ["", "| Query | Risultati AND | TP AND | FP AND | FN AND | Risultati OR | TP OR | FP OR | FN OR |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in comparisons:
        lines.append("| " + " | ".join([r["query_id"]]+[str(r[p+"_"+k]) for p in ("and", "or") for k in ("retrieved", "tp", "fp", "fn")]) + " |")
    lines += ["", "Delta = OR - AND. Verificati insieme AND incluso in OR e recall non decrescente per tutte le query non phrase; per le phrase sono identici anche ranking e score.", "",
              "Comandi: python scripts/evaluate.py --strategy or; python scripts/compare_matching.py"]
    (output / "comparison.md").write_bytes(("\n".join(lines)+"\n").encode("utf-8"))
    return comparisons, macro_rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default="artifacts/homework/results")
    parser.add_argument("--candidate", default="artifacts/homework/results_or")
    parser.add_argument("--queries", default="evaluation/queries.csv")
    parser.add_argument("--output")
    args = parser.parse_args()
    try:
        rows, macro = compare(args.baseline, args.candidate, args.queries, args.output)
        print("Confronto salvato:", len(rows), "query; recall non decrescente e phrase identiche.")
        for r in macro:
            print(r)
    except (ValueError, OSError, KeyError) as error:
        parser.exit(2, str(error)+"\n")
