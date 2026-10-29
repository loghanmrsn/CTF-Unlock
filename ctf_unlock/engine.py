from dataclasses import dataclass, replace
import os
from pathlib import Path
import re
import shutil
from uuid import uuid4

from .models import ArchiveInfo, Limits, Outcome
from .processes import CommandResult, run


def find_7zip() -> str:
    for name in ('7zz', '7z', '7za'):
        location = shutil.which(name)
        if location:
            return location
    for variable in ('ProgramFiles', 'ProgramFiles(x86)'):
        if os.environ.get(variable):
            path = Path(os.environ[variable]) / '7-Zip' / '7z.exe'
            if path.is_file():
                return str(path)
    return ''


@dataclass(frozen=True)
class SevenZip:
    executable: str

    def _run(self, args, limits: Limits, abort=lambda: None):
        executable = Path(self.executable).expanduser()
        if not self.executable or not executable.is_file():
            raise FileNotFoundError('7-Zip absent. Installez-le depuis https://www.7-zip.org/ puis sélectionnez 7z.exe (ou 7zz).')
        return run([str(executable.resolve()), *args], timeout=limits.attempt_seconds, memory_mb=limits.memory_mb, abort=abort)

    def version(self, limits=Limits(), abort=lambda: None):
        result = self._run(['i', '-sccUTF-8'], limits, abort)
        version = re.search(r'7-Zip[^\r\n]*', result.output)
        if result.code or not version:
            raise ValueError('Cet exécutable ne répond pas comme un moteur 7-Zip compatible.')
        return version.group(0)

    def protection(self, info: ArchiveInfo, limits: Limits, abort=lambda: None) -> ArchiveInfo:
        if info.protected is not None or info.outcome:
            return info
        result = self._run(['l', '-slt', '-ba', '-sccUTF-8', '-p' + uuid4().hex, '--', str(info.path)], limits, abort)
        output = result.output.lower()
        if 'wrong password' in output or 'encrypted archive' in output:
            return replace(info, protected=True, detail='En-tête chiffré : liste du contenu indisponible sans mot de passe.')
        if result.code == 0:
            encrypted = re.findall(r'^Encrypted = ([+-])\s*$', result.output, re.MULTILINE)
            return replace(info, protected=('+' in encrypted) if encrypted else None,
                           detail='' if encrypted else 'État de protection indéterminé ; un test complet sera effectué.')
        status = classify(result)
        return replace(info, outcome=status if status != Outcome.FOUND else Outcome.ERROR, detail=result.output[:1000])

    def test(self, info: ArchiveInfo, password: str, limits: Limits, abort=lambda: None) -> CommandResult:
        if not password or '\x00' in password:
            raise ValueError('Un candidat ne peut pas être vide ou contenir un octet nul.')
        # « t » décompresse et vérifie les CRC, sans extraire sur disque. Jamais « x »/« e ».
        return self._run(['t', '-y', '-sccUTF-8', '-bso0', '-bsp0', '-bse1', f'-mmt={limits.threads}',
                          '-p' + password, '--', str(info.path)], limits, abort)


def classify(result: CommandResult) -> Outcome:
    if result.code == 0:
        return Outcome.FOUND
    text = result.output.lower()
    if 'unsupported' in text or 'not implemented' in text:
        return Outcome.UNSUPPORTED
    if 'wrong password' in text or 'data error in encrypted file' in text:
        return Outcome.EXHAUSTED  # Candidat rejeté ; pas encore l'issue de toute la recherche.
    if any(term in text for term in ('unexpected end', 'headers error', 'crc failed', 'is not archive', 'data error')):
        return Outcome.DAMAGED
    return Outcome.ERROR
