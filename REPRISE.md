# Reprise · CTF Unlock 1.2

État au 29 octobre 2026. Sources publiées sur [loghanmrsn/CTF-Unlock](https://github.com/loghanmrsn/CTF-Unlock), branche `main`. Le projet reste local pendant toutes ses recherches ; aucun fichier n'est envoyé à un service d'analyse.

## Résultat livré

Deux modes réels sont sélectionnables dans **Méthode** :

- **7-Zip** : ZIP ZipCrypto, ZIP AES et 7z avec ou sans en-têtes chiffrés. Un test complet de l'archive par candidat. Pause entre les essais, reprise et arrêt.
- **John Jumbo CPU** : ZIP ZipCrypto et ZIP AES. Extraction locale par `zip2john`, calcul sur l'empreinte, puis vérification intégrale du candidat par 7-Zip avant tout succès annoncé. Listes et masques bornés. Pas de pause implémentée ; arrêt disponible. Pas de prise en charge 7z par cet adaptateur John.

Les chemins des trois outils sont sélectionnables et les versions sont vérifiées. John standard n'est pas accepté à la place de Jumbo. Les outils du PATH et l'extracteur adjacent à John sont recherchés. Aucun moteur n'est téléchargé par l'application.

L'intégration John ne fournit pas encore de compteur ou de vitesse fiable : l'interface le dit et le bilan utilise `null`, sans données inventées. Les temps et phases de travail restent affichés.

## Ergonomie et fiabilité améliorées

- Réglages atomiques : chemins des moteurs et limites, jamais fichiers analysés, masques, candidats ou résultats. Migration des anciens réglages version 1 vers la version 2. Un fichier illisible reste intact et protégé contre les sauvegardes automatiques.
- Copie d'un mot de passe effectivement vérifié, effacement après 30 secondes ou à la fermeture seulement si le contenu du presse-papier est inchangé. L'historique du presse-papier Windows n'est pas contrôlé par l'application.
- Export JSON sans mot de passe, candidats, diagnostic brut ou chemin complet du fichier. Refus d'écraser les sources, listes, moteurs ou réglages.
- Aides selon le résultat, avertissement de masque trop grand pour le plafond, interface défilante à partir de 820 × 620 pixels logiques.
- Une erreur de vérification du moteur ne remplace pas un ancien résultat de récupération.
- Processus lancés sans shell. Sous Windows, création suspendue, affectation au Job Object puis reprise du thread initial : les limites sont appliquées avant le moteur et ses futurs enfants. Sous Linux, plafond d'espace mémoire et groupe de processus.

## Confidentialité spécifique au mode John

John nécessite des fichiers temporaires : liste normalisée (64 Mio maximum), empreinte, session et pot. **Le pot peut contenir le mot de passe en clair.** Un dossier temporaire distinct est utilisé pour chaque tâche et supprimé après succès, échec ou annulation normale. Un crash ou une coupure peut laisser des traces ; aucun effacement sécurisé n'est garanti.

La sortie brute de John peut aussi contenir des candidats : elle n'est pas affichée ni exportée. Les sorties de processus sont capturées dans des fichiers temporaires fermés après utilisation. Le mot de passe doit être passé à 7-Zip pour le test final ; il peut donc être visible dans la ligne de commande à un outil local autorisé à lire les processus.

Les originaux ne sont ni extraits sur disque, ni modifiés, ni supprimés. Les tests comparent leur empreinte SHA-256 avant/après récupération.

## Validation Linux effectuée

Python **3.12.14**, PySide6 **6.8.3**, 7-Zip (z) **25.01 x64**, John **1.9.0-jumbo-1+bleeding-5184bc0b8c**, PyInstaller **6.12.0**.

John a été compilé pour CPU, sans OpenCL, depuis le dépôt officiel `openwall/john` (commit `5184bc0b8c`). 7-Zip vient du dépôt officiel `ip7z/7zip`. Aucun moteur tiers non officiel n'est inclus dans les sources ou l'archive de l'application.

**39 tests réussis sous Linux**, aucun ignoré lorsque les trois outils sont fournis, dont **9 tests de la vraie interface Qt**. Ils couvrent :

- Récupération réelle de ZIP ZipCrypto, ZIP AES, 7z, en-têtes chiffrés, mauvaise liste, masque, limites, fichiers invalides, corruption et archives publiques.
- John : ZIP ZipCrypto/AES, masques, liste épuisée, plafond, espaces/deux-points dans le mot de passe, chemins accentués, annulation réelle et suppression du dossier temporaire.
- Vérification indépendante des résultats par 7-Zip et conservation des originaux.
- Arrêt d'un vrai processus, application du plafond mémoire, pause/reprise/fermeture, et réactivité Qt.
- Réglages atomiques, erreurs d'écriture/lecture, migration, rapport sans secret, presse-papier utilisateur préservé et protection contre l'écrasement d'une liste.
- Sélection de John et récupération déclenchée dans Qt, mot de passe masqué, statistiques inconnues explicitement indiquées.

Les interfaces 7-Zip et John ont été capturées et inspectées. Le paquet PyInstaller Linux a été construit et son démarrage vérifié. Cela ne constitue pas une validation interactive Windows.

Pour reproduire : définir `CTF_UNLOCK_7ZIP`, `CTF_UNLOCK_JOHN` et `CTF_UNLOCK_ZIP2JOHN` vers les outils locaux officiels, puis `QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -v`. Sans un outil requis, les tests correspondants sont explicitement ignorés.

## Validation Windows

Le workflow `.github/workflows/windows.yml` utilise Python 3.12 sur `windows-latest`, le 7-Zip du runner et le paquet Windows officiel Openwall **v1.9.1-ce**. Son téléchargement HTTPS est vérifié avec le SHA-256 fixé : `bab72da045d151c0482eb415ce172376323f58148ba395b51e0fe93ef23eb014`.

Le workflow répète les tests trois fois pour vérifier la stabilité, construit avec PyInstaller, contrôle le démarrage hors écran de l'exécutable et produit **CTF-Unlock-Windows**. Les moteurs ne sont pas redistribués dans cet artefact ; l'utilisateur les installe depuis leurs sources officielles.

La validation [40865591410](https://github.com/loghanmrsn/CTF-Unlock/actions/runs/40865591410) a terminé avec **Success** : les **39 tests ont réussi trois fois de suite**, aucun ignoré, dont **9 tests Qt**. Le paquet officiel John Windows a réellement retrouvé les mots de passe ZIP, et 7-Zip les a confirmés. Les tests d'arrêt et de mémoire ont exercé les Job Objects Windows. La construction PyInstaller, le démarrage hors écran de `CTF-Unlock.exe` et la création de l'artefact **CTF-Unlock-Windows** ont réussi.

La boucle d'attente des tests Qt libère explicitement le GIL Python pour ne pas affamer les travailleurs sous certaines versions Windows de PySide. Cela conserve les assertions et reflète le comportement de la boucle native `app.exec()`.

Les réglages et les sources restent locaux ; les sources du projet sont disponibles en ZIP sur GitHub et un ZIP séparé de l'application Windows est fourni dans l'artefact Actions. John et 7-Zip ne sont pas inclus : les installer depuis leurs sources officielles.

Même après réussite automatique, restent à essayer manuellement sur un bureau Windows : BAT, rendu/DPI, vrai glisser-déposer et presse-papier natifs, session prolongée de récupération, fermeture du binaire et éventuels avertissements SmartScreen. Le binaire n'est pas signé.

## Exemples et limites

`examples/demo.zip` (ZIP AES) et `examples/demo.7z` (en-têtes chiffrés) contiennent un fichier de référence et utilisent le mot de passe public **CTF42**. La liste `mots-demo.txt` est fournie. Utiliser le ZIP pour essayer John ; utiliser le 7z avec le moteur 7-Zip.

Pas de Hashcat/GPU, PDF, Office, ZIP64, multi-volume ou auto-extractibles pris en charge. Pas de garantie de récupération, ni de prise en charge de toutes les variantes ZIP. Les encodages non ASCII de mots de passe ne sont pas validés avec ce couple de moteurs. Une erreur chiffrée peut être indiscernable d'un mauvais mot de passe.

La pause John, ses compteurs et sa vitesse en temps réel restent à ajouter avant de les annoncer. Pour les autres formats, ajouter un véritable adaptateur et une validation indépendante avant d'élargir les promesses.

Ne pas modifier DevDock, Portfolio, SecurePass ou le profil GitHub pour poursuivre ce projet.
