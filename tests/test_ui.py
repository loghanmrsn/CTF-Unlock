import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
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
        self.window = MainWindow(engine_path=ENGINE or '/absent.exe')
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
        self.assertEqual(self.window.file_path.text(), str(path))
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
        self.assertEqual(self.window.result.outcome, Outcome.FOUND)
        self.assertIn('7-Zip', self.window.engine_version.text())
        self.assertEqual(self.window.password.text(), 'CTF42')
        self.assertEqual(self.window.password.echoMode(), self.window.password.EchoMode.Password)
        self.assertEqual(self.window.pages.currentIndex(), 3)

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
        wait_until(lambda: self.window.latest.attempted >= 1)
        QTest.mouseClick(self.window.pause_button, Qt.MouseButton.LeftButton)
        wait_until(lambda: 'En pause' in self.window.phase.text())
        self.window.close()
        wait_until(lambda: not self.window.isVisible())
        timer.stop()
        self.assertEqual(self.window.result.outcome, Outcome.INTERRUPTED)
        self.assertTrue(beats)
