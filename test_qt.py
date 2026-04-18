import sys
import folium
from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QUrl

app = QApplication(sys.argv)
win = QMainWindow()
view = QWebEngineView()
win.setCentralWidget(view)

m = folium.Map(location=[47.0, 15.4], zoom_start=13, tiles='OpenStreetMap')
view.setHtml(m.get_root().render(), QUrl("http://localhost/"))

win.show()
print("Map loaded")
# sys.exit(app.exec())
