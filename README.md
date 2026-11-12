# Homework 3 — Motore di ricerca e benchmark Cranfield

Motore Python locale per qualsiasi directory di file `.txt` UTF-8, con indici
posizionali separati per nome e contenuto, OR, phrase query, BM25 e persistenza
JSON. Il motore, il verificatore lessicale e le metriche usano solo standard
library. `ir_datasets` serve esclusivamente all'acquisizione di Cranfield;
nessun framework IR implementa ricerca, ranking o valutazione.

## Ambiente e riproduzione completa

Python **>=3.10**, versione di riferimento **3.10.0** in `.python-version`.
`ir_datasets==0.5.11` è fissato in `requirements.txt`; le dipendenze transitive
effettive dell'ambiente Windows/Python 3.10 sono fissate in
`requirements-lock.txt`. Su altre piattaforme possono servire wheel o strumenti
di compilazione diversi; le versioni effettivamente installate sono comunque
registrate nell'output ambientale. Il motore si usa anche senza queste dipendenze.

Dalla radice del repository, in PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pip check
.venv\Scripts\python.exe scripts/reproduce.py
```

Linux/macOS: sostituire `.venv\Scripts\python.exe` con `.venv/bin/python`.
Non è necessario installare il progetto come pacchetto. La prima acquisizione
richiede rete; il resto della procedura lavora su file locali. `reproduce.py`:

1. verifica versione Python, configurazione e versione di `ir_datasets`;
2. acquisisce o carica uno snapshot locale verificato;
3. prepara i TXT e gli export di query, qrels e metadati;
4. verifica hash, cardinalità e ripetibilità della preparazione;
5. costruisce e salva gli indici;
6. esegue tutti i test automatici e conserva `results/tests.log`;
7. verifica 12 query funzionali con scansione indipendente;
8. esegue le 225 query informative e i benchmark dei tempi;
9. esporta ranking, metriche, misure e informazioni ambientali.

Hash discordanti, test falliti, collisioni o mapping mancanti interrompono la
procedura. La configurazione è `config/experiment.json`: dimensioni 100/300/1400,
almeno 5 ripetizioni, BM25 `k1=1.2`, `b=0.75`, soglia di rilevanza 1.
Non ci sono campionamento casuale, seed o generazione di testi.

## Provenienza e distribuzione

Cranfield offre abstract scientifici inglesi, bisogni informativi reali e
giudizi di rilevanza preesistenti: permette di valutare il recupero informativo
senza fabbricare la ground truth dalle parole o dalle etichette dei documenti.
La collezione completa acquisita comprende **1.400 documenti, 225 query e 1.837
qrels**. È un benchmark piccolo e storico di dominio aeronautico; le misure
non si generalizzano automaticamente ad altri domini o a utenti moderni.

Fonti consultate:

- [Scheda ufficiale ir_datasets Cranfield](https://ir-datasets.com/cranfield.html).
- [Distribuzione dell'Università di Glasgow](https://ir.dcs.gla.ac.uk/resources/test_collections/cran/).
- [Release ir_datasets utilizzata](https://pypi.org/project/ir-datasets/0.5.11/).

La distribuzione pubblica e `cranqrel.readme` incluso nell'archivio non
espongono una licenza esplicita di redistribuzione nelle fonti consultate.
**Documenti, query, qrels e archivio non sono versionati nel repository**;
la licenza del software ir_datasets non è una licenza dei dati. Si versionano
la procedura e gli hash necessari a ricostruire e verificare la copia locale.

`irhome/acquire.py` usa `ir_datasets.load('cranfield')` e i suoi iteratori di
documenti, query e giudizi. Il download originale è controllato dal provider;
si ricontrolla inoltre il suo MD5 atteso
`1730f7be572d95a5a4b56c59a7b900a5`. Lo snapshot del progetto registra SHA-256
dell'archivio, dei record canonici e del manifest di origine, confrontati con
`config/cranfield.lock.json` versionato. I comandi pubblici non aggiornano il
lock automaticamente e non riscaricano dati corrotti per nascondere un errore.

## Copia locale e uso offline

Lo snapshot congelato è in `artifacts/cranfield-source/`:

- `cran.tar.gz`: archivio pubblico originale, immutato, incluso il suo readme;
- `records.json`: tutti i campi esposti dal provider, query e giudizi ordinati;
- `source-manifest.json`: provenienza, versione, conteggi e hash;
- `provider/`: cache tecnica di ir_datasets, non necessaria per ripetere offline.

Una volta creato, lo snapshot viene solo letto e verificato: nessun
aggiornamento o sovrascrittura automatica. Per un'altra macchina copiare i
primi tre file nella stessa directory (o usare `--cache`), rispettando le
condizioni d'uso dei dati, e predisporre l'ambiente software. Quindi:

```powershell
.venv\Scripts\python.exe scripts/acquire_cranfield.py --offline
.venv\Scripts\python.exe scripts/reproduce.py --offline
# Seconda esecuzione completa, con destinazione distinta
.venv\Scripts\python.exe scripts/reproduce.py --offline --output artifacts/cranfield-repeat
.venv\Scripts\python.exe -c "from pathlib import Path; a=Path('artifacts/cranfield-experiment/results/checksums.json'); b=Path('artifacts/cranfield-repeat/results/checksums.json'); assert a.read_bytes()==b.read_bytes(); print('Output deterministici identici')"
```

In modalità offline lo snapshot è caricato senza importare il provider e senza
tentare download; la procedura completa verifica comunque che la dipendenza
documentata sia installata. Il test offline impedisce anche l'apertura di socket.
Per un ambiente interamente isolato, procurarsi prima le dipendenze e le wheel
compatibili; il flag offline riguarda l'esperimento, non il comando pip.

## Trasformazione TXT e identificativi

La collezione pubblica e la sua trasformazione in TXT sono distinte. I record
sono ordinati per **ID originale numerico**, non lessicograficamente. Ogni
documento produce un solo TXT contenente **esattamente `doc.text`**, con la sola
conversione CRLF/CR in LF: nessun titolo aggiunto, nessun `strip`, traduzione,
taglio o newline finale aggiunto. L'adapter ir_datasets rimuove già gli spazi
esterni dei campi nel leggere il formato originale: il progetto conserva il
campo integrale restituito da quella versione. Alcuni abstract contengono già
il titolo nel testo originale; non viene rimosso né duplicato dal progetto.

Il filename segue una regola esplicita: titolo NFKD, conversione ASCII,
minuscolo, sequenze diverse da `[a-z0-9]` sostituite da `_`, eliminazione dei
delimitatori esterni, massimo 80 caratteri di slug; fallback `untitled`.
Si antepone l'ID numerico a quattro cifre e si aggiunge `.txt`:
`0042_aerodynamic_properties_of_wings.txt`. L'ID garantisce unicità anche per
titoli identici o troncati. Si verificano collisioni e conteggi effettivi.

`metadata.csv` e `manifest.json` associano `doc_id` originale, `engine_id`
(filename relativo alla directory indicizzata), filename, percorso relativo
`documents/...`, titolo, autore, bibliografia e SHA-256 del TXT. Il manifest
contiene inoltre configurazione, hash dello snapshot e di tutti gli export.
`verify_dataset` verifica byte, insieme esatto dei file e coerenza del mapping.

L'indicizzatore rimane generico: il collegamento a Cranfield esiste solo nella
valutazione. Essa verifica che il mapping copra esattamente gli ID del motore
e che ogni risultato si associ a un solo ID originale.

## Query, qrels e correttezza lessicale

`queries.json` contiene tutte le 225 query, con testo originale, `query_id`
fornito da ir_datasets e **anche `source_query_id` letto dai marcatori `.I` del
file originale**. Questi ultimi non sono consecutivi: il provider li rinumera
1..225 in ordine di apparizione per allinearli ai qrels. Conserviamo entrambe
le identità e usiamo solo gli ID allineati per collegare query e giudizi.
Le query passano direttamente come `contenuto <testo originale>` attraverso
il normale parser, analyzer e ranking del motore, senza riformulazione.

`qrels.json` è la lista completa dei 1.837 record originali con query ID,
documento ID, `relevance` e `iteration` del provider. Nessun filtro o
ribaltamento dei livelli, nessuna conversione distruttiva in booleani:

| Valore originale | Interpretazione nella scheda del provider | Conteggio |
| --- | --- | ---: |
| -1 | non rilevante | 225 |
| 1 | rilevanza minima | 128 |
| 2 | rilevanza utile | 387 |
| 3 | rilevanza elevata | 734 |
| 4 | risposta completa | 363 |

Per le metriche binarie, `relevance >= 1` è rilevante; `-1` è giudicato non
rilevante. I documenti senza qrel sono **non giudicati**: per il calcolo standard
sono trattati come zero, ma il ranking conserva `judgment: null` e stato
`unjudged`, distinti da `judged_nonrelevant` con valore `-1`. Non si afferma che
gli annotatori abbiano giudicato negativamente tutti i documenti non elencati.
Questa convenzione penalizza risultati potenzialmente utili ma non giudicati,
e il recall si riferisce ai soli rilevanti noti.

`corpus/functional_queries.json` definisce invece 12 controlli lessicali su
entrambi i campi: termini singoli, OR di più termini, frasi, stopword e assenza
di risultati. Il verificatore indipendente legge direttamente i TXT e confronta
token o sottoliste consecutive senza usare indici, parser o analyzer del motore.
I qrels Cranfield **non** valutano le query filename. L'esattezza lessicale
e la rilevanza informativa sono due verifiche separate.

## Metriche IR: benchmark principale su 1.400 documenti

Per tutte le 225 query, con `R` insieme dei rilevanti noti e ranking dei soli
documenti effettivamente restituiti:

- `Precision@10 = rilevanti nei primi 10 / 10`, anche con meno di 10 risultati;
- `Recall@10 = rilevanti nei primi 10 / |R|`;
- `F1@10`: media armonica di queste due metriche per singola query;
- precision, recall e F1 sull'intero insieme recuperato;
- `AP = somma delle precision ai ranghi rilevanti / |R|`, su **tutta** la lista;
- `MAP`: media delle AP delle query;
- `AP@10`: stessa somma limitata ai primi 10, divisa per `min(10, |R|)`;
- `MAP@10`: media delle AP@10, distinta dalla MAP completa.

La convenzione AP@10 preserva quella del progetto precedente. Non è
intercambiabile con implementazioni che usano `|R|` anche a cutoff 10.
I rilevanti non recuperati contribuiscono zero alla somma AP. Non si aggiungono
al ranking documenti non restituiti. Query con rilevanti e nessun risultato:
metriche zero. Senza rilevanti: precision zero per ranking vuoto, recall,
F1 e AP `null`, escluse dalle rispettive macro-medie; si registra quante query
hanno rilevanti. Le macro-medie di F1 non sono la F1 delle metriche medie.

I prefissi di **100 e 300 documenti** sono selezionati per ID numerico crescente
e servono solo alle prestazioni. Gli export conservano tutti i qrels originali,
anche quelli esterni al prefisso, ma **nessuna metrica IR viene calcolata su
questi sottoinsiemi**. Il benchmark principale rimane la collezione completa.

## Prestazioni e output

Per 100/300/1400 documenti si misurano con `time.perf_counter_ns()` almeno cinque
ripetizioni di preparazione, costruzione in memoria, salvataggio JSON,
caricamento e ciascuna delle 225 query. Il download e la verifica dello snapshot
non rientrano nei tempi di indicizzazione. Hash e controlli lessicali sono fuori
dai timer di ricerca; preparazione include scrittura e costruzione del manifest.
Le ripetizioni sono sequenziali, senza warm-up esplicito né svuotamento cache.
Si misurano quindi condizioni potenzialmente calde, sensibili a macchina e OS.

I CSV riportano campioni grezzi, mediana, min/max, deviazione standard della
popolazione e IQR con quartili inclusivi. La dimensione dell'indice è il numero
di byte del JSON, non la RAM o i blocchi allocati dal filesystem.

In `artifacts/cranfield-experiment/`:

- `n100/`, `n300/`, `n1400/`: dataset e `index.json`;
- `n1400/ranking.json`: per ogni query, testo e i due identificativi; per ogni
  risultato, rank, doc_id originale, engine_id, filename, score, giudizio
  disponibile, stato del giudizio e valore binario usato nelle metriche;
- `results/deterministic.json`: configurazione, lock, analyzer, hash dataset,
  indici e ranking, metriche per query, aggregate e controlli funzionali;
- `results/metrics.csv`, `aggregate_metrics.csv`, `functional_checks.json`;
- `results/checksums.json`: hash degli output deterministici principali;
- `results/observed.json`: Python, progetto/commit e stato Git, OS, hardware
  disponibile, tutte le versioni dei pacchetti, configurazione e misure reali;
- `results/timing_samples.csv`, `timing_summary.csv`: tempi per fase e query;
- `results/performance.csv`: confronto delle dimensioni e delle mediane di
  costruzione, persistenza e caricamento; per ricerca, mediana delle 225 mediane
  per query, da leggere insieme ai dettagli e alla variabilità;
- `results/tests.log`: esito effettivo dei test, con durata osservata.

`.gitattributes` mantiene LF negli input testuali versionati anche su Windows.
Tempi e ambiente sono separati dagli output deterministici. Ogni ripetizione
controlla hash dei dataset, degli indici e stabilità dei risultati. I test
ricostruiscono la stessa collezione in due directory e confrontano gli hash;
verificano anche byte degli abstract e integrità degli export originali.
Su un clone senza snapshot locale i test di integrazione Cranfield vengono
saltati, senza download impliciti; `reproduce.py` acquisisce i dati prima dei
test, quindi esegue anche questi controlli.

## Console e comandi separati

```powershell
.venv\Scripts\python.exe scripts/generate_dataset.py --offline
.venv\Scripts\python.exe scripts/search.py build artifacts/cranfield-manual/dataset/documents artifacts/cranfield-manual/index.json
.venv\Scripts\python.exe scripts/search.py query artifacts/cranfield-manual/index.json
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe scripts/evaluate.py --offline
```

Il nome storico `generate_dataset.py` è conservato, ma ora prepara Cranfield;
`--count` seleziona un prefisso, non genera testi. `evaluate.py` esegue il
benchmark completo senza i test; `reproduce.py` include anche i test.
In console:

```text
nome aerodynamic
nome wing pressure
nome "boundary layer"
contenuto pressure velocity
contenuto "heat transfer"
esci
```

Termini senza virgolette: OR. Frasi: tutti i termini consecutivi e nell'ordine
corretto. Le virgolette devono racchiudere tutta la frase; sintassi mista non
supportata. Si stampano ID, filename e punteggio; input errati, query senza
risultati, EOF e Ctrl+C sono gestiti. Per altri TXT usare la stessa console e
`search.py build <directory> <indice.json>`, senza alcun riferimento a Cranfield.

## Motore preservato e struttura

`irhome/engine.py`, `analyzers.py`, `oracle.py`, `io.py` e `scripts/search.py`
mantengono il comportamento originale; la migrazione riguarda dataset,
acquisizione, esperimenti, metriche, script di riproduzione e relativi test.
Le posting list restano `termine -> documento -> posizioni`, distinte nei due
campi. Posizioni zero-based; frasi mediante intersezioni di posizioni traslate.

Analyzer: NFC e `lower`, regex Unicode `[^\W_]+`, stopword e accenti preservati,
nessuno stemming. Filename: basename, rimozione dell'estensione `.txt`, divisione
dei delimitatori. Query e indicizzazione usano lo stesso analyzer del campo.
Il filename deriva da un titolo ASCII, ma l'abstract inglese rimane originale.

BM25 per campo con `N` documenti, inclusi i vuoti:

```text
idf(t) = ln(1 + (N - df(t) + 0.5) / (df(t) + 0.5))
score(d,q) = somma_t qtf(t) * idf(t) *
             tf(t,d)*(k1+1) / (tf(t,d) + k1*(1-b+b*len(d)/avglen))
```

Frasi: filtro posizionale e stessa somma BM25, senza bonus. Parità: ID crescente.
L'indice è JSON deterministico UTF-8 formato 1, senza pickle o esecuzione di
codice al caricamento; configura analyzer e BM25 e conserva lunghezze e percorsi
relativi. Non modificare i file senza ricostruirlo. Formato locale didattico,
non progettato per input JSON ostili.

Il materiale sintetico della versione precedente è isolato in
`legacy/synthetic/` e non viene eseguito. I vecchi output locali
`artifacts/experiment` e `artifacts/repeat` sono storici, non risultati attuali.
Tutti i dati e indici ricostruibili rimangono esclusi da Git. Nessuna relazione
universitaria viene generata: gli output costituiscono i dati per prepararla.
