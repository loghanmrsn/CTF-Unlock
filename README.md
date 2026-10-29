# CTF Unlock 1.1 · its lizhy · Loghan

**Un fichier. Des pistes.**

Application de bureau Python 3.12 + PySide6 pour analyser des archives de challenges CTF et tenter des mots de passe **hors ligne**, sur des fichiers pour lesquels vous disposez d'une autorisation. Thème noir, blanc et argent inspiré du [portfolio](https://loghanmrsn.github.io/Portfolio/).

Le logiciel est utilisable, mais ne garantit aucune récupération. Il ne prétend pas ouvrir tous les fichiers.

## Nouveautés de la version 1.1

- Le chemin de 7-Zip et les limites sont mémorisés automatiquement, avec un bouton d'enregistrement manuel. Aucun chemin d'archive, liste, masque, candidat ou mot de passe n'est mémorisé.
- **Copier** récupère un mot de passe réellement vérifié. Le presse-papier est effacé après 30 secondes ou à la fermeture, uniquement si son contenu est encore celui copié par CTF Unlock. Un autre contenu copié entre-temps est conservé. L'historique éventuel du presse-papier Windows est géré par Windows, pas par l'application.
- **Exporter le bilan JSON** enregistre uniquement nom du fichier (sans chemin complet), moteur, issue, date UTC et statistiques. Aucun mot de passe ni diagnostic brut. L'export refuse de remplacer l'archive, la liste, le moteur ou les réglages, y compris via un lien vers le même fichier.
- Des indications expliquent quoi faire après chaque résultat. Les masques signalent si le plafond de candidats ne couvre pas tout l'espace de recherche.
- L'interface défile sur les petits écrans, avec des commandes accessibles à partir de 820 × 620 pixels logiques.
- Une erreur lors de la vérification du moteur ne remplace plus le résultat d'une recherche précédente par un résultat sans rapport.
- Le workflow GitHub **CTF Unlock Windows** exécute les tests, construit le logiciel et produit l'artefact **CTF-Unlock-Windows**. Il exige le 7-Zip fourni par le runner ; aucune archive de test ne sera simulée si le moteur manque.

Les réglages sont stockés dans `%LOCALAPPDATA%\CTF-Unlock\preferences.json` sous Windows et `$XDG_CONFIG_HOME/ctf-unlock/preferences.json` (ou `~/.config/ctf-unlock/preferences.json`) sous Linux. Leur écriture est atomique. Si le fichier est illisible, l'original reste intact et l'enregistrement automatique est désactivé : corriger ou déplacer ce fichier puis relancer l'application. Les erreurs d'enregistrement restent visibles.

## Formats et moteur réellement pris en charge

| Format | V1 | Vérification d'un candidat |
| --- | --- | --- |
| ZIP classique, ZipCrypto | Oui, testé | `7-Zip t`, archive entière |
| ZIP AES-256 | Oui, testé | Même test complet |
| 7z AES, en-têtes visibles | Oui, testé | Même test complet |
| 7z AES, en-têtes chiffrés | Oui, testé | Même test complet, dont ouverture de l'en-tête |
| Archive non protégée | Détectée puis testée | N'est jamais présentée comme un mot de passe retrouvé |
| ZIP64, ZIP multi-volume | Non dans cette v1 | Refus explicite |
| 7z multi-volume, auto-extractibles | Non dans cette v1 | Hors périmètre ; choisir une archive simple |
| PDF, Office, RAR, autres formats | Non | Architecture prévue pour d'autres adaptateurs |

**Seul 7-Zip est intégré.** John the Ripper et Hashcat ne sont pas appelés et il n'existe pas d'accélération GPU dans cette version. La version du moteur choisi est vérifiée. La version réellement utilisée pour la validation Linux est **7-Zip (z) 25.01 x64** ; les autres versions ne sont pas toutes validées.

