"""Input congelati, piano delle coppie e CSV di revisione umana cieca."""
import csv
from fractions import Fraction
import hashlib
import io
import json
import math
import os
from pathlib import Path
import random
import re
from urllib.parse import urlsplit

from ..dataset import ROOT, verify_dataset
from ..io import read_json, sha256, write_json

DEFAULT_DATASET = ROOT / "artifacts/cranfield300/n300/dataset"
DEFAULT_OUTPUT = ROOT / "artifacts/silver-study"
DEFAULT_CONFIG = ROOT / "config/silver.json"
SETTING_KEYS = set("""protocol_version prompt_version prompt_path schema_path provider base_url base_url_env
api_key_env require_api_key model_id model_env generation timeout_seconds default_request_limit
max_total_requests max_retries retry_delay_seconds sampling_seed audit_pairs_per_stratum future_query_count
future_inference_enabled prices_per_million_tokens_usd validation_policy unassessable_policy
graded_comparison selection_policy""".split())


def text_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def value_hash(value):
    return text_hash(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False))


def pair_id(query_id, doc_id):
    if any(not isinstance(x, str) or not x.isdecimal() or int(x) < 1 for x in (query_id, doc_id)):
        raise ValueError("ID numerici positivi richiesti")
    return f"q{int(query_id):04d}_d{int(doc_id):04d}"


