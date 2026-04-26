from PySide6.QtWidgets import QWidget, QFormLayout, QLabel, QVBoxLayout, QGroupBox, QSpinBox
from PySide6.QtCore import Signal

class DashboardWidget(QWidget):
    bike_weight_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        
        # General Stats
        self.general_group = QGroupBox("General")
        self.general_layout = QFormLayout(self.general_group)
        self.sport_label = QLabel("-")
        self.dist_label = QLabel("-")
        self.time_label = QLabel("-")
        self.elev_label = QLabel("-")
        self.cal_label = QLabel("-")
        self.fitness_score_label = QLabel("-")
        self.general_layout.addRow("Sport:", self.sport_label)
        self.general_layout.addRow("Total Distance:", self.dist_label)
        self.general_layout.addRow("Total Time:", self.time_label)
        self.general_layout.addRow("Elevation Gain:", self.elev_label)
        self.general_layout.addRow("Calories:", self.cal_label)
        self.general_layout.addRow("Fitness Score:", self.fitness_score_label)
        
        # Heart Rate Stats
        self.hr_group = QGroupBox("Heart Rate")
        self.hr_layout = QFormLayout(self.hr_group)
        self.avg_hr_label = QLabel("-")
        self.max_hr_label = QLabel("-")
        self.hr_zones_label = QLabel("-")
        self.hr_layout.addRow("Avg HR:", self.avg_hr_label)
        self.hr_layout.addRow("Max HR:", self.max_hr_label)
        self.hr_layout.addRow("Zones (s):", self.hr_zones_label)
        
        # Power Stats
        self.power_group = QGroupBox("Power (Estimated)")
        self.power_layout = QFormLayout(self.power_group)
        self.avg_power_label = QLabel("-")
        self.np_power_label = QLabel("-")
        self.power_layout.addRow("Avg Power:", self.avg_power_label)
        self.power_layout.addRow("Normalized Power:", self.np_power_label)
        self.track_weight_spin = QSpinBox()
        self.track_weight_spin.setRange(5, 50)
        self.track_weight_spin.setSuffix(" kg")
        self.track_weight_spin.valueChanged.connect(self.bike_weight_changed.emit)
        self.power_layout.addRow("Track Bike Wgt:", self.track_weight_spin)
        
        self.layout.addWidget(self.general_group)
        self.layout.addWidget(self.hr_group)
        self.layout.addWidget(self.power_group)
        self.layout.addStretch()
        
    def update_dashboard(self, summary, sport, default_bike_weight=10):
        # Clear stale data
        for label in [self.dist_label, self.time_label, self.elev_label, self.cal_label, 
                      self.fitness_score_label, self.avg_hr_label, self.max_hr_label, 
                      self.hr_zones_label, self.avg_power_label, self.np_power_label]:
            label.setText("-")
            
        self.sport_label.setText(sport.capitalize())
        
        # Disable signals to prevent recursive update when loading
        self.track_weight_spin.blockSignals(True)
        self.track_weight_spin.setValue(summary.get('track_bike_weight', default_bike_weight))
        self.track_weight_spin.blockSignals(False)
        self.track_weight_spin.setEnabled(sport.lower() == 'cycling')
        
        if summary.get('total_distance_km') is not None:
            self.dist_label.setText(f"{summary['total_distance_km']:.2f} km")
        
        if summary.get('total_timer_time') is not None:
            mins = int(summary['total_timer_time'] // 60)
            secs = int(summary['total_timer_time'] % 60)
            self.time_label.setText(f"{mins}m {secs}s")
            
        if summary.get('elevation_gain') is not None:
            self.elev_label.setText(f"{summary['elevation_gain']:.1f} m")
            
        if summary.get('calories') is not None:
            self.cal_label.setText(f"{summary['calories']} kcal")
            
        if summary.get('fitness_score') is not None:
            self.fitness_score_label.setText(f"{summary['fitness_score']:.1f}")
            
        if summary.get('avg_heart_rate') is not None:
            self.avg_hr_label.setText(f"{summary['avg_heart_rate']} bpm")
            
        if summary.get('max_heart_rate') is not None:
            self.max_hr_label.setText(f"{summary['max_heart_rate']} bpm")
            
        if summary.get('hr_zones') is not None:
            zones_str = "\n".join([f"{k}: {v}" for k, v in summary['hr_zones'].items()])
            self.hr_zones_label.setText(zones_str)
            
        if summary.get('avg_power') is not None:
            self.avg_power_label.setText(f"{summary['avg_power']:.1f} W")
            
        if summary.get('normalized_power') is not None:
            self.np_power_label.setText(f"{summary['normalized_power']:.1f} W")
