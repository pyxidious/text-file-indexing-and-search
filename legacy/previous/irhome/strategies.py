"""Strategie di matching della sola query contenuto non phrase."""
from fractions import Fraction
import math
from pathlib import Path

STOPLIST_PATH = Path(__file__).resolve().parents[1] / "corpus" / "english_stopwords.txt"
STOPWORDS = frozenset(STOPLIST_PATH.read_text(encoding="utf-8").split())
MODES = ("or", "or_stop", "msm", "and")


def validate_strategy(mode, minimum_should_match=0.5):
    if mode not in MODES:
        raise ValueError("Strategia sconosciuta: or, or_stop, msm, and")
    if (isinstance(minimum_should_match, bool) or not math.isfinite(minimum_should_match)
            or not 0 < minimum_should_match <= 1):
        raise ValueError("Minimum should match deve essere finito in (0, 1]")


def required_matches(mode, distinct_terms, minimum_should_match=0.5):
    validate_strategy(mode, minimum_should_match)
    if not distinct_terms:
        return 0
    if mode == "and":
        return distinct_terms
    if mode == "msm":
        # Fraction evita errori di arrotondamento come ceil(0.07 * 100).
        return math.ceil(Fraction(str(minimum_should_match)) * distinct_terms)
    return 1
