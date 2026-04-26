import os
import folium
from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtCore import QUrl

class MapWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        self.web_view = QWebEngineView()
        settings = self.web_view.settings()
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
        self.layout.addWidget(self.web_view)
        self.temp_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'temp_map.html')
        
    def plot_track(self, coordinates):
        """
        Coordinates is a list of [lat, lon]
        """
        if not coordinates or len(coordinates) < 2:
            self.web_view.setHtml("<h2>No GPS Track Available</h2>")
            return
        
        try:
            # Filter out any invalid coordinate pairs
            valid_coords = []
            for c in coordinates:
                if (len(c) == 2 and c[0] is not None and c[1] is not None
                        and -90 <= c[0] <= 90 and -180 <= c[1] <= 180):
                    valid_coords.append(c)
            
            if len(valid_coords) < 2:
                self.web_view.setHtml("<h2>No valid GPS coordinates</h2>")
                return
            
            # Calculate center
            lats = [c[0] for c in valid_coords]
            lons = [c[1] for c in valid_coords]
            center = [sum(lats)/len(lats), sum(lons)/len(lons)]
            
            # Create map using OpenStreetMap and bypass referer blocks
            m = folium.Map(location=center, zoom_start=13, tiles='OpenStreetMap')
            
            # Add track
            folium.PolyLine(
                valid_coords,
                weight=4,
                color='blue',
                opacity=0.8
            ).add_to(m)
            
            # Add Start/End markers
            folium.Marker(valid_coords[0], popup='Start', icon=folium.Icon(color='green')).add_to(m)
            folium.Marker(valid_coords[-1], popup='End', icon=folium.Icon(color='red')).add_to(m)
            
            js = """
            <script>
            var cursorMarker = null;
            function updateCursor(lat, lon) {
                for (var key in window) {
                    if (key.startsWith('map_')) {
                        var map = window[key];
                        if (map instanceof L.Map) {
                            if (!cursorMarker) {
                                cursorMarker = L.circleMarker([lat, lon], {
                                    radius: 8, fillColor: "#ff0000", color: "#000000", weight: 2, fillOpacity: 1
                                }).addTo(map);
                            } else {
                                cursorMarker.setLatLng([lat, lon]);
                            }
                            break;
                        }
                    }
                }
            }
            </script>
            """
            m.get_root().html.add_child(folium.Element(js))
            
            # Save and load with base URL to fake Referer for OSM tiles
            m.save(self.temp_file)
            with open(self.temp_file, 'r', encoding='utf-8') as f:
                html_content = f.read()
            self.web_view.setHtml(html_content, QUrl("http://localhost/"))
        except Exception as e:
            print(f"Map rendering error: {e}")
            self.web_view.setHtml(f"<h2>Map Error: {e}</h2>")

    def update_cursor(self, lat, lon):
        if lat is not None and lon is not None:
            self.web_view.page().runJavaScript(f"updateCursor({lat}, {lon});")
