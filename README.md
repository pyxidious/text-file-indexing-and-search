# Homework 3 — Indicizzazione, ricerca e valutazione lessicale

Motore Python per tutti i `.txt` di una directory, con indici posizionali separati
per **nome** e **contenuto**, console, phrase query e ranking BM25. Il corpus
conservato contiene **300 documenti Cranfield**. Solo libreria standard Python
**>=3.10**; nessuna installazione di pacchetti, download o servizio esterno.

La nuova ground truth è **lessicale binaria e indipendente dal motore**.
Non usa query o relevance judgments ufficiali Cranfield. Sono disponibili
3.000 giudizi proposti automaticamente; **la revisione umana non è stata effettuata**.
Le metriche del corpus non vengono calcolate finché i giudizi non sono validati
e congelati. Questo README documenta il progetto, non è la relazione universitaria.

## Esecuzione

Dalla radice del repository, su Windows, Linux o macOS:

```sh
python scripts/reproduce.py
python scripts/search.py query
```

`reproduce.py` verifica gli hash dei documenti, calcola le statistiche, prepara
le proposte senza sovrascrivere revisioni, esegue i test, costruisce l'indice e
misura tre ripetizioni di indicizzazione. Esegue anche la valutazione **solo se**
esiste una ground truth validata e congelata. Senza validazione stampa lo stato
pendente e termina dopo le operazioni riproducibili già possibili.

Comandi separati:

```sh
python scripts/search.py build
python scripts/search.py query --query "contenuto pressure velocity"
python scripts/ground_truth.py propose
python scripts/benchmark.py
python -m unittest discover -s tests -v
```

In PowerShell, per usare l'ambiente locale già presente, sostituire `python` con
`.venv\Scripts\python.exe`. I comandi non richiedono quell'ambiente specifico.
Su una directory diversa: `python scripts/search.py build percorso/txt artifacts/custom.json`
e `python scripts/search.py query artifacts/custom.json`.

## Architettura e refactoring

Il motore preesistente è stato conservato: indici invertiti posizionali, analyzer,
formula BM25 (`k1=1.2`, `b=0.75`), ordinamento per score decrescente e ID a parità,
salvataggio/caricamento JSON formato 1. Il matching predefinito è stato ridotto
ad AND coerente in entrambi i campi, senza filtri sulle stopword. OR rimane
disponibile esplicitamente nella console con `--strategy or`.

Confronti di strategie, split development/test, acquisizione con export di qrels,
metriche AP/MAP e pipeline LLM sono conservati in `legacy/previous/` e non sono
importati o eseguiti dal progetto corrente. Il dettaglio dell'ispezione e dei
componenti unificati è in [docs/refactoring.md](docs/refactoring.md).

```text
corpus/
  documents/              300 TXT invariati
  metadata.csv            ID Cranfield, filename, titolo, SHA-256, byte
  README.md               provenienza e trasformazioni verificabili
irhome/
  engine.py               indicizzazione, parsing, ricerca e BM25
  analyzers.py, io.py      analyzer e serializzazione esistenti
  dataset.py              inventario, verifica hash e statistiche
  oracle.py               scanner lessicale autonomo
  ground_truth.py         proposta, revisione, congelamento
  metrics.py              TP/FP/FN, P/R/F1, @10 e macro
  evaluation.py           confronto ranking completo / ground truth
  benchmark.py            tempi di costruzione
scripts/
  search.py, ground_truth.py, evaluate.py, benchmark.py, reproduce.py
tests/test_homework.py
evaluation/
  queries.csv
  review.csv              tutte le 3.000 coppie, revisione pendente
  proposed_positives.csv, proposed.json
  dataset_analysis.json
  timing_samples.csv, timing_summary.csv, benchmark.json
docs/refactoring.md
legacy/                   materiale storico escluso
artifacts/homework/        indice e, dopo validazione, risultati (ignorati da Git)
```

`final_positives.csv` e `frozen.json` verranno creati in `evaluation/` soltanto
dopo una revisione umana completa. Nessun file finale vuoto viene spacciato
per ground truth validata. Le altre directory in `artifacts/` sono vecchi output
locali e non sono input del protocollo corrente.

## Dataset

La directory canonica è `corpus/documents/`: **300 file, 309.724 byte,
48.695 token, 3.993 token distinti**, nessun duplicato a contenuto identico
(confronto SHA-256). Non è una verifica di somiglianza semantica fra abstract.
Testi scientifici in inglese su aerodinamica, strato limite, onde d'urto,
trasferimento di calore, stabilità e strutture; includono numeri, trattini,
interruzioni di riga e imperfezioni testuali originali.

