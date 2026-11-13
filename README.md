# Homework 3 — Cranfield 300 e confronto Precision/Recall

Motore lessicale Python per directory di `.txt` UTF-8: due indici invertiti
posizionali (nome/contenuto), OR, phrase query, BM25 e persistenza JSON.
La versione 3 usa un **campione fisso di 300 documenti Cranfield**, con confronto
di strategie sul development e valutazione finale separata sul test.
Motore, metriche e protocollo usano standard library; `ir_datasets` serve solo
all'acquisizione. Nessun LLM, embedding o framework di retrieval.

## Installazione e comando unico

Python **>=3.10**, riferimento **3.10.0** (`.python-version`), con
`ir_datasets==0.5.11`. `requirements.txt` applica i vincoli transitivi effettivi
di `requirements-lock.txt`, registrati su Windows/Python 3.10. Su altre piattaforme
possono servire wheel o strumenti di compilazione compatibili.
Dalla radice del clone, in PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pip check
.venv\Scripts\python.exe scripts/reproduce.py
```

Linux/macOS: sostituire `.venv\Scripts\python.exe` con `.venv/bin/python`.
Non occorre installare il progetto come pacchetto. La prima esecuzione può
scaricare Cranfield; le successive verificano lo snapshot locale.
`config/experiment.json` fissa seed, split, strategie, criterio di scelta,
dimensioni 100/200/300, BM25 e almeno cinque ripetizioni dei tempi.

Il comando verifica ambiente/configurazione, acquisisce o carica lo snapshot,
prepara e verifica i TXT, costruisce gli indici, esegue `unittest`, controlla
le query funzionali, confronta le strategie sul development, salva la scelta
**prima** di valutare il test, esegue i benchmark ed esporta risultati CSV/JSON.
Errori di hash, mapping, test o scelta congelata interrompono la procedura.

## Collezione originale e sottoinsieme

Lo snapshot originale rimane immutato: 1.400 abstract scientifici inglesi,
225 bisogni informativi e 1.837 giudizi di rilevanza. Fonti:

- [Scheda ufficiale Cranfield](https://ir-datasets.com/cranfield.html).
- [Distribuzione dell'Università di Glasgow](https://ir.dcs.gla.ac.uk/resources/test_collections/cran/).
- [ir_datasets 0.5.11](https://pypi.org/project/ir-datasets/0.5.11/).

La selezione documentale è uniforme senza reinserimento: si ordinano tutti i
record per ID originale numerico, si applica `random.Random(42).shuffle` a una
copia, si prendono i primi 300, poi si riordinano gli estratti per ID numerico.
Non si consultano query, qrels, parole dei testi o punteggi del motore per
scegliere i documenti. Non si stratifica: metadati eterogenei di autore/titolo
aggiungerebbero complessità e decisioni arbitrarie. La lista esatta dei 300 ID
è salvata nel manifest; Python e algoritmo sono documentati e verificati da hash.
I campioni 100 e 200 sono prefissi della stessa permutazione, quindi annidati
nel campione 300. Servono soltanto alla scalabilità.

Ogni documento produce un solo TXT con **l'intero campo `doc.text` restituito
dal provider**. Si normalizzano soltanto CRLF/CR in LF, senza `strip`, tagli,
traduzioni, concatenazioni, titolo aggiunto o newline finale aggiunto. Il provider
ha già interpretato i marcatori del formato originale e tolto gli spazi esterni
dei campi; alcuni abstract contengono già il titolo, che viene preservato.

Filename: titolo NFKD, ASCII, minuscolo, sequenze diverse da `[a-z0-9]` in `_`,
delimitatori esterni rimossi, massimo 80 caratteri di slug, fallback `untitled`;
prefisso con ID originale a quattro cifre ed estensione `.txt`.
Esempio: `0042_aerodynamic_properties_of_wings.txt`.
ID diversi garantiscono unicità anche con titoli uguali o troncati.

`metadata.csv` e `manifest.json` conservano ID originale, `engine_id` (filename
relativo alla directory indicizzata), filename, percorso `documents/...`, titolo,
autore, bibliografia, **dimensione in byte e SHA-256**. Il manifest registra
configurazione, ID selezionati, hash dello snapshot e di tutti gli export.
`verify_dataset` verifica byte, insieme esatto dei file, dimensioni e mapping.
L'indicizzatore rimane generico: solo la valutazione associa `engine_id` e
`doc_id` Cranfield tramite manifest.

## Query, qrels, copertura e split

Lo snapshot conserva tutti i 225 testi e i 1.837 qrels originali. Ogni dataset
esporta ancora tutte le 225 query, ma restringe `qrels.json` **ai soli documenti
presenti**, senza cambiare valori o inventare giudizi. I livelli originali sono
`-1` (negativo), `1` (minimo), `2` (utile), `3` (elevato), `4` (risposta completa).
Per le metriche binarie è rilevante ogni grado `>=1`.

Le query conservano `query_id` fornito da ir_datasets e `source_query_id` del
marcatore `.I` nel file originale: questi ultimi non sono consecutivi. Il
provider li riallinea in ordine di apparizione agli ID 1..225 dei qrels; entrambe
le identità sono esportate. La ricerca usa `contenuto <testo originale>` senza
riformulazione e mantiene BM25 `k1=1.2`, `b=0.75`.

Copertura effettiva del campione con seed 42:

| Quantità | Valore |
| --- | ---: |
| Documenti TXT | 300 |
| Query valutabili (almeno un positivo nel campione) | 172 |
| Query escluse: nessun positivo noto nel campione | 53 |
| Giudizi positivi | 352 |
| Giudizi negativi espliciti | 52 |
| Documenti con almeno un giudizio positivo | 174 |
| Coppie query-documento non giudicate, su 225 × 300 | 67.096 |
| Documenti mai giudicati per alcuna delle 225 query | 104 |

Distribuzione del numero di rilevanti noti per query (`rilevanti: numero query`):
`0:53, 1:78, 2:50, 3:24, 4:10, 5:6, 6:2, 7:1, 13:1`.
`coverage.json` conserva anche i conteggi per ogni query e documento, e gli ID
esclusi. La mancanza di giudizio è una proprietà della **coppia query-documento**.

Gli ID delle sole 172 query valutabili vengono ordinati numericamente e mescolati
con un nuovo `random.Random(42)`, indipendente dal campionamento dei documenti.
Il 20%, arrotondato all'intero più vicino con metà verso l'alto, dà **34 query
development**; le restanti **138 sono test**. Gli ID esatti, esclusioni, seed e
regola sono in `results/splits.json`. Nessuna query è scelta in base alle
prestazioni. Le 53 escluse non entrano nelle medie, neppure per precision.

## Strategie e criterio fissato prima del test

Indici, posting list e posizioni non cambiano fra strategie. Sul solo contenuto
non phrase si confrontano:

1. `or`: OR originale, tutti i termini e frequenze di query originali.
2. `or_stop`: OR dopo rimozione delle stopword **dalla query**, anche nel ranking.
3. `msm`: stessa rimozione, con almeno `ceil(quota * termini_distinti)` presenti;
   quote 0,30, 0,50, 0,70. Gli OOV rimangono nel denominatore.
4. `and`: tutti i termini distinti rimasti dopo la stessa rimozione.

La piccola stoplist inglese è esplicita e versionata in
`corpus/english_stopwords.txt`: parole funzionali comuni, preparate per questo
protocollo, senza estrazione dai risultati o dai qrels. Nessuno stemming.
Il suo SHA-256 è registrato. Le stopword restano negli indici e nelle posizioni.
Per filename e phrase query **tutte le strategie conservano la semantica
originale**, incluse le stopword e l'adiacenza. Una query contenuto non phrase
composta soltanto da stopword restituisce zero candidati nelle varianti filtrate;
non c'è fallback. Un termine significativo richiede sempre almeno un match;
si usano termini distinti per MSM e frequenze originali per il punteggio BM25.

Criterio preregistrato nella configurazione: massimizzare **F1@10 macro sul
development**; parità risolte per Recall@10, MAP@10 e ordine dichiarato delle
strategie (OR originale prima). La media armonica penalizza il collasso della
recall; non si impongono obiettivi numerici arbitrari. Solo il development
confronta strategie. `selection.json` viene scritto prima di eseguire il test;
una scelta diversa nella stessa destinazione viene rifiutata.

## Risultati effettivamente misurati

La baseline è stata misurata sul development con il motore precedente prima
della modifica. Le 34 liste e i punteggi sono risultati identici alla modalità
`or` attuale. Sullo stesso campione e sulle stesse 34 query:

| Strategia | Candidati medi | P@10 | R@10 | F1@10 macro | MAP@10 | MAP completa |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| OR originale | 287,735 | 0,073529 | 0,424020 | 0,120054 | 0,239513 | 0,265133 |
| OR stopword | 166,529 | 0,076471 | 0,453431 | 0,125402 | 0,255950 | 0,280309 |
| MSM 30% | 24,529 | 0,061765 | 0,360294 | 0,101226 | 0,192933 | 0,198993 |
| MSM 50% | 4,324 | 0,023529 | 0,102941 | 0,037130 | 0,049918 | 0,049918 |
| MSM 70% | 0,324 | 0,005882 | 0,017157 | 0,008727 | 0,017157 | 0,017157 |
| AND | 0,000 | 0,000000 | 0,000000 | 0,000000 | 0,000000 | 0,000000 |

La baseline recupera in media il **95,912%** della collezione, con mediana
**300** candidati. Sulla lista completa: precision **0,006126**, recall
**0,963235**. La configurazione scelta è **OR stopword**, che migliora entrambe
le metriche @10 e F1@10 e riduce i candidati al 55,510% medio (mediana 174,5).
Sulla lista completa la sua precision è **0,011096** e la recall **0,892157**:
la riduzione della recall completa è un costo reale del filtro.
Il vantaggio di F1@10 è piccolo, circa 0,00535 assoluto; si tratta di un
risultato descrittivo su 34 query, senza prova di significatività statistica.
MSM e AND mostrano un risultato negativo, con perdita eccessiva di recall.

Dopo il congelamento, una sola valutazione finale della configurazione scelta
sulle **138 query test**, senza provare altre strategie sul test:

| Strategia test | Candidati medi | P@10 | R@10 | F1@10 macro | MAP@10 | MAP completa |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| OR stopword | 159,609 | 0,125362 | 0,624395 | 0,198637 | 0,409281 | 0,435277 |

Mediana candidati test **159,5**, frazione recuperata media **53,203%**;
precision completa **0,014789**, recall completa **0,948476**, F1 completa
**0,028788**. Le differenze fra development e test riflettono query differenti;
il confronto tra strategie riguarda il development. Questi risultati descrivono
il sottoinsieme derivato e non sono direttamente confrontabili con Cranfield 1400.
Le riproduzioni ricalcolano lo stesso protocollo congelato per verificare gli
hash: non costituiscono nuovi tentativi di ottimizzazione sul test.

## Convenzioni metriche e limiti

Con `R` rilevanti noti nel **campione** e `h` rilevanti recuperati:
precision completa = `h / candidati`, recall completa = `h / |R|`.
Precision@10 divide i positivi nei primi 10 per **10 fisso**, anche con meno
risultati. Recall@10 divide per `|R|`; F1@10 è la loro media armonica per query.
AP completa somma la precision ai ranghi rilevanti dell'intera lista e divide
per `|R|`; AP@10 limita la somma ai primi 10 e divide per `min(10, |R|)`, come
nella versione precedente. MAP e MAP@10 sono medie delle rispettive AP,
distinte. La convenzione AP@10 differisce da quella con denominatore `|R|`.

Le macro-medie si calcolano per query entro ciascuna fase: la media delle F1
è distinta dalla F1 delle precision/recall medie e dalle metriche micro.
Con positivi ma nessun risultato: tutte le metriche zero. Senza positivi:
recall, F1 e AP non definite; il protocollo esclude queste query prima dello
split. I risultati restituiti sono liste complete, senza troncamento a scopo IR.

Un qrel `-1` è un giudizio esplicitamente negativo; assenza di qrel significa
**non giudicato**. Per le metriche standard i non giudicati contribuiscono zero,
ma gli export conservano `judgment: null` e stato `unjudged`, distinti da `-1`
e `judged_nonrelevant`. Non si assume che gli annotatori abbiano giudicato
negativamente tutti i non giudicati. Qrels incompleti possono penalizzare
risultati realmente utili; il recall si riferisce soltanto ai rilevanti noti.
Il dominio aeronautico storico e il piccolo development limitano la generalità.

## Console: corpus 300 e limite di visualizzazione

Dopo `reproduce.py`, dalla radice:

```powershell
# Usa n300/index.json e selection.json del protocollo corrente
.venv\Scripts\python.exe scripts/search.py query
# La baseline rimane disponibile
.venv\Scripts\python.exe scripts/search.py query --strategy or --limit 10
.venv\Scripts\python.exe scripts/search.py query --strategy msm --minimum-should-match 0.3 --limit 20
```

Esempi di input:

```text
nome aerodynamic
nome "boundary layer"
contenuto pressure velocity
contenuto "heat transfer"
contenuto "of the"
esci
```

Si stampano ID relativo, filename e score; a fine risposta **Candidati** indica
tutti i match, **Visualizzati** solo i primi `--limit` (default 10, intero positivo).
Le metriche @10 usano i primi 10 del ranking completo, indipendentemente dal
limite della console. Ridurre l'output non migliora la Precision@10.
Per frasi usare virgolette sull'intero testo; input errati, nessun risultato,
EOF e Ctrl+C sono gestiti.

Il motore resta utilizzabile su qualsiasi directory:

```powershell
.venv\Scripts\python.exe scripts/generate_dataset.py --offline
.venv\Scripts\python.exe scripts/search.py build artifacts/cranfield300-manual/dataset/documents artifacts/cranfield300-manual/index.json
.venv\Scripts\python.exe scripts/search.py query artifacts/cranfield300-manual/index.json --strategy or_stop
.venv\Scripts\python.exe scripts/search.py query artifacts/cranfield300-manual/index.json --selection artifacts/cranfield300/results/selection.json
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe scripts/evaluate.py --offline
```

Un indice esplicito senza `--strategy` o `--selection` usa OR originale.
`generate_dataset.py` conserva il nome storico, ma prepara abstract originali;
default 300/seed 42. `evaluate.py` esegue il protocollo senza i test automatici.

## Snapshot, offline e integrità

L'acquisizione originale resta in `artifacts/cranfield-source/`:
`cran.tar.gz`, `records.json`, `source-manifest.json`; `provider/` è solo cache
tecnica, non necessaria offline. Il download è verificato dal provider e dal
MD5 atteso `1730f7be572d95a5a4b56c59a7b900a5`; i tre file congelati sono
controllati tramite gli SHA-256 in `config/cranfield.lock.json` versionato.
I comandi non aggiornano il lock, non sovrascrivono snapshot e non riscaricano
silenziosamente file corrotti. Per trasferire una copia offline bastano i tre
file e l'ambiente software già installato; `--cache` può indicare un'altra
directory. Il flag offline riguarda l'esperimento, non l'installazione pip.

```powershell
.venv\Scripts\python.exe scripts/acquire_cranfield.py --offline
.venv\Scripts\python.exe scripts/reproduce.py --offline --output artifacts/cranfield300-repeat
.venv\Scripts\python.exe -c "from pathlib import Path; a=Path('artifacts/cranfield300/results/checksums.json'); b=Path('artifacts/cranfield300-repeat/results/checksums.json'); assert a.read_bytes()==b.read_bytes(); print('Output deterministici identici')"
```

Tutti gli input software/configurazioni/stoplist necessari sono versionati;
documenti, query e qrels originali non vengono redistribuiti nel repository:
le fonti pubbliche e `cranqrel.readme` non espongono una licenza esplicita di
redistribuzione nelle fonti consultate. La licenza di ir_datasets non viene
attribuita ai dati. Il corpus originale resta recuperabile e verificabile.

## Benchmark, test e file prodotti

Su 100/200/300 documenti si misurano almeno cinque ripetizioni con
`perf_counter_ns()` per preparazione, costruzione in memoria, persistenza JSON,
caricamento e ricerca. Il download è fuori dai timer. I tempi di ricerca usano
**solo le 34 query development con la strategia già selezionata**: non riusano
il test. Non si calcolano metriche IR sui campioni 100/200. Nessun warm-up o
svuotamento esplicito delle cache; sono condizioni potenzialmente calde, sensibili
a hardware, OS e carico. Si registrano campioni, mediana, min/max, deviazione
standard della popolazione e IQR inclusivo. Dimensione indice = byte del JSON.

In `artifacts/cranfield300/`, `n100/`, `n200/`, `n300/` contengono dataset e indice.
In `results/`:

- `coverage.json`, `splits.json`: copertura e ID esatti delle query;
- `development_comparison.csv`, `development_metrics.csv`, `development_runs.json`:
  tutte le strategie e ranking completi sul development;
- `selection.json`: configurazione congelata, criterio, hash corpus/split/stoplist
  e confronto usato, dichiarazione che il test non è stato usato per scegliere;
- `test_summary.csv`, `test_metrics.csv`, `test_runs.json`: unica configurazione
  test, rank, score, ID originali e giudizi disponibili per ogni risultato;
- `functional_checks.json`: 12 query per ciascuna delle sei configurazioni,
  con ID esatti dello scanner indipendente e controllo di uguaglianza;
- `deterministic.json`, `checksums.json`: risultati e hash deterministici;
- `observed.json`, `timing_samples.csv`, `timing_summary.csv`, `performance.csv`:
  tempi, variabilità, byte, Python/progetto/commit/stato Git, pacchetti, OS e
  informazioni hardware disponibili, separati dai dati deterministici;
- `tests.log`: esito e durata effettiva di `unittest`.

La suite conserva i test pertinenti e copre nuove strategie, conteggio distinto,
OOV, arrotondamenti, stopword, query vuote dopo filtro, frasi/nome invariati,
assenza di mutazioni degli indici, limite console, qrels, esclusioni, split e
determinismo. Due preparazioni confrontano hash e byte degli abstract. Senza
snapshot locale i test di integrazione sono saltati senza download impliciti;
la procedura completa acquisisce i dati prima dei test e li esegue tutti.

`analyzers.py`, BM25, indici posizionali e formato indice 1 restano invariati;
si estende soltanto il matching delle query. Analyzer: NFC/lower, token Unicode
`[^\W_]+`, stopword e posizioni preservate; filename senza estensione `.txt`.
BM25 usa statistiche del campo, frequenze di query e parità per ID crescente.
Persistenza JSON UTF-8, chiavi ordinate/LF, senza pickle o codice eseguito al load.
`.gitattributes` mantiene LF negli input versionati.

I vecchi output `cranfield-experiment`, `cranfield-repeat`, `experiment`, `repeat`
sono storici; la versione corrente usa soltanto `cranfield300`. Il materiale
sintetico è isolato in `legacy/synthetic/`. Nessuna relazione universitaria è
generata: CSV/JSON contengono i risultati per prepararla separatamente.
