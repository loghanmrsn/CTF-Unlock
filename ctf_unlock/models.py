from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class Outcome(StrEnum):
    FOUND = 'Mot de passe trouvé et vérifié'
    EXHAUSTED = 'Liste ou masque épuisé'
    INTERRUPTED = 'Tâche interrompue'
    LIMITED = 'Limite atteinte'
    DAMAGED = 'Fichier endommagé'
    UNSUPPORTED = 'Format ou méthode non pris en charge'
    UNPROTECTED = 'Archive non protégée'
    ERROR = 'Erreur'


@dataclass(frozen=True)
class ArchiveInfo:
    path: Path
    format: str
    size: int
    protected: bool | None
    outcome: Outcome | None = None
    detail: str = ''


@dataclass(frozen=True)
class Limits:
    seconds: float = 60
    candidates: int = 10000
    threads: int = 1
    memory_mb: int = 512
    attempt_seconds: float = 10

    def validate(self):
        if not 0 < self.seconds <= 3600 or not 1 <= self.candidates <= 1000000:
            raise ValueError('Durée : 1 h maximum ; candidats : 1 à 1 000 000.')
        if not 1 <= self.threads <= 4 or not 128 <= self.memory_mb <= 4096:
            raise ValueError('Threads : 1 à 4 ; mémoire moteur : 128 à 4096 Mio.')
        if not 0 < self.attempt_seconds <= self.seconds:
            raise ValueError('Le délai par essai doit être positif et inférieur à la durée totale.')


@dataclass(frozen=True)
class Progress:
    attempted: int
    total: int | None
    elapsed: float
    phase: str

    @property
    def speed(self):
        return self.attempted / self.elapsed if self.elapsed else 0


@dataclass(frozen=True)
class Result:
    outcome: Outcome
    detail: str
    attempted: int = 0
    elapsed: float = 0
    password: str | None = None
    technical: str = ''
