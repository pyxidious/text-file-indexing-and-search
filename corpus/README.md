# Corpus conservato

`documents/` contiene i 300 TXT già presenti in
`artifacts/cranfield300/n300/dataset/documents/` prima del refactoring, copiati
senza modifiche. Gli hash sono stati verificati contro i metadati e il manifest
locali precedenti. `metadata.csv` conserva soltanto ID originale, filename,
titolo, SHA-256 e dimensione; non contiene giudizi o query ufficiali.

La provenienza Cranfield è documentata dal codice di acquisizione precedente
(`legacy/previous/irhome/acquire.py`) e dal manifest locale: `ir_datasets 0.5.11`,
archivio dichiarato `http://ir.dcs.gla.ac.uk/resources/test_collections/cran/cran.tar.gz`.
Il nuovo workflow non scarica né legge quell'archivio o lo snapshot con qrels.
Non è stata ripetuta un'acquisizione per attribuire nuove garanzie al dato.

Il vecchio manifest dichiara: ordinamento degli ID originali 1..1400,
`random.Random(42).shuffle`, primi 300 e riordinamento numerico dei selezionati.
Il codice precedente implementa tale procedura. È stata riprodotta la sola
permutazione degli ID, verificando che i 300 ID coincidano esattamente con quelli
presenti. Non possiamo ricostruire da ciò motivazioni o passaggi precedenti
all'esecuzione originaria; non ne vengono inventati.

Il preparatore precedente documenta `doc.text`, sola normalizzazione CRLF/CR in
LF, nessun titolo o newline aggiunto. I file attuali sono UTF-8 con soli LF e
restano identici ai byte verificati del sottoinsieme locale; il nuovo workflow
non modifica testi né tenta di ricostruire i byte dell'edizione Cranfield originale.
Eventuali errori o ripetizioni già presenti negli abstract sono preservati.

Il nome era già ottenuto dal titolo con NFKD, conversione ASCII, minuscole,
sequenze non `[a-z0-9]` sostituite da `_`, slug massimo 80 caratteri e ID
numerico a quattro cifre. Tale convenzione è leggibile nel preparatore archiviato
e nei filename attuali. Non è stata applicata una nuova rinomina. L'ID del
motore e dei CSV di revisione è il percorso relativo del TXT; il collegamento
all'ID Cranfield è esplicito nei metadati.

Statistiche verificabili tramite `python scripts/reproduce.py`:
300 documenti, 309.724 byte, 48.695 token e 3.993 token distinti con la
normalizzazione lessicale documentata; nessun gruppo di duplicati SHA-256.
Tutti hanno un titolo nei metadati; 299 iniziano con la medesima sequenza di
token. L'eccezione è l'ID 1369, preservato senza correzioni.

Le altre directory sotto `artifacts/` contengono copie, subset, ambienti e
precedenti esperimenti: non si contano come ulteriori documenti della collezione
e non si scandiscono per costruire i nuovi giudizi. Le dieci query nuove sono
in `evaluation/queries.csv`; non derivano dalle query ufficiali Cranfield.
