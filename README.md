# Homework 3 - Ground truth semantica e valutazione

Motore Python per **300 documenti Cranfield**, con analyzer separati per nome e
contenuto, indici posizionali, parser, AND e phrase query, ranking BM25 e
persistenza JSON. Il motore, le formule delle metriche e il benchmark dei tempi
sono conservati. Solo libreria standard Python >=3.10, nessuna nuova dipendenza.
Non si usano query o relevance judgments ufficiali Cranfield.

Il corpus e ora classificato: **300 documenti, 3.000 giudizi binari**.
Il risultato e una **ground truth semantica proposta mediante Codex e
parzialmente supervisionata da un revisore umano**. La revisione mirata e
completata e importata: **291 giudizi confermati**, distinti in **38 conferme
della calibrazione, 85 nuove conferme dopo discussione e 168 nuove conferme
assistite in blocco**. Queste ultime non attestano una verifica individuale dei
documenti originali; nessuna delle tre modalita e una classificazione originale
indipendente. Sono registrate le sei correzioni storiche e le **15 nuove
correzioni approvate**, tutte da 1 a 0. Il revisore `utente_chat` e uno pseudonimo
dell'utente della conversazione, non un nome reale. Data: 2026-11-13, senza orari.

Le altre **2.709 coppie non sono confermate**. Non e stata
eseguita una valutazione reale e la ground truth **non e congelata**. Le query,
i criteri, il corpus, il motore, gli analyzer, il ranking, il benchmark e le
formule delle metriche restano invariati. La versione esatta di Codex non e
stata resa disponibile nella sessione.

Le proposte complete sono in `evaluation/semantic/codex_proposals/complete_labels.csv`;
la matrice e in `evaluation/semantic/annotations.csv`; la provenienza per tutte
le coppie e in `evaluation/semantic/provenance.csv`. Le 40 etichette gia compilate
coincidevano con la calibrazione corretta e sono state conservate all'importazione.
Le 2.800 nuove proposte sono state redatte dopo lettura integrale dei restanti
280 file, in 14 blocchi da 20, salvati in `codex_proposals/batches/`.

## Avvio

Dalla radice del repository:

```sh
python scripts/semantic_ground_truth.py status
python scripts/verify_semantic_proposals.py
python -m unittest discover -s tests -v
```

La coda `evaluation/semantic/codex_proposals/final_review.csv` contiene
**278 coppie revisionate e nessuna pendente**: le 25 conferme pregresse sono
intatte e sono state importate le altre 253, con le sole 15 correzioni approvate.
La ground truth e pronta per la verifica finale prima del congelamento, ancora
non eseguito. I conteggi distinguono i positivi originali proposti da Codex da
quelli effettivi della matrice corretta.
Per eventuali revisioni successive, non modificare le proposte: compilare per le righe pendenti `human_label`, `human_reason`,
`reviewed_by` e `reviewed_at` con una revisione realmente svolta. Per confermare,
`human_label` e uguale a `proposed_label` e `corrected_label` resta vuoto.
Per correggere, usare l'etichetta voluta in entrambi `human_label` e
`corrected_label` e motivare il cambiamento.

La coda comprende tutte le confidenze basse/medie, un campione di alta confidenza
con seed 42 (due positivi e due negativi per query), e casi affetti da anomalie
del testo o del nome. `review_manifest.json` registra selezione, coppie e seed;
`anomalies.json` descrive otto documenti con testo frammentario o tema discordante
dal basename. I controlli di coerenza Q03=>Q04 e Q01=>Q06 non hanno prodotto
segnalazioni: non sono classificatori e non modificano giudizi.

Dopo aver compilato giudizi umani reali, l'importazione esplicita e:

```sh
python scripts/semantic_ground_truth.py import-review
```

Questo comando importa solo righe con etichetta, motivo, revisore e data gia
compilati, aggiorna matrice e provenienza e registra separatamente le correzioni.
Non compila conferme per righe vuote e non altera `complete_labels.csv`.
Il comando e stato eseguito: 253 nuovi giudizi importati; le 25 conferme
pregresse e le proposte automatiche originali sono rimaste invariate.

In PowerShell si puo sostituire `python` con `.venv\Scripts\python.exe`.
`prepare` resta ripetibile e conserva i giudizi esistenti. La console `annotate`
rimane disponibile; nel protocollo assistito preferire la coda per mantenere
allineate annotazioni e provenienza. Eventuali modifiche manuali incoerenti
vengono rifiutate dal freeze.

