# Homework 3 - Ground truth semantica e valutazione

Motore Python per **300 documenti Cranfield**, con analyzer separati per nome e
contenuto, indici posizionali, parser, AND e phrase query, ranking BM25 e
persistenza JSON. Il motore, le formule delle metriche e il benchmark dei tempi
sono conservati. Solo libreria standard Python >=3.10, nessuna nuova dipendenza.
Non si usano query o relevance judgments ufficiali Cranfield.

La valutazione corrente richiede una **ground truth semantica annotata da un
revisore umano su tutto il corpus**. Stato iniziale: **0/3.000 giudizi completati**,
300 righe con dieci etichette vuote. Nessuna annotazione umana è dichiarata e
nessuna metrica reale è stata calcolata. I test usano solo giudizi sintetici.

## Avvio

Dalla radice del repository:

```sh
python scripts/semantic_ground_truth.py prepare
python scripts/semantic_ground_truth.py annotate
python scripts/semantic_ground_truth.py status
python -m unittest discover -s tests -v
```

In PowerShell si può sostituire `python` con `.venv\Scripts\python.exe`.
`prepare` è ripetibile e conserva tutte le annotazioni già inserite.

## Query e criteri semantici

Le dieci query in `evaluation/queries.csv` restano **invariate**. Il suo campo
storico `expected_match` descrive il matching del motore, non la rilevanza semantica.
`evaluation/semantic/criteria.csv` associa a ogni query un bisogno informativo,
un criterio positivo, uno negativo, una valutazione di chiarezza ed eventuali
proposte di sostituzione. Le proposte non sono applicate.

| ID | Query | Bisogno informativo sintetico |
| --- | --- | --- |
| Q01 | `nome flow` | Moto dei fluidi come oggetto principale del titolo |
| Q02 | `nome pressure` | Pressione, distribuzioni o effetti come tema del titolo |
| Q03 | `nome laminar boundary` | Strato limite laminare |
| Q04 | `nome "boundary layer"` | Fenomeni dello strato limite |
| Q05 | `nome magnetohydrodynamics` | Interazione fra campi magnetici e fluidi conduttori |
| Q06 | `contenuto flow` | Analisi sostanziale del moto dei fluidi |
| Q07 | `contenuto pressure velocity` | Relazione fra pressione e velocità |
| Q08 | `contenuto heat temperature` | Relazione fra fenomeni termici e temperatura |
| Q09 | `contenuto "heat transfer"` | Trasferimento di calore |
| Q10 | `contenuto "mach number"` | Effetti della comprimibilità e del regime rispetto alla velocità del suono |

Q01, Q02 e soprattutto Q06 sono ampie. Il CSV propone rispettivamente
`nome supersonic flow`, `nome pressure distribution` e `contenuto supersonic flow`
per restringere il bisogno. Le altre query sono utilizzabili con i criteri
espliciti indicati. Prima dell'annotazione, il revisore deve concordare la
versione definitiva di query e criteri; le sostituzioni richiedono approvazione.
Dopo la preparazione, ogni modifica agli input viene rilevata: per un nuovo
protocollo usare una nuova directory, copiandovi i criteri aggiornati.

**La presenza esatta dei termini non decide la rilevanza.** Un documento può
essere rilevante con sinonimi e negativo pur contenendo tutte le parole della
query. Per `nome` giudicare **solo nome e titolo**, ignorando il testo anche se
visualizzato dalla console; per `contenuto` giudicare il testo integrale.
Una menzione incidentale non basta. Non consultare ranking o risultati del
motore per attribuire etichette; non usare i giudizi per ottimizzare ranking o
motore prima della valutazione indipendente.

## Annotazione umana

`evaluation/semantic/annotations.csv` contiene una riga per documento e le
colonne `doc_id`, `source_file`, `title`, `Q01` ... `Q10`. L'ID stabile è il percorso
relativo nel corpus, uguale agli ID restituiti dal motore; il riferimento al file
si risolve rispetto a `corpus/documents/`. Titoli completi e identità originali
provengono da `corpus/metadata.csv`.

Etichette ammesse: `1` rilevante, `0` non rilevante, cella vuota non valutata,
`?` dubbio da risolvere. Nessuna etichetta è precompilata. è possibile modificare
il CSV con un editor o foglio elettronico, conservando intestazioni, ID, titoli,
righe e formato CSV UTF-8 (virgola come separatore). Non modificare il CSV mentre
è aperta una sessione di annotazione in console: riavviarla dopo le modifiche.

La console mostra nome, titolo, testo integrale e tutti i dieci bisogni con i
criteri. Si legge ogni documento una volta e si inseriscono dieci etichette:

```text
1010001?00
1 0 1 0 0 0 1 è 0 0
```

