from pathlib import Path
import sys
import time

from PySide6.QtCore import QObject, Property, QPropertyAnimation, QRunnable, QSize, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QPlainTextEdit,
    QProgressBar, QPushButton, QScrollArea, QSpinBox, QStackedWidget, QVBoxLayout, QWidget)

from .archives import inspect
from .candidates import Dictionary, Mask
from .engine import SevenZip, find_7zip
from .models import Limits, Outcome, Progress, Result
from .tasks import Control, recover


def resources():
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))


def text(value, name=''):
    widget = QLabel(value)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    widget.setObjectName(name)
    return widget


def button(value, slot, name=''):
    widget = QPushButton(value)
    widget.setObjectName(name)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    widget.clicked.connect(slot)
    return widget


class SlideSwitch(QCheckBox):
    def __init__(self, title):
        super().__init__(title)
        self._position = 0.0
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(title)
        self.animation = QPropertyAnimation(self, b'position')
        self.animation.setDuration(140)
        self.toggled.connect(self.slide)

    def get_position(self):
        return self._position

    def set_position(self, value):
        self._position = value
        self.update()

    position = Property(float, get_position, set_position)

    def slide(self, checked):
        self.animation.stop()
        self.animation.setStartValue(self._position)
        self.animation.setEndValue(float(checked))
        self.animation.start()

    def sizeHint(self):
        return QSize(55 + self.fontMetrics().horizontalAdvance(self.text()), 30)

    def hitButton(self, point):
        return self.rect().contains(point)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor('#c9c9c9' if self.isChecked() else '#444444'))
        painter.drawRoundedRect(0, 4, 42, 22, 11, 11)
        painter.setBrush(QColor('#171717' if self.isChecked() else '#dddddd'))
        painter.drawEllipse(int(3 + 18 * self._position), 7, 16, 16)
        painter.setPen(QColor('#eeeeea' if self.isEnabled() else '#777777'))
        painter.drawText(self.rect().adjusted(54, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, self.text())
        if self.hasFocus():
            painter.setPen(QColor('#ffffff'))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 5, 5)


class FileDrop(QFrame):
    selected = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName('drop')
        self.setAcceptDrops(True)
        layout = QVBoxLayout(self)
        layout.addWidget(text('ZIP / 7z', 'dropTitle'))
        layout.addWidget(text('Déposez une archive ici\nou sélectionnez-la ci-dessous.', 'muted'))

    def dragEnterEvent(self, event):
        urls = event.mimeData().urls()
        if len(urls) == 1 and urls[0].isLocalFile():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if len(urls) == 1 and urls[0].isLocalFile():
            self.selected.emit(urls[0].toLocalFile())
            event.acceptProposedAction()


class Signals(QObject):
    done = Signal(object)
    progress = Signal(object)


class Worker(QRunnable):
    def __init__(self, action):
        super().__init__()
        self.action = action
        self.signals = Signals()

    def run(self):
        try:
            result = self.action(self.signals.progress.emit)
        except Exception as exc:
            result = Result(Outcome.ERROR, str(exc))
        self.signals.done.emit(result)


