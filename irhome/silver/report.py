"""Report pilota empirico; valori mancanti restano null/N.D., mai stimati come accuratezza."""
from collections import Counter
from pathlib import Path

from ..io import read_json, write_json
from .data import load_study
from .evaluation import agreement, study_metrics
from .runner import dry_run


def cost_and_usage(output, settings):
    receipts = [read_json(p) for p in sorted((Path(output) / "attempts").glob("*.json"))]
    input_tokens = output_tokens = 0
    missing_usage = 0
    for receipt in receipts:
        usage = receipt.get("response", {}).get("usage", {})
        a, b = usage.get("prompt_tokens"), usage.get("completion_tokens")
        if type(a) is int and a >= 0 and type(b) is int and b >= 0:
            input_tokens += a
            output_tokens += b
        else:
            missing_usage += 1
    prices = settings["prices_per_million_tokens_usd"]
    estimate = ((input_tokens * prices["input"] + output_tokens * prices["output"]) / 1_000_000
                if prices["input"] is not None and prices["output"] is not None and not missing_usage else None)
    return {"network_requests_recorded": len(receipts), "input_tokens_reported": input_tokens,
            "output_tokens_reported": output_tokens, "requests_with_unknown_usage": missing_usage,
            "actual_cost_usd": 0 if not receipts else None, "estimated_cost_usd_from_configured_prices": estimate,
            "attempt_status_counts": dict(Counter(r["status"] for r in receipts)),
            "retry_requests": sum(r["retry_number"] > 0 for r in receipts),
            "billing_caveat": "usage can be incomplete after errors; price estimates exclude discounts/cache and are not invoices"}


