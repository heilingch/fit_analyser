import sys
import os
from PySide6.QtWidgets import QApplication, QSplashScreen
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtCore import Qt, QTimer
from main_window import MainWindow

def show_main_window(splash, app):
    window = MainWindow()
    # Keep reference to avoid garbage collection
    app.main_window = window
    window.show()
    if splash:
        splash.finish(window)

def main():
    app = QApplication(sys.argv)
    
    # Optional: Set a nice clean style
    app.setStyle("Fusion")
    
    # Setup App Icon and Splash Screen
    logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "logo.png")
    app.setWindowIcon(QIcon(logo_path))
    
    if os.path.exists(logo_path):
        pixmap = QPixmap(logo_path).scaled(400, 400, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        splash = QSplashScreen(pixmap, Qt.WindowStaysOnTopHint)
        splash.show()
        
        # Wait 1.5 seconds, then load and show the main window
        QTimer.singleShot(1500, lambda: show_main_window(splash, app))
    else:
        show_main_window(None, app)
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
