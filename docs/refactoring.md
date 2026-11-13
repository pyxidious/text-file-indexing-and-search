> Nota: questo documento descrive il refactoring lessicale precedente. Il protocollo di valutazione corrente è semantico; vedere il README e `evaluation/semantic/criteria.csv`.

# Ispezione e refactoring

L'ispezione precedente alle modifiche ha identificato Python >=3.10, nessun
framework per il motore e `ir_datasets==0.5.11` come dipendenza di acquisizione.
Erano presenti un ambiente `.venv`, numerose copie di esperimenti in `artifacts/`,
un archivio sintetico e una pipeline di annotazione silver. Lo stato Git iniziale
era pulito. Non sono stati consultati i testi delle query ufficiali né i qrels
per scegliere le nuove query o costruire i nuovi giudizi.

| Componente precedente | Ruolo verificato | Intervento |
| --- | --- | --- |
| `irhome/engine.py` | Indici posizionali separati, parsing, BM25, JSON | Conservato; AND predefinito in entrambi i campi, OR esplicito; selezione dei file per benchmark |
| `irhome/analyzers.py`, `io.py` | Analyzer distinti e serializzazione | Invariati |
| `strategies.py` | OR con stopword, minimum should match, AND filtrato | Archiviato; matching essenziale direttamente nel motore |
| `oracle.py` | Scansione funzionale indipendente con tutte le strategie | Semplificato a etichette lessicali single/AND/phrase ed estratti |
| `metrics.py` | Precision/Recall/F1 più AP/MAP | Semplificato: TP/FP/FN, P/R/F1, P@10/R@10, macro e valori non definiti |
| `experiment.py`, `comparison.py`, `protocol.py` | Benchmark, split, confronto strategie, scelta sul development, qrels ufficiali | Archiviati; sostituiti da benchmark e valutazione essenziali separati |
| `acquire.py`, vecchio `dataset.py` | Download completo, campionamento, TXT, export query/qrels | Archiviati; corpus locale congelato e verifica hash senza download |
| `irhome/silver/`, `prompts/`, `config/silver.json` | Provider e annotazioni LLM, report e metriche di accordo | Archiviati ed esclusi da tutti i comandi correnti |
| Vecchi script, test, config, README | Comandi e verifica dei protocolli precedenti | Conservati in `legacy/previous/`; suite corrente dedicata ai requisiti richiesti |

Il codice precedente era usato dalle sue pipeline: non è stato dichiarato
inutilizzato né cancellato definitivamente. `legacy/previous/` ne conserva una
copia storica, inclusi i moduli del motore prima delle modifiche, i test e i
requisiti. Non è un secondo percorso supportato per questo homework; i vecchi
README descrivono risultati storici e non valgono per la nuova ground truth.
Nessun comando corrente importa `legacy`, chiama provider o legge query/qrels
Cranfield. I vecchi output locali non sono stati alterati.

La separazione finale è intenzionalmente essenziale: `engine.py` indicizza e cerca;
`oracle.py` e `ground_truth.py` scandiscono e congelano giudizi senza dipendere dal
motore; `evaluation.py` confronta risultati completi e giudizi già validati;
`benchmark.py` misura nuove costruzioni. Nessuna dipendenza aggiunta.

La suite corrente usa aspettative scritte a mano su piccoli documenti artificiali
per verificare parser, campi, AND, ordine/adiacenza delle frasi, separatori,
maiuscole, stopword, OOV e persistenza. Verifica inoltre conti metrici noti,
divisioni non definite, macro, più di 10 risultati, indipendenza dello scanner,
copertura esaustiva, preservazione della revisione e blocchi prima/dopo freeze.
Le simulazioni di revisione nei test riguardano soltanto fixture temporanee;
non rappresentano una revisione umana dei 300 documenti.