I filename hanno già forma `0003_the_boundary_layer_in_simple_shear_flow_past_a_flat_plate.txt`:
ID originale a quattro cifre e slug del titolo. Non sono stati rinominati.
Tutti i 300 metadati contengono un titolo; 299 testi iniziano con gli stessi
token del titolo, mentre il documento 1369 presenta una variante testuale
(`oseens s` nel testo rispetto a `oseen s` nel titolo). Non è stata corretta.

Le frequenze sono conteggi sul testo normalizzato, indipendenti dal motore:
`the` 4.090, `of` 2.705, `flow` 438, `pressure` 282, `boundary` 242, `layer` 226.
Bigrammi ricorrenti: `boundary layer` 174, `heat transfer` 102,
`mach number` 92. Conteggi completi dei primi 40 termini e bigrammi in
`evaluation/dataset_analysis.json`; le occorrenze non sono conteggi di documenti.

La provenienza Cranfield, il campionamento verificato e i limiti di ciò che è
ricostruibile sono descritti in [corpus/README.md](corpus/README.md).
I file sono stati copiati byte per byte dal corpus locale corrente, verificando
gli hash del suo manifest; nessun contenuto è stato modificato.

## Analyzer e sintassi

Due analyzer già presenti, con regole volutamente semplici:

- Unicode NFC e minuscole; token come sequenze di lettere/numeri Unicode
  (`[^\W_]+`). Nessuno stemming, sinonimo o rimozione di stopword.
- Punteggiatura, underscore, trattini, apostrofi e whitespace separano i token.
  Per esempio `boundary-layer` e `boundary\nlayer` hanno gli stessi due token.
  Un punto non introduce un vincolo di confine di frase; `5.8` diventa `5`, `8`.
- Il campo `nome` usa il solo basename senza estensione `.txt`, conservando
  il token numerico dell'ID; `contenuto` usa tutto il testo UTF-8, titolo
  eventualmente già incluso. Le posizioni contano i token, incluse le stopword.

Il prefisso deve essere `nome` o `contenuto`. Termini senza virgolette:
**AND**, tutti devono essere presenti, anche distanti. L'ordine non conta.
Le virgolette devono racchiudere l'intera espressione: tutti i token devono
essere consecutivi e nello stesso ordine. Il matching è insensibile al caso.

```text
nome flow
nome laminar boundary
nome "boundary layer"
contenuto pressure velocity
contenuto "heat transfer"
esci
```

BM25 ordina soltanto i documenti che soddisfano il matching. La console visualizza
10 risultati per default (`--limit` modificabile), stampando anche il totale.
La valutazione non applica quel limite. Query malformate, zero risultati,
EOF e Ctrl+C sono gestiti dalla console.

## Dieci query originali e giudizi proposti

Le query sono state fissate studiando titoli, testi e distribuzioni lessicali,
prima di eseguire query sul motore del corpus. Le espressioni comuni coprono
insiemi ampi; il termine specialistico osservato nel titolo del documento 402
fornisce un caso raro. Non sono state selezionate confrontando ranking o metriche.
Campo, espressione, tipo e criterio atteso sono in `evaluation/queries.csv`.

| ID | Query | Tipo | Positivi proposti |
| --- | --- | --- | ---: |
| Q01 | `nome flow` | Termine | 54 |
| Q02 | `nome pressure` | Termine | 26 |
| Q03 | `nome laminar boundary` | AND | 14 |
| Q04 | `nome "boundary layer"` | Frase | 32 |
| Q05 | `nome magnetohydrodynamics` | Termine | 1 |
| Q06 | `contenuto flow` | Termine | 159 |
| Q07 | `contenuto pressure velocity` | AND | 27 |
| Q08 | `contenuto heat temperature` | AND | 26 |
| Q09 | `contenuto "heat transfer"` | Frase | 41 |
| Q10 | `contenuto "mach number"` | Frase | 63 |

## Ground truth indipendente e revisione

`python scripts/ground_truth.py propose` scandisce tutti i TXT direttamente
dal filesystem e verifica tutte le **10 × 300 = 3.000 coppie**. Lo scanner
reimplementa normalizzazione e matching senza importare motore, analyzer,
parser o metriche. Non legge indici, risultati, score, query ufficiali o qrels.
La rilevanza lessicale è esattamente presenza del termine, presenza di tutti
i termini AND, oppure presenza della sequenza consecutiva per le frasi.

`proposed_positives.csv` contiene tutti i positivi proposti. `review.csv` contiene
ogni coppia, query, ID stabile (percorso relativo del documento), filename,
etichetta automatica, estratto normalizzato e termini presenti. Per un AND
con termini distanti l'estratto può mostrarne soltanto alcuni: consultare tutto
il TXT. Anche un negativo può contenere singoli termini della query.
L'ID originale Cranfield è recuperabile da `corpus/metadata.csv` e dal prefisso
del filename; nessun giudizio Cranfield è associato alle nuove query.

