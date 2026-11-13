# Pipeline pilota per silver qrels

Questa attività è separata dal retrieval: non cambia TXT, campionamento, analyzer,
indici, BM25, strategie, qrels originali o risultati precedenti. Usa standard
library. Gli output sono in `artifacts/silver-study/`, ignorata da Git: conservare
l'intera directory per ricalcolare le metriche senza ripagare l'inferenza.

## Stato verificato

**Pipeline pronta e testata strutturalmente, non validata semanticamente.**
Non sono configurati modello, credenziali API o un endpoint locale. Sono state
preparate 404 coppie note e 120 non giudicate, ma eseguite **zero annotazioni
reali e zero richieste**. Matrice e metriche sono non disponibili, non zero.
Non esistono esempi empirici di errori o accordi. Il report operativo generato
è `artifacts/silver-study/report.md`, con `pilot_metrics.json` e `dry_run.json`.

## Preparazione e dry run

Usare il corpus 300 già esistente. Se manca in un clone nuovo, dopo aver installato
l'ambiente del README preparare **solo** il corpus, senza rieseguire il retrieval:

```powershell
.venv\Scripts\python.exe scripts/generate_dataset.py --output artifacts/cranfield300/n300/dataset
.venv\Scripts\python.exe scripts/annotate_silver.py prepare
.venv\Scripts\python.exe scripts/annotate_silver.py dry-run --phase all
.venv\Scripts\python.exe scripts/annotate_silver.py report
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Con snapshot Cranfield locale aggiungere `--offline` alla sola preparazione del
dataset. La pipeline silver non scarica dati. Ogni sottocomando accetta `--dataset`
e `--output`; `prepare` accetta `--config`. Gli altri comandi usano le impostazioni
congelate nello studio. La ripreparazione identica è idempotente; cambiamenti di
modello, dati, prompt o impostazioni richiedono una nuova directory.

## Provider reale e scelta del modello

Non è stato scelto o eseguito un modello in questo ambiente. Prima dell'inferenza,
fissare un modello/snapshot effettivamente disponibile, capace di leggere l'intero
abstract e rispettare JSON Schema, con costo e parametri di generazione noti.
Non scegliere modello/prompt in base all'accordo sulla validazione finale.

L'adapter effettua un vero HTTP POST a `<base_url>/chat/completions`, con due
messaggi, `response_format.type=json_schema`, schema stretto e `store=false`.
È configurabile per OpenAI e server compatibili. Si segue la
[documentazione ufficiale Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create).
Il trasporto è testato con mock, ma non è stato verificato contro un servizio
LLM reale. Nessuna chiamata alla sessione Codex viene trattata come annotazione.

In `config/silver.json`, `model_id: null` è intenzionale. Impostare `LLM_MODEL`
a un ID/snapshot disponibile prima di preparare uno studio per inferenza.
`OPENAI_API_KEY` deve provenire dall'ambiente sicuro o da un gestore di segreti:
non salvarla in repository né inserirla in chat o file di configurazione.

```powershell
$env:LLM_MODEL = 'ID_SNAPSHOT_DISPONIBILE'
# OPENAI_API_KEY deve essere già fornita dall'ambiente sicuro.
.venv\Scripts\python.exe scripts/annotate_silver.py prepare --output artifacts/silver-live
.venv\Scripts\python.exe scripts/annotate_silver.py dry-run --output artifacts/silver-live --phase pilot
# Inferenza esplicita, potenzialmente a pagamento:
.venv\Scripts\python.exe scripts/annotate_silver.py annotate --output artifacts/silver-live --phase pilot --max-requests 1
```

`LLM_BASE_URL` può indicare un altro endpoint; `api_key_env` configura il nome
della variabile del segreto, mai il valore. Per un server locale senza auth,
una copia del config deve dichiarare `require_api_key=false`. Si accettano HTTPS
o HTTP solo su localhost, senza credenziali/query nella URL; redirect rifiutati.
Gli errori HTTP sono registrati per categoria, senza body o header contenenti segreti.

Impostare solo parametri supportati dal modello. Il default ha soltanto
`max_completion_tokens=2048`; non impone temperature a modelli incompatibili.
Temperature zero e snapshot non garantiscono determinismo perfetto. Il modello
effettivo della prima risposta viene registrato; non può cambiare nello stesso
studio. Preferire snapshot agli alias dinamici e conservare tutte le ricevute.

## Prompt e blinding

`prompts/relevance_judge_v1.txt` e `relevance_response_v1.json` fissano istruzioni
e schema prima della validazione. Nessuna calibrazione: tutte le 404 coppie note
sono validazione finale. Calibrare in futuro richiederebbe un protocollo nuovo
con un insieme separato e una validazione intatta.

Il giudice riceve esclusivamente istruzioni congelate e un JSON con
`information_need` e `document` integrali. ID, filename, qrels, strato, ranking,
punteggi e risposte precedenti non sono trasmessi. Gli ID sono aggiunti localmente
al JSON finale. Il prompt tratta query/documento come dati e rifiuta istruzioni
incorporate; non si forniscono tool. Questo non prova resistenza alla prompt injection.

Scala: 0 nessun contributo sostanziale; 1 background marginale utile a un aspetto
reale; 2 risposta diretta a una parte importante con lacune sostanziali; 3 risposta
centrale con lacune limitate; 4 risposta esplicita e sostanzialmente completa.
Overlap non significa rilevanza. `unassessable` richiede `relevance=null` e resta
distinto dal negativo. La confidence è auto-dichiarata, non probabilità calibrata.

Ogni silver registra query_id, doc_id, relevance, confidence, explanation, evidence,
model_id, prompt_version, assessment, hash, timestamp e ricevuta. I positivi
richiedono almeno una citazione esatta dal TXT; massimo due, fino a 400 caratteri.
JSON malformati, duplicati, campi mancanti, NaN, gradi fuori scala, rifiuti,
troncamenti e citazioni estranee vengono rifiutati e registrati.

**Citazione esistente non equivale a entailment.** Tutte le etichette rimangono
`semantic_review=pending`; la revisione umana deve respingere spiegazioni non
supportate, anche con citazioni formalmente valide. Non si promuove automaticamente
alcuna etichetta silver a gold né si fondono fonti diverse.

## Campionamento e piano futuro

- Pilot: le 404 coppie note (352 positive, 52 negative), ordinate per ID. Si usa
  la presenza del qrel per pianificare, senza inviarne il valore al giudice.
- Non giudicati: 120 coppie assenti dai qrels. Su coppie enumerate per ID numerici,
  40 casuali con `Random(42).sample`; fra le restanti, 40 minime e 40 massime per
  Jaccard degli insiemi di parole `[a-z]+` minuscole, con spareggi per ID.
  L'ordine finale è mescolato. Nessun BM25 o analyzer del motore; il lessico
  serve al campionamento e non produce etichette.
- Futuro: ID delle 225 query ordinati, permutati con un nuovo `Random(42)`, primi
  20 per 300 documenti = 6.000 coppie. Configurabili 15..20 query, quindi
  4.500..6.000 coppie, senza consultare le prestazioni IR.

Il piano e gli hash sono congelati prima dell'inferenza. L'inferenza futura è
**disabilitata** e il comando relativo viene rifiutato. Una futura abilitazione
richiede decisione esplicita dopo pilota e controllo umano; non è stata eseguita.

## Budget e ripresa

Default 10 richieste per invocazione, 600 totali per studio, includendo retry e
richieste incerte; massimo un retry per coppia/invocazione, timeout 60 secondi,
attesa 1 secondo. Senza provider il comando restituisce codice 2, zero richieste.
Il limite è di richieste, non di annotazioni garantite. Errori di autenticazione,
configurazione o cambio modello fermano l'invocazione.

```powershell
# Dopo aver controllato il primo risultato, continuare con budget esplicito.
.venv\Scripts\python.exe scripts/annotate_silver.py annotate --output artifacts/silver-live --phase pilot --max-requests 50
.venv\Scripts\python.exe scripts/annotate_silver.py evaluate --output artifacts/silver-live
# La seconda fase resta una scelta esplicita distinta:
.venv\Scripts\python.exe scripts/annotate_silver.py annotate --output artifacts/silver-live --phase unjudged --max-requests 10
```

Ripetere `annotate` riprende il lavoro senza richiamare coppie già annotate.
Ricevute write-ahead in `attempts/`; risposta salvata prima della validazione;
JSON per coppia in `silver_qrels/`, scritti atomicamente, mai sovrascritti.
Se una risposta è già salvata, l'etichetta mancante può essere ricostruita senza
un'altra chiamata per quella coppia. Alterazioni e hash incompatibili causano errore.

Un solo worker per studio. Ctrl+C rilascia il lock; dopo un hard crash verificare
che nessun worker sia attivo e rimuovere solo il file `run.lock` dello studio.
Richieste `inflight`/`uncertain` non sono ritentate automaticamente.
`--retry-uncertain` è una scelta esplicita con possibile doppio addebito: non si
garantisce esecuzione esattamente-una-volta sul server se la risposta va perduta.

Il dry run stima token come byte UTF-8 della richiesta / 3 arrotondati: è una
stima grezza, non un tokenizer o un conteggio fatturabile. Mostra anche budget
e cap di output. Prezzi `null` significano costo stimato non disponibile; inserirli
per milione nella copia del config prima della preparazione, se noti. La stima
usa input grezzo e cap di output senza retry/sconti. Usage reale ed errori sono
salvati; token e costi possono essere sconosciuti dopo errori. Le stime non sono
fatture. Con zero richieste, costo sostenuto zero; costo medio non definito.

## Metriche e report

`evaluate`/`report` ricalcolano offline. Sulle sole coppie pilot: gold positivo
grado >=1, negativo esplicito -1; silver positivo >=1. Si calcolano TP/FP/FN/TN,
accuracy `(TP+TN)/N`, precision `TP/(TP+FP)`, sensibilità `TP/(TP+FN)`, specificità
`TN/(TN+FP)`, balanced accuracy (media di sensibilità e specificità), F1
`2TP/(2TP+FP+FN)` e Cohen kappa `(accordo_osservato-atteso)/(1-atteso)`.
Denominatori zero → null/N.D. Astensioni escluse dai denominatori e riportate
per classe originale; mancanti e copertura sempre visibili. Una validazione
parziale non equivale alle 404 complete. I non giudicati non sono negativi certi.

Accordo graduato esplorativo: matrice 5x5, accordo esatto, MAE, kappa quadratica.
Per il confronto -1 diventa 0, altri gradi invariati, senza modificare qrels;
la nuova rubrica e quella storica non sono dimostrate equivalenti.
Esempi di accordo/disaccordo includono solo annotazioni reali disponibili.
Con zero risposte, esempi ed errori ricorrenti sono N.D., mai inventati.

Limiti: sbilanciamento, campione piccolo, pool storico incompleto/non infallibile,
possibile memorizzazione del benchmark nel training, prompt injection, dipendenza
da modello/prompt, confidence non calibrata, astensioni selettive e mancata prova
automatica dell'entailment. Non si decide di usare silver come gold dalla sola accuracy.

## Revisione umana separata

`human_blind_unjudged.csv` mostra 120 coppie mescolate, query/documento completi,
senza etichette, risposte LLM o strati. Compilare una copia senza consultare
altri giudizi: assessment `assessable`/`unassessable`, relevance intero 0..4
(vuoto per astensione), explanation, evidence (citazione letterale richiesta
per positivi) e reviewer_id. Non cambiare ID o testi.

```powershell
.venv\Scripts\python.exe scripts/annotate_silver.py import-review artifacts/review_compilata.csv --output artifacts/silver-live
.venv\Scripts\python.exe scripts/annotate_silver.py report --output artifacts/silver-live
```

L'import controlla ID/testi, formato e citazioni e salva batch in `manual_reviews/`,
separati dagli originali e dai silver. Reimportare il medesimo CSV è idempotente;
batch diversi restano revisioni distinte, senza adjudication automatica. Il
confronto silver/umano viene calcolato separatamente per ciascun batch nel
JSON, limitata ai giudizi umani valutabili disponibili. Il campione arricchito
ad alto/basso overlap non stima la prevalenza su tutte le coppie non giudicate.
Una revisione del grado non prova il supporto delle spiegazioni LLM: serve un controllo
umano esplicito. Nessuna validazione semantica dei non giudicati è completa senza revisione.

## Output e test

Deterministici: `study.json`, `pairs.json`, prompt/schema congelati, CSV cieco.
Osservati: ricevute, timestamp, modello effettivo, token, errori/retry e annotazioni.
Derivati offline: `pilot_metrics.json`, `dry_run.json`, `report.md`.
Tutti gli input software/configurazioni/prompt sono versionati; i dati restano
negli artifact locali come il corpus Cranfield originale.

I test usano double locali solo in directory temporanee, con modello
`unit-test-model`, per verificare HTTP, schema, citazioni, metriche calcolate a
mano, budget e ripresa. Non sono annotazioni LLM reali o evidenza semantica, e
non vengono esportati nello studio operativo.