## Query e criteri semantici

Le dieci query in `evaluation/queries.csv` sono **definitive prima
dell'annotazione umana**. Q01, Q02 e Q06 usano le sostituzioni richieste,
tutte di tipo AND; le altre sette query sono invariate. Il campo
storico `expected_match` descrive il matching del motore, non la rilevanza semantica.
`evaluation/semantic/criteria.csv` associa a ogni query un bisogno informativo,
un criterio positivo, uno negativo e una valutazione di chiarezza.
Le precedenti proposte per Q01, Q02 e Q06 sono state applicate; non restano
sostituzioni in attesa. I criteri sono fissati prima di attribuire giudizi.

| ID | Query | Bisogno informativo sintetico |
| --- | --- | --- |
| Q01 | `nome supersonic flow` | Flussi supersonici come oggetto sostanziale del basename |
| Q02 | `nome pressure distribution` | Distribuzione spaziale della pressione dal basename |
| Q03 | `nome laminar boundary` | Strato limite laminare |
| Q04 | `nome "boundary layer"` | Fenomeni dello strato limite |
| Q05 | `nome magnetohydrodynamics` | Interazione fra campi magnetici e fluidi conduttori |
| Q06 | `contenuto supersonic flow` | Analisi sostanziale dei flussi supersonici nel testo |
| Q07 | `contenuto pressure velocity` | Relazione fra pressione e velocità |
| Q08 | `contenuto heat temperature` | Relazione fra fenomeni termici e temperatura |
| Q09 | `contenuto "heat transfer"` | Trasferimento di calore |
| Q10 | `contenuto "mach number"` | Effetti della comprimibilità e del regime rispetto alla velocità del suono |

Per Q01 il solo basename deve indicare uno studio sostanziale di un flusso
supersonico (velocita superiore a quella locale del suono), inclusi i flussi
ipersonici. Non bastano un contesto di prova supersonico, un generico flusso
comprimibile o onde d'urto senza indicazione del regime. Il testo non va usato
per ricavare informazioni assenti dal basename.

Per Q02 il solo basename deve porre al centro la distribuzione **spaziale**
della pressione nel fluido o su una superficie: profilo, variazione lungo una
coordinata, calcolo o misura. Sono esclusi pressione come semplice parametro,
variazioni solo temporali, perdite totali o forze globali senza uno studio della
distribuzione spaziale.

Per Q06 il testo deve analizzare sostanzialmente struttura, proprieta o
interazioni di un flusso supersonico o ipersonico. Sono inclusi confronti fra
regimi quando quello supersonico e analizzato; un numero di Mach maggiore di 1
riportato solo come condizione sperimentale non basta. La formulazione puo
usare sinonimi o descrizioni equivalenti senza i token esatti della query.
I criteri completi 1/0 per tutte le query sono in `criteria.csv`.

Dopo la preparazione, ogni modifica agli input viene rilevata: per un nuovo
protocollo usare una nuova directory, copiandovi i criteri aggiornati.

**La presenza esatta dei termini non decide la rilevanza.** Un documento può
essere rilevante con sinonimi e negativo pur contenendo tutte le parole della
query. Per `nome` giudicare **solo il basename effettivo senza estensione**, ignorando il testo anche se
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
`?` dubbio da risolvere. La matrice corrente contiene proposte Codex. Per correzioni usare la coda e
import-review per aggiornare la provenienza; resta possibile modificare
il CSV con un editor o foglio elettronico, conservando intestazioni, ID, titoli,
righe e formato CSV UTF-8 (virgola come separatore). Non modificare il CSV mentre
è aperta una sessione di annotazione in console: riavviarla dopo le modifiche.

Il titolo dei metadati e solo informativo e non e evidenza per Q01-Q05.
La console mostra nome, titolo, testo integrale e tutti i dieci bisogni con i
criteri. Si legge ogni documento una volta e si inseriscono dieci etichette:

```text
1010001?00
1 0 1 0 0 0 1 ? 0 0
```

`_` svuota una cella; `-` conserva il giudizio precedente. `n`/`p` navigano,
`g 42` va alla riga 42, `g ID` va a un percorso relativo preciso, `q` esce.
Ogni inserimento valido salva atomicamente l'intera matrice prima di passare
al documento successivo. EOF e Ctrl+C conservano i documenti già confermati.
Al riavvio si riparte dal primo documento con celle vuote o dubbie. Anche a
matrice completa si può riaprire la console e correggere giudizi prima del freeze.
`status` conta completati, mancanti e dubbi ed elenca i documenti con `?` irrisolti.

