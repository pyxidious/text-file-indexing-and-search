"""Cache per coppia, ricevute persistenti, budget e ripresa senza duplicare successi."""
from datetime import datetime, timezone
import os
from pathlib import Path
import time

from ..io import read_json
from .data import load_study, text_hash, value_hash
from .provider import ChatProvider, ProviderFailure, extract_judgment, request_body, strict_loads


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, value):
    import json
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as stream:
        stream.write((json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8"))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def annotation_from_receipt(receipt, pair, identity, document):
    if receipt["study_sha256"] != value_hash(identity) or receipt["pair_id"] != pair["pair_id"]:
        raise ValueError("Ricevuta di un altro studio/coppia")
    response = receipt["response"]
    judgment = extract_judgment(response, document)
    return {**pair, **judgment, "source": "llm_silver", "model_id": response["model"],
            "requested_model_id": identity["settings"]["model_id"],
            "prompt_version": identity["settings"]["prompt_version"],
            "prompt_sha256": identity["prompt_sha256"], "study_sha256": value_hash(identity),
            "query_sha256": identity["query_hashes"][pair["query_id"]],
            "document_sha256": identity["document_hashes"][pair["doc_id"]],
            "timestamp_utc": receipt["received_at"], "attempt_id": receipt["attempt_id"],
            "response_sha256": value_hash(response), "system_fingerprint": response.get("system_fingerprint"),
            "deterministic_checks": "passed", "semantic_review": "pending",
            "evidence_offsets": [{"start": document.index(q), "end": document.index(q) + len(q)}
                                 for q in judgment["evidence"]]}


def load_annotations(output, identity, documents, plans):
    output = Path(output)
    all_pairs = {p["pair_id"]: p for pairs in plans.values() for p in pairs}
    cached = {}
    for path in sorted((output / "silver_qrels").glob("*.json")):
        annotation = strict_loads(path.read_text(encoding="utf-8"))
        pid = annotation["pair_id"]
        if pid in cached or pid not in all_pairs or path.name != pid + ".json":
            raise ValueError("Annotazione duplicata o ID non previsto")
        if (not isinstance(annotation["attempt_id"], str) or len(annotation["attempt_id"]) != 6 or
                not annotation["attempt_id"].isascii() or not annotation["attempt_id"].isdigit()):
            raise ValueError("ID ricevuta non valido")
        receipt = read_json(output / "attempts" / (annotation["attempt_id"] + ".json"))
        # Il gruppo lessicale non fa parte dell'etichetta né dell'input al giudice.
        pair = {k: all_pairs[pid][k] for k in ("pair_id", "query_id", "doc_id")}
        expected = annotation_from_receipt(receipt, pair, identity, documents[pair["doc_id"]])
        if annotation != expected:
            raise ValueError("Annotazione alterata o non coerente con risposta/hash/citazioni")
        cached[pid] = annotation
    models = {a["model_id"] for a in cached.values()}
    if cached and (len(models) != 1 or not (output / "actual_model.json").exists() or
                   read_json(output / "actual_model.json")["model_id"] not in models):
        raise ValueError("Metadati del modello mancanti o modelli mescolati nella cache")
    return cached


def dry_run(dataset, output, phase="pilot", limit=None):
    identity, documents, queries, _, plans = load_study(dataset, output)
    settings = identity["settings"]
    cached = load_annotations(output, identity, documents, plans)
    pending = [p for p in plans[phase] if p["pair_id"] not in cached]
    limit = settings["default_request_limit"] if limit is None else limit
    if type(limit) is not int or limit < 1:
        raise ValueError("Il limite richieste deve essere positivo")
    prompt = (Path(output) / "prompt.txt").read_text(encoding="utf-8")
    schema = read_json(Path(output) / "schema.json")
    # Stima grezza in byte/3, non tokenizer né conteggio fatturabile.
    import json
    estimates = [(len(json.dumps(request_body(settings, prompt, schema,
                          queries[p["query_id"]], documents[p["doc_id"]]), ensure_ascii=False).encode("utf-8")) + 2) // 3
                 for p in pending]
    input_estimate = sum(estimates)
    attempts = list((Path(output) / "attempts").glob("*.json"))
    remaining_budget = max(0, settings["max_total_requests"] - len(attempts))
    output_cap = len(pending) * settings["generation"]["max_completion_tokens"]
    prices = settings["prices_per_million_tokens_usd"]
    estimated_cost = ((input_estimate * prices["input"] + output_cap * prices["output"]) / 1_000_000
                      if prices["input"] is not None and prices["output"] is not None else None)
    return {"phase": phase, "planned_pairs": len(plans[phase]), "already_annotated": len(plans[phase]) - len(pending),
            "pending_pairs": len(pending), "request_limit_this_invocation": limit,
            "lifetime_requests_used": len(attempts), "lifetime_requests_remaining": remaining_budget,
            "maximum_requests_this_invocation": min(limit, remaining_budget, len(pending) * (settings["max_retries"] + 1)),
            "estimated_input_tokens_all_pending": input_estimate,
            "maximum_estimated_input_tokens_per_request": max(estimates, default=0),
            "maximum_output_tokens_all_pending_no_retries": output_cap,
            "token_estimate_method": "UTF-8 request bytes / 3 rounded up; rough, not billing tokens",
            "estimated_cost_usd": estimated_cost,
            "cost_estimate_scope": "all pending pairs; rough input, output cap; no retries or discounts; not an invoice",
            "provider": settings["provider"], "model_id": settings["model_id"],
            "provider_configured": ChatProvider(settings).available(),
            "future_inference_enabled": settings["future_inference_enabled"], "network_requests": 0}


def annotate(dataset, output, phase="pilot", limit=None, retry_uncertain=False, provider=None):
    output = Path(output)
    identity, documents, queries, _, plans = load_study(dataset, output)
    settings = identity["settings"]
    if phase == "future" and not settings["future_inference_enabled"]:
        raise ValueError("Annotazione massiva disabilitata: attendere studio pilota e revisione umana")
    summary = dry_run(dataset, output, phase, limit)
    provider = provider or ChatProvider(settings)
    if not provider.available():
        summary.update(status="not_executed_provider_unavailable", actual_requests=0)
        atomic_json(output / "last_run.json", {**summary, "timestamp_utc": now()})
        return summary
    lock = output / "run.lock"
    # Un solo worker: anche dopo un hard crash resta visibile il lock da verificare.
    with lock.open("x", encoding="utf-8") as stream:
        stream.write(str(os.getpid()))
    calls, accepted, blocked, fatal = 0, 0, [], False
    try:
        cached = load_annotations(output, identity, documents, plans)
        prompt = (output / "prompt.txt").read_text(encoding="utf-8")
        schema = read_json(output / "schema.json")
        receipts = [read_json(p) for p in sorted((output / "attempts").glob("*.json"))]
        next_id = max((int(r["attempt_id"]) for r in receipts), default=0) + 1
        for item in plans[phase]:
            pair = {k: item[k] for k in ("pair_id", "query_id", "doc_id")}
            pid, doc = pair["pair_id"], documents[pair["doc_id"]]
            if pid in cached:
                continue
            previous = [r for r in receipts if r["pair_id"] == pid]
            # Ricevuta salvata prima del crash: ricostruire senza pagare altra inferenza.
            recovered = False
            for receipt in reversed(previous):
                if receipt["status"] == "received":
                    try:
                        annotation = annotation_from_receipt(receipt, pair, identity, doc)
                    except ValueError:
                        continue
                    _commit(output, annotation)
                    cached[pid], recovered = annotation, True
                    accepted += 1
                    break
            if recovered:
                continue
            if any(r["status"] in ("inflight", "uncertain") for r in previous) and not retry_uncertain:
                blocked.append(pid)
                continue
            fatal = False
            for retry in range(settings["max_retries"] + 1):
                if calls >= summary["request_limit_this_invocation"] or len(receipts) >= settings["max_total_requests"]:
                    break
                attempt_id = f"{next_id:06d}"
                next_id += 1
                body = request_body(settings, prompt, schema, queries[pair["query_id"]], doc)
                receipt = {"attempt_id": attempt_id, "pair_id": pid, "study_sha256": value_hash(identity),
                           "started_at": now(), "retry_number": retry, "status": "inflight",
                           "request_sha256": value_hash(body)}
                path = output / "attempts" / (attempt_id + ".json")
                atomic_json(path, receipt)  # Write-ahead, prima di qualsiasi rete.
                receipts.append(receipt)
                calls += 1
                retryable = False
                try:
                    response = provider.complete(body)
                    receipt.update(status="received", received_at=now(), response=response)
                    atomic_json(path, receipt)
                    annotation = annotation_from_receipt(receipt, pair, identity, doc)
                    _commit(output, annotation)
                    cached[pid] = annotation
                    accepted += 1
                    break
                except IntegrityFailure:
                    receipt.update(status="integrity_error", error="effective_model_changed_or_existing_label_conflict")
                    fatal = True
                except ProviderFailure as error:
                    receipt.update(status="uncertain" if error.uncertain else "provider_error", error=str(error))
                    retryable, fatal = error.retryable, error.fatal
                except (ValueError, KeyError, TypeError) as error:
                    receipt.update(status="invalid_response", error=type(error).__name__)
                    retryable = True
                atomic_json(path, receipt)
                if not retryable or fatal or retry == settings["max_retries"]:
                    break
                time.sleep(min(settings["retry_delay_seconds"], 60))
            if fatal or calls >= summary["request_limit_this_invocation"] or len(receipts) >= settings["max_total_requests"]:
                break
        summary.update(status="stopped_provider_or_integrity_error" if fatal else "finished_or_budget_reached", actual_requests=calls,
                       accepted_this_invocation=accepted, uncertain_pairs_not_retried=blocked,
                       pending_pairs_after=sum(p["pair_id"] not in cached for p in plans[phase]))
        atomic_json(output / "last_run.json", {**summary, "timestamp_utc": now()})
        return summary
    finally:
        lock.unlink()


class IntegrityFailure(ValueError):
    pass


def _commit(output, annotation):
    model_path = output / "actual_model.json"
    if model_path.exists() and read_json(model_path)["model_id"] != annotation["model_id"]:
        raise IntegrityFailure("Il modello effettivo è cambiato: non mescolare modelli in uno studio")
    if not model_path.exists():
        atomic_json(model_path, {"model_id": annotation["model_id"]})
    destination = output / "silver_qrels" / (annotation["pair_id"] + ".json")
    if destination.exists():
        if read_json(destination) != annotation:
            raise IntegrityFailure("Tentativo di sovrascrivere un'etichetta già salvata")
        return
    atomic_json(destination, annotation)
