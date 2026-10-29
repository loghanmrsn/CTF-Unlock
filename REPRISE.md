# Reprise · CTF Unlock 1.1

État au 29 octobre 2026. Projet neuf, créé dans `/workspace/CTF-Unlock`. Aucun ancien prototype utilisé. Les sources sont publiées sur [loghanmrsn/CTF-Unlock](https://github.com/loghanmrsn/CTF-Unlock), branche `main`. Le checkout local existant a été conservé et son commit initial `8d7f7d8` publié sur le dépôt GitHub vide après son ajout à la sélection de cet environnement.

## Améliorations 1.1

Réglages atomiques mémorisés (moteur/limites uniquement), conservation des réglages corrompus, copie du mot de passe validé avec effacement conditionnel du presse-papier, bilan JSON sans secret, protection des sources contre un export accidentel, aides selon le résultat, avertissement de masque trop grand pour le plafond, interface 820 × 620, conservation du résultat précédent lors d'une erreur de vérification moteur.

Les nouvelles vérifications couvrent le redémarrage avec les réglages, la panne d'écriture atomique, les types invalides, la conservation d'un fichier de réglages corrompu, l'absence de secrets et de chemins complets dans le rapport, le presse-papier utilisateur préservé, le refus d'écrasement d'une liste et les commandes sur petit écran.

Un workflow Windows a été ajouté ; son résultat sera consigné après exécution réelle. Les formats pris en charge restent ZIP/7z et le moteur reste 7-Zip.

## Ce qui fonctionne

- Interface native PySide6 noire, blanche et argent, inspirée du portfolio its lizhy · Loghan.
- Navigation fichier, méthode, réglages, résultats ; zones défilantes pour les petits écrans, interrupteurs coulissants légers.
- Sélection et dépôt d'un fichier local, analyse par signature, taille et protection détectable.
- ZIP classique/ZipCrypto, ZIP AES-256, 7z AES avec ou sans en-têtes chiffrés, via un vrai moteur 7-Zip externe.
- Recherche par liste UTF-8 ou masque borné ; statistiques réelles, candidats terminés et total exact pour les masques, total inconnu annoncé pour les listes.
- Pause entre deux essais, reprise, annulation et arrêt lors de la fermeture de la fenêtre.
- Bornes de durée, de candidats, de threads, de sortie technique et de mémoire moteur. Linux : `prlimit` et groupe de processus ; Windows : Job Object implémenté, à vérifier sur Windows.
- Vérification d'un succès par décompression et contrôle complet de l'archive via `7-Zip t`, code de sortie 0. Aucune extraction ni modification de l'original.
- États séparés : trouvé, épuisé, interrompu, limite atteinte, endommagé, non pris en charge, non protégé, erreur.
- Erreurs de dépendance et diagnostics lisibles, sans journaliser les candidats ni le mot de passe trouvé. Mot de passe masqué par défaut.

## Validation effectuée sous Linux

Python **3.12.14**, PySide6 **6.8.3**, 7-Zip (z) **25.01 x64** depuis le dépôt officiel `ip7z/7zip`, PyInstaller **6.12.0**. Aucun moteur provenant d'un miroir non officiel.

Commande :

```sh
CTF_UNLOCK_7ZIP=/workspace/ctf-tools/7zz QT_QPA_PLATFORM=offscreen \
  .venv/bin/python -m unittest discover -s tests -v
```

**30 tests passent, aucun test ignoré lors de la validation Linux avec moteur présent**, dont **8 tests de la vraie interface Qt**.

Contrôles :

- Génération et décompte d'un masque ; liste BOM/UTF-8, espaces conservés, lignes invalides refusées.
- Signature indépendante de l'extension, ZIP clair, signature inconnue, en-têtes invalides/tronqués.
- Récupération réelle sur ZipCrypto, ZIP AES, 7z avec ou sans en-têtes chiffrés ; second test direct du mot de passe trouvé ; empreinte SHA-256 de l'original inchangée.
- Épuisement d'une mauvaise liste, recherche par masque, archive non protégée ZIP/7z, données ZIP claires à CRC invalide, 7z tronqué.
- Chemins avec espaces et accents, noms et mots de passe contenant des caractères qui seraient spéciaux dans un shell, traités littéralement.
- Pause, reprise, annulation, durée maximale (pauses incluses), borne de candidats, refus explicite d'une dépendance absente.
- Arrêt d'un vrai sous-processus et vérification de la disparition de son PID sous Linux ; allocation au-delà du plafond mémoire refusée par `prlimit`.
- Qt : navigation, dépôt d'un fichier, interrupteurs, validation des champs, affichage de l'absence du moteur, analyse 7z, recherche réelle déclenchée par le bouton, succès masqué, pause et fermeture pendant une tâche. La boucle Qt continue de traiter un timer pendant le travail.

L'interface a été capturée et inspectée sous Linux. Le packaging PyInstaller et le démarrage du paquet sont vérifiés sur Linux ; ce résultat ne constitue pas une validation Windows.

## Exemples inclus

`examples/demo.zip` (ZIP AES) et `examples/demo.7z` (en-têtes chiffrés) ont été créés réellement avec **CTF42**. La liste `examples/mots-demo.txt` contient ce candidat. Le fichier source `preuve.txt` et le script de recréation Windows sont fournis. Aucun binaire moteur externe n'est redistribué dans le ZIP.

## Windows : non validé

Cette livraison ne contient **pas d'exécutable Windows déjà vérifié**. Le lanceur `Lancer-CTF-Unlock.bat`, les instructions et `CTF-Unlock.spec` sont fournis. Il faut installer Python 3.12 et 7-Zip depuis leurs sources officielles.

À vérifier sur une machine Windows :

1. Lancer le BAT, vérifier le chemin de `7z.exe` et sa version dans Réglages.
2. Exécuter les tests avec `CTF_UNLOCK_7ZIP` et `QT_QPA_PLATFORM=offscreen`. Les tests d’arrêt de processus et de mémoire s’exécutent aussi sur Windows (handle système et Job Object).
3. Valider les Job Objects : application effective de la limite mémoire, annulation du moteur et nettoyage des enfants, y compris lors de la fermeture.
4. Faire un essai interactif : dépôt de fichier, rendu/DPI, listes et masques, pause/reprise, résultats, diagnostics et chemins accentués.
5. Construire avec PyInstaller sur Windows, copier tout `dist/CTF-Unlock`, installer 7-Zip sur la machine cible et vérifier le binaire dans les mêmes scénarios. Ne pas annoncer la réussite tant que cela n'a pas été effectué.

## Limites à conserver dans les annonces

- Pas de garantie de récupération. Pas de PDF/Office/RAR, GPU, John ou Hashcat intégrés.
- Pas de ZIP64/multi-volume ni d'auto-extractibles pris en charge par cette v1.
- Un test 7-Zip complet par candidat : les grandes recherches sont lentes.
- Pause seulement après le candidat courant, pas de suspension native de 7-Zip.
- Une erreur de déchiffrement peut provenir d'un mauvais candidat ou de données chiffrées corrompues. Un épuisement n'est pas une preuve d'intégrité du fichier.
- La mémoire limite le moteur ; l'interface Qt n'est pas comprise. Les plafonds sont appliqués immédiatement après le lancement du processus, pas avant sa toute première instruction.
- Les mots de passe passent dans les arguments de 7-Zip et peuvent être observables par des outils locaux autorisés à lire les commandes de processus.

## Étapes suivantes

Priorité à la validation Windows de cette v1 et à la correction d'éventuels défauts réellement observés. Ensuite seulement : nouveaux adaptateurs de format et vérification spécifique pour PDF et Office, éventuellement moteurs spécialisés, sans élargir les promesses avant leurs tests.

Ne pas modifier DevDock, Portfolio, SecurePass ou le profil GitHub pour poursuivre ce projet.
