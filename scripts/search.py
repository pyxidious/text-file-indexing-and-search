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
    build.add_argument("documents", type=Path)
    build.add_argument("index", type=Path)
    build.add_argument("--k1", type=float, default=1.2)
    build.add_argument("--b", type=float, default=0.75)
    search = sub.add_parser("query")
    search.add_argument("index", type=Path)
    search.add_argument("--query", help="Una singola query; altrimenti apre la console")
    args = parser.parse_args()
    if args.command == "build":
        if not args.documents.is_dir():
            parser.error("La directory dei documenti non esiste")
        engine = SearchEngine.build(args.documents, args.k1, args.b)
        engine.save(args.index)
        print(f"Indicizzati {len(engine.documents)} documenti in {args.index}")
        return
    engine = SearchEngine.load(args.index)

    def display(line):
        try:
            rows = engine.search(line)
        except ValueError as error:
            print(f"Input non valido: {error}")
            return
        if not rows:
            print("Nessun risultato.")
        for row in rows:
            print(f"{row['id']}\t{row['filename']}\t{row['score']:.6f}")
        print(f"Risultati: {len(rows)}")

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
