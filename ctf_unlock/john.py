"""Adaptateur CPU John Jumbo pour ZIP ; succès toujours revérifié par 7-Zip."""
from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import tempfile
import time

from .archives import inspect
from .engine import SevenZip, classify
from .models import Limits, Outcome, Progress, Result
from .processes import Aborted, run
from .tasks import Control


def find_john() -> tuple[str, str]:
    executable = shutil.which('john') or ''
    helper = shutil.which('zip2john') or ''
    if executable and not helper:
        adjacent = Path(executable).with_name('zip2john.exe' if Path(executable).suffix.lower() == '.exe' else 'zip2john')
        if adjacent.is_file():
            helper = str(adjacent)
    return executable, helper


def zip_hash(output: str) -> tuple[str, str]:
    for start, end, format_name in [('$pkzip$', '$/pkzip$', 'PKZIP'), ('$pkzip2$', '$/pkzip2$', 'PKZIP'), ('$zip2$', '$/zip2$', 'ZIP')]:
        offset = output.find(start)
        stop = output.find(end, offset)
        if offset >= 0 and stop >= 0:
            ciphertext = output[offset:stop + len(end)]
            if '\n' in ciphertext or '\r' in ciphertext or 'ZFILE' in ciphertext:
                raise ValueError('Cette empreinte ZIP nécessite une référence externe non prise en charge.')
            return ciphertext, format_name
    raise ValueError('zip2john n’a produit aucune empreinte ZIP reconnue (PKZIP ou ZIP AES).')


