# Homework 3 — Motore di ricerca riproducibile

Motore locale Python per file `.txt`, con due indici invertiti posizionali,
ricerca OR e di frasi, ranking BM25 e valutazione quantitativa. Solo standard
library, nessun servizio, rete o modello durante l'esecuzione. Nessuna GUI.

## Ambiente e avvio

Python **3.10 o successivo**. `.python-version` identifica la versione di
riferimento 3.10.0; `pyproject.toml` dichiara il requisito. Non occorre installare
pacchetti né installare il progetto: eseguire i comandi dalla radice del clone.

```powershell
python --version
python -m venv .venv
# Windows PowerShell (in alternativa usare direttamente .venv\Scripts\python.exe)
.venv\Scripts\Activate.ps1
# Linux/macOS: source .venv/bin/activate
python scripts/reproduce.py
```

Il comando unico valida ambiente e configurazione, genera e verifica 100, 300 e
600 documenti, costruisce e salva gli indici, esegue `unittest`, interroga gli
indici, verifica i risultati contro la lettura diretta ed esporta metriche e
misure. Un errore di hash, test o correttezza interrompe l'esecuzione con codice
diverso da zero. La configurazione versionata è `config/experiment.json`.

## Comandi separati

```powershell
python scripts/generate_dataset.py --count 600 --seed 42 --output artifacts/manual/dataset
python scripts/search.py build artifacts/manual/dataset/documents artifacts/manual/index.json
python scripts/search.py query artifacts/manual/index.json
python scripts/search.py query artifacts/manual/index.json --query 'contenuto "reti neurali"'
python -m unittest discover -s tests -v
python scripts/evaluate.py --config config/experiment.json --output artifacts/experiment
```

Nella console:

```text
nome database relazionali
nome "sistemi distribuiti"
contenuto intelligenza artificiale
contenuto "reti neurali"
esci
```

I termini senza virgolette sono in OR. Le virgolette devono racchiudere tutta
la frase; non sono supportati operatori booleani o sintassi mista. Il motore
stampa tutti i risultati: ID, filename e punteggio. Gestisce query vuote,
virgolette non bilanciate, campo errato, nessun risultato, EOF e Ctrl+C.
L'indicizzazione funziona anche su una directory personale UTF-8, ricorsivamente;
i file non testuali sono ignorati, errori di lettura/decodifica sono segnalati.

## Struttura e scelte di implementazione

- `irhome/analyzers.py`: analyzer distinti per nome e contenuto.
- `irhome/engine.py`: costruzione, posting list, phrase matching, BM25, JSON.
- `irhome/dataset.py`, `corpus/`: generatore, testi originali, modelli e query.
- `irhome/oracle.py`: scansione lessicale indipendente su file originali.
- `irhome/metrics.py`, `irhome/experiment.py`: metriche e protocollo di misura.
- `scripts/`: comandi; `tests/`: test con `unittest`.

Entrambi gli analyzer usano Unicode NFC e minuscolo (`lower`), poi sequenze
alfanumeriche Unicode con regex `[^\W_]+`. Accenti preservati, apostrofi e
punteggiatura separano parole, underscore separa token. Nessuno stemming e
nessuna rimozione di stopword. `FilenameAnalyzer` considera il basename, rimuove
solo l'estensione finale `.txt` e divide anche trattini e delimitatori.
Le query passano per gli stessi analyzer usati sui rispettivi campi.

`filename_index` e `content_index` sono due dizionari indipendenti:
`termine -> doc_id -> [posizioni crescenti]`. Le posizioni partono da zero e
contano tutti i token. Una phrase query interseca i documenti dei termini e
poi le posizioni traslate: `p, p+1, ..., p+n-1`. Non attraversa file diversi;
punteggiatura e a capo non introducono token né barriere di frase.

L'ID stabile è il percorso relativo POSIX del documento rispetto alla directory
indicizzata; il nome del dataset include anche un progressivo a sei cifre.
`documents[id]` conserva basename e percorso relativo originale. Per aprire un
documento, unire la directory dei documenti a quel percorso: non si salvano
percorsi assoluti dipendenti dalla macchina. Rinominare un file cambia il suo ID.

L'indice è un unico JSON UTF-8, con formato versione 1, configurazione analyzer,
parametri BM25, metadati, lunghezze di campo e i due indici. Chiavi ordinate,
newline LF, nessun timestamp; caricamento con `json`, senza esecuzione di codice
e senza pickle. Versioni e analyzer incompatibili sono rifiutati. È un formato
didattico per indici locali fidati, senza compressione o validazione di schemi
ostili. Non modificare i documenti senza ricostruire l'indice.

BM25 usa `k1=1.2`, `b=0.75`, configurabili, e statistiche del solo campo cercato:

```text
idf(t) = ln(1 + (N - df(t) + 0.5) / (df(t) + 0.5))
score(d,q) = somma_t qtf(t) * idf(t) *
             tf(t,d)*(k1+1) / (tf(t,d) + k1*(1-b+b*len(d)/avglen))
```

`N` include anche documenti vuoti; `avglen` è la lunghezza media del campo su
tutti i documenti. Un campo interamente vuoto non ha candidati né divisioni per
zero. Una frase filtra i documenti tramite posizioni e ordina quelli ammessi
con la stessa somma BM25 dei suoi termini, senza bonus di frase. I termini
ripetuti contribuiscono secondo `qtf`. Parità risolte per ID crescente.

## Dataset e rilevanza

