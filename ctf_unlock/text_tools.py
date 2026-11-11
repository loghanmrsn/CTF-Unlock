"""Conversions déterministes et bornées pour les challenges de texte."""
import base64
import binascii
from dataclasses import dataclass
import re
from urllib.parse import quote_from_bytes, unquote_to_bytes

OPERATIONS = ('César', 'César · 26 décalages', 'ROT13', 'Texte → hexadécimal',
    'Hexadécimal → octets', 'Texte → Base64', 'Base64 → octets',
    'Texte → binaire', 'Binaire → octets', 'Texte → URL', 'URL → octets', 'XOR · clé hexadécimale')
MAX_INPUT = 65536


@dataclass(frozen=True)
class Output:
    text: str | None
    hex: str = ''


def output(raw):
    try:
        return Output(raw.decode('utf-8'), raw.hex())
    except UnicodeDecodeError:
        return Output(None, raw.hex())


def caesar(value, shift):
    result = []
    for char in value:
        base = ord('A') if 'A' <= char <= 'Z' else ord('a') if 'a' <= char <= 'z' else None
        result.append(chr(base + (ord(char) - base + shift) % 26) if base is not None else char)
    return ''.join(result)


def transform(operation, value, shift=13, key=''):
    raw = value.encode('utf-8')
    if len(raw) > MAX_INPUT:
        raise ValueError('Entrée limitée à 64 Kio UTF-8.')
    if operation not in OPERATIONS:
        raise ValueError('Conversion non prise en charge.')
    if operation == 'César':
        return Output(caesar(value, shift))
    if operation == 'César · 26 décalages':
        if len(raw) > 4096:
            raise ValueError('Les 26 variantes sont limitées à 4 Kio d’entrée.')
        return Output('\n'.join(f'{i:02d} : {caesar(value, i)}' for i in range(26)))
    if operation == 'ROT13':
        return Output(caesar(value, 13))
    if operation == 'Texte → hexadécimal':
        return Output(raw.hex())
    if operation == 'Hexadécimal → octets':
        try:
            return output(bytes.fromhex(value))
        except ValueError as exc:
            raise ValueError('Hexadécimal invalide : paires 00 à ff attendues.') from exc
    if operation == 'Texte → Base64':
        return Output(base64.b64encode(raw).decode('ascii'))
    if operation == 'Base64 → octets':
        try:
            return output(base64.b64decode(''.join(value.split()).encode('ascii'), validate=True))
        except (ValueError, UnicodeError, binascii.Error) as exc:
            raise ValueError('Base64 standard invalide (avec padding = si nécessaire).') from exc
    if operation == 'Texte → binaire':
        return Output(' '.join(f'{item:08b}' for item in raw))
    if operation == 'Binaire → octets':
        bits = ''.join(value.split())
        if set(bits) - set('01') or len(bits) % 8:
            raise ValueError('Binaire invalide : groupes de 8 bits 0/1 requis.')
        return output(bytes(int(bits[i:i+8], 2) for i in range(0, len(bits), 8)))
    if operation == 'Texte → URL':
        return Output(quote_from_bytes(raw, safe=''))
    if operation == 'URL → octets':
        if re.search(r'%(?![0-9a-fA-F]{2})', value):
            raise ValueError('Séquence URL % invalide.')
        return output(unquote_to_bytes(value))
    try:
        secret = bytes.fromhex(key)
    except ValueError as exc:
        raise ValueError('Clé XOR hexadécimale invalide.') from exc
    if not 1 <= len(secret) <= 256:
        raise ValueError('Clé XOR requise, entre 1 et 256 octets hexadécimaux.')
    try:
        raw = bytes.fromhex(value)
    except ValueError as exc:
        raise ValueError('L’entrée XOR doit contenir des octets hexadécimaux.') from exc
    return output(bytes(item ^ secret[i % len(secret)] for i, item in enumerate(raw)))
