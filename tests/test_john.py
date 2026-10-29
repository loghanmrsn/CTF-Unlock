import hashlib
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from ctf_unlock.candidates import Dictionary, Mask
from ctf_unlock.engine import SevenZip
from ctf_unlock.john import JohnJumbo, zip_hash
from ctf_unlock.models import Limits, Outcome, Progress
from ctf_unlock.storage import Preferences, PreferenceStore, report_data
from ctf_unlock.tasks import Control
from support import ENGINE, archive

JOHN = os.environ.get('CTF_UNLOCK_JOHN', '')
EXTRACTOR = os.environ.get('CTF_UNLOCK_ZIP2JOHN', '')


class JohnAdapterTests(unittest.TestCase):
    def test_missing_dependency_and_unsupported_format(self):
        engine = JohnJumbo('/absent/john', '/absent/zip2john', SevenZip(ENGINE or '/absent'))
        with self.assertRaisesRegex(FileNotFoundError, 'John Jumbo absent'):
            engine.version()
        with self.assertRaises(ValueError):
            zip_hash('not a hash')
        self.assertEqual(zip_hash('name:$zip2$*test*$/zip2$:metadata'), ('$zip2$*test*$/zip2$', 'ZIP'))
        self.assertEqual(zip_hash('name:$pkzip$test$/pkzip$'), ('$pkzip$test$/pkzip$', 'PKZIP'))

    def test_preferences_migrate_without_password_storage(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'settings.json'
            path.write_text('{"version":1,"engine":"7zz","limits":{}}', encoding='utf-8')
            store = PreferenceStore(path)
            old = store.load()
            self.assertEqual(old.engine, '7zz')
            self.assertEqual(old.john, '')
            settings = Preferences(old.engine, old.limits, 'john', 'zip2john')
            store.save(settings)
            self.assertEqual(store.load(), settings)

    def test_unknown_engine_counts_remain_unknown(self):
        progress = Progress(None, None, 2, 'John')
        self.assertIsNone(progress.speed)
        from ctf_unlock.models import Result
        report = report_data(Result(Outcome.EXHAUSTED, 'John', None, 2), 'file.zip', 'John')
        self.assertIsNone(report['attempted'])
        self.assertIsNone(report['average_attempts_per_second'])


@unittest.skipUnless(JOHN and EXTRACTOR and ENGINE, 'John Jumbo / zip2john / 7-Zip absents : intégration John non exécutée')
class RealJohnTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='John CTF été ')
        self.root = Path(self.temp.name).resolve()
        self.engine = JohnJumbo(JOHN, EXTRACTOR, SevenZip(ENGINE))
        self.limits = Limits(60, 100, 1, 512, 15)

    def tearDown(self):
        self.temp.cleanup()

    def words(self, entries):
        path = self.root / 'liste de mots.txt'
        path.write_text('\n'.join(entries) + '\n', encoding='utf-8')
        return Dictionary(path)

    def run_search(self, path, source, limits=None, control=None):
        return self.engine.recover(path, source, limits or self.limits, control or Control())

    def test_real_zipcrypto_and_aes_verified_by_7zip(self):
        self.assertIn('jumbo', self.engine.version().lower())
        for aes in (False, True):
            path = archive(self.root, aes=aes, name=f'John AES {aes}.data')
            digest = hashlib.sha256(path.read_bytes()).digest()
            result = self.run_search(path, self.words(['wrong', 'CTF42']))
            self.assertEqual(result.outcome, Outcome.FOUND, result)
            self.assertEqual(result.password, 'CTF42')
            self.assertIsNone(result.attempted)
            self.assertEqual(hashlib.sha256(path.read_bytes()).digest(), digest)

    def test_mask_and_wrong_dictionary(self):
        path = archive(self.root, password='b2', aes=True)
        result = self.run_search(path, Mask('b2', 2, 2))
        self.assertEqual(result.outcome, Outcome.FOUND, result)
        self.assertEqual(result.password, 'b2')
        failed = self.run_search(path, self.words(['wrong', 'still wrong']))
        self.assertEqual(failed.outcome, Outcome.EXHAUSTED, failed)
        self.assertIsNone(failed.password)

    def test_literal_spaces_and_colons(self):
        path = archive(self.root, password=' CTF:42 ', aes=True)
        result = self.run_search(path, self.words(['wrong', ' CTF:42 ']))
        self.assertEqual(result.outcome, Outcome.FOUND, result)
        self.assertEqual(result.password, ' CTF:42 ')

    def test_candidate_limit_unprotected_and_unsupported(self):
        path = archive(self.root)
        result = self.run_search(path, self.words(['wrong', 'CTF42']), Limits(60, 1, 1, 512, 15))
        self.assertEqual(result.outcome, Outcome.LIMITED, result)
        public = archive(self.root, password='', name='public.zip')
        self.assertEqual(self.run_search(public, self.words(['unused'])).outcome, Outcome.UNPROTECTED)
        seven = archive(self.root, '7z')
        self.assertEqual(self.run_search(seven, self.words(['CTF42'])).outcome, Outcome.UNSUPPORTED)

    def test_cancel_and_scratch_cleanup(self):
        path = archive(self.root, aes=True)
        control = Control()
        progress = []
        def update(value):
            progress.append(value.phase)
            if sum(phase.startswith('John calcule') for phase in progress) >= 2:
                control.stop()
        real_temporary_directory = tempfile.TemporaryDirectory
        scratch_paths = []
        def scratch(*args, **kwargs):
            directory = real_temporary_directory(*args, dir=self.root, **kwargs)
            scratch_paths.append(Path(directory.name))
            return directory
        with patch('ctf_unlock.john.tempfile.TemporaryDirectory', side_effect=scratch):
            result = self.engine.recover(path, Mask('0123456789', 6, 6), Limits(60, 100000, 1, 512, 15), control, update)
        self.assertEqual(result.outcome, Outcome.INTERRUPTED, result)
        self.assertTrue(scratch_paths)
        self.assertTrue(all(not p.exists() for p in scratch_paths))
