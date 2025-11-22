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