`_` svuota una cella; `-` conserva il giudizio precedente. `n`/`p` navigano,
`g 42` va alla riga 42, `g ID` va a un percorso relativo preciso, `q` esce.
Ogni inserimento valido salva atomicamente l'intera matrice prima di passare
al documento successivo. EOF e Ctrl+C conservano i documenti già confermati.
Al riavvio si riparte dal primo documento con celle vuote o dubbie. Anche a
matrice completa si può riaprire la console e correggere giudizi prima del freeze.
`status` conta completati, mancanti e dubbi ed elenca i documenti con `?` irrisolti.

## Congelamento e valutazione

Solo dopo che un essere umano ha completato tutte le 3.000 coppie:

```sh
python scripts/semantic_ground_truth.py freeze --reviewer "Nome reale" --approval-note "Revisione semantica completa delle 3000 coppie"
python scripts/evaluate.py
```

Il freeze verifica i 300 documenti e i loro hash rispetto ai metadati, la matrice
completa senza duplicati, etichette esclusivamente 0/1, identità di query, criteri,
corpus e metadati rispetto a `prepared.json`. Rifiuta celle vuote o dubbie.
Genera `positives_Q01.csv` ... `positives_Q10.csv` (anche senza positivi),
oltre a `final_positives.csv` con tutte le coppie query/documento positive
(una query senza positivi è rappresentata dal suo insieme vuoto) e `frozen.json`
con stato `semantic_ground_truth_human_annotated`, revisore, nota e hash degli
input, annotazioni, manifest di preparazione e positivi definitivi.

Il programma non certifica l'identità del revisore: il nome e la nota devono
corrispondere alla revisione realmente svolta. Nessun comando simula approvazioni.
Non si può sovrascrivere un freeze o annotare tramite console dopo il congelamento.
Le modifiche manuali successive vengono rilevate dagli hash e bloccano la
valutazione prima della costruzione dell'indice. Questo è un controllo di
integrità locale, non una firma crittografica contro alterazioni intenzionali.
Per correggere un protocollo congelato creare una nuova directory e ripetere
preparazione/revisione, conservando la vecchia versione.

I comandi supportano `--documents`, `--queries`, `--metadata` e `--output`.
Una directory alternativa deve contenere `criteria.csv`; per valutarla usare
`python scripts/evaluate.py --ground-truth evaluation/nuova-revisione`.
Il comando CLI richiede sempre 300 documenti; i test interni usano fixture ridotte.

## File e protocollo lessicale precedente

- `irhome/semantic.py`: preparazione, validazione, console, freeze e caricamento.
- `scripts/semantic_ground_truth.py`: comandi del protocollo semantico.
- `irhome/evaluation.py`, `scripts/evaluate.py`: valutazione semantica e FP/FN.
- `evaluation/semantic/`: criteri, matrice e manifest iniziale; dopo revisione anche freeze e positivi.
- `tests/test_semantic.py`: test sintetici del workflow e della valutazione.
- `scripts/reproduce.py`: verifica corpus, prepara la matrice senza sovrascriverla,
  esegue test, persistenza e benchmark; valuta solo se esiste il freeze semantico.

La ground truth lessicale precedente rimane separata e invariata in
`evaluation/review.csv`, `evaluation/proposed_positives.csv`, `evaluation/proposed.json`.
`irhome/ground_truth.py`, `irhome/oracle.py` e `scripts/ground_truth.py` conservano
il vecchio scanner e il suo protocollo esclusivamente come ausilio lessicale.
Non trasferire proposte o conferme lessicali nelle celle semantiche. Il valutatore
corrente accetta esclusivamente il freeze semantico, mai quello lessicale.
Gli output storici in `legacy/` e `artifacts/` non sono input del nuovo protocollo.

## Corpus, motore e riproducibilità

I 300 TXT attuali e `corpus/metadata.csv` restano invariati: 309.724 byte.
Provenienza e trasformazioni sono descritte in [corpus/README.md](corpus/README.md).
Le statistiche lessicali restano in `evaluation/dataset_analysis.json`.
BM25 usa `k1=1.2`, `b=0.75`, ordinamento per score decrescente e ID a parità.
Il formato JSON di persistenza rimane quello esistente.

```sh
python scripts/search.py build
python scripts/search.py query --query "contenuto pressure velocity"
python scripts/benchmark.py
python scripts/reproduce.py
```

La suite verifica analyzer, parser, AND, phrase, BM25/persistenza, formule delle
metriche e scanner storico. I test semantici verificano etichette ammesse,
salvataggio/ripresa/modifica, blocco del freeze incompleto, integrità degli input
e del congelamento, valutazione completa oltre dieci risultati, FP e FN anche
con rilevanza espressa senza il termine cercato, output riproducibili byte per byte.
La recall finale misura i positivi semantici annotati su tutti i 300 documenti;
la sua validità dipende dalla completezza e coerenza della revisione umana.

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
(una riga per query), `results.csv` (tutti i risultati, rank e score), `macro.csv`,
`errors.csv` (FP/FN con query e ID documento) ed `evaluation.json` (hash del congelamento e motore). Anche il terminale
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
