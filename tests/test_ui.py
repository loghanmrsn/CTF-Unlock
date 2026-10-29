import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
from unittest.mock import patch
from pathlib import Path
import tempfile
import time
import unittest

from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl, QTimer
from PySide6.QtGui import QDropEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from ctf_unlock.models import Outcome
from ctf_unlock.ui import MainWindow, resources
from support import ENGINE, archive

APP = QApplication.instance() or QApplication([])
APP.setStyle('Fusion')
APP.setStyleSheet((resources() / 'theme.qss').read_text(encoding='utf-8'))


def wait_until(condition, timeout=12):
    deadline = time.monotonic() + timeout
    while not condition():
        APP.processEvents()
        QTest.qWait(10)
        if time.monotonic() > deadline:
            raise AssertionError('Délai Qt dépassé')
    APP.processEvents()


class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='CTF interface été ')
        self.root = Path(self.temp.name).resolve()
        self.window = MainWindow(engine_path=ENGINE or '/absent.exe', preferences_path=self.root / 'preferences.json')
        self.window.show()
        APP.processEvents()

    def tearDown(self):
        self.window.close()
        wait_until(lambda: not self.window.isVisible())
        self.window.pool.waitForDone()
        self.temp.cleanup()

    def test_navigation_switches_and_validation(self):
        QTest.mouseClick(self.window.tabs[1], Qt.MouseButton.LeftButton)
        self.assertEqual(self.window.pages.currentIndex(), 1)
        self.window.method.setCurrentIndex(1)
        self.window.alphabet.setText('aa')
        self.assertIn('distincts', self.window.mask_size.text())
        self.window.start()
        self.assertIn('Sélectionnez', self.window.phase.text())
        self.window.navigate(3)
        QTest.mouseClick(self.window.details_switch, Qt.MouseButton.LeftButton)
        self.assertTrue(self.window.details.isVisible())
        self.window.password.setText('test local')
        QTest.mouseClick(self.window.reveal, Qt.MouseButton.LeftButton)
        self.assertTrue(self.window.reveal.isChecked())
        self.window.seconds.setValue(1)
        self.assertLessEqual(self.window.attempt_time.value(), 1)

    def test_missing_engine_is_visible(self):
        self.window.engine_path.setText('/absent.exe')
        self.window.check_engine()
        wait_until(lambda: not self.window.busy)
        self.assertIn('7-Zip absent', self.window.journal.toPlainText())

    def test_real_drop_signature_with_wrong_extension(self):
        path = self.root / 'not a zip.txt'
        path.write_bytes(b'PK\x03\x04truncated')
        from ctf_unlock.ui import FileDrop
        drop = self.window.findChild(FileDrop)
        mime = QMimeData(); mime.setUrls([QUrl.fromLocalFile(str(path))])
        event = QDropEvent(QPointF(10, 10), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        drop.dropEvent(event)
        wait_until(lambda: not self.window.busy)
        self.assertEqual(Path(self.window.file_path.text()).resolve(), path.resolve())
        self.assertIn('ZIP', self.window.file_info.text())
        self.assertIn('endommagé', self.window.file_info.text())

    @unittest.skipUnless(ENGINE, '7-Zip absent : récupération Qt réelle non exécutée')
    def test_recovery_via_real_interface(self):
        path = archive(self.root, '7z', headers=True)
        words = self.root / 'liste.txt'
        words.write_text('wrong\nCTF42\n', encoding='utf-8')
        self.window.set_file(str(path))
        wait_until(lambda: not self.window.busy)
        self.assertIn('Protection : Oui', self.window.file_info.text())
        self.window.wordlist.setText(str(words))
        QTest.mouseClick(self.window.start_button, Qt.MouseButton.LeftButton)
        self.assertFalse(self.window.start_button.isEnabled())
        wait_until(lambda: not self.window.busy)
        self.assertEqual(self.window.result.outcome, Outcome.FOUND, self.window.result)
        self.assertIn('7-Zip', self.window.engine_version.text())
        self.assertEqual(self.window.password.text(), 'CTF42')
        self.assertEqual(self.window.password.echoMode(), self.window.password.EchoMode.Password)
        self.assertEqual(self.window.pages.currentIndex(), 3)
        QTest.mouseClick(self.window.copy_button, Qt.MouseButton.LeftButton)
        self.assertEqual(APP.clipboard().text(), 'CTF42')
        APP.clipboard().setText('autre contenu utilisateur')
        self.window.clear_copied_password()
        self.assertEqual(APP.clipboard().text(), 'autre contenu utilisateur')
        self.window.copy_password()
        self.window.clear_copied_password()
        self.assertEqual(APP.clipboard().text(), '')
        self.assertNotIn('CTF42', self.window.journal.toPlainText())
        report = self.root / 'bilan.json'
        with patch('ctf_unlock.ui.QFileDialog.getSaveFileName', return_value=(str(report), '')):
            self.window.export_report()
        payload = json.loads(report.read_text(encoding='utf-8'))
        self.assertFalse(payload['password_included'])
        self.assertNotIn('CTF42', report.read_text(encoding='utf-8'))
        original_result = self.window.result
        self.window.engine_path.setText('/absent.exe')
        self.window.check_engine(); wait_until(lambda: not self.window.busy)
        self.assertIs(self.window.result, original_result)
        self.assertIn('7-Zip absent', self.window.phase.text())
        # Une liste peut porter l'extension JSON ; ne jamais l'écraser par un bilan.
        protected_list = self.root / 'liste.json'
        protected_list.write_text('CTF42', encoding='utf-8')
        self.window.wordlist.setText(str(protected_list))
        with patch('ctf_unlock.ui.QFileDialog.getSaveFileName', return_value=(str(protected_list), '')):
            self.window.export_report()
        self.assertEqual(protected_list.read_text(encoding='utf-8'), 'CTF42')
        self.assertIn('Export impossible', self.window.phase.text())


    @unittest.skipUnless(ENGINE, '7-Zip absent : arrêt Qt réel non exécuté')
    def test_close_cancels_task_and_keeps_ui_responsive(self):
        path = archive(self.root, '7z', headers=True)
        self.window.set_file(str(path)); wait_until(lambda: not self.window.busy)
        self.window.method.setCurrentIndex(1)
        self.window.alphabet.setText('0123456789')
        self.window.minimum.setValue(4); self.window.maximum.setValue(4)
        beats = []
        timer = QTimer(); timer.timeout.connect(lambda: beats.append(1)); timer.start(5)
        self.window.start()
        wait_until(lambda: self.window.latest.attempted >= 1 or not self.window.busy)
        self.assertTrue(self.window.busy, (self.window.result, self.window.journal.toPlainText()))
        QTest.mouseClick(self.window.pause_button, Qt.MouseButton.LeftButton)
        wait_until(lambda: 'En pause' in self.window.phase.text() or not self.window.busy)
        self.assertTrue(self.window.busy, (self.window.result, self.window.journal.toPlainText()))
        self.window.close()
        wait_until(lambda: not self.window.isVisible())
        timer.stop()
        self.assertEqual(self.window.result.outcome, Outcome.INTERRUPTED)
        self.assertTrue(beats)

    def test_preferences_survive_window_restart_without_task_data(self):
        self.window.seconds.setValue(123)
        self.window.cap.setValue(27)
        self.window.engine_path.setText('/mon moteur/7zz')
        self.window.wordlist.setText('/ne pas enregistrer/liste.txt')
        self.window.file_path.setText('/ne pas enregistrer/archive.zip')
        self.window.save_preferences()
        restarted = MainWindow(preferences_path=self.root / 'preferences.json')
        try:
            self.assertEqual(restarted.seconds.value(), 123)
            self.assertEqual(restarted.cap.value(), 27)
            self.assertEqual(restarted.engine_path.text(), '/mon moteur/7zz')
            self.assertEqual(restarted.wordlist.text(), '')
            self.assertEqual(restarted.file_path.text(), '')
        finally:
            restarted.close()

    def test_corrupt_preferences_show_error_without_overwrite(self):
        path = self.root / 'corrupt.json'
        path.write_bytes(b'{broken')
        broken = MainWindow(preferences_path=path)
        APP.processEvents()
        self.assertIn('Original conservé', broken.journal.toPlainText())
        broken.close()
        self.assertEqual(path.read_bytes(), b'{broken')

    def test_small_window_keeps_controls_accessible(self):
        self.window.resize(820, 620)
        self.window.navigate(2)
        APP.processEvents()
        self.assertLessEqual(self.window.width(), 820)
        self.assertLessEqual(self.window.height(), 620)
        self.assertTrue(self.window.start_button.isVisible())
        self.assertTrue(self.window.stop_button.isVisible())
        self.assertLessEqual(self.window.stop_button.mapTo(self.window, self.window.stop_button.rect().bottomRight()).y(), self.window.height())
        self.window.method.setCurrentIndex(1)
        self.window.maximum.setValue(8)
        self.assertIn('ne couvre pas', self.window.mask_size.text())

    @unittest.skipUnless(ENGINE and os.environ.get('CTF_UNLOCK_JOHN') and os.environ.get('CTF_UNLOCK_ZIP2JOHN'), 'John Jumbo non fourni : test Qt John non exécuté')
    def test_real_john_selection_recovery_and_honest_statistics(self):
        path = archive(self.root, aes=True)
        words = self.root / 'john liste.txt'
        words.write_text('wrong\nCTF42\n', encoding='utf-8')
        self.window.john_path.setText(os.environ['CTF_UNLOCK_JOHN'])
        self.window.zip2john_path.setText(os.environ['CTF_UNLOCK_ZIP2JOHN'])
        self.window.backend.setCurrentIndex(1)
        self.window.set_file(str(path)); wait_until(lambda: not self.window.busy)
        self.window.wordlist.setText(str(words))
        self.window.start()
        self.assertFalse(self.window.pause_button.isEnabled())
        wait_until(lambda: not self.window.busy)
        self.assertEqual(self.window.result.outcome, Outcome.FOUND, self.window.result)
        self.assertEqual(self.window.password.text(), 'CTF42')
        self.assertIsNone(self.window.result.attempted)
        self.assertIn('non disponibles', self.window.metrics.text())
        self.assertIn('John', self.window.john_version.text())
        self.assertNotIn('CTF42', self.window.journal.toPlainText())
