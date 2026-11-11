"""Atelier hors ligne : texte, observation d'images et SQLite."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog,
    QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
    QSpinBox, QTabBar, QVBoxLayout, QWidget)
from . import image_tools as images, text_tools as texts
from .sqlite_ui import SQLitePanel, button, label


class ContentTabs(QWidget):
    """Les panneaux masqués ne participent pas à la hauteur de l'onglet actif."""
    def __init__(self):
        super().__init__()
        self.panels = []
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.bar = QTabBar()
        self.bar.setExpanding(False)
        self.bar.setDrawBase(False)
        self.bar.setUsesScrollButtons(True)
        self.bar.currentChanged.connect(self.resize_content)
        self.layout.addWidget(self.bar)

    def addTab(self, widget, title):
        widget.layout().setAlignment(Qt.AlignmentFlag.AlignTop)
        widget.layout().addStretch(1)
        self.panels.append(widget)
        self.layout.addWidget(widget)
        self.bar.addTab(title)
        self.resize_content(self.currentIndex())

    def currentIndex(self):
        return self.bar.currentIndex()

    def setCurrentIndex(self, index):
        self.bar.setCurrentIndex(index)

    def resize_content(self, current):
        for i, panel in enumerate(self.panels):
            panel.setVisible(i == current)
        self.updateGeometry()


class ImageCanvas(QLabel):
    picked = Signal(int, int)
    selected = Signal(str)

    def __init__(self):
        super().__init__('Choisissez une image ou déposez-la ici.')
        self.original = None
        self.setFixedHeight(220)
        self.setMinimumWidth(1)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAcceptDrops(True)

    def show_image(self, image):
        self.original = QPixmap.fromImage(QImage(image.tobytes(), image.width, image.height, image.width * 4, QImage.Format.Format_RGBA8888).copy())
        self.resizeEvent(None)

    def resizeEvent(self, event):
        if self.original:
            self.setPixmap(self.original.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation))
        if event:
            super().resizeEvent(event)

    def mousePressEvent(self, event):
        if self.original and self.pixmap() and not self.pixmap().isNull():
            displayed = self.pixmap().size()
            x = event.position().x() - (self.width() - displayed.width()) / 2
            y = event.position().y() - (self.height() - displayed.height()) / 2
            if 0 <= x < displayed.width() and 0 <= y < displayed.height():
                self.picked.emit(int(x * self.original.width() / displayed.width()), int(y * self.original.height() / displayed.height()))

    def dragEnterEvent(self, event):
        urls = event.mimeData().urls()
        if self.isEnabled() and len(urls) == 1 and urls[0].isLocalFile():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if self.isEnabled() and len(urls) == 1 and urls[0].isLocalFile():
            self.selected.emit(urls[0].toLocalFile()); event.acceptProposedAction()


class Histogram(QWidget):
    def __init__(self):
        super().__init__()
        self.rows = ()
        self.setFixedHeight(70)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#121212'))
        maximum = max((max(row) for row in self.rows), default=1) or 1
        for row, color in zip(self.rows, ('#ef9696', '#a7dba7', '#a2bfe7')):
            painter.setPen(QColor(color))
            for x in range(255):
                painter.drawLine(round(x*self.width()/256), round((1-row[x]/maximum)*(self.height()-1)), round((x+1)*self.width()/256), round((1-row[x+1]/maximum)*(self.height()-1)))


