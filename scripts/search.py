"""Costruzione indici e console di ricerca."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from irhome.engine import SearchEngine
from irhome.io import read_json
from irhome.strategies import MODES, validate_strategy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("documents", type=Path)
    build.add_argument("index", type=Path)
    build.add_argument("--k1", type=float, default=1.2)
    build.add_argument("--b", type=float, default=0.75)
    search = sub.add_parser("query")
    search.add_argument("index", type=Path, nargs="?")
    search.add_argument("--query", help="Una singola query; altrimenti apre la console")
    search.add_argument("--strategy", choices=MODES)
    search.add_argument("--minimum-should-match", type=float, default=0.5)
    search.add_argument("--selection", type=Path, help="selection.json congelato dal development")
    search.add_argument("--limit", type=int, default=10, help="Massimo visualizzato, senza cambiare il ranking")
    args = parser.parse_args()
    if args.command == "build":
        if not args.documents.is_dir():
            parser.error("La directory dei documenti non esiste")
        engine = SearchEngine.build(args.documents, args.k1, args.b)
        engine.save(args.index)
        print(f"Indicizzati {len(engine.documents)} documenti in {args.index}")
        return
    if args.limit < 1:
        parser.error("--limit deve essere positivo")
    main = Path("artifacts/cranfield300")
    selection = args.selection or (main / "results/selection.json" if args.index is None else None)
    if args.strategy is not None and args.selection is not None:
        parser.error("Scegliere --strategy oppure --selection")
    mode, ratio = args.strategy or "or", args.minimum_should_match
    if args.strategy is None and selection is not None:
        spec = read_json(selection)["strategy"]
        mode, ratio = spec["mode"], spec["minimum_should_match"]
    validate_strategy(mode, ratio)
    engine = SearchEngine.load(args.index or main / "n300/index.json")

    def display(line):
        try:
            rows = engine.search(line, mode, ratio)
        except ValueError as error:
            print(f"Input non valido: {error}")
            return
        if not rows:
            print("Nessun risultato.")
        for row in rows[:args.limit]:
            print(f"{row['id']}\t{row['filename']}\t{row['score']:.6f}")
        print(f"Candidati: {len(rows)} | Visualizzati: {min(len(rows), args.limit)}")

    if args.query is not None:
        display(args.query)
        return
    print('Usare nome/contenuto e termini o "una frase". Uscita: esci.')
    while True:
        try:
            line = input("> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if line.strip().lower() == "esci":
            break
        display(line)


if __name__ == "__main__":
    main()
