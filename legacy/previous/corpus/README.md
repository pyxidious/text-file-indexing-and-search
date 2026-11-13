# Input dell'esperimento corrente

`functional_queries.json` contiene 12 query di correttezza lessicale sui campi
nome e contenuto, con aspettative positive e negative. I risultati esatti sono
verificati con `irhome/oracle.py`, che legge direttamente i file.

Lo snapshot conserva 225 query e 1.837 giudizi. I TXT correnti sono un campione
uniforme di 300 documenti con seed 42; i qrels esportati sono ristretti ai soli
ID presenti. Copertura e split development/test sono in `results/coverage.json`
e `results/splits.json`, ottenuti prima di confrontare le strategie.

`english_stopwords.txt` è una piccola lista originale di parole funzionali
inglesi, fissa e versionata prima del confronto. Si applica soltanto alle query
contenuto non phrase delle varianti filtrate; non modifica gli indici. Gli
stessi input della stoplist sono letti anche dallo scanner indipendente, che
reimplementa il matching senza usare le funzioni di selezione del motore.

Query informative e giudizi sono quelli originali di Cranfield acquisiti da
`ir_datasets==0.5.11`. Non sono etichette tematiche e non vengono prodotti dal
motore. La soglia binaria è `relevance >= 1`. `-1` indica un giudizio negativo;
l'assenza di un qrel indica un documento non giudicato, non un giudizio negativo.

Non si versionano documenti, query o qrels originali: la disponibilità pubblica
non equivale a una licenza esplicita di redistribuzione. Le pagine ufficiali e
`cranqrel.readme` sono stati consultati; non vi è una licenza esplicita per il
corpus nelle fonti consultate. I file si acquisiscono con la procedura del README
e si verificano tramite `config/cranfield.lock.json`. La licenza MIT del software
ir_datasets non viene attribuita ai dati Cranfield.

Il precedente materiale sintetico è isolato in `legacy/synthetic/` e non è usato.