def resolved_settings(config):
    config = dict(config)
    if set(config) != SETTING_KEYS:
        raise ValueError("Campi di configurazione mancanti/inattesi; le credenziali devono stare solo nell'ambiente")
    for name in ("api_key_env", "model_env", "base_url_env"):
        if not isinstance(config[name], str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", config[name]):
            raise ValueError("Specificare il nome della variabile d'ambiente, non il valore del segreto")
    if type(config["require_api_key"]) is not bool or type(config["sampling_seed"]) is not int:
        raise ValueError("Tipi di autenticazione/seed non validi")
    config["base_url"] = os.environ.get(config["base_url_env"], config["base_url"]).rstrip("/")
    config["model_id"] = os.environ.get(config["model_env"], config["model_id"])
    url = urlsplit(config["base_url"])
    if (url.username or url.password or url.query or url.fragment or not url.hostname or
            (url.scheme != "https" and not (url.scheme == "http" and url.hostname in ("localhost", "127.0.0.1", "::1")))):
        raise ValueError("Endpoint HTTPS o localhost, senza credenziali/query nella URL, richiesto")
    if config["provider"] != "openai-compatible-chat-completions":
        raise ValueError("Provider non supportato")
    allowed = {"temperature", "top_p", "max_completion_tokens", "reasoning_effort", "seed"}
    if set(config["generation"]) - allowed:
        raise ValueError("Parametri di generazione non consentiti")
    for key in ("default_request_limit", "max_total_requests", "audit_pairs_per_stratum"):
        if type(config[key]) is not int or config[key] < 1:
            raise ValueError(f"Configurazione intera positiva richiesta: {key}")
    if type(config["generation"].get("max_completion_tokens")) is not int or config["generation"]["max_completion_tokens"] < 1:
        raise ValueError("Limite token di output positivo richiesto")
    if type(config["max_retries"]) is not int or not 0 <= config["max_retries"] <= 3:
        raise ValueError("Retry ammessi: 0..3")
    if not 0 < config["timeout_seconds"] <= 60 or not 0 <= config["retry_delay_seconds"] <= 60:
        raise ValueError("Timeout o attesa retry fuori dai limiti")
    if config["future_query_count"] not in (15, 16, 17, 18, 19, 20):
        raise ValueError("Il piano futuro richiede 15..20 query")
    for price in config["prices_per_million_tokens_usd"].values():
        if price is not None and (type(price) not in (int, float) or not math.isfinite(price) or price < 0):
            raise ValueError("Prezzo non valido")
    return config


def load_corpus(dataset):
    dataset = Path(dataset)
    digest = verify_dataset(dataset)
    manifest = read_json(dataset / "manifest.json")
    if manifest["configuration"]["count"] != 300 or manifest["configuration"]["seed"] != 42:
        raise ValueError("Richiesto il corpus esistente da 300 documenti con seed 42")
    if manifest["source_records_sha256"] != read_json(ROOT / "config/cranfield.lock.json")["records_sha256"]:
        raise ValueError("Provenienza del corpus diversa dallo snapshot Cranfield congelato")
    documents = {}
    for row in manifest["documents"]:
        documents[row["doc_id"]] = (dataset / row["path"]).read_bytes().decode("utf-8")
    queries = {row["query_id"]: row["text"] for row in read_json(dataset / "queries.json")}
    if len(queries) != 225 or len(documents) != 300:
        raise ValueError("Identificativi duplicati o conteggi errati")
    return documents, queries, read_json(dataset / "qrels.json"), digest


def make_plans(documents, queries, qrels, seed=42, per_stratum=40, future_count=20):
    doc_ids, query_ids = sorted(documents, key=int), sorted(queries, key=int)
    known = {(r["query_id"], r["doc_id"]) for r in qrels}
    if len(known) != len(qrels):
        raise ValueError("Qrels duplicati")
    def row(q, d, **extra):
        return {"pair_id": pair_id(q, d), "query_id": q, "doc_id": d, **extra}
    pilot = [row(q, d) for q, d in sorted(known, key=lambda x: (int(x[0]), int(x[1])))]
    # Tokenizzazione locale per CAMPIONAMENTO, indipendente dagli analyzer e da BM25.
    tokens = lambda text: set(re.findall(r"[a-z]+", text.lower()))
    dt = {d: tokens(documents[d]) for d in doc_ids}
    qt = {q: tokens(queries[q]) for q in query_ids}
    unjudged = [(q, d) for q in query_ids for d in doc_ids if (q, d) not in known]
    if len(unjudged) < 3 * per_stratum:
        raise ValueError("Coppie non giudicate insufficienti")
    rng = random.Random(seed)
    random_pairs = rng.sample(unjudged, per_stratum)
    selected = set(random_pairs)
    # Jaccard di insiemi di parole: solo indice di overlap, MAI giudizio di rilevanza.
    score = lambda qd: Fraction(len(qt[qd[0]] & dt[qd[1]]), len(qt[qd[0]] | dt[qd[1]]) or 1)
    remaining = [p for p in unjudged if p not in selected]
    ordered = sorted(remaining, key=lambda p: (score(p), int(p[0]), int(p[1])))
    low, high = ordered[:per_stratum], list(reversed(ordered[-per_stratum:]))
    audit = [row(q, d, stratum=group, lexical_overlap=float(score((q, d))))
             for group, pairs in (("random", random_pairs), ("low_overlap", low), ("high_overlap", high))
             for q, d in pairs]
    rng.shuffle(audit)  # L'ordine non comunica il gruppo al giudice o al revisore.
    future_ids = query_ids.copy()
    random.Random(seed).shuffle(future_ids)
    future_ids = sorted(future_ids[:future_count], key=int)
    return {"pilot": pilot, "unjudged": audit,
            "future": [row(q, d) for q in future_ids for d in doc_ids]}, future_ids


def csv_bytes(rows, fields):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def prepare_study(dataset=DEFAULT_DATASET, output=DEFAULT_OUTPUT, config_path=DEFAULT_CONFIG):
    dataset, output = Path(dataset), Path(output)
    config = resolved_settings(read_json(config_path))
    prompt = (ROOT / config["prompt_path"]).read_text(encoding="utf-8")
    schema = read_json(ROOT / config["schema_path"])
    documents, queries, qrels, manifest_hash = load_corpus(dataset)
    plans, future_ids = make_plans(documents, queries, qrels, config["sampling_seed"],
                                    config["audit_pairs_per_stratum"], config["future_query_count"])
    if len(plans["pilot"]) != 404:
        raise ValueError("Attese le 404 coppie originali nel sottoinsieme")
    identity = {"protocol_version": config["protocol_version"], "settings": config,
                "dataset_manifest_sha256": manifest_hash, "prompt_sha256": text_hash(prompt),
                "schema_sha256": value_hash(schema), "pairs_sha256": value_hash(plans),
                "query_hashes": {q: text_hash(queries[q]) for q in sorted(queries, key=int)},
                "document_hashes": {d: text_hash(documents[d]) for d in sorted(documents, key=int)},
                "original_qrels_sha256": sha256(dataset / "qrels.json"),
                "future_query_ids": future_ids}
    output.mkdir(parents=True, exist_ok=True)
    frozen = output / "study.json"
    if frozen.exists():
        if read_json(frozen) != identity:
            raise ValueError("Input/prompt/modello/configurazione cambiati: usare una nuova directory di studio")
        load_study(dataset, output)
        return identity
    if any(output.iterdir()):
        raise ValueError("Destinazione non vuota senza study.json: usare una directory pulita")
    write_json(output / "pairs.json", plans)
    (output / "prompt.txt").write_bytes(prompt.encode("utf-8"))
    write_json(output / "schema.json", schema)
    write_json(frozen, identity)
    blind = list(plans["unjudged"])
    random.Random(config["sampling_seed"] + 1).shuffle(blind)
    rows = [{"pair_id": p["pair_id"], "query_id": p["query_id"], "doc_id": p["doc_id"],
             "query_text": queries[p["query_id"]], "document_text": documents[p["doc_id"]],
             "assessment": "", "relevance": "", "explanation": "", "evidence": "", "reviewer_id": ""}
            for p in blind]
    (output / "human_blind_unjudged.csv").write_bytes(csv_bytes(rows, list(rows[0])))
    return identity


def load_study(dataset=DEFAULT_DATASET, output=DEFAULT_OUTPUT):
    output = Path(output)
    identity = read_json(output / "study.json")
    documents, queries, qrels, digest = load_corpus(dataset)
    plans = read_json(output / "pairs.json")
    if (digest != identity["dataset_manifest_sha256"] or value_hash(plans) != identity["pairs_sha256"] or
            text_hash((output / "prompt.txt").read_text(encoding="utf-8")) != identity["prompt_sha256"] or
            value_hash(read_json(output / "schema.json")) != identity["schema_sha256"] or
            sha256(Path(dataset) / "qrels.json") != identity["original_qrels_sha256"] or
            {q: text_hash(t) for q, t in queries.items()} != identity["query_hashes"] or
            {d: text_hash(t) for d, t in documents.items()} != identity["document_hashes"]):
        raise ValueError("Integrità/versione degli input dello studio non valida")
    all_pairs = []
    for phase, pairs in plans.items():
        if phase not in ("pilot", "unjudged", "future"):
            raise ValueError("Fase sconosciuta")
        seen = set()
        for p in pairs:
            if (p["query_id"] not in queries or p["doc_id"] not in documents or
                    p["pair_id"] != pair_id(p["query_id"], p["doc_id"]) or p["pair_id"] in seen):
                raise ValueError("Coppia duplicata o ID non valido")
            seen.add(p["pair_id"])
        if phase != "future":
            all_pairs.extend(seen)
    if len(all_pairs) != len(set(all_pairs)):
        raise ValueError("Pilot e non giudicati non devono sovrapporsi")
    return identity, documents, queries, qrels, plans
