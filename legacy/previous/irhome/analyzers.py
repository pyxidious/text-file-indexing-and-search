"""Le posizioni sono ordinali di token, a partire da zero."""
import re
import unicodedata

ANALYZER_CONFIG = {
    "unicode": "NFC", "case": "lower", "token_pattern": r"[^\W_]+",
    "stopwords": "preserved", "positions": "zero-based token offsets",
    "filename": "basename; strip terminal .txt; split non-alphanumeric delimiters",
}


def normalize(text):
    return unicodedata.normalize("NFC", text).lower()


class ContentAnalyzer:
    def __call__(self, text):
        return re.findall(r"[^\W_]+", normalize(text), flags=re.UNICODE)


class FilenameAnalyzer(ContentAnalyzer):
    def __call__(self, text):
        text = normalize(text.replace("\\", "/").rsplit("/", 1)[-1])
        if text.endswith(".txt"):
            text = text[:-4]
        return super().__call__(text)


ANALYZERS = {"nome": FilenameAnalyzer(), "contenuto": ContentAnalyzer()}
