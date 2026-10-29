import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ctf_unlock.models import Limits, Outcome, Result
from ctf_unlock.storage import Preferences, PreferenceStore, report_data


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'config' / 'preferences.json'
        self.store = PreferenceStore(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_preferences_roundtrip_and_positive_field_list(self):
        preferences = Preferences('C:/Program Files/7-Zip/7z.exe', Limits(120, 42, 2, 256, 5))
        self.store.save(preferences)
        self.assertEqual(self.store.load(), preferences)
        data = json.loads(self.path.read_text(encoding='utf-8'))
        self.assertEqual(set(data), {'version', 'engine', 'limits'})
        self.assertNotIn('password', data)

    def test_failed_atomic_save_keeps_old_preferences(self):
        self.store.save(Preferences())
        old = self.path.read_bytes()
        with patch('ctf_unlock.storage.os.replace', side_effect=PermissionError('Disque protégé')):
            with self.assertRaises(PermissionError):
                self.store.save(Preferences('nouveau moteur'))
        self.assertEqual(self.path.read_bytes(), old)
        self.assertEqual(list(self.path.parent.glob('*.tmp')), [])

    def test_corrupt_preferences_are_never_overwritten(self):
        self.path.parent.mkdir()
        self.path.write_bytes(b'{broken')
        with self.assertRaisesRegex(ValueError, 'Original conservé'):
            self.store.load()
        with self.assertRaises(ValueError):
            self.store.save(Preferences())
        self.assertEqual(self.path.read_bytes(), b'{broken')

    def test_invalid_types_versions_and_limits_are_rejected(self):
        self.path.parent.mkdir()
        for data in [
            {'version': True},
            {'version': 1, 'engine': '', 'limits': {'threads': True}},
            {'version': 1, 'engine': '', 'limits': {'memory_mb': -10}},
            {'version': 1, 'engine': '', 'limits': {'attempt_seconds': 'secret'}},
        ]:
            self.path.write_text(json.dumps(data), encoding='utf-8')
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.store.load()

    def test_report_excludes_secrets_paths_and_raw_diagnostics(self):
        secret = 'SECRET-NOT-TO-EXPORT'
        result = Result(Outcome.FOUND, 'detail ' + secret, 4, 2, secret, 'diagnostic ' + secret)
        report = report_data(result, str(Path(self.temp.name) / 'challenge.zip'), '7-Zip test')
        encoded = json.dumps(report)
        self.assertNotIn(secret, encoded)
        self.assertNotIn(self.temp.name, encoded)
        self.assertEqual(report['file_name'], 'challenge.zip')
        self.assertFalse(report['password_included'])
        self.assertEqual(report['attempted'], 4)
