import pyqtgraph as pg
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox
from PySide6.QtCore import Qt, Signal

class FitPlotWidget(QWidget):
    cursorMoved = Signal(int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        # Setup pyqtgraph plot
        self.plot_widget = pg.PlotWidget(background='w')
        self.layout.addWidget(self.plot_widget)
        
        self.checkbox_container = QWidget()
        self.checkbox_layout = QHBoxLayout(self.checkbox_container)
        self.layout.addWidget(self.checkbox_container)
        self.checkboxes = {}
        
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.addLegend()
        self.plot_widget.setLabel('bottom', "Time", units="min")
        
        # Enable minor ticks (and pyqtgraph draws grid for them if possible)
        self.plot_widget.getAxis('bottom').setTickSpacing()
        self.plot_widget.getAxis('left').setTickSpacing()
        
        # Crosshair setup
        self.vLine = pg.InfiniteLine(angle=90, movable=False)
        self.hLine = pg.InfiniteLine(angle=0, movable=False)
        self.plot_widget.addItem(self.vLine, ignoreBounds=True)
        self.plot_widget.addItem(self.hLine, ignoreBounds=True)
        
        # Label to show data values
        self.label = QLabel("Hover over plot to see values")
        self.label.setAlignment(Qt.AlignRight | Qt.AlignTop)
        self.layout.insertWidget(0, self.label)
        
        self.proxy = pg.SignalProxy(self.plot_widget.scene().sigMouseMoved, rateLimit=60, slot=self.mouseMoved)
        
        self.x_data = None
        self.y_data = None
        self.curves = {}

    def plot_data(self, x, y_data_dict, x_label="Time (min)"):
        self.plot_widget.clear()
        self.curves.clear()
        self.plot_widget.addItem(self.vLine, ignoreBounds=True)
        self.plot_widget.addItem(self.hLine, ignoreBounds=True)
        
        self.plot_widget.setLabel('bottom', x_label)
        
        self.x_data = x
        self.y_data = y_data_dict
        self.x_unit = "min" if "Time" in x_label else "km"
        
        colors = {
            'heart_rate': 'r',
            'speed_kmh': 'b',
            'altitude': 'g',
            'power': 'm',
            'temperature': (255, 140, 0)  # orange
        }
        
        names = {
            'heart_rate': 'Heart Rate (bpm)',
            'speed_kmh': 'Speed (km/h)',
            'altitude': 'Altitude (m)',
            'power': 'Power (W)',
            'temperature': 'Temperature (°C)'
        }
        
        # Create different ViewBoxes for different scales if needed
        # For simplicity, plotting them on same axis for now or normalize
        # Or better: create multiple axis. But let's start simple.
        for key, y_array in y_data_dict.items():
            if y_array is not None and len(y_array) > 0:
                pen = pg.mkPen(color=colors.get(key, 'k'), width=2)
                curve = self.plot_widget.plot(x, y_array, pen=pen, name=names.get(key, key), connect='finite')
                self.curves[key] = curve
                
        # Update checkboxes
        for i in reversed(range(self.checkbox_layout.count())): 
            widget = self.checkbox_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)
        self.checkboxes.clear()
        
        for key, curve in self.curves.items():
            cb = QCheckBox(names.get(key, key))
            cb.setChecked(True)
            # Use partial or a proper binding to avoid lambda scoping issues
            cb.toggled.connect(lambda state, k=key: self._toggle_curve(state, k))
            self.checkbox_layout.addWidget(cb)
            self.checkboxes[key] = cb
            
    def _toggle_curve(self, state, curve_name):
        curve = self.curves.get(curve_name)
        if curve:
            curve.setVisible(state)
            self.plot_widget.update()
                
    def mouseMoved(self, evt):
        pos = evt[0]
        if self.plot_widget.sceneBoundingRect().contains(pos):
            mousePoint = self.plot_widget.getPlotItem().vb.mapSceneToView(pos)
            
            # Find closest x index
            if self.x_data is not None and len(self.x_data) > 0:
                import numpy as np
                idx = (np.abs(self.x_data - mousePoint.x())).argmin()
                x_val = self.x_data[idx]
                
                fmt = {
                    'heart_rate': lambda v: f"HR: {v:.0f} bpm",
                    'speed_kmh': lambda v: f"Speed: {v:.1f} km/h",
                    'altitude': lambda v: f"Alt: {v:.0f} m",
                    'power': lambda v: f"Power: {v:.0f} W",
                    'temperature': lambda v: f"Temp: {v:.1f} °C"
                }
                
                parts = [f"<span style='font-weight: bold;'>X: {x_val:.1f} {getattr(self, 'x_unit', '')}</span>"]
                
                for key, y_array in self.y_data.items():
                    if y_array is not None and len(y_array) > idx:
                        y_val = y_array[idx]
                        formatter = fmt.get(key, lambda v: f"{key}: {v:.2f}")
                        parts.append(f"<span>{formatter(y_val)}</span>")
                        
                label_text = "&nbsp;&nbsp;|&nbsp;&nbsp;".join(parts)
                self.label.setText(label_text)
                
                # Emit signal with data index
                self.cursorMoved.emit(idx)
                
            self.vLine.setPos(mousePoint.x())
            self.hLine.setPos(mousePoint.y())
