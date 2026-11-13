"""Tre costruzioni fresche su prefissi deterministici della stessa lista di file."""
from datetime import datetime, timezone
from pathlib import Path
import platform
from statistics import median
import sys
from time import perf_counter_ns

from .dataset import corpus_identity, document_paths, write_csv
from .engine import SearchEngine
from .io import sha256, write_json


def benchmark(documents="corpus/documents", output="evaluation", repetitions=3):
    if type(repetitions) is not int or repetitions < 3:
        raise ValueError("Richieste almeno tre ripetizioni")
    paths = document_paths(documents)
    if len(paths) < 200:
        raise ValueError("Servono almeno 200 documenti")
    root = Path(documents).resolve()
    output = Path(output)
    samples, summaries, subsets = [], [], {}
    for size in sorted({100, 200, len(paths)}):
        selected = paths[:size]
        subsets[str(size)] = [p.relative_to(root).as_posix() for p in selected]
        values = []
        for repetition in range(1, repetitions + 1):
            start = perf_counter_ns()
            engine = SearchEngine.build(root, paths=selected)
            elapsed = perf_counter_ns() - start
            if len(engine.documents) != size:
                raise AssertionError("Conteggio inatteso nell'indice fresco")
            del engine
            values.append(elapsed / 1_000_000)
            samples.append(dict(documents=size, repetition=repetition, indexing_ms=values[-1]))
        summaries.append(dict(documents=size, repetitions=repetitions,
                              median_ms=median(values), min_ms=min(values), max_ms=max(values)))
    write_csv(output / "timing_samples.csv", samples, list(samples[0]))
    write_csv(output / "timing_summary.csv", summaries, list(summaries[0]))
    write_json(output / "benchmark.json", dict(measured_at_utc=datetime.now(timezone.utc).isoformat(),
               python=sys.version, platform=platform.platform(), processor=platform.processor(),
               engine_sha256=sha256(Path(__file__).with_name("engine.py")),
               corpus=corpus_identity(documents), subsets=subsets,
               protocol="perf_counter_ns; fresh in-memory index each run; includes UTF-8 reads, tokenization, postings, lengths; excludes discovery, preparation, download, JSON save and object disposal; no cache flush or warm-up", 
               summary=summaries))
    for row in summaries:
        print(f"{row['documents']} documenti: mediana {row['median_ms']:.3f} ms ({repetitions} ripetizioni)")
    return summaries
