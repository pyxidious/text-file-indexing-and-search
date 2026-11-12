"""Due indici posizionali, ricerca OR/phrase e ranking BM25."""
from collections import Counter
import math
from pathlib import Path

from .analyzers import ANALYZERS, ANALYZER_CONFIG
from .io import read_json, write_json


def parse_query(line):
    parts = line.strip().split(maxsplit=1)
    if len(parts) != 2 or parts[0] not in ANALYZERS:
        raise ValueError('Usare nome o contenuto seguiti da termini o da "una frase".')
    field, text = parts
    phrase = text.startswith('"') and text.endswith('"')
    if '"' in text and (not phrase or text.count('"') != 2):
        raise ValueError("Le virgolette devono racchiudere tutta la frase.")
    if phrase:
        text = text[1:-1]
    tokens = ANALYZERS[field](text)
    if not tokens:
        raise ValueError("La query deve contenere almeno una parola.")
    return field, tokens, phrase


class SearchEngine:
    def __init__(self, k1=1.2, b=0.75):
        if not math.isfinite(k1) or k1 <= 0 or not math.isfinite(b) or not 0 <= b <= 1:
            raise ValueError("BM25 richiede k1 > 0 e 0 <= b <= 1, entrambi finiti.")
        self.k1, self.b = k1, b
        self.documents = {}
        self.filename_index = {}
        self.content_index = {}
        self.lengths = {field: {} for field in ANALYZERS}

    @classmethod
    def build(cls, directory, k1=1.2, b=0.75):
        engine = cls(k1, b)
        root = Path(directory).resolve()
        # L'ID è il percorso relativo POSIX: stabile senza dipendere dall'ordine o dal contenuto.
        for path in sorted(root.rglob("*"), key=lambda p: p.relative_to(root).as_posix()):
            if not path.is_file() or path.suffix.lower() != ".txt":
                continue
            doc_id = path.relative_to(root).as_posix()
            engine.documents[doc_id] = {"filename": path.name, "path": doc_id}
            for field, text in (("nome", path.name),
                                ("contenuto", path.read_text(encoding="utf-8"))):
                tokens = ANALYZERS[field](text)
                engine.lengths[field][doc_id] = len(tokens)
                index = engine.index_for(field)
                for position, term in enumerate(tokens):
                    index.setdefault(term, {}).setdefault(doc_id, []).append(position)
        return engine

    def index_for(self, field):
        if field not in ANALYZERS:
            raise ValueError("Campo sconosciuto")
        return self.filename_index if field == "nome" else self.content_index

    def search(self, line):
        field, terms, phrase = parse_query(line)
        index = self.index_for(field)
        postings = [index.get(term, {}) for term in terms]
        if phrase:
            candidates = set(postings[0])
            for posting in postings[1:]:
                candidates.intersection_update(posting)
            # Trasla ogni posting rispetto alla posizione iniziale della frase.
            matched = set()
            for doc in sorted(candidates):
                starts = set(postings[0][doc])
                for offset, posting in enumerate(postings[1:], 1):
                    starts.intersection_update(pos - offset for pos in posting[doc])
                if starts:
                    matched.add(doc)
            candidates = matched
        else:
            candidates = set().union(*(set(posting) for posting in postings))
        n = len(self.documents)
        lengths = self.lengths[field]
        avgdl = sum(lengths.values()) / n if n else 0
        results = []
        for doc in sorted(candidates):
            score = 0.0
            # Query frequency esplicita: un termine ripetuto contribuisce più volte.
            for term, qtf in sorted(Counter(terms).items()):
                posting = index.get(term, {})
                tf = len(posting.get(doc, []))
                if tf:
                    idf = math.log(1 + (n - len(posting) + 0.5) / (len(posting) + 0.5))
                    norm = self.k1 * (1 - self.b + self.b * lengths[doc] / avgdl)
                    score += qtf * idf * tf * (self.k1 + 1) / (tf + norm)
            results.append({"id": doc, "filename": self.documents[doc]["filename"],
                            "score": score})
        return sorted(results, key=lambda row: (-row["score"], row["id"]))

    def save(self, path):
        write_json(path, {"format_version": 1, "analyzers": ANALYZER_CONFIG,
                          "bm25": {"k1": self.k1, "b": self.b},
                          "documents": self.documents, "lengths": self.lengths,
                          "filename_index": self.filename_index,
                          "content_index": self.content_index})

    @classmethod
    def load(cls, path):
        value = read_json(path)  # JSON, mai pickle o eval.
        if value["format_version"] != 1 or value["analyzers"] != ANALYZER_CONFIG:
            raise ValueError("Versione o analyzer dell'indice incompatibili")
        engine = cls(**value["bm25"])
        for key in ("documents", "lengths", "filename_index", "content_index"):
            setattr(engine, key, value[key])
        return engine
