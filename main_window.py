import os
import json
import traceback
from datetime import datetime

from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QSplitter, QPushButton, QFileDialog,
                             QTabWidget, QComboBox, QLabel, QTableWidget,
                             QTableWidgetItem, QHeaderView, QAbstractItemView)
from PySide6.QtCore import Qt, QThread, Signal

from fitparse import FitFile
from data_model import FitAnalyzer, semicircles_to_degrees
from widgets.plot_widget import FitPlotWidget
from widgets.map_widget import MapWidget
from widgets.config_widget import ConfigWidget
from widgets.dashboard_widget import DashboardWidget


class SortableTableItem(QTableWidgetItem):
    """QTableWidgetItem that sorts by UserRole data (numeric) instead of display text."""
    def __lt__(self, other):
        my_data = self.data(Qt.UserRole)
        other_data = other.data(Qt.UserRole)
        if my_data is not None and other_data is not None:
            try:
                return float(my_data) < float(other_data)
            except (ValueError, TypeError):
                return str(my_data) < str(other_data)
        return super().__lt__(other)


class GeocoderWorker(QThread):
    """Background thread to reverse-geocode start coordinates without blocking UI."""
    result_ready = Signal(dict)  # {filename: location_string}

    def __init__(self, coords_by_file):
        super().__init__()
        self.coords_by_file = coords_by_file  # {filename: (lat, lon)}

    def run(self):
        try:
            import reverse_geocoder as rg
            if not self.coords_by_file:
                self.result_ready.emit({})
                return

            filenames = list(self.coords_by_file.keys())
            coord_list = [self.coords_by_file[f] for f in filenames]

            results = rg.search(coord_list)
            out = {}
            for fname, geo in zip(filenames, results):
                name = geo.get('name', '')
                admin1 = geo.get('admin1', '')
                cc = geo.get('cc', '')
                if admin1 and name:
                    out[fname] = f"{name}, {admin1}"
                elif name:
                    out[fname] = f"{name}, {cc}"
                else:
                    out[fname] = cc
            self.result_ready.emit(out)
        except Exception as e:
            print(f"Geocoder error: {e}")
            self.result_ready.emit({})


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fit File Analyzer")
        self.resize(1400, 900)

        self.data_model = FitAnalyzer()
        self.current_folder = os.getcwd()
        self._file_meta = {}       # {filename: {date, sport, dist, duration, lat, lon}}
        self._geo_cache_path = ""  # path to geocode cache file
        self._geo_cache = {}       # {filename: location_string}
        self._geo_worker = None

        self._init_ui()
        self.load_folder()

    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        self.splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(self.splitter)

        # --- Left Panel: Map & Plot ---
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # Inner splitter for Map and Plot
        self.v_splitter = QSplitter(Qt.Vertical)
        left_layout.addWidget(self.v_splitter)

        self.map_widget = MapWidget()
        self.v_splitter.addWidget(self.map_widget)

        # Plot area with controls
        plot_container = QWidget()
        plot_layout = QVBoxLayout(plot_container)
        plot_layout.setContentsMargins(0, 0, 0, 0)

        # Plot Controls
        plot_controls = QHBoxLayout()
        plot_controls.addWidget(QLabel("X-Axis:"))
        self.x_axis_combo = QComboBox()
        self.x_axis_combo.addItems(["Time (minutes)", "Distance (km)"])
        self.x_axis_combo.currentIndexChanged.connect(self.update_plot)
        plot_controls.addWidget(self.x_axis_combo)
        plot_controls.addStretch()
        plot_layout.addLayout(plot_controls)

        self.plot_widget = FitPlotWidget()
        plot_layout.addWidget(self.plot_widget)

        self.v_splitter.addWidget(plot_container)

        # --- Right Panel: Sidebar ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # Folder selection
        folder_layout = QHBoxLayout()
        self.btn_select_folder = QPushButton("Select Folder")
        self.btn_select_folder.clicked.connect(self.select_folder)
        folder_layout.addWidget(self.btn_select_folder)
        right_layout.addLayout(folder_layout)

        # File Table (replaces QListWidget)
        self.file_table = QTableWidget()
        self.file_table.setColumnCount(6)
        self.file_table.setHorizontalHeaderLabels(
            ["Date", "Sport", "Distance", "Duration", "Location", "File"])
        self.file_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.file_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.file_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.file_table.setSortingEnabled(True)
        self.file_table.horizontalHeader().setStretchLastSection(True)
        self.file_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.file_table.verticalHeader().setVisible(False)
        self.file_table.itemSelectionChanged.connect(self.on_file_selected)
        right_layout.addWidget(self.file_table)

        # Tabs for Dashboard / Config
        self.tabs = QTabWidget()
        self.dashboard = DashboardWidget()
        self.config_widget = ConfigWidget(self.data_model)

        self.tabs.addTab(self.dashboard, "Dashboard")
        self.tabs.addTab(self.config_widget, "Settings")
        right_layout.addWidget(self.tabs)

        # Connect save config to re-analyze current file
        self.config_widget.save_btn.clicked.connect(self.reanalyze_current_file)

        self.splitter.addWidget(left_panel)
        self.splitter.addWidget(right_panel)

        # Set splitter ratios
        self.splitter.setSizes([800, 600])
        self.v_splitter.setSizes([400, 400])

    # ---- Folder & File Scanning ----

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Fit Files Folder")
        if folder:
            self.current_folder = folder
            self.load_folder()

    def load_folder(self):
        self.file_table.setSortingEnabled(False)  # disable during population
        self.file_table.setRowCount(0)
        self._file_meta.clear()

        if not self.current_folder:
            return

        # Load geocode cache
        self._geo_cache_path = os.path.join(self.current_folder, ".fit_geo_cache.json")
        self._geo_cache = {}
        if os.path.exists(self._geo_cache_path):
            try:
                with open(self._geo_cache_path, 'r') as f:
                    self._geo_cache = json.load(f)
            except Exception:
                pass

        fit_files = sorted([f for f in os.listdir(self.current_folder)
                            if f.lower().endswith('.fit')])

        coords_to_geocode = {}  # files that need geocoding

        for fname in fit_files:
            meta = self._extract_file_metadata(fname)
            self._file_meta[fname] = meta

            row = self.file_table.rowCount()
            self.file_table.insertRow(row)

            # Date — use SortableTableItem that sorts by the raw datetime string
            date_item = SortableTableItem(meta.get('date_str', ''))
            date_item.setData(Qt.UserRole, meta.get('date_sort', ''))
            self.file_table.setItem(row, 0, date_item)

            # Sport
            self.file_table.setItem(row, 1, QTableWidgetItem(meta.get('sport', '')))

            # Distance — sortable numeric
            dist_item = SortableTableItem(meta.get('dist_str', ''))
            dist_item.setData(Qt.UserRole, meta.get('dist_km', 0.0))
            self.file_table.setItem(row, 2, dist_item)

            # Duration — sortable numeric
            dur_item = SortableTableItem(meta.get('dur_str', ''))
            dur_item.setData(Qt.UserRole, meta.get('dur_sec', 0))
            self.file_table.setItem(row, 3, dur_item)

            # Location — from cache or pending geocode
            loc = self._geo_cache.get(fname, '')
            self.file_table.setItem(row, 4, QTableWidgetItem(loc if loc else '...'))

            if not loc and meta.get('lat') is not None and meta.get('lon') is not None:
                coords_to_geocode[fname] = (meta['lat'], meta['lon'])

            # Filename (hidden sort key for loading)
            file_item = QTableWidgetItem(fname)
            self.file_table.setItem(row, 5, file_item)

        self.file_table.setSortingEnabled(True)
        self.file_table.sortByColumn(0, Qt.DescendingOrder)  # newest first

        # Kick off background geocoding for uncached files
        if coords_to_geocode:
            self._geo_worker = GeocoderWorker(coords_to_geocode)
            self._geo_worker.result_ready.connect(self._on_geocode_done)
            self._geo_worker.start()

    def _extract_file_metadata(self, filename):
        """Quickly parse session metadata from a .fit file without full analysis."""
        meta = {
            'date_str': '', 'date_sort': '', 'sport': '',
            'dist_str': '', 'dist_km': 0.0,
            'dur_str': '', 'dur_sec': 0,
            'lat': None, 'lon': None
        }
        fpath = os.path.join(self.current_folder, filename)
        try:
            fitfile = FitFile(fpath)

            # Get session data
            for session in fitfile.get_messages('session'):
                # Date
                ts = session.get_value('start_time') or session.get_value('timestamp')
                if ts and isinstance(ts, datetime):
                    meta['date_str'] = ts.strftime('%Y-%m-%d %H:%M')
                    meta['date_sort'] = ts.strftime('%Y%m%d%H%M%S')

                # Sport
                sport = session.get_value('sport')
                if sport:
                    meta['sport'] = str(sport).capitalize()

                # Distance
                dist = session.get_value('total_distance')
                if dist is not None:
                    dist_km = dist / 1000.0
                    meta['dist_km'] = dist_km
                    meta['dist_str'] = f"{dist_km:.1f} km"

                # Duration
                dur = session.get_value('total_timer_time')
                if dur is not None:
                    meta['dur_sec'] = int(dur)
                    h = int(dur // 3600)
                    m = int((dur % 3600) // 60)
                    if h > 0:
                        meta['dur_str'] = f"{h}h {m:02d}m"
                    else:
                        meta['dur_str'] = f"{m}m"

                # Start coordinates (for geocoding)
                start_lat = session.get_value('start_position_lat')
                start_lon = session.get_value('start_position_long')
                if start_lat is not None and start_lon is not None:
                    meta['lat'] = semicircles_to_degrees(start_lat)
                    meta['lon'] = semicircles_to_degrees(start_lon)

                break  # only need first session

            # If no start coords from session, grab first record
            if meta['lat'] is None:
                for record in fitfile.get_messages('record'):
                    lat = record.get_value('position_lat')
                    lon = record.get_value('position_long')
                    if lat is not None and lon is not None:
                        meta['lat'] = semicircles_to_degrees(lat)
                        meta['lon'] = semicircles_to_degrees(lon)
                        break

        except Exception as e:
            print(f"Metadata extraction failed for {filename}: {e}")

        return meta

    def _on_geocode_done(self, results):
        """Called when background geocoding finishes. Update table and cache."""
        self._geo_cache.update(results)

        # Update table cells
        for row in range(self.file_table.rowCount()):
            fname_item = self.file_table.item(row, 5)
            if fname_item:
                fname = fname_item.text()
                if fname in results:
                    self.file_table.item(row, 4).setText(results[fname])

        # Save cache
        try:
            with open(self._geo_cache_path, 'w') as f:
                json.dump(self._geo_cache, f, indent=2)
        except Exception:
            pass

    # ---- File Selection & Analysis ----

    def on_file_selected(self):
        selected = self.file_table.selectedItems()
        if not selected:
            return

        row = selected[0].row()
        fname_item = self.file_table.item(row, 5)
        if not fname_item:
            return

        file_name = fname_item.text()
        file_path = os.path.join(self.current_folder, file_name)

        try:
            if self.data_model.load_fit_file(file_path):
                self.update_ui()
        except Exception as e:
            print(f"Error loading {file_name}: {e}")
            traceback.print_exc()

    def reanalyze_current_file(self):
        selected = self.file_table.selectedItems()
        if selected:
            self.on_file_selected()

    def update_ui(self):
        # Update Dashboard
        self.dashboard.update_dashboard(self.data_model.summary, self.data_model.sport)

        # Update Map
        track = self.data_model.get_map_track()
        self.map_widget.plot_track(track)

        # Update Plot
        self.update_plot()

    def update_plot(self):
        x_axis_type = 'elapsed_time'
        x_label = "Time (min)"
        if self.x_axis_combo.currentIndex() == 1:
            x_axis_type = 'distance'
            x_label = "Distance (km)"

        x_data, y_data = self.data_model.get_plot_data(x_axis=x_axis_type)
        if x_data is not None:
            self.plot_widget.plot_data(x_data, y_data, x_label)
