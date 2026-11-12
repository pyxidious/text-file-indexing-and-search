# Input dell'esperimento corrente

`functional_queries.json` contiene 12 query di correttezza lessicale sui campi
nome e contenuto, con aspettative positive e negative. I risultati esatti sono
verificati con `irhome/oracle.py`, che legge direttamente i file.

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
