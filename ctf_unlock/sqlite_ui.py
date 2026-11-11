"""Inspecteur SQLite : toutes les opérations disque/SQL sont déléguées au worker."""
from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFileDialog, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QSpinBox,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)
from . import sqlite_tools as sql


def label(value):
    item = QLabel(value)
    item.setTextFormat(Qt.TextFormat.PlainText)
    item.setWordWrap(True)
    return item


def button(value, slot):
    item = QPushButton(value)
    item.clicked.connect(slot)
    return item


class SQLitePanel(QWidget):
    requested = Signal(object)
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self.catalog = self.page = self.loaded = None
        self.history = []
        layout = QVBoxLayout(self)
        layout.addWidget(label('SQLite local · tables, schéma, requêtes et exports'))
        layout.addWidget(label('Lecture seule sur copie temporaire. Bases SQLite non chiffrées uniquement ; aucune connexion serveur, import de dump ou récupération de lignes supprimées.'))
        row = QHBoxLayout()
        self.path = QLineEdit(); self.path.setReadOnly(True)
        row.addWidget(self.path, 1)
        row.addWidget(button('Choisir une base', self.choose))
        row.addWidget(button('Analyser', self.analyze))
        layout.addLayout(row)
        self.info = label('Choisissez une base SQLite. La signature sera vérifiée.')
        layout.addWidget(self.info)
        self.tables = QComboBox()
        self.tables.setPlaceholderText('Choisir une table ou une vue')
        self.tables.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.tables.setMinimumContentsLength(16)
        self.tables.currentIndexChanged.connect(self.schema)
        layout.addWidget(self.tables)
        self.structure = QPlainTextEdit(); self.structure.setReadOnly(True); self.structure.setFixedHeight(140)
        layout.addWidget(self.structure)
        row = QHBoxLayout()
        self.filter = QLineEdit(); self.filter.setPlaceholderText('Filtrer les valeurs de la table (texte littéral)'); self.filter.setMaxLength(256)
        self.limit = QSpinBox(); self.limit.setRange(1, sql.MAX_ROWS); self.limit.setValue(100); self.limit.setPrefix('Lignes : ')
        row.addWidget(self.filter, 1); row.addWidget(self.limit)
        row.addWidget(button('Lire la table', self.read_table))
        layout.addLayout(row)
        self.editor = QPlainTextEdit(); self.editor.setPlaceholderText('SELECT … ou WITH … SELECT …'); self.editor.setFixedHeight(100)
        layout.addWidget(self.editor)
        layout.addWidget(button('Exécuter la requête de lecture', self.read_query))
        self.result = QTableWidget()
        self.result.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.result.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.result.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.result.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.result.horizontalHeader().setDefaultSectionSize(180)
        self.result.setMinimumWidth(1); self.result.setFixedHeight(220)
        layout.addWidget(self.result)
        row = QHBoxLayout()
        self.previous = button('Page précédente', lambda: self.move(False))
        self.next = button('Page suivante', lambda: self.move(True))
        self.json = button('Exporter JSON', lambda: self.export('json'))
        self.csv = button('Exporter CSV', lambda: self.export('csv'))
        for item in (self.previous, self.next, self.json, self.csv):
            item.setEnabled(False); row.addWidget(item)
        layout.addLayout(row)
        self.status = label('Sélectionnez des lignes pour les exporter, sinon toute la page sera exportée. Les exports peuvent contenir les données sensibles du challenge.')
        layout.addWidget(self.status)
        layout.addWidget(label('Limites : base 256 Mio, WAL 64 Mio ; 128 objets/colonnes ; 5 s par requête ; 500 lignes, 10 000 cellules et 2 Mio par page ; cellule 1 Mio. La pagination sans ORDER BY n’assure pas un ordre stable.'))

    def error(self, exc):
        self.status.setText('Erreur : ' + str(exc))
        self.failed.emit(str(exc))

    def choose(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Choisir une base SQLite locale', '', 'SQLite (*.sqlite *.sqlite3 *.db);;Tous les fichiers (*)')
        if path:
            self.path.setText(path)
            self.analyze()

    def clear_page(self):
        self.page = self.loaded = None
        self.history = []
        self.result.clear(); self.result.setRowCount(0); self.result.setColumnCount(0)
        for item in (self.previous, self.next, self.json, self.csv):
            item.setEnabled(False)

    def analyze(self):
        if not self.path.text():
            self.error('Choisissez un fichier SQLite.'); return
        self.catalog = None
        self.clear_page()
        self.tables.clear(); self.structure.clear(); self.info.setText('Analyse en cours…')
        path = self.path.text()
        self.requested.emit(lambda abort: {'catalog': sql.inspect_database(path, abort)})

    def schema(self, index):
        if not self.catalog or index < 0:
            return
        catalog, name = self.catalog, self.tables.currentData()
        self.editor.setPlainText('SELECT * FROM ' + sql.identifier(name))
        self.requested.emit(lambda abort: {'schema': sql.object_schema(catalog, name, abort)})

    def read_table(self):
        if not self.catalog or self.tables.currentIndex() < 0:
            self.error('Choisissez une table.'); return
        self.request_page(('table', self.tables.currentData(), self.filter.text(), self.limit.value()), 0)

    def read_query(self):
        if not self.catalog:
            self.error('Analysez d’abord une base.'); return
        self.request_page(('query', self.editor.toPlainText(), '', self.limit.value()), 0)

    def request_page(self, request, offset):
        catalog = self.catalog
        def action(abort):
            kind, value, needle, limit = request
            page = sql.table_page(catalog, value, needle, limit, offset, abort) if kind == 'table' else sql.query(catalog, value, limit, offset, abort=abort)
            return {'page': page, 'request': request}
        self.requested.emit(action)

    def move(self, forward):
        if self.page and self.loaded:
            offset = self.page.offset + len(self.page.rows) if forward else (self.history[-1] if self.history else 0)
            self.request_page(self.loaded, offset)

    def export(self, kind):
        if not self.page:
            return
        selected = [item.row() for item in self.result.selectionModel().selectedRows()]
        path, _ = QFileDialog.getSaveFileName(self, 'Créer un export de la sélection ou de la page', 'CTF-Unlock-donnees.' + kind, kind.upper() + ' (*.' + kind + ')')
        if path:
            page = self.page
            self.requested.emit(lambda abort: {'saved': sql.export_page(page, path, kind, selected, abort)})

    def complete(self, value):
        if 'catalog' in value:
            self.catalog = value['catalog']
            self.tables.blockSignals(True)
            self.tables.clear()
            for name, kind, definition in self.catalog.objects:
                self.tables.addItem(f'{name} ({kind})', name)
            self.tables.setCurrentIndex(-1)
            self.tables.blockSignals(False)
            self.info.setText(f'SQLite · {self.catalog.fingerprint[0][2]:,} octets · {len(self.catalog.objects)} tables/vues' + (' (liste limitée)' if self.catalog.limited else '') + (' · WAL copié' if self.catalog.wal else '') + '\nChoisissez une table ou écrivez une requête SELECT.')
            self.status.setText('Base analysée en lecture seule. Aucune ligne encore lue.')
        elif 'schema' in value:
            self.structure.setPlainText(value['schema'])
            self.status.setText('Schéma lu. Les indices reposent sur les noms, pas sur une détection de secrets.')
        elif 'page' in value:
            page, request = value['page'], value['request']
            if not self.page or request != self.loaded or page.offset == 0:
                self.history = []
            elif page.offset > self.page.offset:
                self.history.append(self.page.offset)
            elif self.history and page.offset == self.history[-1]:
                self.history.pop()
            self.page, self.loaded = page, request
            self.result.clear(); self.result.setColumnCount(len(page.columns)); self.result.setRowCount(len(page.rows))
            self.result.setHorizontalHeaderLabels(page.columns)
            for r, row in enumerate(page.rows):
                for c, item in enumerate(row):
                    rendered = 'NULL' if item is None else ('hex:' + item[:128].hex() + f' ({len(item)} octets)' if isinstance(item, bytes) else str(item))
                    self.result.setItem(r, c, QTableWidgetItem(rendered[:512]))
            self.previous.setEnabled(page.offset > 0)
            self.next.setEnabled(page.more and page.offset + len(page.rows) <= 10000000)
            self.json.setEnabled(True); self.csv.setEnabled(True)
            self.status.setText(f'{len(page.rows)} lignes à partir de {page.offset} · ' + ('suite disponible ou limite de page atteinte' if page.more else 'fin du résultat') + '. Affichage des cellules limité ; export des valeurs complètes de cette page.')
        elif 'saved' in value:
            self.status.setText('Export créé : ' + value['saved'])
