"""Verificatore lessicale indipendente: scansiona file, senza usare indice o analyzer.

La specifica NFC/lower/token è reimplementata qui per non condividere bug nelle
posting list, nel parser o nella ricerca posizionale del motore.
"""
from pathlib import Path
import re
import unicodedata
from decimal import Decimal, ROUND_CEILING


def direct_scan(directory, query, strategy="or", minimum_should_match=0.5):
    match = re.fullmatch(r'(nome|contenuto)\s+(.+)', query.strip())
    if not match:
        raise ValueError("Query non valida")
    field, text = match.groups()
    phrase = text.startswith('"') and text.endswith('"')
    if '"' in text and (not phrase or text.count('"') != 2):
        raise ValueError("Virgolette non valide")

    def words(value):
        value = unicodedata.normalize("NFC", value).lower()
        if field == "nome":
            value = value.replace("\\", "/").split("/")[-1]
            if value.endswith(".txt"):
                value = value[:-4]
        return re.findall(r"[^\W_]+", value)

    wanted = words(text[1:-1] if phrase else text)
    if not wanted:
        raise ValueError("Query vuota")
    if strategy not in ("or", "or_stop", "msm", "and"):
        raise ValueError("Strategia non valida")
    ratio = Decimal(str(minimum_should_match))
    if not ratio.is_finite() or not 0 < ratio <= 1:
        raise ValueError("Quota non valida")
    effective = strategy if field == "contenuto" and not phrase else "or"
    if effective != "or":
        stopwords = set((Path(__file__).resolve().parents[1] / "corpus/english_stopwords.txt")
                        .read_text(encoding="utf-8").split())
        wanted = [word for word in wanted if word not in stopwords]
    if not wanted:
        return set()
    distinct = set(wanted)
    required = (len(distinct) if effective == "and" else
                int((ratio * len(distinct)).to_integral_value(rounding=ROUND_CEILING))
                if effective == "msm" else 1)
    matches = set()
    root = Path(directory)
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() != ".txt":
            continue
        tokens = words(path.name if field == "nome" else path.read_text(encoding="utf-8"))
        if phrase:
            found = any(tokens[i:i + len(wanted)] == wanted
                        for i in range(len(tokens) - len(wanted) + 1))
        else:
            found = len(distinct.intersection(tokens)) >= required
        if found:
            matches.add(path.relative_to(root).as_posix())
    return matches
