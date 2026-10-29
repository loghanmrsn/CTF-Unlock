import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import zipfile

from ctf_unlock.archives import inspect
from ctf_unlock.candidates import Dictionary, Mask
from ctf_unlock.engine import SevenZip
from ctf_unlock.models import Limits, Outcome
from ctf_unlock.processes import Aborted, run
from ctf_unlock.tasks import Control, recover
from support import ENGINE, archive


class CandidatesTests(unittest.TestCase):
    def test_mask_order_count_and_bounds(self):
        mask = Mask('ab', 1, 2)
        self.assertEqual(list(mask.generate()), ['a', 'b', 'aa', 'ab', 'ba', 'bb'])
        self.assertEqual(mask.total, 6)
        for mask in [Mask('', 1, 2), Mask('aa', 1, 2), Mask('ab', 3, 2), Mask('ab', 1, 9)]:
            with self.subTest(mask=mask), self.assertRaises(ValueError):
                mask.validate()

    def test_list_preserves_spaces_and_rejects_long_lines(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'mots.txt'
            path.write_text('\ufeff premier \n\nCTF42\n', encoding='utf-8')
            self.assertEqual(list(Dictionary(path).generate()), [' premier ', 'CTF42'])
            path.write_text('x' * 129, encoding='utf-8')
            with self.assertRaises(ValueError):
                list(Dictionary(path).generate())

    def test_signatures_invalid_and_plain_zip_without_engine(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'fausse extension.txt'
            with zipfile.ZipFile(path, 'w') as z:
                z.writestr('preuve.txt', 'valide')
            self.assertEqual(inspect(path).format, 'ZIP')
            self.assertIs(inspect(path).protected, False)
            path.write_bytes(b'PK\x03\x04broken')
            self.assertEqual(inspect(path).outcome, Outcome.DAMAGED)
            path.write_bytes(b'random invalid file')
            self.assertEqual(inspect(path).outcome, Outcome.UNSUPPORTED)
            path.write_bytes(b'7z\xbc\xaf\x27\x1c\0')
            self.assertEqual(inspect(path).outcome, Outcome.DAMAGED)

    def test_missing_engine_is_explicit(self):
        with self.assertRaisesRegex(FileNotFoundError, '7-Zip absent'):
            SevenZip('/not/a/real/7z.exe').version()

    def test_process_stop_closes_real_child(self):
        with tempfile.TemporaryDirectory() as root:
            marker = Path(root) / 'pid'
            control = threading.Event()
            error = []
            def worker():
                try:
                    run([sys.executable, '-c', 'import os,time,pathlib,sys;pathlib.Path(sys.argv[1]).write_text(str(os.getpid()));time.sleep(30)', str(marker)], timeout=10, memory_mb=512, abort=lambda: 'annulé' if control.is_set() else None)
                except Aborted as exc:
                    error.append(str(exc))
            thread = threading.Thread(target=worker)
            thread.start()
            deadline = time.monotonic() + 5
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertTrue(marker.exists())
            pid = int(marker.read_text())
            kernel, handle = None, None
            if os.name == 'nt':
                import ctypes
                from ctypes import wintypes
                kernel = ctypes.WinDLL('kernel32', use_last_error=True)
                kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
                kernel.OpenProcess.restype = wintypes.HANDLE
                kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
                kernel.WaitForSingleObject.restype = wintypes.DWORD
                kernel.CloseHandle.argtypes = [wintypes.HANDLE]
                handle = kernel.OpenProcess(0x100000, False, pid)
                self.assertTrue(handle)
            control.set(); thread.join(3)
            self.assertFalse(thread.is_alive())
            self.assertEqual(error, ['annulé'])
            if handle:
                try:
                    self.assertEqual(kernel.WaitForSingleObject(handle, 2000), 0)
                finally:
                    kernel.CloseHandle(handle)
            else:
                with self.assertRaises(ProcessLookupError):
                    os.kill(pid, 0)


@unittest.skipUnless(ENGINE, '7-Zip absent : tests d’intégration non exécutés')
class RealArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='CTF Unlock été ')
        self.root = Path(self.temp.name).resolve()
        self.engine = SevenZip(ENGINE)
        self.limits = Limits(seconds=30, candidates=100, threads=1, memory_mb=512, attempt_seconds=10)

    def tearDown(self):
        self.temp.cleanup()

    def words(self, values):
        path = self.root / 'liste avec espaces.txt'
        path.write_text('\n'.join(values) + '\n', encoding='utf-8')
        return Dictionary(path)

    def recover(self, path, values, **kwargs):
        return recover(path, self.words(values), self.engine, kwargs.get('limits', self.limits), kwargs.get('control', Control()), kwargs.get('progress', lambda p: None))

    def test_version_and_recovery_zip_crypto_zip_aes_7z(self):
        self.assertIn('7-Zip', self.engine.version())
        for kind, aes, headers in [('zip', False, False), ('zip', True, False), ('7z', False, False), ('7z', False, True)]:
            with self.subTest(kind=kind, aes=aes, headers=headers):
                path = archive(self.root, kind, name=f'archive {kind} {aes} {headers}.bin', aes=aes, headers=headers)
                original = hashlib.sha256(path.read_bytes()).digest()
                metadata = self.engine.protection(inspect(path), self.limits)
                self.assertEqual(metadata.format, 'ZIP' if kind == 'zip' else '7z')
                self.assertTrue(metadata.protected)
                result = self.recover(path, ['incorrect', 'CTF42'])
                self.assertEqual(result.outcome, Outcome.FOUND, result)
                self.assertEqual(result.password, 'CTF42')
                self.assertEqual(result.attempted, 2)
                self.assertEqual(hashlib.sha256(path.read_bytes()).digest(), original)
                self.assertEqual(self.engine.test(metadata, result.password, self.limits).code, 0)

    def test_damaged_unprotected_payload_is_not_reported_as_open(self):
        path = self.root / 'crc invalide.zip'
        with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_STORED) as stream:
            stream.writestr('preuve.txt', b'UNIQUE-CONTENT-CTF')
        payload = path.read_bytes().replace(b'UNIQUE-CONTENT-CTF', b'DAMAGED-CONTENT-XX')
        path.write_bytes(payload)
        result = self.recover(path, ['unused'])
        self.assertEqual(result.outcome, Outcome.DAMAGED, result)
        self.assertIsNone(result.password)

    def test_literal_password_and_path_metacharacters(self):
        password = ' CTF ; $42 '
        path = archive(self.root, password=password, name='challenge ; $ (1).zip')
        result = self.recover(path, ['wrong', password])
        self.assertEqual(result.outcome, Outcome.FOUND, result)
        self.assertEqual(result.password, password)

    def test_wrong_list_is_exhausted_not_found(self):
        path = archive(self.root)
        result = self.recover(path, ['wrong', 'still wrong'])
        self.assertEqual(result.outcome, Outcome.EXHAUSTED, result)
        self.assertIsNone(result.password)

    def test_real_mask(self):
        path = archive(self.root, password='b2')
        result = recover(path, Mask('b2', 2, 2), self.engine, self.limits, Control())
        self.assertEqual(result.outcome, Outcome.FOUND, result)
        self.assertEqual(result.password, 'b2')
        self.assertEqual(result.attempted, 2)

    def test_unprotected_zip_and_7z(self):
        for kind in ['zip', '7z']:
            path = archive(self.root, kind, password='', name='public.' + kind)
            result = self.recover(path, ['wrong'])
            self.assertEqual(result.outcome, Outcome.UNPROTECTED, result)
            self.assertIsNone(result.password)

    def test_invalid_and_truncated_archives(self):
        path = self.root / 'invalid.zip'
        path.write_bytes(b'not an archive')
        self.assertEqual(self.recover(path, ['x']).outcome, Outcome.UNSUPPORTED)
        path = archive(self.root, '7z')
        path.write_bytes(path.read_bytes()[:-10])
        self.assertEqual(self.recover(path, ['CTF42']).outcome, Outcome.DAMAGED)

    def test_candidate_limit_and_duration(self):
        path = archive(self.root)
        limited = self.recover(path, ['a', 'b', 'c'], limits=Limits(30, 1, 1, 512, 10))
        self.assertEqual(limited.outcome, Outcome.LIMITED)
        self.assertEqual(limited.attempted, 1)
        control = Control()
        def progress(p):
            if p.attempted == 1:
                control.pause(True)
        result = self.recover(path, ['a', 'b'], limits=Limits(.4, 100, 1, 512, .3), control=control, progress=progress)
        self.assertEqual(result.outcome, Outcome.LIMITED, result)
        self.assertLess(result.elapsed, 3)

    def test_pause_resume_and_cancellation(self):
        path = archive(self.root)
        control = Control()
        seen = []
        paused = threading.Event()
        def progress(p):
            seen.append(p)
            if p.attempted == 1:
                control.pause(True)
            if 'En pause' in p.phase:
                paused.set()
        results = []
        task = threading.Thread(target=lambda: results.append(self.recover(path, ['wrong', 'CTF42'], control=control, progress=progress)))
        task.start()
        self.assertTrue(paused.wait(5))
        count = seen[-1].attempted
        time.sleep(.1)
        self.assertEqual(seen[-1].attempted, count)
        # Le callback ne redemande la pause qu'à l'essai 1 : ne pas l'appeler après reprise.
        control.stop()
        task.join(3)
        self.assertFalse(task.is_alive())
        self.assertEqual(results[0].outcome, Outcome.INTERRUPTED)

    def test_resume_finds_password(self):
        path = archive(self.root)
        control = Control(); control.pause(True)
        timer = threading.Timer(.2, lambda: control.pause(False))
        timer.start()
        try:
            result = self.recover(path, ['CTF42'], control=control)
            self.assertEqual(result.outcome, Outcome.FOUND, result)
        finally:
            timer.join()

    def test_missing_dependency_returns_error(self):
        path = archive(self.root)
        result = recover(path, self.words(['CTF42']), SevenZip('/missing.exe'), self.limits, Control())
        self.assertEqual(result.outcome, Outcome.ERROR)
        self.assertIn('7-Zip absent', result.detail)

    def test_memory_limit_is_enforced(self):
        result = run([sys.executable, '-c', 'import time;time.sleep(.1);x=bytearray(256*1024*1024)'], timeout=3, memory_mb=128)
        self.assertNotEqual(result.code, 0)
        self.assertIn('MemoryError', result.output)
