# Homework 3 — Indicizzazione e ricerca di testi

Motore Python su **300 documenti Cranfield**, con indici invertiti posizionali,
ricerca AND/OR, phrase query e ranking BM25. La valutazione usa dieci query e
una ground truth semantica congelata: **3.000 giudizi, 291 conferme assistite e
521 coppie query-documento rilevanti**.

## 1. Requisiti

Python **>=3.10**; workflow verificato con **Python 3.10.0**. Si usa soltanto la
libreria standard: nessun pacchetto da installare e nessun servizio esterno.
`.python-version` indica l'ambiente originario; `pyproject.toml` dichiara i requisiti.

## 2. Dataset

Il corpus deriva da Cranfield, acquisito originariamente con `ir_datasets 0.5.11`.
I 1.400 documenti sono stati ordinati per ID numerico, permutati con
`random.Random(42).shuffle`, selezionando i primi 300 e riordinandoli per ID.
È esportato `doc.text` in UTF-8, convertendo CRLF/CR in LF, senza aggiungere titolo,
newline o altre correzioni. Il filename contiene l'ID originale a quattro cifre
e uno slug ASCII del titolo, limitato a 80 caratteri.

I TXT e `corpus/metadata.csv` sono versionati, con ID originali, titoli, dimensioni
e SHA-256. Non occorre scaricare Cranfield per riprodurre l'esperimento.
[Procedura e prove di provenienza](docs/reproducibility.md#provenienza-del-corpus).

## 3. Architettura

- **`nome`**: basename effettivo senza `.txt`, compreso l'ID; non il titolo completo dei metadati.
- **`contenuto`**: intero testo UTF-8 del file.
- Analyzer distinti: Unicode NFC, minuscole, token alfanumerici; nessuno stemming,
  sinonimo o rimozione di stopword. Due indici invertiti con posizioni dei token.
- Termini senza virgolette: **AND predefinito**, oppure OR esplicito, unione dei posting.
  Le **phrase query** richiedono adiacenza e ordine e rimangono identiche con AND e OR.
- **BM25**: `k1=1.2`, `b=0.75`; score decrescente, ID crescente a parità. Persistenza JSON.

## 4. Installazione e avvio

```sh
git clone https://github.com/pyxidious/text-file-indexing-and-search.git
cd text-file-indexing-and-search
python --version
python -m unittest discover -s tests -v
python scripts/verify_semantic_proposals.py
python scripts/search.py build
python scripts/search.py query --query "contenuto pressure velocity"
```

Eseguire dalla radice del repository. Per la console OR aggiungere `--strategy or`.
La console mostra dieci risultati per default; la valutazione utilizza tutti i risultati.

## 5. Riproduzione AND e OR

```sh
python scripts/evaluate.py --strategy and
python scripts/evaluate.py --strategy or
python scripts/compare_matching.py
```

Le due corse usano lo stesso freeze e producono rispettivamente
`artifacts/homework/results/` e `artifacts/homework/results_or/`.
`artifacts/` è **esclusa da Git**: questi output vengono generati localmente,
non sono risultati già scaricabili dal clone. Il confronto verifica recall OR
non inferiore per le query non phrase e ranking identico per le phrase.

## 6. Risultati principali

| Metrica macro | AND | OR |
|---|---:|---:|
| Precision | 0.900230 | 0.638625 |
| Recall | 0.426630 | 0.725550 |
| F1 | 0.538633 | 0.572009 |

OR aumenta la recall e riduce la precision; l'F1 macro migliora moderatamente.
Le medie sono calcolate sulle dieci query. Le formule e i casi non definiti
sono descritti nel [documento tecnico](docs/reproducibility.md).

Benchmark originario, tre costruzioni indipendenti per dimensione:

| Documenti | Mediana indicizzazione |
|---:|---:|
| 100 | 61,85 ms |
| 200 | 121,02 ms |
| 300 | 185,62 ms |

```sh
python scripts/benchmark.py
```

I campioni e il protocollo originari sono versionati in `evaluation/`.
Questo comando **aggiorna i file di benchmark versionati**; i tempi possono
variare fra macchine ed esecuzioni. Non serve rieseguirlo per verificare le metriche.

## 7. Ground truth e limiti

`evaluation/semantic/frozen.json` documenta il freeze definitivo e gli hash.
I 291 giudizi confermati comprendono 38 conferme di calibrazione, 85 dopo
discussione e 168 in blocco; **2.709 giudizi restano proposte non confermate**.
La supervisione è assistita, non una validazione umana indipendente di tutte le coppie.
Per Q01–Q05 la rilevanza riguarda esclusivamente il basename; per Q06–Q10 il testo.
Non sono usati query o relevance judgments ufficiali Cranfield.

Le proposte, le correzioni e la provenienza sono conservate e protette dagli hash,
anche quando i manifest descrivono una fase storica. L'esatta versione del modello
LLM non è disponibile: si riproduce la valutazione dei giudizi congelati, non
l'annotazione generativa originale.

## 8. Struttura essenziale

```text
corpus/                  300 TXT e metadata.csv
evaluation/              query, statistiche del corpus e benchmark versionati
  semantic/              giudizi congelati, proposte e prove di supervisione
irhome/                  motore, metriche, verifica e persistenza
scripts/                 ricerca, valutazione, confronto e controlli
tests/                   42 test automatici su fixture temporanee
provenance/              estratto della conversione Cranfield e identificativi delle sorgenti
docs/reproducibility.md   dettagli tecnici di riproducibilità
artifacts/               output locali generati, non versionati
```