Les signatures ZIP et 7z sont lues dans le fichier, indépendamment de l'extension. Les ZIP auto-extractibles ne sont pas recherchés à l'intérieur d'un exécutable. Les conteneurs Office basés sur ZIP peuvent être identifiés comme ZIP ; cela ne constitue pas une prise en charge du chiffrement Office.

## Installer sur Windows

1. Installer **Python 3.12 64 bits**, avec le lanceur `py`, depuis [python.org](https://www.python.org/).
2. Installer **7-Zip** depuis son [site officiel](https://www.7-zip.org/). Aucun moteur n'est téléchargé automatiquement ou fourni dans ce ZIP.
3. Extraire entièrement le projet dans un dossier accessible en écriture.
4. Double-cliquer sur **Lancer-CTF-Unlock.bat**. Il crée `.venv`, vérifie Python 3.12, installe PySide6 puis lance l'application.
5. Dans **Réglages**, vérifier le moteur détecté. Au besoin, sélectionner `C:\Program Files\7-Zip\7z.exe`, puis cliquer sur **Détecter / vérifier la version**.

L'installation Python nécessite Internet pour les dépendances ; l'analyse et les recherches ne font aucune requête réseau. Une fois les dépendances installées, démarrage sans vérification réseau :

```bat
.venv\Scripts\python.exe app.py
```

Si un ancien `.venv` utilise une autre version Python, le supprimer et relancer le BAT. Ne pas déplacer un environnement virtuel entre machines.

## Essayer immédiatement

Le dossier `examples/` contient deux vraies archives chiffrées :

- `demo.zip` : ZIP AES-256 ;
- `demo.7z` : 7z avec en-têtes chiffrés ;
- mot de passe connu : **`CTF42`** ;
- liste fournie : `mots-demo.txt`.

Après installation de 7-Zip, sélectionner une de ces archives, choisir la liste, puis démarrer. `preuve.txt` est leur contenu de référence. `CREER-DEMO.bat` permet de les recréer après avoir déplacé les anciennes archives ; il refuse de remplacer les exemples existants.

## Utiliser l'interface

1. **Fichier** : déposer un seul fichier local ou le sélectionner. L'analyse asynchrone affiche signature, taille et protection lorsque détectable. Sans moteur, la signature et les métadonnées ZIP restent consultables ; l'absence de 7-Zip est signalée.
2. **Méthode** : choisir une liste UTF-8 ou un masque.
3. **Réglages** : définir moteur, durée totale, candidats, threads, mémoire et délai d'une opération moteur.
4. **Démarrer** : consulter les essais terminés, leur vitesse moyenne, le temps écoulé et le résultat.

Les mots de passe trouvés sont masqués par défaut ; l'interrupteur **Afficher le mot de passe trouvé** permet de les lire. Le journal n'inscrit pas les candidats ni le mot de passe trouvé. Les diagnostics de 7-Zip restent consultables avec **Détails techniques**. Aucun résultat simulé n'est affiché.

### Liste

Un mot de passe par ligne, UTF-8 avec ou sans BOM. Les espaces en début et fin sont **conservés**. Lignes vides ignorées, 128 caractères maximum par candidat, aucun octet nul. La liste est lue progressivement ; son nombre total n'est pas inventé, la progression affiche donc le nombre d'essais et « total inconnu ».

### Masque borné

Saisir de 1 à 64 caractères **distincts**, puis des longueurs de 1 à 8. Par exemple `ab2`, longueur 2, produit `aa`, `ab`, `a2`, `ba`, etc. Il s'agit d'un alphabet et de bornes de longueur, pas de la syntaxe des masques Hashcat. L'espace total de recherche est calculé exactement, mais les limites de durée et de candidats peuvent interrompre son exploration. Aucun dictionnaire ou candidat n'est envoyé à un service externe.

### Pause et arrêt

7-Zip ne propose pas de pause portable du test courant. **Mettre en pause** attend sa fin et bloque les prochains candidats ; l'état « En pause » confirme la pause effective. La durée maximale continue à s'écouler pendant la pause. **Reprendre** poursuit la même tâche, sans réinitialiser ses compteurs.

**Arrêter** termine le processus moteur et nettoie son groupe. Fermer la fenêtre demande également cet arrêt et attend la fin du travail avant de quitter. Une seule tâche et un seul processus moteur fonctionnent à la fois.

## Limites de ressources

- Durée totale configurable : 1 à 3600 secondes dans l'interface, préparation et pauses incluses. Contrôle périodique pendant les opérations moteur et entre les essais ; les accès système au fichier et le nettoyage peuvent ajouter un court délai.
- Délai par opération moteur : 0,1 seconde à la durée totale. Un test complet qui dépasse ce délai rend la recherche **incomplète** ; il ne prouve pas que le candidat est faux.
- Nombre d'essais : 1 à 1 000 000 maximum. Une recherche arrêtée par cette borne est distinguée d'une liste réellement épuisée.
- Threads 7-Zip : 1 à 4, transmis par `-mmt`. Ce n'est pas un plafond global de pourcentage CPU.
- Mémoire **du moteur** : 128 à 4096 Mio. Windows utilise un Job Object avec limite mémoire totale et destruction des enfants à la fermeture. Linux utilise `prlimit(RLIMIT_AS)` et un groupe de processus. Ces mécanismes sont configurés juste après la création du processus. La mémoire de l'interface Qt n'est pas incluse. Une limite insuffisante peut empêcher l'ouverture d'une archive même avec le bon mot de passe.
- Sortie technique bornée à 1 Mio par appel, puis arrêt avec erreur ; métadonnées d'archive bornées à 16 Mio. ZIP : au plus 10 000 entrées annoncées. Si les limites système ne peuvent pas être appliquées, l'appel est interrompu avec une erreur explicite.

Chaque candidat lance **un test complet de l'archive**. Ce moteur est volontairement simple et lent par rapport à un outil spécialisé utilisant des empreintes et un GPU. Il convient aux petits challenges et aux listes ciblées, pas à de grandes explorations exhaustives.

## Comprendre les résultats

- **Mot de passe trouvé et vérifié** : 7-Zip a décompressé et vérifié l'archive entière en mémoire avec ce candidat, code de sortie 0. Pas de simple comparaison d'extension ou d'en-tête, pas d'extraction sur disque.
- **Liste ou masque épuisé** : tous les candidats produits ont été rejetés sans validation. Cela ne signifie pas qu'aucun mot de passe n'existe.
- **Tâche interrompue** : arrêt utilisateur ou fermeture.
- **Limite atteinte** : temps total, délai moteur ou nombre de candidats atteint ; recherche incomplète.
- **Fichier endommagé** : structure/troncature/CRC invalide détecté sans ambiguïté.
- **Format ou méthode non pris en charge** : signature ou variante non gérée, ou méthode signalée comme non prise en charge par 7-Zip.
- **Archive non protégée** : test intégral réussi sans mot de passe nécessaire ; aucun mot de passe « trouvé » n'est affiché.
- **Erreur** : dépendance absente, problème d'accès, limites non applicables, mémoire insuffisante ou autre erreur moteur ; diagnostic affiché.

**Ambiguïté réelle :** pour certaines archives chiffrées, 7-Zip ne peut pas distinguer des données altérées d'un mauvais mot de passe. Une erreur « Wrong password? » rejette le candidat ; si la recherche s'épuise, le logiciel explique cette ambiguïté et n'affirme pas que le fichier est sain. Des méthodes rares ou des variantes de ZIP non testées peuvent aussi échouer. Les gros fichiers peuvent dépasser les limites avant toute conclusion.

## Conservation des originaux et confidentialité

Les opérations moteur sont uniquement `i` (version), `l` (liste) et `t` (test). Aucun appel d'extraction, modification, réparation ou suppression. Les chemins sont absolus et les commandes utilisent des **listes d'arguments, sans shell**. Le programme ne construit jamais une commande shell à partir du nom du fichier ou d'un candidat. Une modification externe de la taille/date du fichier pendant la recherche provoque un arrêt.

Les fichiers originaux et les listes restent à leur emplacement. Les sorties temporaires du moteur sont automatiquement fermées ; aucun fichier n'est envoyé à un service, et l'application n'enregistre jamais les candidats ou mots de passe sur disque. Elle mémorise seulement moteur et limites ; un bilan statistique peut être exporté volontairement sans mot de passe ni diagnostic brut. Le mot de passe doit toutefois être fourni à 7-Zip comme argument de processus : il peut être visible pour les outils locaux ayant accès à la ligne de commande. Les chemins et les messages techniques peuvent apparaître dans l'interface. La lecture peut modifier la date d'accès gérée par le système, pas le contenu du fichier.

## Tests

Les tests construisent de petites archives réelles dans des dossiers temporaires, avec des mots de passe connus. Installer 7-Zip avant de lancer les tests d'intégration.

Windows :

```bat
set CTF_UNLOCK_7ZIP=C:\Program Files\7-Zip\7z.exe
set QT_QPA_PLATFORM=offscreen
.venv\Scripts\python.exe -m unittest discover -s tests -v
set QT_QPA_PLATFORM=
```

Linux :

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
CTF_UNLOCK_7ZIP=/chemin/vers/7zz QT_QPA_PLATFORM=offscreen \
  .venv/bin/python -m unittest discover -s tests -v
.venv/bin/python app.py
```

`CTF_UNLOCK_7ZIP` est une variable **de test** ; dans l'application, sélectionner le moteur dans Réglages ou l'installer à un emplacement automatiquement détecté.

**30 tests réussis sous Linux**, dont huit tests Qt réels. Sans moteur, les tests d'intégration correspondants sont signalés **skipped**, pas réussis. Les tests d’arrêt de processus et de limite mémoire sont exécutables sous Linux et Windows ; le test Windows attend effectivement la terminaison du processus via son handle système. Le rendu Qt a été capturé et inspecté sous Linux. **Windows, son Job Object, le BAT et un exécutable Windows ne sont pas encore validés** : voir `REPRISE.md`.

## Construire un exécutable Windows

**Sur Windows**, avec Python 3.12 et les dépendances installées :

```bat
.venv\Scripts\python.exe -m pip install PyInstaller==6.12.0
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean CTF-Unlock.spec
```

Le dossier `dist\CTF-Unlock` contient `CTF-Unlock.exe` et `_internal` avec Python, Qt et le thème. Copier **tout le dossier**, pas uniquement le `.exe`. 7-Zip reste une dépendance externe à installer depuis son site officiel. Pour partager, copier aussi `README.md`, `REPRISE.md` et `examples/` à côté de l'exécutable, puis archiver tout le dossier. L'exécutable n'est pas signé.

PyInstaller ne fabrique pas un exécutable Windows depuis Linux. Le packaging et son démarrage sont vérifiés ici **uniquement pour Linux** ; aucun binaire Windows fonctionnel n'est annoncé.

## Structure et extensions futures

```text
app.py                     point d'entrée Qt
ctf_unlock/models.py       états, résultats et limites
ctf_unlock/archives.py     signatures et métadonnées bornées
ctf_unlock/engine.py       adaptateur 7-Zip, vérification réelle
ctf_unlock/processes.py    processus et limites système
ctf_unlock/candidates.py   dictionnaire progressif et masque
ctf_unlock/tasks.py        recherche, pause, annulation
ctf_unlock/ui.py           interface Qt et travaux hors du thread GUI
ctf_unlock/storage.py      réglages atomiques et bilans sans mot de passe
theme.qss                  thème noir, blanc et argent
tests/                     validations unitaires, moteurs et interface
examples/                  archives connues et liste de démonstration
```

Pour PDF ou Office, ajouter un adaptateur de format et un moteur capables de **vérifier réellement** leurs mots de passe, puis leurs tests. Ils ne sont pas implémentés ici. Pas de récupération garantie ni de prise en charge « tous fichiers ».
