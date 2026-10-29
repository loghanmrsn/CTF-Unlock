"""Réglages et rapports locaux : écritures atomiques, aucun mot de passe persisté."""
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile

from .models import Limits, Result


def preferences_path() -> Path:
    if sys.platform == 'win32':
        root = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
        return root / 'CTF-Unlock' / 'preferences.json'
    return Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'ctf-unlock' / 'preferences.json'


def write_json(path: Path, data: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, prefix='.ctf-', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@dataclass(frozen=True)
class Preferences:
    engine: str = ''
    limits: Limits = field(default_factory=Limits)
    john: str = ''
    zip2john: str = ''

    def validate(self):
        for path in (self.engine, self.john, self.zip2john):
            if not isinstance(path, str) or len(path) > 4096 or '\x00' in path:
                raise ValueError('Chemin du moteur invalide dans les réglages.')
        for name, value in asdict(self.limits).items():
            if name in ('candidates', 'threads', 'memory_mb'):
                valid = type(value) is int
            else:
                valid = type(value) in (int, float)
            if not valid:
                raise ValueError('Type invalide dans les limites enregistrées.')
        self.limits.validate()


class PreferenceStore:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path is not None else preferences_path()
        self.read_only = False

    def load(self) -> Preferences:
        try:
            with self.path.open('rb') as stream:
                raw = stream.read(16385)
        except FileNotFoundError:
            self.read_only = False
            return Preferences()
        except OSError:
            self.read_only = True
            raise
        try:
            if len(raw) > 16384:
                raise ValueError('Fichier de réglages trop volumineux.')
            data = json.loads(raw.decode('utf-8'))
            if not isinstance(data, dict) or type(data.get('version')) is not int or data['version'] not in (1, 2):
                raise ValueError('Version des réglages non reconnue.')
            expected = {'version', 'engine', 'limits'} | ({'john', 'zip2john'} if data['version'] == 2 else set())
            if set(data) != expected or not isinstance(data['limits'], dict):
                raise ValueError('Structure des réglages invalide.')
            preferences = Preferences(data['engine'], Limits(**data['limits']), data.get('john', ''), data.get('zip2john', ''))
            preferences.validate()
        except (ValueError, TypeError) as exc:
            self.read_only = True
            raise ValueError(f'Réglages illisibles : {self.path}. Original conservé, sauvegarde automatique désactivée. {exc}') from exc
        self.read_only = False
        return preferences

    def save(self, preferences: Preferences):
        if self.read_only:
            raise ValueError('Les réglages existants sont protégés après une erreur de lecture. Corrigez ou déplacez le fichier puis relancez.')
        preferences.validate()
        write_json(self.path, {'version': 2, 'engine': preferences.engine, 'john': preferences.john, 'zip2john': preferences.zip2john, 'limits': asdict(preferences.limits)})


def report_data(result: Result, source_name: str, engine_version: str) -> dict:
    # Liste positive : ne pas sérialiser le résultat complet ni les diagnostics bruts.
    return {
        'version': 1,
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'file_name': Path(source_name).name,
        'engine': engine_version,
        'outcome': str(result.outcome),
        'attempted': result.attempted,
        'elapsed_seconds': round(result.elapsed, 3),
        'average_attempts_per_second': round(result.attempted / max(result.elapsed, .001), 3) if result.attempted is not None else None,
        'password_included': False,
    }
