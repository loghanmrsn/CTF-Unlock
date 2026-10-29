"""Orchestration indépendante de Qt ; moteur remplaçable pour d'autres formats."""
from dataclasses import replace
from pathlib import Path
from threading import Event
import time

from .archives import inspect
from .engine import SevenZip, classify
from .models import Limits, Outcome, Progress, Result
from .processes import Aborted


class Control:
    def __init__(self):
        self.cancelled = Event()
        self.paused = Event()

    def stop(self):
        self.cancelled.set()

    def pause(self, value: bool):
        self.paused.set() if value else self.paused.clear()


def recover(path: Path, source, engine: SevenZip, limits: Limits, control: Control,
            progress=lambda p: None) -> Result:
    start = time.monotonic()
    attempts = 0
    total = None
    def elapsed():
        return time.monotonic() - start
    def abort():
        if control.cancelled.is_set():
            return 'Arrêt demandé.'
        if elapsed() >= limits.seconds:
            return 'Durée maximale atteinte (pauses incluses).'
        return None
    def result(outcome, detail, password=None, technical=''):
        return Result(outcome, detail, attempts, elapsed(), password, technical)
    def notify(phase):
        progress(Progress(attempts, total, elapsed(), phase))
    try:
        limits.validate()
        notify('Analyse du fichier…')
        info = inspect(path)
        if info.outcome:
            return result(info.outcome, info.detail)
        original = info.path.stat()
        fingerprint = (original.st_size, original.st_mtime_ns)
        notify('Moteur vérifié : ' + engine.version(limits, abort))
        info = engine.protection(info, limits, abort)
        if info.outcome:
            return result(info.outcome, info.detail)
        if info.protected is not True:
            # Un succès avec un candidat aléatoire confirme seulement l'absence de protection.
            from uuid import uuid4
            test = engine.test(info, uuid4().hex, limits, abort)
            if test.code == 0:
                return result(Outcome.UNPROTECTED, 'Archive testée intégralement : aucun mot de passe nécessaire.')
            status = classify(test)
            if info.protected is False or status != Outcome.EXHAUSTED:
                return result(status if status != Outcome.FOUND else Outcome.ERROR, 'Le test d’intégrité a échoué.', technical=test.output)
        total = source.total
        for candidate in source.generate():
            if abort():
                raise Aborted(abort())
            while control.paused.is_set():
                notify('En pause · reprise entre deux essais')
                if abort():
                    raise Aborted(abort())
                time.sleep(.05)
            if attempts >= limits.candidates:
                return result(Outcome.LIMITED, 'Nombre maximal de candidats atteint ; recherche incomplète.')
            current = info.path.stat()
            if (current.st_size, current.st_mtime_ns) != fingerprint:
                return result(Outcome.ERROR, 'Le fichier source a changé pendant la tâche ; recherche arrêtée.')
            notify('Vérification complète du candidat…')
            tested = engine.test(info, candidate, limits, abort)
            attempts += 1
            status = classify(tested)
            notify('Recherche en cours')
            if status == Outcome.FOUND:
                return result(Outcome.FOUND, '7-Zip a testé l’archive entière avec succès (code 0, décompression et CRC). Aucun fichier extrait.', candidate)
            if status != Outcome.EXHAUSTED:
                return result(status, 'Le moteur ne peut pas poursuivre. Consulter les détails techniques.', technical=tested.output)
        if abort():
            raise Aborted(abort())
        return result(Outcome.EXHAUSTED, 'Aucun candidat n’a validé l’archive. Une corruption des données chiffrées peut être indiscernable d’un mauvais mot de passe.')
    except Aborted as exc:
        return result(Outcome.INTERRUPTED if control.cancelled.is_set() else Outcome.LIMITED, str(exc))
    except (OSError, ValueError, RuntimeError) as exc:
        return result(Outcome.ERROR, str(exc))
