Tutti i testi di `topics.json` sono contenuti originali preparati per questo
homework, senza download né dipendenze da corpus esterni. Le frasi descrivono
12 temi; aperture, schede lessicali e paragrafi trasversali sono modelli di
composizione, non output di servizi durante l'esecuzione.

Ogni documento riceve un'etichetta principale con assegnazione ciclica bilanciata.
Per ciascuna query `thematic` in `queries.json` è rilevante (giudizio binario 1)
ogni documento con `topic` uguale a quello della query. Gli altri hanno giudizio
0 implicito. Il generatore materializza questi giudizi in `qrels.json`, senza
consultare indici o risultati. Gli ID sono percorsi relativi dei file.

È una ground truth **sintetica**: un documento può essere tematicamente rilevante
senza contenere esattamente le parole della query, e un testo di altro tema può
contenere parole utili. I risultati non stimano la rilevanza giudicata da persone
su documenti reali; template e vocabolario finiti possono rendere alcune query
molto facili. Le query F verificano correttezza lessicale con scansione diretta;
le query T misurano recupero tematico con etichette assegnate alla costruzione.