Il valore predefinito è 600 file italiani su 12 argomenti, con temi assegnati
ciclicamente e bilanciati (50 file per tema a 600). `random.Random(seed)` locale,
seed 42, seleziona aperture, 3–15 paragrafi e schede lessicali da input versionati.
Le frasi del tema prevalgono sulle frasi trasversali, che introducono termini
condivisi. Nomi significativi, lunghezze variabili, sinonimi e forme correlate;
nessuna data, rete o stato globale. Le collezioni 100/300 sono prefissi della 600.
La riproducibilità va verificata con gli hash nell'ambiente Python documentato;
per confronti fra nuove versioni di Python ripetere i controlli, senza presumere
che ogni dettaglio delle funzioni casuali resti invariato per sempre.

Ogni dataset contiene `documents/`, `metadata.csv` (ID, filename, tema),
`queries.json` (12 query funzionali e 24 tematiche), `qrels.json` e `manifest.json`.
Il manifest contiene configurazione, SHA-256 degli input originali e di ogni
documento, metadato, query e qrels; non contiene il proprio hash. L'hash del
manifest, registrato nei risultati, identifica tutta la collezione.
La verifica ricontrolla ogni hash e l'insieme esatto dei file in `documents/`.
Per cambiare seed o dimensione usare una nuova directory: il generatore non
cancella file estranei. La stessa configurazione può essere rieseguita.

I qrels sono **sintetici**, binari: per una query tematica sono rilevanti tutti
e soli i documenti con la sua etichetta, assegnata prima dell'indicizzazione.
I documenti non elencati hanno giudizio 0. Non si ricavano qrels dai risultati.
Questo non equivale a giudizi umani: template finiti possono facilitare le
query, e la rilevanza reale dipende da intento, completezza e contesto.
Vedere anche `corpus/README.md` per la specifica degli input.

Le query funzionali hanno invece ground truth lessicale calcolata con lettura
diretta, normalizzazione e confronto di liste di token; il verificatore non usa
indice, parser o analyzer del motore. Tutte le 36 query vengono controllate
contro questo verificatore per l'esattezza dell'insieme recuperato. Il ranking
BM25 è verificato anche con un esempio calcolato nei test.

## Metriche e protocollo

Per ogni query si esportano Precision@10 (divisore fisso 10, anche se i risultati
sono meno), Recall@10, precision e recall su tutti i risultati, F1 su questi
ultimi e AP@10. AP@10 somma le precision ai ranghi rilevanti fino a 10 e divide
per `min(10, numero_rilevanti)`. MAP@10 è la media delle AP@10. Questa convenzione
troncata va considerata nel confronto con implementazioni che dividono per
tutti i rilevanti. La macro-media di F1 è distinta dalla F1 delle medie.

Query con rilevanti ma nessun risultato: precision, recall, F1 e AP a zero.
Query senza rilevanti: recall, F1 e AP non definite (`null`/campo CSV vuoto),
escluse dalle rispettive macro-medie; precision resta zero in caso di nessun
risultato. Si registra il numero di query con rilevanti. Le medie funzionali e
tematiche sono separate: il successo lessicale non misura la rilevanza tematica.

Per ciascuna dimensione si misurano almeno 5 ripetizioni con
`time.perf_counter_ns()`, separando:

1. generazione (scrittura documenti e costruzione manifest inclusi; verifica
   degli hash dopo la misura);
2. costruzione in memoria e salvataggio JSON, anche sommate come `index_total`;
3. caricamento dell'indice;
4. ogni singola query (analisi, matching, ranking e ordinamento, senza stampa).

Le verifiche di hash, la scansione diretta, i test e l'esportazione delle metriche
sono fuori dalle misure di ricerca. Non si misura generazione dentro
indicizzazione né caricamento dentro ricerca. I campioni sono sequenziali,
senza warm-up esplicito né svuotamento delle cache del filesystem: le scritture
ripetute sovrascrivono gli stessi file. Sono misure con cache potenzialmente
calde, influenzate da OS, hardware e carico. Non sono confronti cold-start e
non si pretendono tempi uguali fra macchine.

Si esportano campioni grezzi, mediana, min/max, deviazione standard della
popolazione e IQR con quartili inclusivi. La dimensione dell'indice è il numero
di byte del JSON, non lo spazio allocato a blocchi né la RAM del processo.

## Output e ripetizione

`artifacts/experiment/n100`, `n300`, `n600` contengono dataset, `index.json` e
`ranking.json` con risultati effettivi completi (ID, nome, score).
In `artifacts/experiment/results/`:

- `deterministic.json`: configurazione, analyzer, hash, byte degli indici,
  metriche per query e macro-medie, inclusa MAP@10.
- `metrics.csv`: metriche per query con dimensione e tipo.
- `checksums.json`: hash degli output deterministici principali.
- `observed.json`: Python, versione progetto/commit e stato Git se disponibile,
  OS, processore, architettura, CPU logiche, configurazione, hash dataset,
  ripetizioni e tempi realmente osservati; RAM non disponibile indicata `null`.
- `timing_samples.csv`, `timing_summary.csv`: misure e statistiche per fase/query.

Gli output ambientali e temporali sono separati da quelli deterministici. Il
benchmark controlla gli hash di ogni generazione e salvataggio ripetuti e la
stabilità del ranking. Un test rigenera due volte in directory diverse e
confronta tutti gli hash. Per verificare anche due esecuzioni complete:

```powershell
python scripts/reproduce.py --output artifacts/repeat
python -c "from pathlib import Path; a=Path('artifacts/experiment/results/checksums.json'); b=Path('artifacts/repeat/results/checksums.json'); assert a.read_bytes()==b.read_bytes(); print('Hash deterministici identici')"
```

I file generati sono ignorati da Git; tutti gli input per ricostruirli sono
versionabili. Prima di pubblicare il repository eseguire la procedura e
conservare gli output locali o allegarli separatamente a una release. Non sono
inclusi numeri di benchmark inventati né una relazione universitaria.