def make_report(dataset, output):
    output = Path(output)
    identity, _, _, _, _ = load_study(dataset, output)
    scores, examples, annotations, plans = study_metrics(dataset, output)
    usage = cost_and_usage(output, identity["settings"])
    batches = {p.stem: read_json(p)["reviews"] for p in sorted((output / "manual_reviews").glob("*.json"))}
    manual = [r for rows in batches.values() for r in rows]
    human_comparisons = {batch: agreement({r["pair_id"]: r["relevance"] if r["relevance"] else -1
                                         for r in rows if r["assessment"] == "assessable"}, annotations)
                         for batch, rows in batches.items()}
    reviewed_ids = {r["pair_id"] for r in manual if r["assessment"] == "assessable"}
    audit_ids = {p["pair_id"] for p in plans["unjudged"]}
    dry = {phase: dry_run(dataset, output, phase) for phase in ("pilot", "unjudged", "future")}
    model_ids = sorted({a["model_id"] for a in annotations.values()})
    result = {"status": "not_semantically_validated", "requested_model_id": identity["settings"]["model_id"],
              "models_actually_used": model_ids, "annotations_really_executed": len(annotations),
              "pilot_agreement": scores, "examples_from_real_annotations": examples, "usage": usage,
              "mean_estimated_cost_per_annotation_usd": usage["estimated_cost_usd_from_configured_prices"] / len(annotations)
              if annotations and usage["estimated_cost_usd_from_configured_prices"] is not None else None,
              "unjudged_annotations": len(audit_ids & set(annotations)),
              "human_assessed_unjudged_pairs": len(audit_ids & reviewed_ids),
              "human_reviews_complete": audit_ids <= reviewed_ids,
              "silver_vs_human_by_batch": human_comparisons,
              "semantic_grounding_of_model_explanations": "requires separate human entailment review; quote checks alone insufficient",
              "confidence_caveat": "self-reported, not calibrated probability", "dry_runs": dry}
    write_json(output / "pilot_metrics.json", result)
    write_json(output / "dry_run.json", dry)
    n = len(annotations)
    show = lambda v: "non disponibile" if v is None else str(v)
    text = ["# Studio pilota silver qrels — report operativo", "",
            "Stato: **pipeline pronta, validità semantica non dimostrata**.", "",
            "## Protocollo congelato e scelta del modello", "",
            "Prompt relevance-judge-v1 e scala 0..4 fissati prima della validazione; nessuna calibrazione sui qrels.",
            "Tutte le 404 coppie note sono validazione finale. Le classi originali sono 352 positive e 52 negative.",
            "Non si usano gli split development/test del retrieval per scegliere il giudice.",
            f"Modello richiesto: {show(result['requested_model_id'])}. Modelli effettivamente usati: {model_ids or 'nessuno'}.",
            "La configurazione richiede una scelta esplicita del modello/snapshot disponibile prima di preparare lo studio.",
            "Il provider implementato usa Chat Completions con JSON Schema; nessuna chiamata alla sessione Codex.", "",
            "## Esecuzione effettiva", "", f"Annotazioni realmente salvate: **{n}**.",
            f"Richieste registrate: {usage['network_requests_recorded']}; retry: {usage['retry_requests']}.",
            f"Token input/output riportati: {usage['input_tokens_reported']}/{usage['output_tokens_reported']}.",
            f"Richieste con usage sconosciuta: {usage['requests_with_unknown_usage']}.",
            f"Costo effettivo disponibile USD: {show(usage['actual_cost_usd'])}; stima da prezzi configurati: {show(usage['estimated_cost_usd_from_configured_prices'])}.",
            f"Costo medio stimabile per annotazione USD: {show(result['mean_estimated_cost_per_annotation_usd'])}.", "",
            "## Accordo con Cranfield", "", f"Matrice binaria: {show(scores['confusion_matrix'])}.",
            f"Coppie valutate: {scores['assessed_pairs']}; mancanti: {len(scores['missing_pairs'])}; unassessable: {len(scores['unassessable_pairs'])}."]
    for metric in ("accuracy", "precision", "recall_sensitivity", "specificity", "balanced_accuracy", "f1", "cohen_kappa"):
        text.append(f"- {metric}: {show(scores[metric])}")
    text += ["", "Le astensioni restano salvate, escluse dai denominatori e contate separatamente per classe originale.",
             "Le metriche sono condizionate alle coppie valutabili e disponibili; una validazione parziale non equivale alle 404 complete.",
             "Accordo graduato esplorativo: matrice 5x5, accordo esatto, MAE e kappa quadratica nel JSON.",
             "Il mapping -1→0 è solo una vista per il confronto: le scale non sono dimostrate equivalenti.", "",
             "## Accordi, disaccordi e casi da rivedere", ""]
    for group, values in examples.items():
        text.append(f"### {group} (confronto binario, soglia >= 1)")
        if not values:
            text.append("Nessun esempio empirico disponibile: non vengono inventati query, citazioni o errori del modello.")
        for example in values:
            text += [f"- Coppia {example['pair_id']}: originale {example['original_relevance']}, silver {example['silver_relevance']}.",
                     f"  Query: {example['query_text']}", f"  Estratto: {example['document_excerpt']}",
                     f"  Spiegazione: {example['explanation']}"]
    text += ["", "Con annotazioni disponibili, TP/FP/FN/TN descrivono il comportamento su positivi e negativi;", 
             "i disaccordi e le astensioni hanno priorità di revisione. Con zero risposte non si possono identificare errori ricorrenti.",
             "Tutte le spiegazioni silver restano pending: citazioni letterali valide non provano il supporto semantico delle affermazioni.",
             "Le motivazioni non supportate devono essere respinte dal controllo umano; non esiste promozione automatica a gold.", "",
             "## Campione non giudicato e revisione cieca", "",
             f"Pianificate {len(plans['unjudged'])} coppie: gruppi random/high_overlap/low_overlap da {identity['settings']['audit_pairs_per_stratum']}; seed {identity['settings']['sampling_seed']}, senza BM25.",
             f"Annotate {result['unjudged_annotations']}; revisionate con giudizio umano valutabile {result['human_assessed_unjudged_pairs']}.",
             "Il CSV human_blind_unjudged.csv mostra query e abstract integrali, ma nessuna etichetta, fonte, strato o risposta LLM.",
             "Completare i campi in una copia, senza cambiare testi/ID; importare con import-review.",
             "I confronti silver/umani sono separati per batch nel JSON, senza pooling o adjudication automatica.",
             "La validazione semantica delle coppie non giudicate richiede revisione umana, anche se le etichette LLM fossero complete.", "",
             "## Dry run e limiti", ""]
    for phase, plan in dry.items():
        text.append(f"- {phase}: {plan['planned_pairs']} coppie; {plan['pending_pairs']} pendenti; input stimato {plan['estimated_input_tokens_all_pending']} token.")
    text += ["", "Stime token: byte UTF-8 della richiesta divisi per 3, arrotondati; non sono conteggi di fatturazione.",
             "I limiti di output includono gli eventuali token di ragionamento del provider. Prezzi non configurati → costi stimati N.D.",
             "Temperature zero e snapshot non garantiscono risposte identiche. Conservare ricevute, etichette e hash per ricalcolare senza inferenza.",
             "Rischi metodologici: sbilanciamento, piccolo campione, pool Cranfield incompleto, annotazione storica non infallibile,",
             "contaminazione da training del modello sul benchmark, iniezione di istruzioni nei dati, confidence non calibrata e mancata prova di entailment.",
             "Il campione arricchito ad alto/basso overlap non rappresenta la prevalenza di rilevanza di tutte le coppie non giudicate.",
             "Il futuro piano ha 15–20 query selezionate casualmente con seed fisso prima dei risultati; 4.500–6.000 coppie.",
             "L'inferenza massiva è disabilitata e dipende dai risultati pilota e dalla revisione umana.",
             "Questo report non è la relazione universitaria definitiva.", ""]
    (output / "report.md").write_bytes("\n".join(text).encode("utf-8"))
    return result
