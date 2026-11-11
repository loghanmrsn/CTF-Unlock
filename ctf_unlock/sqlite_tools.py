"""Inspection SQLite locale sur copie temporaire, sans connexion serveur."""
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path
import csv
import json
import math
import sqlite3
import tempfile
import time

from .processes import Aborted

MAX_DATABASE = 256 * 1024 * 1024
MAX_WAL = 64 * 1024 * 1024
MAX_RESULT_BYTES = 2 * 1024 * 1024
MAX_CELL_BYTES = 1024 * 1024
MAX_OBJECTS, MAX_ROWS, MAX_CELLS = 128, 500, 10000


def check(abort):
    reason = abort()
    if reason:
        raise Aborted(reason)


def identity(path):
    try:
        s = path.stat()
        return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns
    except FileNotFoundError:
        return None


def fingerprint(path):
    return identity(path), identity(Path(str(path) + '-wal'))


def identifier(value):
    if not value or '\0' in value:
        raise ValueError('Identifiant SQL invalide.')
    return '"' + value.replace('"', '""') + '"'


def authorize(action, first, second, database_name, trigger):
    if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_RECURSIVE):
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_FUNCTION and (second or '').lower() not in {
        'load_extension', 'readfile', 'writefile', 'eval', 'fts3_tokenizer',
    }:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_PRAGMA and (first or '').lower() in {
        'table_info', 'table_xinfo', 'index_list', 'index_info', 'foreign_key_list',
    }:
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


@contextmanager
def database(path, abort=lambda: None, expected=None):
    check(abort)
    source = Path(path).resolve(strict=True)
    if not source.is_file():
        raise ValueError('Sélectionnez un fichier SQLite.')
    with source.open('rb') as stream:
        if stream.read(16) != b'SQLite format 3\0':
            raise ValueError('Signature SQLite absente. Bases chiffrées, dumps SQL et autres formats non pris en charge.')
    journal = Path(str(source) + '-journal')
    if journal.exists() and journal.stat().st_size:
        raise ValueError('Journal de transaction présent : fermez le logiciel propriétaire et fournissez une copie cohérente.')
    before = fingerprint(source)
    if expected is not None and expected != before:
        raise ValueError('La base a changé depuis son analyse. Analysez-la de nouveau.')
    connection = None
    interrupted = None
    with tempfile.TemporaryDirectory(prefix='ctf-unlock-sql-') as folder:
        target = Path(folder) / 'snapshot.sqlite'
        for original, destination, maximum in [
            (source, target, MAX_DATABASE),
            (Path(str(source) + '-wal'), Path(str(target) + '-wal'), MAX_WAL),
        ]:
            if not original.exists():
                continue
            if original.stat().st_size > maximum:
                raise ValueError('Base ou journal WAL trop volumineux (256 Mio / 64 Mio maximum).')
            copied = 0
            with original.open('rb') as incoming, destination.open('xb') as outgoing:
                while chunk := incoming.read(1024 * 1024):
                    check(abort)
                    copied += len(chunk)
                    if copied > maximum:
                        raise ValueError('Le fichier a grandi pendant sa copie.')
                    outgoing.write(chunk)
        if fingerprint(source) != before:
            raise ValueError('Base modifiée pendant la copie : fermez son application puis réessayez.')
        try:
            connection = sqlite3.connect(target.as_uri() + '?mode=ro', uri=True, timeout=.5, isolation_level=None)
            for category, maximum in [
                (sqlite3.SQLITE_LIMIT_LENGTH, MAX_CELL_BYTES),
                (sqlite3.SQLITE_LIMIT_SQL_LENGTH, 16384),
                (sqlite3.SQLITE_LIMIT_COLUMN, 128),
                (sqlite3.SQLITE_LIMIT_EXPR_DEPTH, 100),
                (sqlite3.SQLITE_LIMIT_COMPOUND_SELECT, 20),
                (sqlite3.SQLITE_LIMIT_VDBE_OP, 250000),
            ]:
                connection.setlimit(category, maximum)
            connection.execute('PRAGMA trusted_schema=OFF')
            connection.execute('PRAGMA query_only=ON')
            connection.execute('PRAGMA cache_size=-2048')
            connection.execute('PRAGMA temp_store=FILE')
            # Les TEXT mal encodés sont conservés comme octets, jamais remplacés.
            def decode(raw):
                try:
                    return raw.decode('utf-8')
                except UnicodeDecodeError:
                    return raw
            connection.text_factory = decode
            deadline = time.monotonic() + 5
            def progress():
                nonlocal interrupted
                interrupted = abort() or ('Limite SQL de 5 secondes atteinte.' if time.monotonic() >= deadline else None)
                return int(bool(interrupted))
            connection.set_progress_handler(progress, 1000)
            connection.set_authorizer(authorize)
            yield connection, source, before
        except sqlite3.Error as exc:
            if interrupted:
                raise Aborted(interrupted) from exc
            raise ValueError('Lecture SQLite impossible : ' + str(exc)) from exc
        except MemoryError as exc:
            raise ValueError('Requête trop complexe pour les limites SQLite.') from exc
        finally:
            if connection:
                connection.close()


@dataclass(frozen=True)
class Catalog:
    source: Path
    fingerprint: tuple
    objects: tuple
    limited: bool
    wal: bool


@dataclass(frozen=True)
class Page:
    source: Path
    columns: tuple
    rows: tuple
    offset: int
    more: bool


