"""Inspection par signature ; aucun fichier n'est extrait ni écrit."""
from pathlib import Path
import struct
import zipfile
import zlib
from .models import ArchiveInfo, Outcome

SEVEN = b'7z\xbc\xaf\x27\x1c'
MAX_METADATA = 16 * 1024 * 1024


def inspect(path: Path) -> ArchiveInfo:
    path = Path(path).expanduser().resolve()
    size = path.stat().st_size
    if not path.is_file():
        raise ValueError('Sélectionnez un fichier, pas un dossier.')
    with path.open('rb') as stream:
        signature = stream.read(32)
        if signature.startswith((b'PK\x03\x04', b'PK\x05\x06', b'PK\x06\x06')):
            fmt = 'ZIP'
            try:
                stream.seek(max(0, size - 65557))
                tail = stream.read()
                end = tail.rfind(b'PK\x05\x06')
                if end < 0 or len(tail) - end < 22:
                    raise ValueError('Répertoire ZIP absent ou tronqué.')
                _, disk, cd_disk, _, entries, cd_size, _, _ = struct.unpack('<4s4H2LH', tail[end:end + 22])
                if disk or cd_disk or entries == 65535 or cd_size == 0xffffffff:
                    return ArchiveInfo(path, fmt, size, None, Outcome.UNSUPPORTED, 'ZIP multi-volume et ZIP64 hors périmètre de cette v1.')
                if entries > 10000 or cd_size > MAX_METADATA:
                    return ArchiveInfo(path, fmt, size, None, Outcome.UNSUPPORTED, 'Métadonnées ZIP au-delà des limites v1 (10 000 entrées / 16 Mio).')
                with zipfile.ZipFile(path) as archive:
                    items = archive.infolist()
                    protected = any(item.flag_bits & 1 for item in items if not item.is_dir())
                return ArchiveInfo(path, fmt, size, protected)
            except (zipfile.BadZipFile, ValueError, struct.error) as exc:
                return ArchiveInfo(path, fmt, size, None, Outcome.DAMAGED, str(exc))
        if signature.startswith(SEVEN):
            fmt = '7z'
            if len(signature) < 32 or zlib.crc32(signature[12:32]) != struct.unpack('<I', signature[8:12])[0]:
                return ArchiveInfo(path, fmt, size, None, Outcome.DAMAGED, 'En-tête 7z tronqué ou CRC invalide.')
            offset, length, crc = struct.unpack('<QQI', signature[12:32])
            if 32 + offset + length > size:
                return ArchiveInfo(path, fmt, size, None, Outcome.DAMAGED, 'Archive 7z tronquée.')
            if length > MAX_METADATA:
                return ArchiveInfo(path, fmt, size, None, Outcome.UNSUPPORTED, 'En-tête 7z supérieur à 16 Mio.')
            stream.seek(32 + offset)
            if zlib.crc32(stream.read(length)) != crc:
                return ArchiveInfo(path, fmt, size, None, Outcome.DAMAGED, 'CRC de l’en-tête suivant 7z invalide.')
            return ArchiveInfo(path, fmt, size, None, detail='Protection à confirmer avec 7-Zip.')
    return ArchiveInfo(path, 'Inconnu', size, None, Outcome.UNSUPPORTED, 'Signature non prise en charge. V1 : ZIP et 7z non auto-extractibles, un seul volume.')
