import csv
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from ctf_unlock import sqlite_tools as sql
from ctf_unlock.processes import Aborted


class SQLiteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='CTF SQLite été ')
        self.root = Path(self.temp.name)
        self.path = self.root / ('données #.bin' if os.name == 'nt' else 'données #?.bin')
        self.con = sqlite3.connect(self.path)
        self.con.executescript('''CREATE TABLE users(id INTEGER PRIMARY KEY, name TEXT, flag BLOB);
            CREATE INDEX user_names ON users(name);
            CREATE VIEW flags AS SELECT id, flag FROM users;
            CREATE TABLE child(parent INTEGER REFERENCES users(id));
            CREATE TABLE "quo""te"("col""x" TEXT);''')
        self.con.executemany('INSERT INTO users VALUES (?,?,?)', [(1, 'alice_100%', b'flag{local}'), (2, '=FORMULA()', None), (3, 'été', b'\x00\xff')])
        self.con.execute('INSERT INTO "quo""te" VALUES (?)', ('quoted',))
        self.con.commit(); self.con.close()
        self.original = self.path.read_bytes()
        self.catalog = sql.inspect_database(self.path)

    def tearDown(self):
        self.assertEqual(self.path.read_bytes(), self.original)
        self.temp.cleanup()

    def test_signature_catalog_schema_and_quoted_identifiers(self):
        self.assertEqual([row[0] for row in self.catalog.objects], ['child', 'flags', 'quo"te', 'users'])
        schema = sql.object_schema(self.catalog, 'users')
        self.assertIn('user_names', schema)
        self.assertIn('flag', schema)
        self.assertIn('REFERENCES', sql.object_schema(self.catalog, 'child'))
        self.assertEqual(sql.table_page(self.catalog, 'quo"te').rows, (('quoted',),))
        with self.assertRaises(ValueError):
            sql.table_page(self.catalog, 'users; DROP TABLE users')

    def test_literal_filter_and_injection_strings(self):
        for needle in ['%', '_', 'alice_100%']:
            self.assertEqual(len(sql.table_page(self.catalog, 'users', needle).rows), 1)
        self.assertFalse(sql.table_page(self.catalog, 'users', "' OR 1=1 --").rows)
        self.assertEqual(sql.table_page(self.catalog, 'users', 'été').rows[0][0], 3)

    def test_select_with_and_pagination(self):
        first = sql.query(self.catalog, 'SELECT id FROM users ORDER BY id;', 2)
        self.assertEqual(first.rows, ((1,), (2,)))
        self.assertTrue(first.more)
        last = sql.query(self.catalog, 'SELECT id FROM users ORDER BY id', 2, 2)
        self.assertEqual(last.rows, ((3,),)); self.assertFalse(last.more)
        self.assertEqual(sql.query(self.catalog, 'WITH f AS (SELECT flag FROM users WHERE id=1) SELECT * FROM f').rows, ((b'flag{local}',),))

    def test_writes_attachments_extensions_and_multi_statements_denied(self):
        for statement in ["DELETE FROM users", "UPDATE users SET name='oops'", 'DROP TABLE users', "ATTACH DATABASE ':memory:' AS other", 'PRAGMA query_only=OFF', "SELECT load_extension('absent')", "SELECT 1; DELETE FROM users", 'SELECT * FROM pragma_query_only']:
            with self.subTest(statement=statement), self.assertRaises(ValueError):
                sql.query(self.catalog, statement)
        self.assertEqual(len(sql.table_page(self.catalog, 'users').rows), 3)
        self.assertEqual(set(p.name for p in self.root.iterdir()), {self.path.name})

    def test_lossless_export_blobs_null_invalid_text_and_formula_csv(self):
        page = sql.query(self.catalog, "SELECT '=header', name, flag, CAST(x'ff' AS TEXT) FROM users ORDER BY id")
        target = self.root / 'export.json'
        sql.export_page(page, target, 'json', [1, 2])
        result = json.loads(target.read_text(encoding='utf-8'))
        self.assertEqual(len(result['rows']), 2)
        self.assertIsNone(result['rows'][0][2])
        self.assertEqual(result['rows'][1][2], {'$bytes_hex': '00ff'})
        self.assertEqual(result['rows'][0][3], {'$bytes_hex': 'ff'})
        csvfile = self.root / 'export.csv'
        sql.export_page(page, csvfile, 'csv', [1])
        with csvfile.open(encoding='utf-8', newline='') as stream:
            rows = list(csv.reader(stream))
        self.assertEqual(rows[1][0], "'=header")
        self.assertEqual(rows[1][1], "'=FORMULA()")
        for path in [target, self.path]:
            with self.assertRaises(ValueError):
                sql.export_page(page, path, 'json')

    def test_wal_snapshot_includes_commits_without_touching_sidecars(self):
        walpath = self.root / 'WAL.sqlite'
        writer = sqlite3.connect(walpath)
        try:
            writer.execute('PRAGMA journal_mode=WAL'); writer.execute('PRAGMA wal_autocheckpoint=0')
            writer.execute('CREATE TABLE messages(flag TEXT)'); writer.execute("INSERT INTO messages VALUES ('flag{wal}')"); writer.commit()
            paths = [walpath, Path(str(walpath)+'-wal'), Path(str(walpath)+'-shm')]
            before = {p: p.read_bytes() for p in paths}
            catalog = sql.inspect_database(walpath)
            self.assertTrue(catalog.wal)
            self.assertEqual(sql.table_page(catalog, 'messages').rows, (('flag{wal}',),))
            self.assertEqual({p: p.read_bytes() for p in paths}, before)
        finally:
            writer.close()

    def test_change_detection_corruption_hot_journal_and_bounds(self):
        with patch.object(sql, 'MAX_DATABASE', 10), self.assertRaises(ValueError):
            sql.inspect_database(self.path)
        invalid = self.root / 'bad.db'; invalid.write_bytes(b'not SQLite')
        with self.assertRaisesRegex(ValueError, 'Signature'):
            sql.inspect_database(invalid)
        hot = Path(str(self.path) + '-journal'); hot.write_bytes(b'hot journal')
        with self.assertRaisesRegex(ValueError, 'Journal'):
            sql.inspect_database(self.path)
        hot.unlink()
        with patch.object(sql, 'fingerprint', return_value=('changed', None)), self.assertRaisesRegex(ValueError, 'changé'):
            sql.query(self.catalog, 'SELECT 1')
        for limit, offset in [(0,0),(501,0),(1,-1)]:
            with self.assertRaises(ValueError):
                sql.query(self.catalog, 'SELECT 1', limit, offset)

    def test_cancel_query_and_export_cleanup(self):
        calls = []
        def abort():
            calls.append(1)
            return 'arrêt' if len(calls) > 10 else None
        with self.assertRaises(Aborted):
            sql.query(self.catalog, 'WITH RECURSIVE r(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM r) SELECT sum(x) FROM r', abort=abort)
        page = sql.table_page(self.catalog, 'users')
        calls.clear(); target = self.root / 'cancelled.json'
        def export_abort():
            calls.append(1)
            return 'arrêt' if len(calls) > 2 else None
        with self.assertRaises(Aborted):
            sql.export_page(page, target, 'json', abort=export_abort)
        self.assertFalse(target.exists())

    def test_result_bytes_cells_and_cell_limits(self):
        with patch.object(sql, 'MAX_RESULT_BYTES', 8):
            page = sql.query(self.catalog, "SELECT '12345' FROM users")
            self.assertEqual(page.rows, (('12345',),)); self.assertTrue(page.more)
        with patch.object(sql, 'MAX_CELLS', 2):
            page = sql.query(self.catalog, 'SELECT id, name FROM users')
            self.assertEqual(len(page.rows), 1); self.assertTrue(page.more)
        with self.assertRaises(ValueError):
            sql.query(self.catalog, 'SELECT zeroblob(2000000)')