Procedura per il revisore umano, prima di interrogare il motore sulle dieci query:

1. Esaminare positivi, negativi e casi dubbi rispetto alla definizione lessicale;
   consultare i TXT quando l'estratto non basta. Non usare il ranking come guida.
2. Impostare `reviewed=1` per ogni coppia verificata. Lasciare `manual_label`
   vuoto per confermare, oppure inserire `0`/`1`; una modifica richiede `reason`.
   Usare motivazioni lessicali: non sostituire il criterio con una valutazione semantica.
3. Dopo la revisione completa, eseguire con un'identità reale e una nota reale:

```sh
python scripts/ground_truth.py freeze --reviewer "Nome del revisore" --approval-note "Revisione lessicale completa delle 3000 coppie"
python scripts/evaluate.py
```

Il congelamento rifiuta coppie mancanti/duplicate, revisioni incomplete,
etichette non valide o correzioni senza motivazione. Produce il CSV separato
`final_positives.csv` e `frozen.json`, con identità di corpus/query/scanner,
hash di giudizi e revisione, revisore e nota. Non sovrascrive un congelamento
esistente. Il valutatore controlla gli hash **prima di interrogare il motore**;
modifiche successive richiedono una nuova revisione in una nuova directory.
Per un nuovo esperimento usare `--output evaluation/nuova-revisione` nello scanner
e `--ground-truth evaluation/nuova-revisione` nel valutatore.

Attualmente tutti i campi di revisione sono vuoti: **nessuna validazione umana
è dichiarata**. Le metriche finali restano da eseguire dopo tale passaggio.
I test simulano il processo esclusivamente su documenti artificiali temporanei.

Questa ground truth misura la **correttezza lessicale**, non l'utilità semantica
o la rilevanza tematica esaustiva. Un documento può essere semanticamente utile
senza usare i token richiesti; qui sarebbe negativo secondo la definizione.
La recall misura tutti i positivi lessicali del corpus, grazie alla scansione
esaustiva; non la recall dei bisogni informativi originari di Cranfield.

## Metriche

Su tutti i risultati: TP = recuperati rilevanti, FP = recuperati non rilevanti,
FN = rilevanti non recuperati; `P = TP/(TP+FP)`, `R = TP/(TP+FN)` e
`F1 = 2TP/(2TP+FP+FN)`, equivalente alla media armonica quando definita.
Si aggiungono P@10 (denominatore fisso 10, anche con meno risultati) e R@10
(denominatore tutti i positivi), usando il ranking BM25 completo.

Senza risultati la precision è non definita. Con positivi ma nessun risultato,
recall e F1 sono zero. Senza positivi, recall, R@10 e F1 sono non definite;
la precision è zero se ci sono risultati, altrimenti non definita. P@10 resta
definita con denominatore fisso 10. Un valore non definito è `None` in Python,
`null` in JSON e una cella vuota in CSV. Le macro-medie escludono soltanto i
valori non definiti della rispettiva metrica e riportano il numero di query
incluse. Non si calcolano AP, MAP, MRR o nDCG.

Dopo la validazione, `artifacts/homework/results/` conterrà `metrics.csv`
(una riga per query), `results.csv` (tutti i risultati, rank e score), `macro.csv`
e `evaluation.json` (hash del congelamento e motore). Anche il terminale
mostrerà conteggi e metriche. Prima del freeze il comando fallisce senza
generare metriche o interrogare il motore.

## Tempi effettivamente misurati

Esecuzione locale del 13 novembre 2026, Python 3.10.0 / Windows, tre ripetizioni:

| Documenti | Mediana indicizzazione (ms) |
| ---: | ---: |
| 100 | 61,8482 |
| 200 | 121,0195 |
| 300 | 185,6225 |

I sottoinsiemi sono i primi 100/200/tutti i file ordinati per percorso relativo
POSIX crescente: deterministici, annidati e indipendenti dalle query. Non sono
necessariamente gli stessi subset dei vecchi esperimenti. Lista esatta, hash,
timestamp e ambiente sono in `evaluation/benchmark.json`; campioni grezzi e
mediane/min/max nei CSV `timing_samples.csv` e `timing_summary.csv`.

Timer `perf_counter_ns`: include lettura UTF-8 dei file, analyzer dei due campi,
costruzione posting/posizioni e lunghezze. Esclude scoperta dei file, preparazione,
download, serializzazione JSON e distruzione dell'oggetto. Ogni prova costruisce
un nuovo indice in memoria e controlla il numero di documenti; non accumula dati.
Non si svuotano le cache e non c'è warm-up esplicito: i tempi dipendono anche
da filesystem, cache e carico della macchina. Non sono garanzie prestazionali.
Rieseguire `python scripts/benchmark.py` aggiorna i risultati osservati; i tempi
non saranno identici fra esecuzioni.
