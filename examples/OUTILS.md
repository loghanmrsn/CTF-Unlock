# Essayer les outils CTF

Tout est exécuté localement. Ces exemples sont publics et ne contiennent aucune donnée personnelle.

## Texte

Dans **Outils CTF → Texte / encodages**, choisir ROT13 et saisir `synt{PGS42}` : le résultat doit être `flag{CTF42}`. Hexadécimal `666c61677b43544634327d` donne le même texte avec **Hexadécimal → octets**.

XOR attend une entrée et une clé en hexadécimal : `040e0305`, clé `42`, donne `FLAG`. Ce n'est pas une recherche automatique de clé. César propose un décalage choisi ou les 26 variantes ; seuls A–Z et a–z changent.

## Images et colorimétrie

Charger ou déposer `image-demo.png` sur la zone d'image. Cliquer un pixel pour lire ses valeurs originales. Essayer les canaux R/G/B/A et les plans de bits 0–7. Le bit 0 est le bit de poids faible d'un canal.

Pour l'extraction de l'exemple : canaux **RGB**, bit **0**, pixel **0**, **19 octets**, **Premier bit → poids fort**. Le texte extrait est `flag{pixels_locaux}`. Les bits sont parcourus ligne par ligne, pixels de gauche à droite, canaux dans l'ordre choisi ; les octets incomplets sont omis.

La palette/histogramme utilise au plus 65 536 pixels et exclut les pixels entièrement transparents. Palette par groupes de 16 niveaux, couleurs moyennes représentatives : elle est approximative. Ni correction d'orientation EXIF ni gestion ICC ; les calculs supposent du sRGB. Les vues ne prouvent pas qu'une image contient un message. Aucun OCR, décryptage universel ou détection automatique de langue n'est intégré.

**Exporter PNG** crée un nouveau fichier à partir de la dernière vue appliquée, sans remplacer l'original ni un autre fichier existant. Les métadonnées de l'original ne sont pas recopiées volontairement dans cette vue.

## SQLite

Dans **SQLite / SQL**, ouvrir `demo.sqlite`, choisir `challenge_notes`, puis **Lire la table**. La base est reconnue par sa signature. Exemple de requête :

```sql
SELECT c.title, n.body
FROM challenges AS c JOIN notes AS n ON c.id = n.challenge_id
WHERE n.body LIKE '%flag%'
ORDER BY n.id
```

Résultat public : `flag{sqlite_local}`. On peut consulter le schéma, les index et les clés étrangères, filtrer les valeurs d'une table, utiliser SELECT ou WITH…SELECT et parcourir les pages. Ajouter ORDER BY pour un ordre stable. Les noms de colonnes « flag », « password », etc. sont seulement des indices, jamais une preuve de découverte.

Exporter en JSON/CSV les lignes sélectionnées, ou toute la page si rien n'est sélectionné. L'export ne couvre pas automatiquement les pages suivantes. Le JSON conserve les colonnes et les lignes séparément, les NULL et les octets sous la forme `{"$bytes_hex":"00ff"}` ; les réels non finis sont balisés `$float`. Les TEXT non UTF-8 sont aussi conservés comme octets. CSV : NULL devient vide, octets `hex:…`, chaînes commençant par un préfixe de formule protégées par une apostrophe. Préférer JSON pour préserver les types.

L'inspecteur copie la base et son éventuel WAL dans un dossier temporaire privé ; il n'ouvre pas l'original avec SQLite, ne crée pas de SHM à côté et ne restaure pas un journal de transaction. Si un journal rollback est présent, fermer le logiciel qui possède la base et fournir une copie cohérente. Une base changée depuis l'analyse doit être analysée à nouveau. Les copies temporaires sont supprimées à la fin normale ; un crash peut laisser des traces, sans garantie d'effacement sécurisé.

Écritures, ATTACH, chargement d'extensions et commandes multiples refusés. Aucune connexion à MySQL/PostgreSQL, import/exécution de `.sql`, injection SQL, prise en charge SQLCipher ou récupération de lignes supprimées. Limites : base 256 Mio, WAL 64 Mio ; 128 objets/colonnes ; requête 16 Kio et 5 s ; résultat 500 lignes/10 000 cellules/2 Mio, cellule 1 Mio. L'affichage visuel tronque les cellules longues, mais l'export utilise les valeurs complètes de la page. **Arrêter** annule le traitement ; la dernière page réussie reste exportable après une erreur.
