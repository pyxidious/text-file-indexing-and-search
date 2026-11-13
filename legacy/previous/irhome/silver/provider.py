"""Adapter HTTP reale, senza SDK: Chat Completions con JSON Schema stretto."""
import json
import math
import os
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


def strict_loads(text):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("Chiave JSON duplicata")
            value[key] = item
        return value
    def invalid_constant(value):
        raise ValueError("Costante JSON non finita")
    return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid_constant)


def validate_judgment(value, document):
    keys = {"assessment", "relevance", "confidence", "explanation", "evidence"}
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError("Campi del giudizio incompleti o inattesi")
    status, grade = value["assessment"], value["relevance"]
    if status == "assessable":
        if type(grade) is not int or grade not in range(5):
            raise ValueError("Rilevanza ammessa: intero 0..4")
    elif status != "unassessable" or grade is not None:
        raise ValueError("Unassessable richiede relevance=null")
    confidence = value["confidence"]
    if type(confidence) not in (int, float) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
        raise ValueError("Confidence non valida")
    if not isinstance(value["explanation"], str) or not value["explanation"].strip() or len(value["explanation"]) > 2000:
        raise ValueError("Spiegazione mancante o troppo lunga")
    evidence = value["evidence"]
    if (not isinstance(evidence, list) or len(evidence) > 2 or
            any(not isinstance(q, str) for q in evidence) or len(evidence) != len(set(evidence))):
        raise ValueError("Evidence non valida o duplicata")
    for quote in evidence:
        if not isinstance(quote, str) or not 4 <= len(quote) <= 400 or quote not in document:
            raise ValueError("Citazione non letterale, vuota o fuori limite")
    if status == "assessable" and grade >= 1 and not evidence:
        raise ValueError("Un giudizio positivo richiede evidence nel documento")
    return value


def extract_judgment(response, document):
    try:
        choice = response["choices"][0]
        if choice["finish_reason"] != "stop" or choice["message"].get("refusal"):
            raise ValueError("Risposta rifiutata o incompleta")
        if not isinstance(response["model"], str) or not response["model"].strip():
            raise ValueError("Identificativo modello effettivo assente")
        return validate_judgment(strict_loads(choice["message"]["content"]), document)
    except (KeyError, IndexError, TypeError) as error:
        raise ValueError("Envelope del provider incompleto") from error


def request_body(settings, prompt, schema, query_text, document_text):
    # Nessun ID, gruppo di campionamento, qrel, ranking o altra annotazione.
    return {"model": settings["model_id"], "store": False, **settings["generation"],
            "messages": [{"role": "system", "content": prompt},
                         {"role": "user", "content": json.dumps({"information_need": query_text,
                                                                   "document": document_text}, ensure_ascii=False)}],
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "relevance_judgment", "strict": True, "schema": schema}}}


class ProviderFailure(Exception):
    def __init__(self, kind, retryable=False, uncertain=False, fatal=False):
        super().__init__(kind)  # Solo categoria; mai body HTTP, header o segreti.
        self.retryable, self.uncertain, self.fatal = retryable, uncertain, fatal


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HTTPError(req.full_url, code, "Redirect rifiutato", headers, fp)


class ChatProvider:
    def __init__(self, settings):
        self.settings = settings

    def available(self):
        return bool(self.settings["model_id"]) and (not self.settings["require_api_key"] or
                                                   bool(os.environ.get(self.settings["api_key_env"])))

    def complete(self, body):
        if not self.available():
            raise ProviderFailure("provider_or_credentials_not_configured", fatal=True)
        key = os.environ.get(self.settings["api_key_env"])
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = "Bearer " + key
        request = Request(self.settings["base_url"] + "/chat/completions",
                          data=json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8"),
                          headers=headers, method="POST")
        try:
            with build_opener(NoRedirect).open(request, timeout=self.settings["timeout_seconds"]) as response:
                raw = response.read(4_000_001).decode("utf-8")
                if len(raw) > 4_000_000:
                    raise ProviderFailure("response_too_large", uncertain=True)
                if key:
                    raw = raw.replace(key, "[REDACTED_CREDENTIAL]")
                try:
                    value = strict_loads(raw)
                except ValueError:
                    value = {"invalid_json_response": raw}
                return value
        except HTTPError as error:
            status = error.code
            error.close()
            raise ProviderFailure(f"http_{status}", retryable=status == 429 or 500 <= status < 600,
                                  fatal=400 <= status < 500 and status != 429) from None
        except (URLError, TimeoutError, OSError, UnicodeError):
            raise ProviderFailure("transport_failure", uncertain=True) from None
