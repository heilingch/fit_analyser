import sys
import pyqtgraph as pg
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QCheckBox, QHBoxLayout

app = QApplication(sys.argv)
win = QWidget()
layout = QVBoxLayout(win)
pw = pg.PlotWidget()
layout.addWidget(pw)

curve = pw.plot([1,2,3], [1,2,3], name="test")

cb_layout = QHBoxLayout()
cb = QCheckBox("Toggle")
cb.setChecked(True)
cb.toggled.connect(curve.setVisible)
cb_layout.addWidget(cb)
layout.addLayout(cb_layout)

win.show()
print("Plotted")