class Toolbox(QWidget):
    requested = Signal(object)
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self.data = self.preview = self.output = None
        self.pending = ''
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.tabs = ContentTabs()
        layout.addWidget(self.tabs)
        self.build_text()
        self.build_image()
        self.sqlite = SQLitePanel()
        self.sqlite.requested.connect(lambda operation: self.dispatch('sqlite', operation))
        self.sqlite.failed.connect(self.failed)
        self.tabs.addTab(self.sqlite, 'SQLite / SQL')
        self.tabs.resize_content(0)
        self.status = label('Traitement local. Aucun décryptage automatique ou résultat simulé.')
        layout.addWidget(self.status)
        layout.addStretch(1)

    def dispatch(self, kind, operation):
        self.pending = kind
        self.status.setText('Travail local en cours…')
        self.requested.emit(lambda abort: {kind: operation(abort)})

    def on_error(self, message, interrupted=False):
        prefix = 'Traitement interrompu : ' if interrupted else 'Erreur : '
        self.status.setText(prefix + message)
        if self.pending == 'sqlite':
            self.sqlite.status.setText(prefix + message + '\nLa dernière page réussie, si présente, est conservée.')
        self.pending = ''

    def build_text(self):
        panel = QWidget(); layout = QVBoxLayout(panel)
        layout.addWidget(label('César, encodages et XOR avec une clé connue. César ne transforme que les lettres ASCII ; aucune langue n’est détectée automatiquement.'))
        self.operation = QComboBox(); self.operation.addItems(texts.OPERATIONS)
        layout.addWidget(self.operation)
        options = QHBoxLayout()
        self.shift = QSpinBox(); self.shift.setRange(-25, 25); self.shift.setValue(13); self.shift.setPrefix('Décalage : ')
        self.key = QLineEdit(); self.key.setPlaceholderText('Clé XOR hexadécimale, par exemple 42'); self.key.setMaxLength(512)
        options.addWidget(self.shift); options.addWidget(self.key, 1)
        layout.addLayout(options)
        self.operation.currentTextChanged.connect(self.text_options)
        self.text_options()
        row = QHBoxLayout()
        self.input = QPlainTextEdit(); self.input.setPlaceholderText('Texte ou octets encodés à convertir · 64 Kio maximum'); self.input.setFixedHeight(170)
        self.result = QPlainTextEdit(); self.result.setReadOnly(True); self.result.setPlaceholderText('Résultat réel de la conversion'); self.result.setFixedHeight(170)
        row.addWidget(self.input, 1); row.addWidget(self.result, 1); layout.addLayout(row)
        self.result_hex = QPlainTextEdit(); self.result_hex.setReadOnly(True); self.result_hex.setFixedHeight(80); self.result_hex.hide()
        layout.addWidget(self.result_hex)
        layout.addWidget(button('Transformer', self.convert_text))
        row = QHBoxLayout()
        self.copy = button('Copier le résultat', self.copy_text); self.copy.setEnabled(False); row.addWidget(self.copy)
        self.reuse = button('Réutiliser le résultat', self.reuse_text); self.reuse.setEnabled(False); row.addWidget(self.reuse)
        layout.addLayout(row)
        self.tabs.addTab(panel, 'Texte / encodages')

    def text_options(self):
        self.shift.setVisible(self.operation.currentText() == 'César')
        self.key.setVisible(self.operation.currentText() == 'XOR · clé hexadécimale')

    def convert_text(self):
        operation, value, shift, key = self.operation.currentText(), self.input.toPlainText(), self.shift.value(), self.key.text()
        self.dispatch('text', lambda abort: texts.transform(operation, value, shift, key))

    def copy_text(self):
        if self.output:
            QApplication.clipboard().setText(self.output.text if self.output.text is not None else self.output.hex)

    def reuse_text(self):
        if self.output:
            self.input.setPlainText(self.output.text if self.output.text is not None else self.output.hex)
            if self.output.text is None:
                self.operation.setCurrentText('Hexadécimal → octets')

    def build_image(self):
        panel = QWidget(); layout = QVBoxLayout(panel)
        layout.addWidget(label('PNG, JPEG, BMP, GIF, WebP · 20 Mio / 4 millions de pixels. Première image seulement, sans correction EXIF ni profil ICC. Les vues et bits ne prouvent pas la présence d’un message.'))
        row = QHBoxLayout()
        self.image_path = QLineEdit(); self.image_path.setReadOnly(True); row.addWidget(self.image_path, 1)
        row.addWidget(button('Choisir une image', self.choose_image)); layout.addLayout(row)
        self.image_info = label('Image non chargée. Cliquez un pixel de la vue pour lire sa valeur originale.'); layout.addWidget(self.image_info)
        self.canvas = ImageCanvas(); self.canvas.picked.connect(self.pick_pixel); self.canvas.selected.connect(self.load_image); layout.addWidget(self.canvas)
        row = QHBoxLayout()
        self.view = QComboBox(); self.view.addItems(['Original', 'Inversion', 'Gris', 'Canal', 'Plan de bits'])
        self.channel = QComboBox(); self.channel.addItems(list('RGBA'))
        self.bit = QSpinBox(); self.bit.setRange(0, 7); self.bit.setPrefix('Bit : ')
        for item in (self.view, self.channel, self.bit): row.addWidget(item)
        layout.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(button('Appliquer la vue', self.apply_view))
        self.save = button('Exporter PNG', self.save_image); self.save.setEnabled(False); row.addWidget(self.save)
        layout.addLayout(row)
        self.palette = label('Palette et histogramme RGB approximatifs, échantillonnés à 65 536 pixels maximum ; pixels entièrement transparents exclus.'); layout.addWidget(self.palette)
        self.histogram = Histogram(); layout.addWidget(self.histogram)
        row = QHBoxLayout()
        self.color = QLineEdit('#FFFFFF'); self.color.setMaxLength(7); row.addWidget(self.color)
        row.addWidget(button('Calculer la couleur', self.calculate_color)); layout.addLayout(row)
        self.color_result = label('RGB, HSV, luminance et contraste sRGB.'); layout.addWidget(self.color_result)
        self.metadata = QPlainTextEdit(); self.metadata.setReadOnly(True); self.metadata.setFixedHeight(80); self.metadata.setPlaceholderText('Métadonnées lisibles (bornées).'); layout.addWidget(self.metadata)
        layout.addWidget(label('Extraction de bits sur les pixels décodés originaux, ligne par ligne. Les octets incomplets sont omis.'))
        row = QHBoxLayout()
        self.channels = QComboBox(); self.channels.addItems(['RGB', 'RGBA', 'R', 'G', 'B', 'A'])
        self.order = QComboBox(); self.order.addItems(['Premier bit → poids fort', 'Premier bit → poids faible'])
        self.start = QSpinBox(); self.start.setRange(0, images.MAX_PIXELS-1); self.start.setPrefix('Pixel : ')
        self.count = QSpinBox(); self.count.setRange(1, 65536); self.count.setValue(1024); self.count.setPrefix('Octets : ')
        row.addWidget(self.channels); row.addWidget(self.order); layout.addLayout(row)
        row = QHBoxLayout(); row.addWidget(self.start); row.addWidget(self.count); layout.addLayout(row)
        layout.addWidget(button('Extraire le bit choisi', self.extract))
        self.bits_result = QPlainTextEdit(); self.bits_result.setReadOnly(True); self.bits_result.setFixedHeight(110); layout.addWidget(self.bits_result)
        self.tabs.addTab(panel, 'Images / couleurs')

    def choose_image(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Choisir une image', '', 'Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;Tous les fichiers (*)')
        if path: self.load_image(path)

    def load_image(self, path):
        self.image_path.setText(path)
        self.data = self.preview = None
        self.save.setEnabled(False)
        self.canvas.original = None; self.canvas.clear(); self.metadata.clear(); self.bits_result.clear()
        self.histogram.rows = (); self.histogram.update()
        self.palette.setText('Analyse en cours…'); self.image_info.setText('Analyse en cours…')
        self.dispatch('image', lambda abort: images.analyze_image(path, abort))

    def require_image(self):
        if not self.data:
            self.failed.emit('Choisissez d’abord une image valide.'); return False
        return True

    def apply_view(self):
        if not self.require_image(): return
        data, view, channel, bit = self.data, self.view.currentText(), self.channel.currentText(), self.bit.value()
        self.dispatch('preview', lambda abort: images.view_image(data, view, channel, bit, abort))

    def pick_pixel(self, x, y):
        if self.data and 0 <= x < self.data.width and 0 <= y < self.data.height:
            start = (y*self.data.width+x)*4
            r, g, b, a = self.data.rgba[start:start+4]
            self.color.setText(f'#{r:02X}{g:02X}{b:02X}')
            self.color_result.setText(f'Pixel original ({x}, {y}) · alpha {a}/255\n' + images.color_info(self.color.text()))

    def calculate_color(self):
        try: self.color_result.setText(images.color_info(self.color.text()))
        except ValueError as exc: self.failed.emit(str(exc))

    def save_image(self):
        if not self.preview or not self.data: return
        path, _ = QFileDialog.getSaveFileName(self, 'Créer une nouvelle image PNG', 'CTF-Unlock-vue.png', 'PNG (*.png)')
        if path:
            preview, source = self.preview, self.data.source
            self.dispatch('saved', lambda abort: images.save_preview(preview, source, path, abort))

    def extract(self):
        if not self.require_image(): return
        data, channels, bit, start, count, msb = self.data, self.channels.currentText(), self.bit.value(), self.start.value(), self.count.value(), self.order.currentIndex() == 0
        self.dispatch('bits', lambda abort: images.extract_bits(data, channels, bit, start, count, msb, abort))

    def complete(self, value):
        if 'sqlite' in value:
            self.sqlite.complete(value['sqlite'])
        elif 'text' in value:
            self.output = value['text']
            self.result.setPlainText(self.output.text if self.output.text is not None else 'Octets non UTF-8 : voir leur représentation hexadécimale ci-dessous.')
            self.result_hex.setPlainText(self.output.hex if self.output.text is None else '')
            self.result_hex.setVisible(self.output.text is None)
            self.copy.setEnabled(True); self.reuse.setEnabled(True)
        elif 'image' in value:
            self.data = value['image']
            self.preview = images.pixels(self.data)
            self.view.setCurrentText('Original')
            self.canvas.show_image(self.preview); self.save.setEnabled(True)
            self.image_info.setText(f'{self.data.format} · {self.data.width} × {self.data.height} · mode {self.data.mode} · première image, coordonnées originales')
            self.palette.setText('Palette approximative : ' + (' · '.join(f'{color} ({share:.1%})' for color, share in self.data.palette) or 'aucun pixel visible') + f'\n{self.data.sample_count:,} pixels visibles échantillonnés · sans gestion ICC.')
            self.histogram.rows = self.data.histograms; self.histogram.update()
            self.metadata.setPlainText(self.data.metadata)
            self.start.setMaximum(self.data.width*self.data.height-1)
        elif 'preview' in value:
            self.preview = value['preview']; self.canvas.show_image(self.preview)
        elif 'bits' in value:
            raw = value['bits']; result = texts.output(raw)
            self.bits_result.setPlainText(f'{len(raw)} octets extraits, sans interprétation automatique.\nHEX : {raw.hex()}\nUTF-8 : ' + (result.text if result.text is not None else 'invalide'))
        self.status.setText('Export créé : ' + value['saved'] if 'saved' in value else 'Traitement terminé localement.')
        self.pending = ''