class MainWindow(QMainWindow):
    def __init__(self, engine_path=None):
        super().__init__()
        self.setWindowTitle('CTF Unlock · its lizhy')
        self.resize(1100, 820)
        self.setMinimumSize(920, 740)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.busy = False
        self.recovering = False
        self.closing = False
        self.control = Control()
        self.result = None
        self.latest = Progress(0, None, 0, '')
        self.started = 0
        root = QWidget()
        row = QHBoxLayout(root)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        side = QFrame()
        side.setObjectName('sidebar')
        side.setFixedWidth(205)
        nav = QVBoxLayout(side)
        nav.setContentsMargins(22, 30, 22, 24)
        nav.addWidget(text('U /', 'mark'))
        nav.addWidget(text('CTF Unlock', 'brand'))
        nav.addWidget(text('L’ATELIER HORS LIGNE', 'micro'))
        nav.addSpacing(35)
        self.tabs = []
        for index, title in enumerate(['01   Fichier', '02   Méthode', '03   Réglages', '04   Résultats']):
            tab = button(title, lambda checked=False, i=index: self.navigate(i), 'nav')
            tab.setCheckable(True)
            self.tabs.append(tab)
            nav.addWidget(tab)
        nav.addStretch()
        nav.addWidget(text('LOCAL / SANS COMPTE', 'micro'))
        nav.addWidget(text('its lizhy · Loghan', 'muted'))
        row.addWidget(side)
        layout = QVBoxLayout()
        layout.setContentsMargins(30, 28, 30, 22)
        layout.setSpacing(14)
        layout.addWidget(text('OBSERVER. ESSAYER. VÉRIFIER.', 'micro'))
        layout.addWidget(text('Un fichier. Des pistes.', 'hero'))
        layout.addWidget(text('Récupération locale pour vos challenges CTF et fichiers autorisés.\nZIP et 7z uniquement · aucun résultat garanti.', 'muted'))
        self.pages = QStackedWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.pages)
        layout.addWidget(scroll, 1)
        self.build_file_page()
        self.build_method_page()
        self.build_settings_page(engine_path)
        self.build_results_page()
        self.phase = text('Choisissez une archive et vérifiez le moteur dans Réglages.', 'status')
        layout.addWidget(self.phase)
        self.metrics = text('0 essai · 0,00 essai/s · 0,0 s', 'micro')
        layout.addWidget(self.metrics)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setValue(0)
        self.bar.setTextVisible(False)
        layout.addWidget(self.bar)
        controls = QHBoxLayout()
        self.start_button = button('Démarrer', self.start, 'primary')
        self.pause_button = button('Mettre en pause', self.toggle_pause)
        self.stop_button = button('Arrêter', self.stop)
        self.pause_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        controls.addWidget(self.start_button)
        controls.addWidget(self.pause_button)
        controls.addWidget(self.stop_button)
        layout.addLayout(controls)
        row.addLayout(layout, 1)
        self.setCentralWidget(root)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_metrics)
        self.timer.start(250)
        self.navigate(0)

    def navigate(self, index):
        self.pages.setCurrentIndex(index)
        for i, tab in enumerate(self.tabs):
            tab.setChecked(i == index)

    def page(self, title):
        widget = QFrame()
        widget.setObjectName('panel')
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)
        layout.addWidget(text(title, 'section'))
        self.pages.addWidget(widget)
        return widget, layout

    def build_file_page(self):
        self.file_panel, layout = self.page('Votre fichier')
        drop = FileDrop()
        drop.selected.connect(self.set_file)
        layout.addWidget(drop)
        file_row = QHBoxLayout()
        self.file_path = QLineEdit()
        self.file_path.setReadOnly(True)
        self.file_path.setPlaceholderText('Aucune archive sélectionnée')
        file_row.addWidget(self.file_path)
        file_row.addWidget(button('Parcourir…', self.choose_file))
        layout.addLayout(file_row)
        layout.addWidget(button('Analyser la signature et la protection', self.analyze))
        self.file_info = text('Format : —\nTaille : —\nProtection : —', 'muted')
        layout.addWidget(self.file_info)
        layout.addStretch()

    def build_method_page(self):
        self.method_panel, layout = self.page('Une piste à la fois')
        self.method = QComboBox()
        self.method.addItems(['Liste de mots de passe', 'Masque borné'])
        layout.addWidget(self.method)
        self.methods = QStackedWidget()
        dictionary = QWidget()
        form = QVBoxLayout(dictionary)
        form.setContentsMargins(0, 0, 0, 0)
        self.wordlist = QLineEdit()
        self.wordlist.setPlaceholderText('Liste texte UTF-8 · un candidat par ligne')
        form.addWidget(self.wordlist)
        form.addWidget(button('Choisir la liste…', self.choose_list))
        form.addWidget(text('Les espaces sont conservés. Lignes vides ignorées.\n128 caractères maximum par mot de passe.', 'muted'))
        form.addStretch()
        self.methods.addWidget(dictionary)
        mask = QWidget()
        form = QFormLayout(mask)
        form.setContentsMargins(0, 0, 0, 0)
        self.alphabet = QLineEdit('0123456789')
        self.minimum = QSpinBox()
        self.maximum = QSpinBox()
        for widget, default in [(self.minimum, 1), (self.maximum, 3)]:
            widget.setRange(1, 8)
            widget.setValue(default)
        form.addRow('Caractères distincts autorisés', self.alphabet)
        form.addRow('Longueur minimale', self.minimum)
        form.addRow('Longueur maximale', self.maximum)
        self.mask_size = text('', 'muted')
        form.addRow(self.mask_size)
        self.alphabet.textChanged.connect(self.update_mask)
        self.minimum.valueChanged.connect(self.update_mask)
        self.maximum.valueChanged.connect(self.update_mask)
        self.methods.addWidget(mask)
        layout.addWidget(self.methods)
        self.method.currentIndexChanged.connect(self.methods.setCurrentIndex)
        layout.addWidget(text('7-Zip vérifie l’archive entière pour chaque candidat.\nCe mode convient aux petites listes ciblées ; pas d’accélération GPU.', 'muted'))
        self.update_mask()

    def build_settings_page(self, engine_path):
        self.settings_panel, layout = self.page('Moteur et limites')
        self.engine_path = QLineEdit(find_7zip() if engine_path is None else engine_path)
        self.engine_path.setPlaceholderText('7z.exe ou 7zz · installation officielle requise')
        layout.addWidget(self.engine_path)
        controls = QHBoxLayout()
        controls.addWidget(button('Sélectionner le moteur…', self.choose_engine))
        controls.addWidget(button('Détecter / vérifier la version', self.check_engine))
        layout.addLayout(controls)
        self.engine_version = text('Version non vérifiée. Seul 7-Zip est intégré en v1.', 'muted')
        layout.addWidget(self.engine_version)
        form = QFormLayout()
        self.seconds = QSpinBox(); self.seconds.setRange(1, 3600); self.seconds.setValue(60)
        self.cap = QSpinBox(); self.cap.setRange(1, 1000000); self.cap.setValue(10000)
        self.threads = QSpinBox(); self.threads.setRange(1, 4); self.threads.setValue(1)
        self.memory = QSpinBox(); self.memory.setRange(128, 4096); self.memory.setSingleStep(128); self.memory.setValue(512)
        self.attempt_time = QDoubleSpinBox(); self.attempt_time.setRange(.1, 3600); self.attempt_time.setValue(10)
        self.seconds.valueChanged.connect(self.attempt_time.setMaximum)
        for title, widget in [('Durée totale maximale (s, pauses incluses)', self.seconds), ('Nombre maximal de candidats', self.cap),
                              ('Threads 7-Zip', self.threads), ('Mémoire du moteur (Mio)', self.memory), ('Délai par opération moteur (s)', self.attempt_time)]:
            form.addRow(title, widget)
        layout.addLayout(form)
        layout.addWidget(text('Une seule tâche et un seul processus moteur à la fois.\nLa mémoire limite le moteur, pas l’interface Qt. La pause attend la fin de l’essai courant.', 'muted'))

    def build_results_page(self):
        _, layout = self.page('Résultats réels')
        self.result_title = text('Aucune tâche exécutée.', 'section')
        layout.addWidget(self.result_title)
        self.password = QLineEdit()
        self.password.setReadOnly(True)
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText('Aucun mot de passe vérifié')
        layout.addWidget(self.password)
        self.reveal = SlideSwitch('Afficher le mot de passe trouvé')
        self.reveal.toggled.connect(lambda checked: self.password.setEchoMode(QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password))
        layout.addWidget(self.reveal)
        self.journal = QPlainTextEdit()
        self.journal.setReadOnly(True)
        self.journal.setMaximumBlockCount(300)
        layout.addWidget(self.journal, 1)
        self.details_switch = SlideSwitch('Détails techniques')
        layout.addWidget(self.details_switch)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumBlockCount(500)
        self.details.setMaximumHeight(130)
        self.details.hide()
        self.details_switch.toggled.connect(self.details.setVisible)
        layout.addWidget(self.details)

    def log(self, message):
        self.journal.appendPlainText(message)

    def error(self, message):
        self.phase.setText('Erreur : ' + message)
        self.log('Erreur : ' + message)

    def choose_file(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Choisir une archive', '', 'Tous les fichiers (*)')
        if path:
            self.set_file(path)

    def set_file(self, path):
        if not self.busy:
            self.file_path.setText(path)
            self.file_info.setText('Analyse en attente…')
            self.password.clear()
            self.result = None
            self.result_title.setText('Aucune recherche sur ce fichier.')
            self.analyze()

    def choose_list(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Choisir une liste UTF-8', '', 'Fichiers texte (*.txt);;Tous les fichiers (*)')
        if path:
            self.wordlist.setText(path)

    def choose_engine(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Sélectionner 7z.exe ou 7zz')
        if path:
            self.engine_path.setText(path)

    def limits(self):
        limits = Limits(self.seconds.value(), self.cap.value(), self.threads.value(), self.memory.value(), self.attempt_time.value())
        limits.validate()
        return limits

    def update_mask(self):
        try:
            self.mask_size.setText(f'{self.mask().total:,} candidats possibles avant application des limites.')
        except ValueError as exc:
            self.mask_size.setText(str(exc))

    def mask(self):
        return Mask(self.alphabet.text(), self.minimum.value(), self.maximum.value())

    def begin(self, action, recovering=False):
        if self.busy:
            return
        self.busy = True
        self.recovering = recovering
        self.started = time.monotonic()
        self.latest = Progress(0, None, 0, 'Travail en cours…')
        self.control = Control()
        self.stop_button.setEnabled(True)
        self.start_button.setEnabled(False)
        self.pause_button.setEnabled(recovering)
        self.pause_button.setText('Mettre en pause')
        for panel in (self.file_panel, self.method_panel, self.settings_panel):
            panel.setEnabled(False)
        self.bar.setRange(0, 0)
        self.worker = Worker(action)
        self.worker.signals.progress.connect(self.on_progress)
        self.worker.signals.done.connect(self.done)
        self.pool.start(self.worker)

    def check_engine(self):
        if self.busy:
            return
        try:
            limits = self.limits()
        except ValueError as exc:
            self.error(str(exc)); return
        engine = SevenZip(self.engine_path.text())
        self.begin(lambda progress: {'version': engine.version(limits, lambda: 'Arrêt demandé.' if self.control.cancelled.is_set() else None)})

    def analyze(self):
        if self.busy:
            return
        try:
            path = Path(self.file_path.text())
            if not self.file_path.text():
                raise ValueError('Sélectionnez une archive.')
            limits = self.limits()
        except ValueError as exc:
            self.error(str(exc)); return
        engine = SevenZip(self.engine_path.text())
        def action(progress):
            info = inspect(path)
            data = {'info': info}
            if not info.outcome:
                try:
                    abort = lambda: 'Arrêt demandé.' if self.control.cancelled.is_set() else None
                    data['version'] = engine.version(limits, abort)
                    data['info'] = engine.protection(info, limits, abort)
                except Exception as exc:
                    data['engine_error'] = str(exc)
            return data
        self.begin(action)

    def start(self):
        if self.busy:
            return
        try:
            if not self.file_path.text():
                raise ValueError('Sélectionnez une archive dans Fichier.')
            limits = self.limits()
            source = self.mask() if self.method.currentIndex() else Dictionary(Path(self.wordlist.text()))
            if isinstance(source, Mask):
                source.validate()
            elif not self.wordlist.text() or not source.path.is_file():
                raise ValueError('Choisissez une liste existante dans Méthode.')
            engine = SevenZip(self.engine_path.text())
            path = Path(self.file_path.text())
        except (ValueError, OSError) as exc:
            self.error(str(exc)); return
        self.result = None
        self.password.clear()
        self.reveal.setChecked(False)
        self.details.clear()
        self.result_title.setText('Recherche en cours…')
        self.log('Nouvelle recherche locale. L’original ne sera ni extrait, ni modifié.')
        self.navigate(3)
        self.begin(lambda progress: recover(path, source, engine, limits, self.control, progress), recovering=True)

    def toggle_pause(self):
        if self.busy and self.recovering:
            paused = not self.control.paused.is_set()
            self.control.pause(paused)
            self.pause_button.setText('Reprendre' if paused else 'Mettre en pause')
            self.log('Pause demandée après l’essai courant.' if paused else 'Reprise demandée.')

    def stop(self):
        self.control.stop()
        self.phase.setText('Arrêt demandé · nettoyage des processus…')
        self.stop_button.setEnabled(False)

    def on_progress(self, progress):
        self.latest = progress
        self.phase.setText(progress.phase)
        if progress.phase.startswith('Moteur vérifié : '):
            self.engine_version.setText(progress.phase.removeprefix('Moteur vérifié : '))
            self.log(progress.phase)
        if progress.total:
            self.bar.setRange(0, 1000)
            self.bar.setValue(int(1000 * progress.attempted / progress.total))
        self.refresh_metrics()

    def refresh_metrics(self):
        if self.busy:
            elapsed = time.monotonic() - self.started
            attempts = self.latest.attempted
            total = f' / {self.latest.total:,}' if self.latest.total else ' / total inconnu'
            self.metrics.setText(f'{attempts:,}{total} essais · {attempts / max(elapsed, .001):.2f} essai/s · {elapsed:.1f} s')

    def done(self, value):
        self.busy = False
        self.recovering = False
        for panel in (self.file_panel, self.method_panel, self.settings_panel):
            panel.setEnabled(True)
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.pause_button.setEnabled(False)
        self.bar.setRange(0, 1000)
        self.bar.setValue(0)
        if isinstance(value, Result):
            self.result = value
            self.result_title.setText(str(value.outcome))
            self.phase.setText(str(value.outcome))
            self.metrics.setText(f'{value.attempted:,} essais · {value.attempted / max(value.elapsed, .001):.2f} essai/s · {value.elapsed:.1f} s')
            self.password.setText(value.password or '')
            self.log(f'{value.outcome}\n{value.detail}')
            self.details.setPlainText(value.technical or 'Pas de diagnostic technique supplémentaire. Les arguments contenant les mots de passe ne sont pas journalisés.')
            if value.outcome in (Outcome.FOUND, Outcome.UNPROTECTED):
                self.bar.setValue(1000)
        else:
            self.phase.setText('Analyse terminée.')
            if 'version' in value:
                self.engine_version.setText(value['version'])
                self.log('Moteur vérifié : ' + value['version'])
            if 'info' in value:
                info = value['info']
                protection = 'Oui' if info.protected else 'Non' if info.protected is False else 'Indéterminée'
                self.file_info.setText(f'Format : {info.format} · signature\nTaille : {info.size:,} octets\nProtection : {protection}\n{info.outcome or ""}\n{info.detail}')
            if 'engine_error' in value:
                self.error(value['engine_error'])
                self.engine_version.setText(value['engine_error'])
        if self.closing:
            self.close()

    def closeEvent(self, event):
        if self.busy:
            self.closing = True
            self.stop()
            event.ignore()
        else:
            event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('CTF Unlock')
    app.setOrganizationName('its lizhy')
    app.setStyle('Fusion')
    try:
        app.setStyleSheet((resources() / 'theme.qss').read_text(encoding='utf-8'))
    except OSError as exc:
        print(f'Thème indisponible : {exc}', file=sys.stderr)
    window = MainWindow()
    window.show()
    return app.exec()
