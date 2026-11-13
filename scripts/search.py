"""Costruzione indici e console di ricerca."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from irhome.engine import SearchEngine


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("documents", type=Path, nargs="?", default=Path("corpus/documents"))
    build.add_argument("index", type=Path, nargs="?", default=Path("artifacts/homework/index.json"))
    search = sub.add_parser("query")
    search.add_argument("index", type=Path, nargs="?", default=Path("artifacts/homework/index.json"))
    search.add_argument("--query")
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--strategy", choices=("and", "or"), default="and")
    args = parser.parse_args()
    if args.command == "build":
        engine = SearchEngine.build(args.documents)
        engine.save(args.index)
        print(f"Indicizzati {len(engine.documents)} documenti in {args.index}")
        return
    if args.limit < 1:
        parser.error("--limit deve essere positivo")
    engine = SearchEngine.load(args.index)

    def display(line):
        try:
            rows = engine.search(line, args.strategy)
        except ValueError as error:
            print(f"Input non valido: {error}")
            return
        for row in rows[:args.limit]:
            print(f"{row['id']}\t{row['score']:.6f}")
        if not rows:
            print("Nessun risultato.")
        print(f"Candidati: {len(rows)} | Visualizzati: {min(len(rows), args.limit)}")

    if args.query is not None:
        display(args.query)
        return
    print('Usare nome/contenuto e termini o "una frase". AND predefinito. Uscita: esci.')
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
