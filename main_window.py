import os
import json
import traceback
import pandas as pd
from datetime import datetime

from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QSplitter, QPushButton, QFileDialog,
                             QTabWidget, QComboBox, QLabel, QTableWidget,
                             QTableWidgetItem, QHeaderView, QAbstractItemView,
                             QProgressBar, QStyle, QStatusBar)
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


class MetadataWorker(QThread):
    """Background thread to extract metadata without blocking UI."""
    progress = Signal(int, int)
    result_ready = Signal(dict)

    def __init__(self, folder, files):
        super().__init__()
        self.folder = folder
        self.files = files

    def run(self):
        results = {}
        total = len(self.files)
        cache_path = os.path.join(self.folder, ".fit_meta_cache.json")
        cache = {}
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r') as f:
                    cache = json.load(f)
            except Exception:
                pass

        for i, fname in enumerate(self.files):
            fpath = os.path.join(self.folder, fname)
            try:
                mtime = os.path.getmtime(fpath)
            except OSError:
                continue

            cached_meta = cache.get(fname)
            if cached_meta and cached_meta.get('_mtime') == mtime:
                meta = cached_meta
            else:
                meta = self._extract(fpath)
                meta['_mtime'] = mtime
                cache[fname] = meta

            results[fname] = meta
            self.progress.emit(i + 1, total)

        try:
            with open(cache_path, 'w') as f:
                json.dump(cache, f)
        except Exception:
            pass

        self.result_ready.emit(results)

    def _extract(self, fpath):
        meta = {
            'date_str': '', 'date_sort': '', 'sport': '',
            'dist_str': '', 'dist_km': 0.0,
            'dur_str': '', 'dur_sec': 0,
            'lat': None, 'lon': None
        }
        try:
            fitfile = FitFile(fpath)
            for session in fitfile.get_messages('session'):
                ts = session.get_value('start_time') or session.get_value('timestamp')
                if ts and isinstance(ts, datetime):
                    meta['date_str'] = ts.strftime('%Y-%m-%d %H:%M')
                    meta['date_sort'] = ts.strftime('%Y%m%d%H%M%S')

                sport = session.get_value('sport')
                if sport:
                    meta['sport'] = str(sport).capitalize()

                dist = session.get_value('total_distance')
                if dist is not None:
                    dist_km = dist / 1000.0
                    meta['dist_km'] = dist_km
                    meta['dist_str'] = f"{dist_km:.1f} km"

                dur = session.get_value('total_timer_time')
                if dur is not None:
                    meta['dur_sec'] = int(dur)
                    h = int(dur // 3600)
                    m = int((dur % 3600) // 60)
                    if h > 0:
                        meta['dur_str'] = f"{h}h {m:02d}m"
                    else:
                        meta['dur_str'] = f"{m}m"

                start_lat = session.get_value('start_position_lat')
                start_lon = session.get_value('start_position_long')
                if start_lat is not None and start_lon is not None:
                    meta['lat'] = semicircles_to_degrees(start_lat)
                    meta['lon'] = semicircles_to_degrees(start_lon)
                break

            if meta['lat'] is None:
                for record in fitfile.get_messages('record'):
                    lat = record.get_value('position_lat')
                    lon = record.get_value('position_long')
                    if lat is not None and lon is not None:
                        meta['lat'] = semicircles_to_degrees(lat)
                        meta['lon'] = semicircles_to_degrees(lon)
                        break
        except Exception as e:
            print(f"Metadata extraction failed for {fpath}: {e}")
        return meta



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
                
                flag = ""
                if cc and len(cc) == 2:
                    try:
                        flag = chr(ord(cc[0].upper()) + 127397) + chr(ord(cc[1].upper()) + 127397) + " "
                    except Exception:
                        pass
                        
                if admin1 and name:
                    out[fname] = f"{flag}{name}, {admin1}"
                elif name:
                    out[fname] = f"{flag}{name}, {cc}"
                else:
                    out[fname] = f"{flag}{cc}"
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
        self.current_folder = self.data_model.config.get('settings', {}).get('last_folder', os.getcwd())
        if not os.path.exists(self.current_folder):
            self.current_folder = os.getcwd()
            
        self._file_meta = {}       # {filename: {date, sport, dist, duration, lat, lon}}
        self._geo_cache_path = ""  # path to geocode cache file
        self._geo_cache = {}       # {filename: location_string}
        self._geo_worker = None
        self._meta_worker = None

        self._init_ui()
        self.apply_theme()
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
        self.plot_widget.cursorMoved.connect(self._on_cursor_moved)
        plot_layout.addWidget(self.plot_widget)

        self.v_splitter.addWidget(plot_container)

        # --- Right Panel: Sidebar ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # Folder selection
        folder_layout = QHBoxLayout()
        self.btn_select_folder = QPushButton(" Select Folder")
        self.btn_select_folder.setIcon(self.style().standardIcon(QStyle.SP_DirIcon))
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
        
        # Connect dashboard track weight change
        self.dashboard.bike_weight_changed.connect(self._on_track_weight_changed)
        
        # Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.status_bar.addPermanentWidget(self.progress_bar)

    def apply_theme(self):
        theme_name = self.data_model.config.get('settings', {}).get('theme', 'light')
        theme_path = os.path.join(os.path.dirname(__file__), 'themes', f"{theme_name}.qss")
        if os.path.exists(theme_path):
            with open(theme_path, 'r') as f:
                self.setStyleSheet(f.read())
        
        import pyqtgraph as pg
        if 'dark' in theme_name or 'high_contrast' in theme_name:
            bg_col = '#1e1e1e' if theme_name == 'dark' else ('#154360' if theme_name == 'dark_blue' else ('#1e8449' if theme_name == 'dark_green' else 'k'))
            fg_col = '#e0e0e0' if theme_name == 'dark' else ('#d4e6f1' if theme_name == 'dark_blue' else ('#d5f5e3' if theme_name == 'dark_green' else 'w'))
            pg.setConfigOption('background', bg_col)
            pg.setConfigOption('foreground', fg_col)
            if hasattr(self, 'plot_widget'):
                self.plot_widget.plot_widget.setBackground(bg_col)
        else:
            pg.setConfigOption('background', 'w')
            pg.setConfigOption('foreground', 'k')
            if hasattr(self, 'plot_widget'):
                self.plot_widget.plot_widget.setBackground('w')
            
        self.update_plot()

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
            
        self.data_model.config.setdefault('settings', {})['last_folder'] = self.current_folder
        self.data_model.save_config(self.data_model.config)

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
                            if f.lower().endswith('.fit') or f.lower().endswith('.gpx')])
                            
        if not fit_files:
            self.status_bar.showMessage("No fit/gpx files found in directory.", 3000)
            return

        self.status_bar.showMessage("Loading folder...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, len(fit_files))
        
        self._meta_worker = MetadataWorker(self.current_folder, fit_files)
        self._meta_worker.progress.connect(self.progress_bar.setValue)
        self._meta_worker.result_ready.connect(self._on_metadata_done)
        self._meta_worker.start()

    def _on_metadata_done(self, results):
        self._file_meta = results
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage(f"Loaded {len(results)} files.", 3000)
        
        coords_to_geocode = {}
        for fname, meta in self._file_meta.items():
            row = self.file_table.rowCount()
            self.file_table.insertRow(row)

            date_item = SortableTableItem(meta.get('date_str', ''))
            date_item.setData(Qt.UserRole, meta.get('date_sort', ''))
            self.file_table.setItem(row, 0, date_item)

            sport_str = meta.get('sport', '')
            sport_map = {'Cycling': '🚴', 'Running': '🏃', 'Swimming': '🏊', 'Walking': '🚶', 'Hiking': '🥾'}
            sport_display = sport_map.get(sport_str, sport_str)
            sport_item = QTableWidgetItem(sport_display)
            # Make the sport emoji slightly larger
            font = sport_item.font()
            font.setPointSize(16)
            sport_item.setFont(font)
            sport_item.setTextAlignment(Qt.AlignCenter)
            self.file_table.setItem(row, 1, sport_item)

            dist_item = SortableTableItem(meta.get('dist_str', ''))
            dist_item.setData(Qt.UserRole, meta.get('dist_km', 0.0))
            self.file_table.setItem(row, 2, dist_item)

            dur_item = SortableTableItem(meta.get('dur_str', ''))
            dur_item.setData(Qt.UserRole, meta.get('dur_sec', 0))
            self.file_table.setItem(row, 3, dur_item)

            loc = self._geo_cache.get(fname, '')
            self.file_table.setItem(row, 4, QTableWidgetItem(loc if loc else '...'))

            if not loc and meta.get('lat') is not None and meta.get('lon') is not None:
                coords_to_geocode[fname] = (meta['lat'], meta['lon'])

            file_item = QTableWidgetItem(fname)
            self.file_table.setItem(row, 5, file_item)

        self.file_table.setSortingEnabled(True)
        self.file_table.sortByColumn(0, Qt.DescendingOrder)

        if coords_to_geocode:
            self._geo_worker = GeocoderWorker(coords_to_geocode)
            self._geo_worker.result_ready.connect(self._on_geocode_done)
            self._geo_worker.start()

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
            if file_name.lower().endswith('.fit'):
                success = self.data_model.load_fit_file(file_path)
            elif file_name.lower().endswith('.gpx'):
                success = self.data_model.load_gpx_file(file_path)
            else:
                success = False
                
            if success:
                # Apply track-specific bike weight if cached
                cached_meta = self._file_meta.get(file_name, {})
                if 'track_bike_weight' in cached_meta:
                    self.data_model.summary['track_bike_weight'] = cached_meta['track_bike_weight']
                    self.data_model._calculate_metrics() # recalc with track weight
                
                self.update_ui()
        except Exception as e:
            print(f"Error loading {file_name}: {e}")
            traceback.print_exc()

    def reanalyze_current_file(self):
        self.apply_theme()
        selected = self.file_table.selectedItems()
        if selected:
            self.on_file_selected()

    def _on_track_weight_changed(self, weight):
        selected = self.file_table.selectedItems()
        if not selected: return
        fname = self.file_table.item(selected[0].row(), 5).text()
        
        # update cache and data model
        if fname in self._file_meta:
            self._file_meta[fname]['track_bike_weight'] = weight
            
            # update cache file
            cache_path = os.path.join(self.current_folder, ".fit_meta_cache.json")
            try:
                with open(cache_path, 'w') as f:
                    json.dump(self._file_meta, f)
            except Exception: pass
            
        self.data_model.summary['track_bike_weight'] = weight
        self.data_model._calculate_metrics()
        self.update_ui()

    def update_ui(self):
        # Update Dashboard
        default_bw = self.data_model.config['equipment'].get('bike_weight_kg', 10)
        self.dashboard.update_dashboard(self.data_model.summary, self.data_model.sport, default_bw)

        # Update Map
        track = self.data_model.get_map_track()
        self.map_widget.plot_track(track)

        # Update Plot
        self.update_plot()

    def _on_cursor_moved(self, idx):
        if not self.data_model.data.empty and idx < len(self.data_model.data):
            try:
                lat = self.data_model.data['position_lat'].iloc[idx]
                lon = self.data_model.data['position_long'].iloc[idx]
                if pd.notna(lat) and pd.notna(lon):
                    self.map_widget.update_cursor(lat, lon)
            except Exception:
                pass

    def update_plot(self):
        x_axis_type = 'elapsed_time'
        x_label = "Time (min)"
        if self.x_axis_combo.currentIndex() == 1:
            x_axis_type = 'distance'
            x_label = "Distance (km)"

        x_data, y_data = self.data_model.get_plot_data(x_axis=x_axis_type)
        if x_data is not None:
            self.plot_widget.plot_data(x_data, y_data, x_label)
