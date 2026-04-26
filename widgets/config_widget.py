from PySide6.QtWidgets import QWidget, QFormLayout, QSpinBox, QPushButton, QVBoxLayout, QLabel, QComboBox

class ConfigWidget(QWidget):
    def __init__(self, data_model, parent=None):
        super().__init__(parent)
        self.data_model = data_model
        
        self.layout = QVBoxLayout(self)
        self.form_layout = QFormLayout()
        
        # User settings
        self.age_spin = QSpinBox()
        self.age_spin.setRange(10, 100)
        self.age_spin.setValue(self.data_model.config['user'].get('age', 30))
        
        self.weight_spin = QSpinBox()
        self.weight_spin.setRange(30, 200)
        self.weight_spin.setValue(self.data_model.config['user'].get('weight_kg', 75))
        
        self.max_hr_spin = QSpinBox()
        self.max_hr_spin.setRange(100, 250)
        self.max_hr_spin.setValue(self.data_model.config['user'].get('max_hr', 190))
        
        self.resting_hr_spin = QSpinBox()
        self.resting_hr_spin.setRange(30, 120)
        self.resting_hr_spin.setValue(self.data_model.config['user'].get('resting_hr', 60))
        
        self.bike_weight_spin = QSpinBox()
        self.bike_weight_spin.setRange(5, 50)
        self.bike_weight_spin.setValue(self.data_model.config['equipment'].get('bike_weight_kg', 10))
        
        # General Settings
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["light", "dark", "high_contrast", "dark_blue", "dark_green"])
        current_theme = self.data_model.config.get('settings', {}).get('theme', 'light')
        self.theme_combo.setCurrentText(current_theme)
        
        self.power_filter_spin = QSpinBox()
        self.power_filter_spin.setRange(1, 60)
        self.power_filter_spin.setSuffix(" s")
        self.power_filter_spin.setValue(self.data_model.config.get('settings', {}).get('power_filter_window', 5))
        
        self.form_layout.addRow("Theme:", self.theme_combo)
        self.form_layout.addRow("Power Filter Window:", self.power_filter_spin)
        self.form_layout.addRow("Age:", self.age_spin)
        self.form_layout.addRow("Weight (kg):", self.weight_spin)
        self.form_layout.addRow("Max HR:", self.max_hr_spin)
        self.form_layout.addRow("Resting HR:", self.resting_hr_spin)
        self.form_layout.addRow("Bike Weight (kg):", self.bike_weight_spin)
        
        self.layout.addWidget(QLabel("<h2>Configuration</h2>"))
        self.layout.addLayout(self.form_layout)
        
        self.save_btn = QPushButton("Save & Recalculate")
        self.save_btn.clicked.connect(self.save_config)
        self.layout.addWidget(self.save_btn)
        self.layout.addStretch()
        
    def save_config(self):
        config_data = {
            "user": {
                "age": self.age_spin.value(),
                "weight_kg": self.weight_spin.value(),
                "max_hr": self.max_hr_spin.value(),
                "resting_hr": self.resting_hr_spin.value()
            },
            "equipment": {
                "bike_weight_kg": self.bike_weight_spin.value()
            },
            "settings": {
                "theme": self.theme_combo.currentText(),
                "power_filter_window": self.power_filter_spin.value(),
                "last_folder": self.data_model.config.get('settings', {}).get('last_folder', '')
            }
        }
        self.data_model.save_config(config_data)
        # Note: Recalculate will need to be triggered from main window 
        # or we can emit a signal here, but since main window handles files, 
        # we let the main window connect to save_btn.clicked
