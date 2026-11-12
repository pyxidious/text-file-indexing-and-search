"""Verificatore lessicale indipendente: scansiona file, senza usare indice o analyzer.

La specifica NFC/lower/token è reimplementata qui per non condividere bug nelle
posting list, nel parser o nella ricerca posizionale del motore.
"""
from pathlib import Path
import re
import unicodedata


def direct_scan(directory, query):
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
            found = bool(set(wanted).intersection(tokens))
        if found:
            matches.add(path.relative_to(root).as_posix())
    return matches
