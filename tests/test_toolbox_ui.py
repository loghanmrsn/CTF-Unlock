import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
from PySide6.QtCore import Qt, QTimer, QPointF, QMimeData, QUrl
from PySide6.QtGui import QDropEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractItemView
from ctf_unlock.ui import MainWindow
from test_ui import APP, wait_until


class ToolboxInterfaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='CTF atelier été ')
        self.root = Path(self.temp.name)
        self.window = MainWindow(engine_path='/absent', preferences_path=self.root/'preferences.json')
        self.window.show(); self.window.navigate(4); APP.processEvents()
        self.box = self.window.toolbox

    def tearDown(self):
        self.window.close()
        wait_until(lambda: not self.window.isVisible())
        self.window.pool.waitForDone()
        self.temp.cleanup()

    def wait(self):
        wait_until(lambda: not self.window.busy)

    def database(self):
        self.box.tabs.setCurrentIndex(2)
        self.panel = self.box.sqlite
        path = self.root / 'challenge été.db'
        with closing(sqlite3.connect(path)) as con:
            con.execute('CREATE TABLE users(id INTEGER PRIMARY KEY, flag TEXT)')
            con.executemany('INSERT INTO users VALUES (?,?)', [(1,'flag{local}'),(2,'autre'),(3,'100%')])
            con.commit()
        self.before = path.read_bytes()
        self.panel.path.setText(str(path)); self.panel.analyze(); self.wait()
        self.assertIsNotNone(self.panel.catalog, self.window.phase.text())
        self.panel.tables.setCurrentIndex(0); self.wait()
        return path

    def test_real_text_conversion_copy_reuse_and_binary(self):
        self.box.operation.setCurrentText('ROT13'); self.box.input.setPlainText('synt{PGS42}')
        self.box.convert_text(); self.wait()
        self.assertEqual(self.box.result.toPlainText(), 'flag{CTF42}')
        viewport = self.window.page_scroll.viewport()
        self.assertLessEqual(self.box.copy.mapTo(viewport, self.box.copy.rect().bottomRight()).y(), viewport.height())
        self.box.copy_text(); self.assertEqual(APP.clipboard().text(), 'flag{CTF42}')
        self.box.reuse_text(); self.assertEqual(self.box.input.toPlainText(), 'flag{CTF42}')
        self.box.operation.setCurrentText('Hexadécimal → octets'); self.box.input.setPlainText('ff00')
        self.box.convert_text(); self.wait()
        self.assertIsNone(self.box.output.text); self.assertTrue(self.box.result_hex.isVisible())
        self.assertEqual(self.box.result_hex.toPlainText(), 'ff00')
        self.box.input.setPlainText('invalid'); self.box.convert_text(); self.wait()
        self.assertIn('Erreur', self.box.status.text())

    def test_image_drop_real_pixel_views_bits_and_export(self):
        self.box.tabs.setCurrentIndex(1)
        path = self.root / 'pixels.png'
        source = Image.new('RGB', (8,2), (254,0,0))
        for i, bit in enumerate('0100000101000010'):
            source.putpixel((i%8,i//8), (254+int(bit),0,0))
        source.save(path)
        original = path.read_bytes()
        mime = QMimeData(); mime.setUrls([QUrl.fromLocalFile(str(path))])
        event = QDropEvent(QPointF(10,10), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        self.box.canvas.dropEvent(event); self.wait()
        self.assertEqual(self.box.data.format, 'PNG')
        self.assertFalse(self.box.canvas.pixmap().isNull())
        self.window.page_scroll.ensureWidgetVisible(self.box.canvas); APP.processEvents()
        QTest.mouseClick(self.box.canvas, Qt.MouseButton.LeftButton, pos=self.box.canvas.rect().center())
        self.assertIn('Pixel original', self.box.color_result.text())
        self.box.channels.setCurrentText('R'); self.box.count.setValue(2); self.box.extract(); self.wait()
        self.assertIn('HEX : 4142', self.box.bits_result.toPlainText())
        self.box.view.setCurrentText('Plan de bits'); self.box.apply_view(); self.wait()
        self.assertEqual(self.box.preview.getpixel((1,0)), (255,255,255,255))
        target = self.root / 'nouvelle vue.png'
        with patch('ctf_unlock.toolbox_ui.QFileDialog.getSaveFileName', return_value=(str(target),'')):
            self.box.save_image(); self.wait()
        self.assertTrue(target.exists()); self.assertEqual(path.read_bytes(), original)

    def test_color_calculator_without_image_and_small_layout(self):
        self.box.tabs.setCurrentIndex(1); self.box.color.setText('#000000'); self.box.calculate_color()
        self.assertIn('21.00:1', self.box.color_result.text())
        self.window.resize(820,620); APP.processEvents()
        self.assertEqual(self.window.width(), 820)
        self.assertTrue(self.window.stop_button.isVisible())
        self.assertFalse(self.window.start_button.isVisible())
        for index in (0,1,2):
            self.box.tabs.setCurrentIndex(index); APP.processEvents()
            self.assertLessEqual(self.box.tabs.width(), self.window.page_scroll.viewport().width(), f'onglet {index}')

    def test_sqlite_schema_filter_pages_query_and_selected_export(self):
        path = self.database()
        self.assertIn('PRIMARY KEY', self.panel.structure.toPlainText())
        self.assertEqual(self.panel.result.editTriggers(), QAbstractItemView.EditTrigger.NoEditTriggers)
        self.panel.limit.setValue(2); self.panel.read_table(); self.wait()
        self.assertEqual(self.panel.result.rowCount(), 2); self.assertTrue(self.panel.next.isEnabled())
        self.panel.move(True); self.wait()
        self.assertEqual(self.panel.page.offset, 2); self.assertEqual(self.panel.result.rowCount(),1)
        self.panel.move(False); self.wait(); self.assertEqual(self.panel.page.offset,0)
        self.panel.filter.setText('%'); self.panel.read_table(); self.wait()
        self.assertEqual(self.panel.page.rows, ((3,'100%'),))
        self.panel.editor.setPlainText('SELECT flag FROM users ORDER BY id'); self.panel.read_query(); self.wait()
        self.panel.result.selectRow(0)
        target = self.root / 'selection.json'
        with patch('ctf_unlock.sqlite_ui.QFileDialog.getSaveFileName', return_value=(str(target),'')):
            self.panel.export('json'); self.wait()
        data = json.loads(target.read_text(encoding='utf-8'))
        self.assertEqual(data, {'columns':['flag'], 'rows':[['flag{local}']]})
        self.assertEqual(path.read_bytes(), self.before)

    def test_sqlite_write_error_preserves_successful_page_and_original(self):
        path = self.database()
        self.panel.read_table(); self.wait(); previous = self.panel.page
        self.panel.editor.setPlainText("DELETE FROM users")
        self.panel.read_query(); self.wait()
        self.assertIn('Erreur', self.panel.status.text()); self.assertIs(self.panel.page, previous)
        self.assertEqual(path.read_bytes(), self.before)
        target = self.root / 'last-valid.csv'
        with patch('ctf_unlock.sqlite_ui.QFileDialog.getSaveFileName', return_value=(str(target),'')):
            self.panel.export('csv'); self.wait()
        self.assertIn('flag{local}', target.read_text(encoding='utf-8'))

    def test_sqlite_cancel_real_query_keeps_ui_alive(self):
        path = self.database()
        self.panel.editor.setPlainText('WITH RECURSIVE r(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM r) SELECT sum(x) FROM r')
        beats=[]
        timer=QTimer(); timer.timeout.connect(lambda: beats.append(1)); timer.start(5)
        self.panel.read_query()
        self.assertTrue(self.window.busy); self.assertFalse(self.window.tools_panel.isEnabled())
        QTimer.singleShot(50, self.window.stop)
        self.wait(); timer.stop()
        self.assertTrue(beats); self.assertTrue(self.window.tools_panel.isEnabled())
        self.assertIn('Arrêt demandé', self.panel.status.text())
        self.assertEqual(path.read_bytes(), self.before)

    def test_sqlite_invalid_new_file_clears_old_page(self):
        self.database(); self.panel.read_table(); self.wait()
        bad=self.root/'invalid.db'; bad.write_bytes(b'not SQLite')
        self.panel.path.setText(str(bad)); self.panel.analyze(); self.wait()
        self.assertIsNone(self.panel.catalog); self.assertIsNone(self.panel.page)
        self.assertEqual(self.panel.result.rowCount(),0)
        self.assertFalse(self.panel.json.isEnabled()); self.assertIn('Signature SQLite', self.panel.status.text())
