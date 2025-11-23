Je lis mes livres sur ma kobo.
idéalement, j'aimerais pouvoir les ouvrir sur mon ordinateur, avec les highlights aux bons endroits, discuter du livre avec un LLM, prendre des notes exportées dans obsidian, et faire des cartes anki.

# Récupération des ebooks

La première étape est de récupérer le livre avec les highlights, on verra pour la suite plus tard.

Dossier de kobo:
/Users/hugovaillaud/Library/Application Support/Kobo/Kobo Desktop Edition
Dans ce dossier, il y a le dossier kepub. Il contient des fichiers dont les noms ressemblent à "0844c89a-ad50-41dc-8b27-850246d47124", pas sûr du format. Mais je suppose que c'est les livres encryptés.

Pour récupérer mes ebooks, je peux utiliser le site kobo et télécharger les livres. Ca me télécharge un fichier `URLLink.acsm`qui est inexploitable en l'état, mais je peux utiliser le programme `Adobe Digital Editions` pour l'ouvrir et le convertir en epub.

Pour le moment j'ai acheté mes livres via la boutique kobo mais je suis ouvert à passer par un autre biais.

Ok j'ai récupéré le repo https://github.com/TnS-hun/kobo-book-downloader et ça a trop bien marché.
Problem solved.

# récupération des highlights

Je dois synchroniser ma liseuse kobo après ma lecture, puis synchroniser mon app kobo sur mon mac, et enfin synchroniser depuis mon interface sur l'écran principal.
C'est pas idéal, mais ça marche.

Note technique : J'ai exploré l'API web de Kobo (`library_sync`, `reading_state`, `notebooks`, etc.) pour tenter de récupérer les highlights directement depuis le cloud sans passer par Kobo Desktop. Malheureusement, aucun endpoint public ou privé testé ne retourne les annotations utilisateurs.  La méthode via la base SQLite locale (`Kobo.sqlite`) reste donc la seule solution fiable actuellement.
Pour plus tard, je pourrai explorer plus en profondeur.

# Prise de notes

L'intégration est en place avec Obsidian.

**Localisation :**

- Vault : `/Users/hugovaillaud/Documents/synced_vault`
- Dossier racine : `books/`

**Structure des fichiers :**

- Chaque livre a son propre dossier : `books/Titre_du_Livre/`
- **Note Principale** (`Titre_du_Livre.md`) : Contient la liste des chapitres. Elle est créée vide (juste avec le titre), et les liens vers les chapitres s'ajoutent automatiquement au fur et à mesure que l'on crée des notes pour ces chapitres.
- **Notes de Chapitre** (`Titre_du_Chapitre.md`) : Contiennent le texte écrit depuis l'interface. Le nom du fichier correspond exactement au titre du chapitre dans la table des matières.

**Fonctionnalités :**

- **Synchronisation Bi-directionnelle** :
  - Les modifications dans l'interface Reader sont sauvegardées en temps réel (autosave) dans le fichier `.md`.
  - Si le fichier `.md` est modifié dans Obsidian, l'interface Reader se met à jour automatiquement (polling toutes les 2s quand le panneau est ouvert).
- **Interface** : Un panneau latéral rétractable ("📝 Notes") permet d'éditer la note du chapitre courant en Markdown.
- **Workflow** : On lit un chapitre, on ouvre le panneau de notes, on écrit. Le fichier est créé à la volée s'il n'existe pas, et un lien est ajouté dans la Note Principale du livre.

# Chat

Je veux qu'on puisse ouvrir des discussions avec un LLM à propos du chapitre qu'on lit.
Il  y a un historique de discussions par chapitre, accessible facilement.
On peut facilement ajouter le chapitre entier, des bouts de chapitre spécifiques et la note du chapitre en contexte dans la discussion.
On peut demander au LLM d'ajouter/modifier facilement la note de chapitre en fonction de notre discussion.

# To do
- [x] possibilité de highlighter dans le chapitre courant.

- [x] faire en sorte que les highlights ne s'enlèvent pas lors de la synchronisation.

- [x] le higlight devrait être une option comme le quoting.

streaming of output in chat.

improve chat interface.

access to chat history

new conversation button

is the context of old messages added to history as well ?

utiliser langgraph.