## Congelamento e valutazione

Solo dopo la revisione mirata conclusiva e l importazione esplicita dei suoi
giudizi sara possibile congelare il protocollo assistito (non eseguito ora):

```sh
python scripts/semantic_ground_truth.py freeze --reviewer "utente_chat" --approval-note "Revisione mirata completata del protocollo assistito"
python scripts/evaluate.py
```

Il freeze verifica i 300 documenti e i loro hash rispetto ai metadati, la matrice
completa senza duplicati, etichette esclusivamente 0/1, identità di query, criteri,
corpus e metadati rispetto a `prepared.json`. Rifiuta celle vuote o dubbie.
Genera `positives_Q01.csv` ... `positives_Q10.csv` (anche senza positivi),
oltre a `final_positives.csv` con tutte le coppie query/documento positive
(una query senza positivi è rappresentata dal suo insieme vuoto) e `frozen.json`
con stato `semantic_ground_truth_codex_assisted_partially_supervised`,
conteggi espliciti di confermati/non confermati e `full_manual_validation=false`.
Conserva hash di provenienza, proposte, manifest e coda, oltre a revisore, nota e hash degli
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

La ground truth lessicale precedente e archiviata separatamente in
`evaluation/historical/lexical/`: `review.csv`, `proposed_positives.csv` e
`proposed.json` sono conservati byte per byte, insieme alla copia delle query
originali in `queries.csv` e a un README che li identifica come **storici**.
Sono proposte lessicali, non giudizi semantici o metriche validate. Non vanno
usate con le query definitive. Nessun vecchio output locale viene ricalcolato.
Il manifest di preparazione mantiene l identita delle query e dei criteri
definitivi. La matrice successivamente completata non equivale a validazione
umana completa: la provenienza distingue 291 conferme assistite e 2.709
giudizi non confermati.
`irhome/ground_truth.py`, `irhome/oracle.py` e `scripts/ground_truth.py` conservano
il vecchio scanner e il suo protocollo esclusivamente come ausilio lessicale.
Non trasferire proposte o conferme lessicali nelle celle semantiche. Il valutatore
corrente accetta esclusivamente il freeze semantico, mai quello lessicale.
Gli output storici in `legacy/` e `artifacts/` non sono input del nuovo protocollo.

## Tracciabilita del protocollo assistito

- `calibration_labels.csv`: le 200 proposte della calibrazione corretta, invariate.
- `calibration_review.csv`: le 38 conferme della calibrazione. `supervision.json`
  e `final_supervision.json` distinguono queste dalle nuove 85 conferme discusse
  e 168 conferme in blocco, con data, pseudonimo e coppie esplicite.
- `annotation_discrepancies.csv`: le sei correzioni storiche confermate.
  `human_corrections.csv` registra anche le 15 nuove correzioni approvate.
- `history/v3_before_final_review_import/`: snapshot precedente a questa
  registrazione e importazione, comprese le 25 righe da conservare intatte.
- `complete_labels.csv`: tutte le 3.000 proposte originali, con confidenza e motivo.
- `batches/*.json`: decisioni individuali dei 14 blocchi, non regole lessicali.
- `classification_manifest.json`, `classification_prompt.txt`, `run_inputs.json`:
  protocollo, istruzioni, identita e hash degli input/output e dei blocchi.
- `history/v2_before_human_confirmation/`: copia precedente alla registrazione
  delle conferme e matrice con le 40 etichette presenti prima dell'importazione.
- `provenance.csv` nella directory semantica: fonte della proposta, etichetta
  effettiva, eventuale etichetta preesistente e conferma umana per ogni coppia.

I negativi chiari sono motivati con una sintesi fattuale del campo esaminato e
il bisogno non soddisfatto; positivi e ogni incertezza hanno motivazioni
individuali. Non si sono utilizzati matching del motore, ranking o qrels.
Il freeze assistito rifiuta provenienza mancante, incoerente o duplicata,
proposte alterate e coda ancora pendente. I relativi file entrano negli hash
verificati anche al caricamento. La presenza del manifest assistito impedisce
il ripiego silenzioso sul vecchio stato di annotazione interamente umana.
Il protocollo manuale originario resta utilizzabile in directory separate prive
di proposte e provenienza Codex.

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
