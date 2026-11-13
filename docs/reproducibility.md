# Riproducibilità dell'esperimento

## Provenienza del corpus

La fonte dichiarata dal codice di acquisizione è Cranfield tramite
`ir_datasets 0.5.11`, archivio
`http://ir.dcs.gla.ac.uk/resources/test_collections/cran/cran.tar.gz`.
Questa dipendenza apparteneva all'acquisizione una tantum: il workflow attuale
usa i 300 TXT versionati, senza download, query ufficiali o qrels.

`provenance/cranfield_origin.json` conserva versione, URL, checksum MD5 e SHA-256
dell'archivio, hash dello snapshot originario, elenco degli ID selezionati e hash
dei metadati. I checksum upstream sono evidenza storica: non è stata ripetuta
l'acquisizione durante la pulizia del repository.

`provenance/cranfield_preparation.py` conserva senza modifiche le funzioni
originarie `select_documents`, `normalized_newlines` e `document_filename`,
insieme all'operazione di esportazione dei byte. Il JSON identifica commit e
blob Git delle sorgenti complete precedenti. Sono recuperabili, senza riscrivere
la storia, con:

```sh
git show ebe01475f3bfe3ec65be4777594a0a03a090cd18:legacy/previous/irhome/dataset.py
git show ebe01475f3bfe3ec65be4777594a0a03a090cd18:legacy/previous/irhome/acquire.py
```

Procedura verificabile:

1. Ordinare numericamente gli ID originali `1..1400`.
2. Applicare `random.Random(42).shuffle`, prendere i primi 300, riordinarli per ID.
3. Usare `doc.text`, normalizzando soltanto CRLF/CR in LF, e codificare UTF-8.
   Non aggiungere titolo, `strip`, traduzione o newline finale.
4. Convertire il titolo con NFKD, ASCII con `ignore`, minuscole; sostituire le
   sequenze non `[a-z0-9]` con `_`, eliminare `_` agli estremi, troncare a 80
   caratteri, rimuovere `_` finali; usare `untitled` se vuoto. Anteporre l'ID
   numerico a quattro cifre e aggiungere `.txt`.

Il motore usa come ID il percorso relativo POSIX, uguale al filename nel corpus
corrente; `metadata.csv` lo collega all'ID Cranfield originale. Il titolo può
essere più lungo del basename: per le query `nome` conta soltanto quest'ultimo.
I 300 file occupano 309.724 byte. Errori e frammenti degli abstract sono preservati;
non si afferma equivalenza con i byte grezzi dell'archivio prima della conversione
operata dal provider. La selezione degli ID, i filename e gli hash locali si verificano con:

```sh
python provenance/cranfield_preparation.py
```

## Ambiente e integrità

Python >=3.10, verificato con 3.10.0; soltanto libreria standard. Nessun `pip install`
è necessario. `pyproject.toml` dichiara `dependencies = []`; `.python-version`
registra l'ambiente originario. Non sono richiesti snapshot o ambienti in `artifacts/`.

Dalla radice di un clone pulito:

```sh
python --version
python -m unittest discover -s tests -v
python scripts/verify_semantic_proposals.py
python scripts/semantic_ground_truth.py status
```

Il verificatore controlla corpus/metadati, 3.000 coppie, proposte, correzioni e
ripartizione delle conferme; `status` carica il freeze e verifica anche gli hash
di annotazioni, provenienza, positivi definitivi e file di supervisione.
I test di revisione usano soltanto dati artificiali temporanei.

Tutta `evaluation/semantic/` resta versionata. I file `history/`, `calibration*`,
i blocchi delle proposte e i manifest sono prove della procedura o dipendenze dei
controlli, non esperimenti alternativi da rilanciare. Alcune utility e i moduli
`ground_truth.py`/`oracle.py` restano perché importati, testati o identificati da
hash nei manifest; non si usa una ground truth lessicale nella valutazione finale.
Non aggiornare le descrizioni storiche dei manifest: l'autorità del congelamento
è `frozen.json`, stato `semantic_ground_truth_codex_assisted_partially_supervised`.

## Valutazione e output

```sh
python scripts/search.py build
python scripts/search.py query --query "contenuto pressure velocity"
python scripts/evaluate.py --strategy and
python scripts/evaluate.py --strategy or
python scripts/compare_matching.py
```

`build` produce `artifacts/homework/index.json`; `query` lo carica. Le valutazioni
costruiscono indici in memoria con lo stesso motore e controllano il freeze prima
della ricerca. AND è il default. OR unisce i posting dei termini non quotati;
phrase query, analyzer e BM25 restano identici.

Le directory locali `artifacts/homework/results/` (AND) e `results_or/` (OR)
contengono `metrics.csv`, `macro.csv`, `results.csv`, `errors.csv`, `evaluation.json`.
Il confronto aggiunge in `results_or/` `comparison.csv`, `comparison_macro.csv`,
`comparison.json` e `comparison.md`, con differenze OR meno AND e hash delle corse.
Non sono file versionati: un clone li genera eseguendo i comandi sopra.

Per preservare una corsa locale preesistente, scegliere directory diverse:

```sh
python scripts/evaluate.py --strategy and --output artifacts/replay/and
python scripts/evaluate.py --strategy or --output artifacts/replay/or
python scripts/compare_matching.py --baseline artifacts/replay/and --candidate artifacts/replay/or
```

Le metriche complete usano tutti i risultati: `P=TP/(TP+FP)`, `R=TP/(TP+FN)`,
`F1=2TP/(2TP+FP+FN)`. P@10 divide sempre per 10; R@10 divide per tutti i rilevanti.
Precision è non definita senza risultati; recall, R@10 e F1 sono non definite
senza rilevanti. Le macro-medie escludono i valori non definiti della singola
metrica e riportano quante query includono. Nell'esperimento tutte le dieci sono
definite. Le formule sono quelle del modulo `irhome/metrics.py`.

Corpus, query, freeze e codice fissati rendono deterministici gli insiemi di
risultati e i conteggi; gli score in virgola mobile sono confrontabili entro la
precisione numerica. I risultati macro di riferimento sono nel README.

## Benchmark e giudizi assistiti

```sh
python scripts/benchmark.py
```

Il benchmark usa i primi 100, 200 e tutti i 300 percorsi ordinati e tre indici
freschi per dimensione. `perf_counter_ns` include lettura UTF-8, tokenizzazione,
posting, posizioni e lunghezze; esclude scoperta dei file, serializzazione JSON
e distruzione dell'oggetto. Non svuota le cache e non esegue warm-up esplicito.
Aggiorna i file versionati `evaluation/benchmark.json`, `timing_samples.csv` e
`timing_summary.csv`, con ambiente, subset e campioni. Le mediane originarie
sono 61,8482 / 121,0195 / 185,6225 ms; nuove misure dipendono da macchina e carico.
Per misurare senza sostituirle: `python scripts/benchmark.py --output artifacts/benchmark`.

La ground truth contiene 521 positivi fra 3.000 coppie. La supervisione assistita
ha confermato 38 coppie di calibrazione, 85 dopo discussione e 168 in blocco;
queste ultime non attestano lettura individuale dei documenti. Le altre 2.709
coppie non sono confermate. Prompt, proposte e revisioni sono disponibili, ma
mancano versione esatta del modello e condizioni complete della generazione:
non è riproducibile l'annotazione LLM originale. È riproducibile la valutazione
sullo stesso riferimento congelato, con i suoi limiti metodologici.