def inspect_database(path, abort=lambda: None):
    with database(path, abort) as (con, source, stamp):
        objects = con.execute("SELECT name, type, substr(sql,1,16384) FROM sqlite_schema WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' ORDER BY name LIMIT ?", (MAX_OBJECTS + 1,)).fetchall()
        return Catalog(source, stamp, tuple(objects[:MAX_OBJECTS]), len(objects) > MAX_OBJECTS, stamp[1] is not None)


def require_object(catalog, name):
    if name not in [row[0] for row in catalog.objects]:
        raise ValueError('Choisissez un objet de la base analysée.')
    return identifier(name)


def object_schema(catalog, name, abort=lambda: None):
    quoted = require_object(catalog, name)
    with database(catalog.source, abort, catalog.fingerprint) as (con, _, __):
        columns = con.execute(f'PRAGMA table_xinfo({quoted})').fetchall()
        indexes = con.execute(f'PRAGMA index_list({quoted})').fetchmany(128)
        foreign = con.execute(f'PRAGMA foreign_key_list({quoted})').fetchmany(128)
    definition = next(row[2] for row in catalog.objects if row[0] == name) or ''
    hints = [str(row[1]) for row in columns if any(word in str(row[1]).lower() for word in ('flag', 'secret', 'password', 'token', 'email', 'user', 'key'))]
    return '\n'.join([definition[:16384], '\nColonnes :'] + [f'• {row[1]} · {row[2] or "sans type"} · PK={row[5]} · NOT NULL={row[3]}' for row in columns] + [f'\nIndex (128 max.) : {indexes}', f'Clés étrangères (128 max.) : {foreign}', f'Indices par noms seulement : {", ".join(hints) or "aucun"}. Aucun secret confirmé.'])


def query(catalog, sql, limit=100, offset=0, parameters=(), abort=lambda: None):
    sql = sql.strip().removesuffix(';').strip()
    if not sql or len(sql.encode('utf-8')) > 16000 or not 1 <= limit <= MAX_ROWS or not 0 <= offset <= 10000000:
        raise ValueError('Requête vide/trop longue ou pagination hors limites.')
    # Un seul sous-select. L'authorizer reste la barrière pour toutes les opérations.
    with database(catalog.source, abort, catalog.fingerprint) as (con, source, _):
        with closing(con.execute(f'SELECT * FROM ({sql}) LIMIT ? OFFSET ?', (*parameters, limit + 1, offset))) as cursor:
            columns = tuple(info[0] for info in cursor.description)
            maximum = min(limit, max(1, MAX_CELLS // len(columns)))
            rows, volume, more = [], 0, False
            for row in cursor:
                check(abort)
                size = sum(len(item) if isinstance(item, bytes) else len(str(item).encode('utf-8')) for item in row)
                if len(rows) >= maximum or volume + size > MAX_RESULT_BYTES:
                    more = True
                    break
                rows.append(row)
                volume += size
            if more and not rows:
                raise ValueError('La première ligne dépasse le plafond de résultat de 2 Mio.')
            return Page(source, columns, tuple(rows), offset, more)


def table_page(catalog, name, needle='', limit=100, offset=0, abort=lambda: None):
    quoted = require_object(catalog, name)
    with database(catalog.source, abort, catalog.fingerprint) as (con, _, __):
        columns = con.execute(f'PRAGMA table_xinfo({quoted})').fetchall()
    if len(needle) > 256:
        raise ValueError('Filtre limité à 256 caractères.')
    parameters = ()
    sql = f'SELECT * FROM {quoted}'
    if needle:
        pattern = '%' + needle.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        names = [identifier(row[1]) for row in columns if row[6] != 1]
        sql += ' WHERE ' + ' OR '.join(f'CAST({col} AS TEXT) LIKE ? ESCAPE char(92)' for col in names)
        parameters = (pattern,) * len(names)
    return query(catalog, sql, limit, offset, parameters, abort)


def json_value(value):
    if isinstance(value, bytes):
        return {'$bytes_hex': value.hex()}
    if isinstance(value, float) and not math.isfinite(value):
        return {'$float': repr(value)}
    return value


def csv_value(value):
    if value is None:
        return ''
    if isinstance(value, bytes):
        return 'hex:' + value.hex()
    if isinstance(value, str) and value.lstrip(' \t\r\n\ufeff').startswith(('=', '+', '-', '@')):
        return "'" + value
    return value


def export_page(page, path, kind, selected=(), abort=lambda: None):
    target = Path(path).resolve()
    if target == page.source.resolve() or target.exists():
        raise ValueError('Choisissez un nouveau fichier : aucun fichier existant ne sera écrasé.')
    if kind not in ('json', 'csv'):
        raise ValueError('Export JSON ou CSV uniquement.')
    indexes = sorted(set(selected)) if selected else range(len(page.rows))
    if any(index < 0 or index >= len(page.rows) for index in indexes):
        raise ValueError('Sélection de lignes invalide.')
    check(abort)
    created = False
    try:
        with target.open('x', encoding='utf-8', newline='') as stream:
            created = True
            if kind == 'json':
                rows = []
                for index in indexes:
                    check(abort)
                    rows.append([json_value(item) for item in page.rows[index]])
                json.dump({'columns': page.columns, 'rows': rows}, stream, ensure_ascii=False, allow_nan=False, indent=2)
            else:
                writer = csv.writer(stream)
                writer.writerow([csv_value(item) for item in page.columns])
                for index in indexes:
                    check(abort)
                    writer.writerow([csv_value(item) for item in page.rows[index]])
            check(abort)
    except BaseException:
        if created:
            target.unlink(missing_ok=True)
        raise
    return str(target)
