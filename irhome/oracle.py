"""Scanner lessicale autonomo. Non importa motore, parser o analyzer dell'indice."""
import re
import unicodedata

NORMALIZATION = "NFC; lower; Unicode alphanumeric runs; underscore/punctuation/whitespace separate; no stemming or stopwords; filename basename without .txt"


def words(text):
    return re.findall(r"[^\W_]+", unicodedata.normalize("NFC", text).lower())


def expression(text, kind):
    phrase = kind == "phrase"
    if phrase:
        if not (text.startswith(chr(34)) and text.endswith(chr(34)) and text.count(chr(34)) == 2):
            raise ValueError("Phrase query: racchiudere l'intera espressione tra virgolette")
        text = text[1:-1]
    elif chr(34) in text:
        raise ValueError("Virgolette ammesse soltanto per le frasi")
    terms = words(text)
    if (not terms or kind not in ("single", "and", "phrase")
            or (kind == "single" and len(terms) != 1)
            or (kind == "and" and len(terms) < 2)):
        raise ValueError("Tipo di query o termini non validi")
    return terms


def inspect_text(text, terms, phrase):
    # Gli offset sul testo NFC permettono estratti anche per negativi parziali.
    text = unicodedata.normalize("NFC", text).lower()
    matches = list(re.finditer(r"[^\W_]+", text))
    tokens = [m.group() for m in matches]
    if phrase:
        starts = [i for i in range(len(tokens) - len(terms) + 1)
                  if tokens[i:i + len(terms)] == terms]
        found = bool(starts)
    else:
        starts = [i for i, token in enumerate(tokens) if token in terms]
        found = set(terms).issubset(tokens)
    offset = matches[starts[0]].start() if starts else 0
    end = matches[starts[0] + len(terms) - 1].end() if phrase and starts else offset + 160
    excerpt = text[max(0, offset - 60):max(offset + 160, end + 60)].replace("\n", " ")
    present = sorted(set(terms).intersection(tokens))
    return int(found), excerpt, " ".join(present)


def scan_document(path, field, terms, phrase):
    text = path.stem if field == "nome" else path.read_text(encoding="utf-8")
    return inspect_text(text, terms, phrase)