@dataclass(frozen=True)
class JohnJumbo:
    executable: str
    extractor: str
    verifier: SevenZip

    def command(self, arguments, limits, abort=lambda: None, timeout=None, heartbeat=None):
        path = Path(self.executable).expanduser()
        if not self.executable or not path.is_file():
            raise FileNotFoundError('John Jumbo absent. Sélectionnez john.exe (ou john) depuis une distribution officielle Openwall.')
        return run([str(path.expanduser().absolute()), *arguments], timeout=timeout or limits.attempt_seconds,
                   memory_mb=limits.memory_mb, abort=abort,
                   env={'OMP_NUM_THREADS': str(limits.threads), 'OMP_DYNAMIC': 'FALSE'}, heartbeat=heartbeat)

    def version(self, limits=Limits(), abort=lambda: None):
        result = self.command(['--list=build-info'], limits, abort)
        version = re.search(r'^Version:\s*(.+)$', result.output, re.MULTILINE)
        if result.code or not version or 'jumbo' not in version.group(1).lower():
            raise ValueError('John Jumbo requis ; le John standard ne fournit pas les formats ZIP de cette intégration.')
        if not self.extractor or not Path(self.extractor).expanduser().is_file():
            raise FileNotFoundError('zip2john absent. Sélectionnez zip2john.exe (ou zip2john) du même paquet officiel Jumbo.')
        return 'John ' + version.group(1).strip()

    def recover(self, path: Path, source, limits: Limits, control: Control, progress=lambda p: None):
        started = time.monotonic()
        def elapsed():
            return time.monotonic() - started
        def abort():
            if control.cancelled.is_set():
                return 'Arrêt demandé.'
            if elapsed() >= limits.seconds:
                return 'Durée maximale atteinte.'
            return None
        def notify(phase):
            progress(Progress(None, None, elapsed(), phase))
        def result(state, detail, password=None):
            return Result(state, detail, None, elapsed(), password)
        def unchanged(info, fingerprint):
            current = info.path.stat()
            if (current.st_size, current.st_mtime_ns) != fingerprint:
                raise ValueError('Le fichier source a changé pendant la tâche.')
        try:
            limits.validate()
            info = inspect(path)
            if info.outcome:
                return result(info.outcome, info.detail)
            if info.format != 'ZIP':
                return result(Outcome.UNSUPPORTED, 'John intégré ici : ZIP uniquement. Pour 7z, choisissez le moteur 7-Zip.')
            before = info.path.stat()
            fingerprint = (before.st_size, before.st_mtime_ns)
            version = self.version(limits, abort)
            version += ' / ' + self.verifier.version(limits, abort)
            notify('Moteur vérifié : ' + version)
            if not info.protected:
                tested = self.verifier.test(info, 'ctf-unlock-unprotected-probe', limits, abort)
                return result(Outcome.UNPROTECTED if tested.code == 0 else classify(tested), 'Test d’intégrité de l’archive non protégée.')
            notify('Extraction locale de l’empreinte ZIP…')
            extracted = run([str(Path(self.extractor).expanduser().absolute()), str(info.path)], timeout=limits.attempt_seconds,
                            memory_mb=limits.memory_mb, abort=abort)
            if extracted.code:
                return result(Outcome.ERROR, 'zip2john a échoué. Vérifiez l’archive et la compatibilité de son paquet Jumbo.')
            try:
                ciphertext, format_name = zip_hash(extracted.output)
            except ValueError as exc:
                return result(Outcome.UNSUPPORTED, str(exc))
            unchanged(info, fingerprint)
            # John écrit un pot et un état de session ; ils restent confinés et sont
            # supprimés à la sortie normale de cette tâche, annulation comprise.
            with tempfile.TemporaryDirectory(prefix='ctf-unlock-john-') as temporary:
                scratch = Path(temporary)
                hashes, words, pot = scratch / 'hash.txt', scratch / 'words.txt', scratch / 'result.pot'
                hashes.write_text('ctf-unlock:' + ciphertext + '\n', encoding='utf-8')
                count, truncated, size = 0, False, 0
                notify('Préparation de la liste locale temporaire…')
                with words.open('wb') as stream:
                    for candidate in source.generate():
                        if abort():
                            raise Aborted(abort())
                        if count >= limits.candidates:
                            truncated = True
                            break
                        encoded = (candidate + '\n').encode('utf-8')
                        size += len(encoded)
                        if size > 64 * 1024 * 1024:
                            return result(Outcome.LIMITED, 'Liste temporaire au-delà de 64 Mio ; recherche non exécutée.')
                        stream.write(encoded)
                        count += 1
                        if count % 1000 == 0:
                            notify(f'Préparation : {count:,} candidats (pas encore testés)')
                if not count:
                    return result(Outcome.EXHAUSTED, 'La source ne contient aucun candidat non vide.')
                if abort():
                    raise Aborted(abort())
                unchanged(info, fingerprint)
                notify('John calcule · compteurs et vitesse non disponibles dans cette intégration')
                executed = self.command([
                    f'--format={format_name}', '--encoding=UTF-8', f'--wordlist={words}',
                    f'--pot={pot}', f'--session={scratch / "session"}', '--log-stderr', '--mem-file-size=0',
                    str(hashes),
                ], limits, abort, timeout=max(.01, limits.seconds - elapsed()),
                    heartbeat=lambda: notify('John calcule · compteurs et vitesse non disponibles dans cette intégration'))
                if executed.code:
                    return result(Outcome.ERROR, f'John a échoué (code {executed.code}). Vérifiez le format CPU, les limites et les dépendances du paquet Jumbo. Sa sortie brute n’est pas affichée car elle peut contenir des secrets.')
                shown = self.command([f'--format={format_name}', f'--pot={pot}', '--encoding=UTF-8', '--show', str(hashes)], limits, abort)
                if shown.code:
                    return result(Outcome.ERROR, 'John n’a pas pu relire son résultat temporaire.')
                summary = re.search(r'(\d+) password hash(?:es)? cracked, (\d+) left', shown.output)
                if not summary or sum(map(int, summary.groups())) != 1:
                    return result(Outcome.ERROR, 'John n’a pas confirmé le chargement d’une empreinte unique. Aucun épuisement n’est annoncé.')
                for line in shown.output.splitlines():
                    if line.startswith('ctf-unlock:'):
                        candidate = line.removeprefix('ctf-unlock:')
                        unchanged(info, fingerprint)
                        notify('Candidat John obtenu · vérification intégrale par 7-Zip…')
                        tested = self.verifier.test(info, candidate, limits, abort)
                        unchanged(info, fingerprint)
                        if tested.code == 0:
                            return result(Outcome.FOUND, 'Candidat trouvé par John et validé sur l’archive entière par 7-Zip. Les fichiers temporaires sont supprimés.', candidate)
                        return result(Outcome.ERROR, 'Le candidat John n’a pas validé l’archive entière. Aucun mot de passe n’est annoncé.')
                unchanged(info, fingerprint)
                return result(Outcome.LIMITED if truncated else Outcome.EXHAUSTED,
                              'Plafond de candidats atteint ; source non épuisée.' if truncated else 'John a épuisé les candidats fournis sans résultat vérifié. Une corruption chiffrée peut rester indiscernable d’un mauvais mot de passe.')
        except Aborted as exc:
            return result(Outcome.INTERRUPTED if control.cancelled.is_set() else Outcome.LIMITED, str(exc))
        except (OSError, ValueError, RuntimeError) as exc:
            return result(Outcome.ERROR, str(exc))
