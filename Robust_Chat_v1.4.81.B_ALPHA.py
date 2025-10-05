import re
import sys, math, json, datetime, time, traceback, random
import os, sys
from PyQt5.QtWidgets import (QScrollArea, QFrame, 
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QTextEdit, QGroupBox,
    QMessageBox, QStatusBar, QListWidget, QListWidgetItem, QInputDialog,
    QShortcut, QFileDialog, QSizePolicy, QTabWidget, QToolBar, QGraphicsView,
    QGraphicsScene, QCheckBox
, QScrollArea, QFrame)

def _to_base36(n: int, width: int = 4) -> str:
    digits = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    if n <= 0:
        return '0'.rjust(width, '0')
    s = ''
    while n:
        n, r = divmod(n, 36)
        s = digits[r] + s
    return s.rjust(width, '0')
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QRectF, QRegularExpression, QSize, QPointF
from PyQt5.QtGui import QKeySequence, QFont, QFontMetrics, QPen, QBrush, QRegularExpressionValidator, QColor, QPolygonF
try:
    import serial
    SERIAL_AVAILABLE = True
except Exception:
    serial = None
    SERIAL_AVAILABLE = False

# --------- Helpers ---------

# ---- Geo helpers: distance/bearing/cardinal (Step D) ----
def _geo_haversine_km(lat1, lon1, lat2, lon2):
    import math
    R = 6371.0  # km
    phi1 = math.radians(float(lat1)); phi2 = math.radians(float(lat2))
    dphi = math.radians(float(lat2) - float(lat1))
    dlmb = math.radians(float(lon2) - float(lon1))
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlmb/2)**2
    c = 2*math.atan2(a**0.5, (1-a)**0.5)
    return R*c

def _geo_initial_bearing_deg(lat1, lon1, lat2, lon2):
    import math
    phi1 = math.radians(float(lat1)); phi2 = math.radians(float(lat2))
    dlmb = math.radians(float(lon2) - float(lon1))
    x = math.sin(dlmb)*math.cos(phi2)
    y = math.cos(phi1)*math.sin(phi2) - math.sin(phi1)*math.cos(phi2)*math.cos(dlmb)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0

_CARD16 = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"]
def _geo_cardinal16(deg):
    try:
        idx = int(((float(deg) + 11.25) % 360) // 22.5)
        return _CARD16[idx]
    except Exception:
        return "N"

def diag_log(msg: str):
    try:
        base = app_base_dir()
        # Root log
        with open(os.path.join(base, 'startup_log.txt'), 'a', encoding='utf-8') as f:
            f.write(msg + '\n')
        # Store log
        store = os.path.join(base, 'store')
        os.makedirs(store, exist_ok=True)
        with open(os.path.join(store, 'diagnostic.log'), 'a', encoding='utf-8') as f2:
            f2.write(msg + '\n')
    except Exception:
        pass

def app_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

from PyQt5.QtGui import QFontDatabase, QFont

def _install_vt323_font():
    """Load bundled VT323 if available so theme changes never alter the face/metrics."""
    try:
        base = app_base_dir()
        candidates = [
            os.path.join(base, "fonts", "VT323-Regular.ttf"),
            os.path.join(base, "VT323-Regular.ttf"),
        ]
        for p in candidates:
            if os.path.isfile(p):
                QFontDatabase.addApplicationFont(p)
                break
    except Exception:
        pass

from PyQt5.QtGui import QFontInfo

def _log_font_snapshot(tag, widget):
    try:
        base = app_base_dir()
        store = os.path.join(base, "store"); os.makedirs(store, exist_ok=True)
        out = os.path.join(store, "diagnostic_font.txt")
        fi = QFontInfo(widget.font())
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"{tag}: family={fi.family()} pointSize={fi.pointSize()} pixelSize={fi.pixelSize()} exactMatch={fi.exactMatch()}\n")
    except Exception:
        pass

def store_path(filename: str):
    base = app_base_dir()
    store = os.path.join(base, "store")
    os.makedirs(store, exist_ok=True)
    return os.path.join(store, filename)

def load_json(filename: str):
    path = store_path(filename)
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                diag_log(f"load_json OK: {filename} -> type={type(data).__name__}")
                return data
        else:
            diag_log(f"load_json MISS: {filename} (no file)")
    except Exception as e:
        diag_log(f"load_json ERROR: {filename}: {e}")
    return {}

def save_json(filename: str, data):
    path = store_path(filename)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        diag_log(f"save_json OK: {filename}")
    except Exception as e:
        diag_log(f"save_json ERROR: {filename}: {e}")

def load_json_root(filename: str):
    path = os.path.join(app_base_dir(), filename)
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                diag_log(f"load_json_root OK: {filename} -> type={type(data).__name__}")
                return data
        else:
            diag_log(f"load_json_root MISS: {filename} (no file)")
    except Exception as e:
        diag_log(f"load_json_root ERROR: {filename}: {e}")
    return {}

def save_json_root(filename: str, data):
    path = os.path.join(app_base_dir(), filename)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        diag_log(f"save_json_root OK: {filename}")
    except Exception as e:
        diag_log(f"save_json_root ERROR: {filename}: {e}")

def base_callsign(cs: str) -> str:
    cs = (cs or "").strip().upper()
    m = re.match(r'^([A-Z0-9/]+?)(?:-([0-9]{1,2}|\*))?$', cs)
    return m.group(1) if m else cs

def parse_callsign_ssid(cs: str):
    """Return (base, ssid_str or None). Accepts '*' as wildcard SSID."""
    cs = (cs or '').strip().upper()
    m = re.match(r'^([A-Z0-9/]+?)(?:-([0-9]{1,2}|\*))?$', cs)
    if not m:
        return cs, None
    base, ss = m.group(1), m.group(2)
    return base, ss

# --------- Fleet (file-backed) ---------
class FleetManager:
    def __init__(self, path):
        self.path = path
        self.enabled = False
        self.active_fleets = ["Default"]
        self.fleets = [{"name":"Default","rules":{"default_action":"show","autopermit":False},"members":[]}]  # fallback
        self.load()

    def load(self):
        data = load_json_root(os.path.basename(self.path)) or {}
        try:
            # If file is just a list of callsigns, migrate to Default group
            if isinstance(data, list):
                data = {"active_fleets": ["Default"],
                        "fleets": [{"name":"Default","rules":{"default_action":"show","autopermit":False},
                                   "members":[base_callsign(x) for x in data if isinstance(x,(str,))]}]}
            af = data.get("active_fleets") or ["Default"]
            fl = data.get("fleets") or self.fleets
            # Coerce fleets to expected structure
            if isinstance(fl, dict) and "members" in fl:
                fl = [fl]
            norm_fleets = []
            if isinstance(fl, list):
                for f in fl:
                    if isinstance(f, dict):
                        name = str(f.get("name","Default") or "Default")
                        members = f.get("members", [])
                        if isinstance(members, dict):
                            members = list(members.keys())
                        if isinstance(members, list):
                            members = [str(m).upper() for m in members if isinstance(m,(str,))]
                        else:
                            members = []
                        rules = f.get("rules") if isinstance(f.get("rules"), dict) else {"default_action":"show","autopermit":False}
                        norm_fleets.append({"name": name, "rules": rules, "members": members})
            if norm_fleets:
                self.fleets = norm_fleets
            if isinstance(af, list) and af:
                self.active_fleets = [str(af[0])]
        except Exception:
            pass
        # ensure default exists
        if not any(f.get("name")=="Default" for f in self.fleets):
            self.fleets.append({"name":"Default","rules":{"default_action":"show","autopermit":False},"members":[]})

    def save(self):
        data = {"active_fleets": self.active_fleets, "fleets": self.fleets}
        save_json_root(os.path.basename(self.path), data)

    def list_fleet_names(self):
        return [f.get("name","?") for f in self.fleets]

    def set_active(self, name: str):
        self.active_fleets = [name or "Default"]
        self.save()

    def list_members(self, name: str):
        for f in self.fleets:
            if f.get("name") == name:
                return list(f.get("members") or [])
        return []

    def add_group(self, name: str):
        name = (name or "").strip()
        if not name: return False
        if any(f.get("name")==name for f in self.fleets):
            return False
        self.fleets.append({"name":name,"rules":{"default_action":"show","autopermit":False},"members":[]})
        self.save()
        return True

    def add_member(self, group: str, callsign: str):
        group = (group or "").strip()
        base, ss = parse_callsign_ssid(callsign)
        if not group or not base:
            return False
        norm = base
        if ss == '*':
            norm = f"{base}-*"
        else:
            try:
                if ss is not None and 1 <= int(ss) <= 99:
                    norm = f"{base}-*"
            except Exception:
                pass
        for f in self.fleets:
            if f.get("name") == group:
                if norm not in f.get("members", []):
                    f.setdefault("members", []).append(norm)
                    self.save()
                    return True
                return False
        return False

    def matches_member(self, stored: str, callsign: str) -> bool:
        """Return True if stored entry matches callsign per wildcard rules.
        - stored 'BASE-*' matches BASE or any BASE-SSID
        - stored 'BASE' matches only BASE (no SSID)
        """
        b, ss = parse_callsign_ssid(callsign)
        if stored.endswith('-*'):
            return stored[:-2] == b
        return stored == b

    def remove_member(self, group: str, callsign: str):
        group = (group or "").strip()
        cs = base_callsign(callsign)
        for f in self.fleets:
            if f.get("name")==group and cs in f.get("members",[]):
                f["members"].remove(cs)
                self.save()
                return True
        return False

# --------- Serial thread (stub) ---------
class SerialReaderThread(QThread):
    line_received = pyqtSignal(str)
    def __init__(self, owner):
        super().__init__()
        
        
        
        
        # Positions store

        try:

            self._positions = self._load_positions()

        except Exception:

            self._positions = {}

# One-shot coordinate beacon flag
        self._beacon_coords_force_once = False
# Load beacon coordinate state
        try:
            _c = self._load_beacon_coords_from_settings()
            self._beacon_coords_enabled = bool(_c.get('enabled'))
            self._beacon_coords_lat = _c.get('lat')
            self._beacon_coords_lon = _c.get('lon')
            self._beacon_coords_last_ts = _c.get('last_ts')
        except Exception:
            self._beacon_coords_enabled = False
            self._beacon_coords_lat = None
            self._beacon_coords_lon = None
            self._beacon_coords_last_ts = None
# Ensure a status bar exists
        try:
            if not hasattr(self, "status_bar") or self.status_bar is None:
                from PyQt5.QtWidgets import QStatusBar
                self.status_bar = QStatusBar()
                self.setStatusBar(self.status_bar)
        except Exception:
            pass
        self._stop = False
        self.owner = owner  # ChatApp instance (has .ser)

    def run(self):
        buf = bytearray()
        while not self._stop:
            try:
                ser = getattr(self.owner, 'ser', None)
                if ser and ser.is_open:
                    data = ser.read(256)
                    if data:
                        buf.extend(data)
                        while True:
                            cut = None
                            for i, b in enumerate(buf):
                                if b in (10, 13):  # CR/LF
                                    cut = i; break
                            if cut is None: break
                            line = bytes(buf[:cut]).decode('utf-8', errors='ignore')
                            j = cut
                            while j < len(buf) and buf[j] in (10,13):
                                j += 1
                            buf = buf[j:]
                            line = line.strip()
                            if line:
                                self.line_received.emit(line)
                    else:
                        self.msleep(15)
                else:
                    self.msleep(50)
            except Exception:
                # Blank or invalid fields: DISABLE coordinate beacons
                try:
                    self._beacon_coords_enabled = False
                    self._beacon_coords_lat = None
                    self._beacon_coords_lon = None
                    self._beacon_coords_last_ts = None
                    self._beacon_coords_force_once = False
                    # Persist disabled state
                    try:
                        self._save_beacon_coords_to_settings(False, None, None, None)
                    except Exception:
                        pass
                    # Optional: feedback
                    try:
                        self._status('Fixed position cleared; coordinate beacons disabled', 3000)
                    except Exception:
                        pass
                except Exception:
                    pass
        self._ack_pause_default = 12.0
        self._ack_sent = {}
        self._ack_sent_ttl = 600.0
        self.get_mycall = get_mycall
        self.get_live = get_live
        self.get_theme = get_theme
        v = QVBoxLayout(self)
        ctrl = QHBoxLayout()
        self.zoom_in = QPushButton("+")
        self.zoom_out = QPushButton("-")
        self.reset_btn = QPushButton("RESET")
        for b in (self.zoom_in, self.zoom_out, self.reset_btn):
            b.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        ctrl.addWidget(self.zoom_in); ctrl.addWidget(self.zoom_out); ctrl.addWidget(self.reset_btn); ctrl.addStretch(1)
        v.addLayout(ctrl)
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        v.addWidget(self.view, 1)
        self.zoom_in.clicked.connect(lambda: self.view.scale(1.15, 1.15))
        self.zoom_out.clicked.connect(lambda: self.view.scale(1/1.15, 1/1.15))
        self.reset_btn.clicked.connect(self.reset_view)
        self.draw_graph()

    def reset_view(self):
        self.view.resetTransform()
        r = self.scene.itemsBoundingRect()
        if r.isValid():
            self.view.fitInView(r.adjusted(-40, -40, 40, 40), Qt.KeepAspectRatio)

    def _triangle(self, cx, cy, size):
        h = size
        r = h / (3**0.5)  # radius relation for equilateral
        pts = []
        for k in range(3):
            ang = -math.pi/2 + k * 2*math.pi/3  # point up
            pts.append(QPointF(cx + r*math.cos(ang), cy + r*math.sin(ang)))
        return QPolygonF(pts)

    def draw_graph(self):
        self.scene.clear()

        # ---- Metrics label helper (Step D) ----
        def _add_metrics_label(callsign: str, cx: float, baseline_y: float, first_line_height: float):
            try:
                csu = (callsign or "").strip().upper()
                myu = (self.get_mycall() or "MYCALL").strip().upper()
                if csu == myu:
                    return  # skip MYCALL
                m = None
                gm = getattr(self, 'get_metric', None)
                if callable(gm):
                    try:
                        m = gm(callsign)
                    except Exception:
                        m = None
                if m:
                    line2 = f"{m['km_str']} km / {m['mi_str']} mi"
                    line3 = f"{m['deg_str']}° {m['card']}"
                else:
                    line2 = "No Position"
                    line3 = ""
                from PyQt5.QtGui import QFont
                f = QFont(self.font())
                try:
                    f.setPointSize(max(8, f.pointSize()-2))
                except Exception:
                    pass
                t2 = self.scene.addText(line2); t2.setDefaultTextColor(t_text); t2.setFont(f); t2.setZValue(8)
                bb2 = t2.boundingRect()
                t2.setPos(cx - bb2.width()/2, baseline_y + first_line_height + 2)
                if line3:
                    t3 = self.scene.addText(line3); t3.setDefaultTextColor(t_text); t3.setFont(f); t3.setZValue(8)
                    bb3 = t3.boundingRect()
                    t3.setPos(cx - bb3.width()/2, baseline_y + first_line_height + 2 + bb2.height() + 2)
            except Exception:
                pass
        # theme colors
        t = self.get_theme() if hasattr(self, 'get_theme') else {}
        t_edge = QColor(t.get('map_edge', '#505050'))
        t_text = QColor(t.get('text', '#000000'))
        self.view.setBackgroundBrush(QBrush(QColor(t.get('panel_bg', '#f5f5f5'))))

        # helper: clipped line to avoid icons/labels at endpoints
        def draw_edge(ax, ay, bx, by, rA, rB, label_h_src=0.0):
            dx, dy = (bx-ax), (by-ay)
            L = (dx*dx + dy*dy) ** 0.5
            if L < 1e-6:
                return
            ux, uy = dx / L, dy / L
            extra_src = (label_h_src + 6.0) if uy > 0 else 0.0  # if going downward from source, skip label below
            sx, sy = ax + ux * (rA + 2.0 + extra_src), ay + uy * (rA + 2.0 + extra_src)
            ex, ey = bx - ux * (rB + 2.0), by - uy * (rB + 2.0)
            self.scene.addLine(sx, sy, ex, ey, pen_edge)

        my = base_callsign(self.get_mycall() or "MYCALL")
        parents, children, edges = self.get_live()

        # layout constants (half-size, thicker borders)
        R1, R2 = 220.0, 120.0
        size_centre = 17.0
        size_parent = 14.0
        size_child  = 11.0
        fm = QFontMetrics(self.font())
        label_h = fm.height()

        pen_my = QPen(QColor("cyan")); pen_my.setWidthF(4.0)
        pen_parent = QPen(QColor(0,255,0)); pen_parent.setWidthF(4.0)   # lime
        pen_child  = QPen(QColor(255,165,0)); pen_child.setWidthF(4.0)  # orange
        pen_edge   = QPen(t_edge); pen_edge.setWidthF(1.2)
        brush_transparent = QBrush(Qt.NoBrush)

        pos = {}
        cx, cy = 0.0, 0.0

        # centre (MYCALL)
        tri = self._triangle(cx, cy, size_centre)
        self.scene.addPolygon(tri, pen_my, brush_transparent)
        titem = self.scene.addText(my); titem.setDefaultTextColor(t_text)
        tb = titem.boundingRect()
        titem.setPos(cx - tb.width()/2, cy + size_centre/2 + 6)
        r_my = size_centre / (3**0.5)
        pos[my] = (cx, cy, r_my)

        # parents ring
        parent_names = sorted(parents.keys())
        n = max(1, len(parent_names))
        for i, p in enumerate(parent_names):
            ang = (2*math.pi*i)/n
            px = cx + R1*math.cos(ang); py = cy + R1*math.sin(ang)
            r_src = pos[my][2]; r_dst = size_parent / (3**0.5)
            draw_edge(cx, cy, px, py, r_src, r_dst, label_h_src=label_h)
            pt = self._triangle(px, py, size_parent)
            self.scene.addPolygon(pt, pen_parent, brush_transparent)
            tt = self.scene.addText(p); tt.setDefaultTextColor(t_text)
            bb = tt.boundingRect()
            tt.setPos(px - bb.width()/2, py + size_parent/2 + 6)
            _add_metrics_label(p, px, py + size_parent/2 + 6, bb.height())
            pos[p] = (px, py, r_dst)
            kids = sorted(children.get(p, []))
            m = max(1, len(kids))
            for j, c in enumerate(kids):
                a2 = ang + (2*math.pi*j)/m / 3.0
                kx = px + R2*math.cos(a2); ky = py + R2*math.sin(a2)
                r_src = pos[p][2]; r_dst = size_child / (3**0.5)
                draw_edge(px, py, kx, ky, r_src, r_dst, label_h_src=label_h)
                kt = self._triangle(kx, ky, size_child)
                self.scene.addPolygon(kt, pen_child, brush_transparent)
                tt2 = self.scene.addText(c); tt2.setDefaultTextColor(t_text)
                bb2 = tt2.boundingRect()
                tt2.setPos(kx - bb2.width()/2, ky + size_child/2 + 6)
                _add_metrics_label(c, kx, ky + size_child/2 + 6, bb2.height())
                pos.setdefault(c, (kx, ky, r_dst))

        # additional edges
        for src, dst in edges:
            if src in pos and dst in pos:
                x1, y1, _ = pos[src]; x2, y2, _ = pos[dst]
                r1 = pos[src][2]; r2 = pos[dst][2]
                draw_edge(x1, y1, x2, y2, r1, r2, label_h_src=label_h)

        self.reset_view()

# --------- Theme Manager ---------
class ThemeManager:
    def __init__(self):
        self.themes = {
            "Light": {
                "bg": "#ffffff", "panel_bg": "#f5f5f5", "text": "#000000", "border": "#444444",
                "button_bg": "#e6e6e6", "button_fg": "#000000", "input_bg": "#ffffff",
                "map_edge": "#505050"
            },
            "Dark Red": {
                "bg": "#121212", "panel_bg": "#1e1e1e", "text": "#ff4d4d", "border": "#ff4d4d",
                "button_bg": "#2a2a2a", "button_fg": "#ff4d4d", "input_bg": "#232323",
                "map_edge": "#884444"
            },
            "Dark Green": {
                "bg": "#0f1210", "panel_bg": "#171a18", "text": "#7CFC00", "border": "#7CFC00",
                "button_bg": "#202320", "button_fg": "#7CFC00", "input_bg": "#1b1e1c",
                "map_edge": "#3aa35a"
            },
        }
        self.current = self.themes["Light"]

    def apply(self, window, name: str):
        self.current = self.themes.get(name, self.themes["Light"])
        t = self.current
        fpt = getattr(window, "_font_pt", 12)
        
        mt  = max(12, fpt + 8)
        pad = max(4,  fpt // 2)
        
        qss = f"""
        QWidget {{ background: {t['bg']}; color: {t['text']}; font: 12pt "VT323"; }}
        QGroupBox {{ background: {t['panel_bg']}; border: 1px solid {t['border']}; border-radius: 6px; margin-top: 16px; }}
        QGroupBox::title {{ subcontrol-origin: margin; left: 8px; padding: 0 8px; }}
        QPushButton {{ background: {t['button_bg']}; color: {t['button_fg']}; border: 1px solid {t['border']}; border-radius: 6px; padding: 4px 10px; }}
        QLineEdit, QTextEdit {{ background: {t['input_bg']}; color: {t['text']}; border: 1px solid {t['border']}; border-radius: 6px; }}
        QListWidget {{ background: {t['input_bg']}; color: {t['text']}; border: 1px solid {t['border']}; border-radius: 6px; }}
        QToolBar {{ background: {t['panel_bg']}; border-bottom: 1px solid {t['border']}; }}
        QTabBar::tab {{ background: {t['panel_bg']}; color: {t['text']}; padding: 4px 10px; margin: 2px; border: 1px solid {t['border']}; border-bottom: none; }}
        QTabBar::tab:selected {{ background: {t['bg']}; }}
        QStatusBar {{ background: {t['panel_bg']}; color: {t['text']}; border-top: 1px solid {t['border']}; }}
        """

        try:
            window.setStyleSheet(qss)
            _install_vt323_font()
            from PyQt5.QtGui import QFont
            window.setFont(QFont('VT323', 12))
            _log_font_snapshot('apply_theme_after_setFont', window)
        except Exception:
            pass

    def color(self, key, default="#808080"):
        return self.current.get(key, default)

# --------- Main App ---------
# ---------- ACK state (inserted) ----------
ACK_TAG_RE = re.compile(r"\[ACK:([A-Za-z0-9]{4,10})\]")

class AckState:
    def __init__(self, app, ack_id: str, base_text: str, pause_s: int):
        from PyQt5.QtCore import QTimer
        self.app = app
        self.ack_id = ack_id
        self.base_text = base_text
        self.pause_s = max(1, int(pause_s))
        self.max_attempts = 3
        self.attempts = 0
        self.done = False
        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._on_retry)
        self.echo_texts = set()

    def start(self):
        self._send_attempt()

    def _send_attempt(self):
        if self.done: return
        self.attempts += 1
        line = f"{self.base_text} (attempt {self.attempts}/3)"
        if self.app.send_user_text(line):
            self.echo_texts.add(self._norm(line))
            import time
            self.last_tx_time = time.monotonic()
            self.app._ack_update_ui(self.ack_id, line, status=f"attempt {self.attempts}/3")
            import random
            delay = self.pause_s + random.uniform(0.2, 0.7)
            self.timer.start(int(delay*1000))
            self.app._diag(f"[ACK] arming retry in {delay:.2f}s for {self.ack_id}")
        else:
            try:
                self.app._diag(f"[ACK] send failed on attempt {self.attempts}/3 (serial closed?)")
            except Exception:
                pass
            self.timer.start(1000)

    def _on_retry(self):
        if self.done: return
        if self.attempts < self.max_attempts:
            self.app._diag(f"[RETRY] {self.ack_id} {self.attempts+1}/3")
            self._send_attempt()
        else:
            self.done = True
            text = f"{self.base_text} (FAILED after 3/3)"
            self.app._ack_update_ui(self.ack_id, text, status="failed")
            self.app._diag(f"[ACK] giving up {self.ack_id} after 3/3")

    def on_ack_received(self):
        if self.done: return
        self.done = True
        self.timer.stop()
        text = f"{self.base_text} (ACK received {self.ack_id})"
        self.app._ack_update_ui(self.ack_id, text, status="ack")

    def _norm(self, s: str) -> str:
        return re.sub(r"[\r\n]+", "", s).strip()

# --- Network Graph widget (fallback/portable) ---
# Provides a minimal viewer for the link graph when a full LinkMapWidget isn't provided by modules.
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QGraphicsView, QGraphicsScene
from PyQt5.QtGui import QPen, QBrush, QColor, QFont
from PyQt5.QtCore import Qt, QTimer, QPointF

class LinkMapWidget(QWidget):
    def __init__(self, get_mycall, get_live, get_theme):
        super().__init__()
        # ACK/Retry + Auto-ACK state
        self.ack_counter = 1
        self.sent_by_ack = {}
        self.retry_timers = {}
        self._ack_pause_default = 12.0
        self._ack_sent = {}
        self._ack_sent_ttl = 600.0
        self.get_mycall = get_mycall
        self.get_live = get_live
        self.get_theme = get_theme
        v = QVBoxLayout(self)
        ctrl = QHBoxLayout()
        self.zoom_in = QPushButton("+")
        self.zoom_out = QPushButton("-")
        self.reset_btn = QPushButton("RESET")
        for b in (self.zoom_in, self.zoom_out, self.reset_btn):
            b.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        ctrl.addWidget(self.zoom_in); ctrl.addWidget(self.zoom_out); ctrl.addWidget(self.reset_btn); ctrl.addStretch(1)
        v.addLayout(ctrl)
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.view.setMinimumSize(300, 220)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        v.addWidget(self.view, 1)
        self.zoom_in.clicked.connect(lambda: self.view.scale(1.15, 1.15))
        self.zoom_out.clicked.connect(lambda: self.view.scale(1/1.15, 1/1.15))
        self.reset_btn.clicked.connect(self.reset_view)
        self.draw_graph()

    def reset_view(self):
        self.view.resetTransform()
        r = self.scene.itemsBoundingRect()
        if r.isValid():
            self.view.fitInView(r.adjusted(-40, -40, 40, 40), Qt.KeepAspectRatio)

    def _triangle(self, cx, cy, size):
        h = size
        r = h / (3**0.5)  # radius relation for equilateral
        pts = []
        for k in range(3):
            ang = -math.pi/2 + k * 2*math.pi/3  # point up
            pts.append(QPointF(cx + r*math.cos(ang), cy + r*math.sin(ang)))
        return QPolygonF(pts)

    def draw_graph(self):
        self.scene.clear()
        # theme colors
        t = self.get_theme() if hasattr(self, 'get_theme') else {}
        t_edge = QColor(t.get('map_edge', '#505050'))
        t_text = QColor(t.get('text', '#000000'))
        self.view.setBackgroundBrush(QBrush(QColor(t.get('panel_bg', '#f5f5f5'))))

        # helper: clipped line to avoid icons/labels at endpoints
        def draw_edge(ax, ay, bx, by, rA, rB, label_h_src=0.0):
            dx, dy = (bx-ax), (by-ay)
            L = (dx*dx + dy*dy) ** 0.5
            if L < 1e-6:
                return
            ux, uy = dx / L, dy / L
            extra_src = (label_h_src + 6.0) if uy > 0 else 0.0  # if going downward from source, skip label below
            sx, sy = ax + ux * (rA + 2.0 + extra_src), ay + uy * (rA + 2.0 + extra_src)
            ex, ey = bx - ux * (rB + 2.0), by - uy * (rB + 2.0)
            self.scene.addLine(sx, sy, ex, ey, pen_edge)

        my = base_callsign(self.get_mycall() or "MYCALL")
        parents, children, edges = self.get_live()

        # layout constants (half-size, thicker borders)
        R1, R2 = 220.0, 120.0
        size_centre = 17.0
        size_parent = 14.0
        size_child  = 11.0
        fm = QFontMetrics(self.font())
        label_h = fm.height()

        pen_my = QPen(QColor("cyan")); pen_my.setWidthF(4.0)
        pen_parent = QPen(QColor(0,255,0)); pen_parent.setWidthF(4.0)   # lime
        pen_child  = QPen(QColor(255,165,0)); pen_child.setWidthF(4.0)  # orange
        pen_edge   = QPen(t_edge); pen_edge.setWidthF(1.2)
        brush_transparent = QBrush(Qt.NoBrush)

        pos = {}
        cx, cy = 0.0, 0.0

        # centre (MYCALL)
        tri = self._triangle(cx, cy, size_centre)
        self.scene.addPolygon(tri, pen_my, brush_transparent)
        titem = self.scene.addText(my); titem.setDefaultTextColor(t_text)
        tb = titem.boundingRect()
        titem.setPos(cx - tb.width()/2, cy + size_centre/2 + 6)
        r_my = size_centre / (3**0.5)
        pos[my] = (cx, cy, r_my)

        # parents ring
        parent_names = sorted(parents.keys())
        n = max(1, len(parent_names))
        for i, p in enumerate(parent_names):
            ang = (2*math.pi*i)/n
            px = cx + R1*math.cos(ang); py = cy + R1*math.sin(ang)
            r_src = pos[my][2]; r_dst = size_parent / (3**0.5)
            draw_edge(cx, cy, px, py, r_src, r_dst, label_h_src=label_h)
            pt = self._triangle(px, py, size_parent)
            self.scene.addPolygon(pt, pen_parent, brush_transparent)
            tt = self.scene.addText(p); tt.setDefaultTextColor(t_text)
            bb = tt.boundingRect()
            tt.setPos(px - bb.width()/2, py + size_parent/2 + 6)
            pos[p] = (px, py, r_dst)
            kids = sorted(children.get(p, []))
            m = max(1, len(kids))
            for j, c in enumerate(kids):
                a2 = ang + (2*math.pi*j)/m / 3.0
                kx = px + R2*math.cos(a2); ky = py + R2*math.sin(a2)
                r_src = pos[p][2]; r_dst = size_child / (3**0.5)
                draw_edge(px, py, kx, ky, r_src, r_dst, label_h_src=label_h)
                kt = self._triangle(kx, ky, size_child)
                self.scene.addPolygon(kt, pen_child, brush_transparent)
                tt2 = self.scene.addText(c); tt2.setDefaultTextColor(t_text)
                bb2 = tt2.boundingRect()
                tt2.setPos(kx - bb2.width()/2, ky + size_child/2 + 6)
                pos.setdefault(c, (kx, ky, r_dst))

        # additional edges
        for src, dst in edges:
            if src in pos and dst in pos:
                x1, y1, _ = pos[src]; x2, y2, _ = pos[dst]
                r1 = pos[src][2]; r2 = pos[dst][2]
                draw_edge(x1, y1, x2, y2, r1, r2, label_h_src=label_h)

        self.reset_view()

# --------- Theme Manager ---------
# (Removed duplicate ThemeManager class)

class AckState:
    def __init__(self, app, ack_id: str, base_text: str, pause_s: int):
        from PyQt5.QtCore import QTimer
        self.app = app
        self.ack_id = ack_id
        self.base_text = base_text
        self.pause_s = max(1, int(pause_s))
        self.max_attempts = 3
        self.attempts = 0
        self.done = False
        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._on_retry)
        self.echo_texts = set()

    def start(self):
        self._send_attempt()

    def _send_attempt(self):
        if self.done: return
        self.attempts += 1
        line = f"{self.base_text} (attempt {self.attempts}/3)"
        if self.app.send_user_text(line):
            self.echo_texts.add(self._norm(line))
            import time
            self.last_tx_time = time.monotonic()
            self.app._ack_update_ui(self.ack_id, line, status=f"attempt {self.attempts}/3")
            import random
            delay = self.pause_s + random.uniform(0.2, 0.7)
            self.timer.start(int(delay*1000))
            self.app._diag(f"[ACK] arming retry in {delay:.2f}s for {self.ack_id}")
        else:
            self.timer.start(1000)

    def _on_retry(self):
        if self.done: return
        if self.attempts < self.max_attempts:
            self.app._diag(f"[RETRY] {self.ack_id} {self.attempts+1}/3")
            self._send_attempt()
        else:
            self.done = True
            text = f"{self.base_text} (FAILED after 3/3)"
            self.app._ack_update_ui(self.ack_id, text, status="failed")
            self.app._diag(f"[ACK] giving up {self.ack_id} after 3/3")

    def on_ack_received(self):
        if self.done: return
        self.done = True
        self.timer.stop()
        text = f"{self.base_text} (ACK received {self.ack_id})"
        self.app._ack_update_ui(self.ack_id, text, status="ack")

    def _norm(self, s: str) -> str:
        return re.sub(r"[\r\n]+", "", s).strip()

class ChatApp(QMainWindow):

    def _ensure_color_attrs(self):
        """Fallback QColor-based palette so QBrush(..., QColor) calls are safe before theme loads."""
        try:
            from PyQt5.QtGui import QColor
        except Exception:
            # As a last resort, leave attributes unset; caller should guard.
            return
        defaults = {
            # Keep both SENT and TX synonyms for legacy codepaths
            "COLOR_SENT": QColor(0, 255, 0),      # bright green
            "COLOR_TX":   QColor(0, 176, 255),    # blue-ish for TX text if used
            "COLOR_RX":   QColor(255, 165, 0),    # orange
            "COLOR_ACK":  QColor(0, 200, 0),      # dark green
            "COLOR_SYS":  QColor(170, 170, 170),  # grey
            "COLOR_ERR":  QColor(255, 82, 82),    # red
        }
        for k, v in defaults.items():
            if not hasattr(self, k) or getattr(self, k) is None:
                try:
                    setattr(self, k, v)
                except Exception:
                    pass


    def _nuke_lock_size(self):
        # Lock window height to current value (nuclear option)
        try:
            h = self.height()
            if h > 0:
                self.setMinimumHeight(h)
                self.setMaximumHeight(h)
        except Exception:
            pass

    def _nuke_unlock_size(self):
        try:
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)
        except Exception:
            pass
    def showEvent(self, e):
        try:
            from PyQt5.QtCore import QTimer
            if not hasattr(self, '_shown_once'):
                self._shown_once = True
                if getattr(self, '_start_maximized', False):
                    # Maximize on first show, then lock to that height to prevent tab growth
                    self.showMaximized()
                    try:
                        QTimer.singleShot(0, self._nuke_lock_size)
                    except Exception:
                        pass
                else:
                    # Normal startup: lock to initial height
                    try:
                        self._nuke_lock_size()
                    except Exception:
                        pass
        except Exception:
            pass
        return super().showEvent(e)

    def _link_graph_prune(self, expiry_sec=3600):
        """Prune link graph parents whose last seen timestamp in positions is older than expiry_sec.
        This removes parent entries from self._graph_parents and persists the link_graph file if changed."""
        try:
            now = int(time.time())
            pos = getattr(self, '_positions', {}) or {}
            gp = getattr(self, '_graph_parents', {}) or {}
            removed = False
            to_remove = []
            for parent in list(gp.keys()):
                p_key = parent
                # find last_update in positions if present
                ent = pos.get(p_key) or pos.get(p_key.upper()) or pos.get(p_key.lower()) or {}
                last = ent.get('last_update')
                if last is None:
                    # If there's no position entry for this parent, we treat as stale
                    to_remove.append(parent)
                    continue
                try:
                    last_ts = int(last)
                except Exception:
                    to_remove.append(parent)
                    continue
                if last_ts < (now - int(expiry_sec)):
                    to_remove.append(parent)
            for p in to_remove:
                try:
                    gp.pop(p, None)
                    removed = True
                except Exception:
                    pass
            if removed:
                try:
                    # persist change using existing save routine if available
                    save_fn = getattr(self, '_save_link_graph', None)
                    if callable(save_fn):
                        save_fn()
                    else:
                        # fallback: write store/link_graph.json
                        import json, os
                        store = os.path.join(os.path.dirname(__file__), 'store')
                        os.makedirs(store, exist_ok=True)
                        with open(os.path.join(store, 'link_graph.json'), 'w', encoding='utf-8') as fh:
                            json.dump({'parents': gp, 'children': gp, 'edges': []}, fh, indent=2)
                except Exception:
                    pass
            # update in-memory
            try:
                self._graph_parents = gp
            except Exception:
                pass
        except Exception:
            pass

    # ---- Metrics helpers (Step D) ----
    def _my_position(self):
        try:
            if getattr(self, '_beacon_coords_enabled', False):
                lat = getattr(self, '_beacon_coords_lat', None)
                lon = getattr(self, '_beacon_coords_lon', None)
                if lat is not None and lon is not None:
                    return float(lat), float(lon)
        except Exception:
            pass
        try:
            myc = (self.mycall_edit.text() or '').strip().upper() if hasattr(self, 'mycall_edit') else ''
            if not myc:
                return (None, None)
            b = base_callsign(myc)
            pos = getattr(self, '_positions', {}) or {}
            ent = pos.get(b) or {}
            lat = ent.get('lat'); lon = ent.get('lon')
            if lat is not None and lon is not None:
                return float(lat), float(lon)
        except Exception:
            pass
        return (None, None)

    def _station_position(self, callsign: str):
        try:
            cs = base_callsign(callsign or '')
            pos = getattr(self, '_positions', {}) or {}
            ent = pos.get(cs) or {}
            lat = ent.get('lat'); lon = ent.get('lon')
            if lat is not None and lon is not None:
                return float(lat), float(lon)
        except Exception:
            pass
        return (None, None)

    def _metric_from_mycall(self, callsign: str):
        try:
            if not callsign:
                return None
            my_lat, my_lon = self._my_position()
            if my_lat is None or my_lon is None:
                return None
            st_lat, st_lon = self._station_position(callsign)
            if st_lat is None or st_lon is None:
                return None
            km = _geo_haversine_km(my_lat, my_lon, st_lat, st_lon)
            mi = km * 0.621371
            deg = _geo_initial_bearing_deg(my_lat, my_lon, st_lat, st_lon)
            card = _geo_cardinal16(deg)
            def _fmt(x): return f"{x:.1f}" if x < 100 else f"{x:.0f}"
            return {"km": km, "mi": mi, "deg": deg, "card": card,
                    "km_str": _fmt(km), "mi_str": _fmt(mi),
                    "deg_str": f"{int(round(deg))%360:03d}"}
        except Exception:
            return None
    def _apply_tx_color_for_theme(self, theme_name: str = ''):
        try:
            nm = (theme_name or getattr(self, 'theme_name', '') or getattr(self, 'current_theme', '')).strip().lower()
            from PyQt5.QtGui import QColor
            if 'dark green' in nm:
                self.COLOR_SENT = QColor(0, 200, 0)
            elif 'dark red' in nm:
                self.COLOR_SENT = QColor(220, 0, 0)
            else:
                if not hasattr(self, 'COLOR_SENT'):
                    self.COLOR_SENT = QColor(0, 255, 0)
        except Exception:
            pass
# ---- UI helpers for message display ----
    def _strip_ack_id(self, text: str) -> str:
        try:
            import re as _re
            t = (text or '')
            # Remove [ACK:####]
            t = _re.sub(r'\s*\[ACK:[0-9A-Z]{4,8}\]\s*', ' ', t, flags=_re.I)
            # Remove trailing status decorations like (attempt 1/3) or (FAILED after 3/3)
            t = _re.sub(r'\s*\((?:attempt\s+\d/3|failed\s+after\s+3/3)\)\s*', ' ', t, flags=_re.I)
            return t.strip()
        except Exception:
            return text

    def _ticks_for_status(self, status: str) -> str:
        try:
            s = (status or '').strip().lower()
            if s.startswith('attempt'):
                return ' ✓'
            if s == 'ack' or 'acked' in s:
                return ' ✓✓'
            if s.startswith('failed'):
                return ' ✗'
            return ''
        except Exception:
            return ''
    def _update_last_tx_label(self):
        import datetime as _dt
        try:
            ts = getattr(self, '_last_tx_iso', None)
            if not ts:
                try:
                    self.last_tx_label.setText('Last TX: —')
                except Exception:
                    pass
                return
            dt = _dt.datetime.fromisoformat(ts.replace('Z','+00:00'))
            now = _dt.datetime.now(_dt.timezone.utc)
            delta = max(0, int((now - dt).total_seconds()))
            m, s = divmod(delta, 60)
            h, m = divmod(m, 60)
            if h:
                txt = f'{h}h {m}m {s}s ago'
            elif m:
                txt = f'{m}m {s}s ago'
            else:
                txt = f'{s}s ago'
            try:
                self.last_tx_label.setText(f'Last TX: {txt}')
            except Exception:
                pass
        except Exception:
            try:
                self.last_tx_label.setText('Last TX: —')
            except Exception:
                pass

    def _touch_last_tx(self, iso=None):
        try:
            if iso is None:
                try:
                    iso = self._utc_now_iso()
                except Exception:
                    import datetime as _dt
                    iso = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
            self._last_tx_iso = iso
            self._update_last_tx_label()
        except Exception:
            pass
# ===== File Transfer (Upload → META/OK/PART/END with PING/PONG probes) =====
    def _file_make_fid(self, width=5):
        import random, string
        return ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(width))

    def _file_chunks(self, data: bytes, max_b64_per_line=180):
        raw = (max_b64_per_line * 3) // 4
        for i in range(0, len(data), raw):
            yield data[i:i+raw]

    def _get_target_call(self):
        try:
            t = (self.to_edit.text() or "").strip().upper()
            return t
        except Exception:
            return ""

    def _send_protocol_line(self, payload: str, to: str):
        try:
            me = (self.mycall_edit.text() or "").strip().upper()
        except Exception:
            me = ""
        if not to or not me:
            try: self._status("Target/MyCALL missing for file transfer")
            except Exception: pass
            return False
        line = f"{to} DE {me} {payload}"
        try:
            return self.send_user_text(line)
        except Exception:
            return False

    def _send_with_ack(self, payload: str, to: str, ack_id: str):
        # Step 3: track who is allowed to ACK this id
        try:
            if not hasattr(self, '_pending_outbox'):
                self._pending_outbox = {}
            self._pending_outbox[ack_id] = {'target': (to or '').strip().upper(), 'ts': _time_ack.monotonic()}
            # prune >15 minutes
            for k, v in list(self._pending_outbox.items()):
                if (_time_ack.monotonic() - v.get('ts', 0)) > 900:
                    self._pending_outbox.pop(k, None)
        except Exception:
            pass
        msg = f"{payload} [ACK:{ack_id}]"
        try:
            a = AckState(self, ack_id, f"{to} DE " + (self.mycall_edit.text().strip().upper() if hasattr(self, "mycall_edit") else "MYCALL") + " " + msg, int(getattr(self, "_ack_pause", 12)))
            if getattr(self, "_ack_states", None) is None:
                self._ack_states = {}
            self._ack_states[ack_id] = a
            a.start()
        except Exception:
            self._send_protocol_line(msg, to)

    # --- Sender-side: wait for FILE OK and between-part PING/PONG probe ---
    def _wait_file_ok(self, fid: str, timeout=30):
        import time
        self._file_last_ok = ""
        t0 = time.time()
        while time.time() - t0 < timeout:
            # Check flag set by RX on 'FILE OK [FID:fid]'
            if getattr(self, "_file_last_ok", "") == fid:
                return True
            QApplication.processEvents()
            time.sleep(0.1)
        return False

    def _wait_probe_pong(self, fid: str, to: str, timeout=30, interval=3):
        import time
        t0 = time.time()
        tries = 0
        while time.time() - t0 < timeout:
            # Send PING
            self._send_protocol_line(f"FILE PING [FID:{fid}]", to)
            tries += 1
            # Wait interval, look for PONG flag
            t1 = time.time()
            while time.time() - t1 < interval:
                if getattr(self, "_file_last_pong", "") == fid:
                    return True
                QApplication.processEvents()
                time.sleep(0.05)
        return False

    def send_file_path(self, path: str):
        """Upload-only file send with strict accept (FILE OK) + PING/PONG between parts. Sender cap 500 KB."""
        import os, hashlib, base64, time
        try:
            to = self._get_target_call()
            if not to:
                QMessageBox.information(self, "Send File", "Please set a Target/TO callsign first.")
                return False
            with open(path, "rb") as f:
                data = f.read()

            # Sender-side cap
            MAX_FILE_SIZE = 500 * 1024
            if len(data) > MAX_FILE_SIZE:
                try: self._status(f"File too large: {len(data)} bytes (limit {MAX_FILE_SIZE} bytes).")
                except Exception: pass
                QMessageBox.warning(self, "Send File", f"File too large: {len(data)} bytes (limit {MAX_FILE_SIZE} bytes).")
                return False

            name = os.path.basename(path)
            sha1 = hashlib.sha1(data).hexdigest()
            fid  = self._file_make_fid()
            parts = list(self._file_chunks(data))
            N = len(parts)

            # 1) Offer
            meta = f'FILE META name="{name}" size={len(data)} sha1={sha1} [FID:{fid}]'
            self._send_protocol_line(meta, to)
            try: self._status(f"Offered file: {name} ({len(data)} bytes) — waiting for OK…")
            except Exception: pass

            # 2) Wait for FILE OK
            if not self._wait_file_ok(fid, timeout=30):
                try: self._status("File offer declined or timed out.")
                except Exception: pass
                return False

            # 3) Send parts with inter-chunk PING/PONG
            for i, chunk in enumerate(parts, start=1):
                if i > 1:
                    if not self._wait_probe_pong(fid, to, timeout=30, interval=3):
                        try: self._status("Receiver unresponsive (no PONG) — aborting file send.")
                        except Exception: pass
                        return False
                b64 = base64.b64encode(chunk).decode("ascii")
                payload = f'FILE PART {i}/{N} [FID:{fid}] {b64}'
                ack_id = self._file_make_fid(4)
                self._send_with_ack(payload, to, ack_id)
                # brief UI breathing room
                QApplication.processEvents(); time.sleep(0.05)

            # 4) End
            end = f'FILE END [FID:{fid}]'
            self._send_protocol_line(end, to)
            try: self._status(f"File sent: {name} ({len(data)} bytes) in {N} parts.")
            except Exception: pass
            return True
        except Exception as e:
            try: self._status(f"File send failed: {e}")
            except Exception: pass
            return False

    def _on_upload_file_selected(self, path: str):
        return self.send_file_path(path)

    # --- Receiver-side: offers list + OK/NO + PONG + reassembly ---
    def _ensure_file_state(self):
        if not hasattr(self, "_file_offers"): self._file_offers = {}
        if not hasattr(self, "_file_rx"): self._file_rx = {}
        if not hasattr(self, "_file_last_ok"): self._file_last_ok = ""
        if not hasattr(self, "_file_last_pong"): self._file_last_pong = ""

    def _incoming_selected_sid(self):
        it = self.incoming_list.currentItem()
        return it.text() if it else None

    def _incoming_accept_selected(self):
        self._ensure_file_state()
        it = self.incoming_list.currentItem()
        if not it: 
            self._status("No incoming file selected.")
            return
        txt = it.text()
        m = re.search(r'\[([0-9A-Z]{4,6})\]', txt)
        fid = m.group(1) if m else None
        if not fid or fid not in self._file_offers:
            self._status("Invalid selection.")
            return
        frm = self._file_offers[fid].get("from","")
        # Send OK back to sender
        self._send_protocol_line(f"FILE OK [FID:{fid}]", frm)
        self._status(f"Accepted file [FID:{fid}] from {frm}")
        # Keep in list until END completes

    def _incoming_decline_selected(self):
        self._ensure_file_state()
        it = self.incoming_list.currentItem()
        if not it: 
            self._status("No incoming file selected.")
            return
        txt = it.text()
        m = re.search(r'\[([0-9A-Z]{4,6})\]', txt)
        fid = m.group(1) if m else None
        if not fid or fid not in self._file_offers:
            self._status("Invalid selection.")
            return
        frm = self._file_offers[fid].get("from","")
        self._send_protocol_line(f"FILE NO [FID:{fid}]", frm)
        self._status(f"Declined file [FID:{fid}] from {frm}")
        # Remove from UI and state
        row = self.incoming_list.row(self.incoming_list.currentItem())
        self.incoming_list.takeItem(row)
        try: del self._file_offers[fid]
        except Exception: pass

    def _incoming_reset_window(self):
        self._ensure_file_state()
        self.incoming_list.clear()
        self._file_offers.clear()
        self._status("Incoming file window reset.")

    def _rx_handle_file_line(self, to: str, frm: str, msg: str) -> bool:
        """Parse FILE frames; drive offers + respond to PING; reassemble to store/inbox/"""
        try:
            if not msg.startswith("FILE "):
                return False
            import re, base64, os, hashlib
            self._ensure_file_state()
            me = (self.mycall_edit.text().strip().upper() if hasattr(self, "mycall_edit") else "")
            # PING/PONG quick path
            if msg.startswith("FILE PING"):
                mf = re.search(r'\[FID:([0-9A-Z]+)\]', msg)
                if mf:
                    fid = mf.group(1)
                    # Reply PONG
                    self._send_protocol_line(f"FILE PONG [FID:{fid}]", frm)
                return True
            if msg.startswith("FILE PONG"):
                mf = re.search(r'\[FID:([0-9A-Z]+)\]', msg)
                if mf:
                    self._file_last_pong = mf.group(1)
                return True
            if msg.startswith("FILE OK"):
                mf = re.search(r'\[FID:([0-9A-Z]+)\]', msg)
                if mf:
                    self._file_last_ok = mf.group(1)
                return True
            if msg.startswith("FILE NO"):
                # Sender can optionally handle this; here we just consume it
                return True

            # From here: META/PART/END
            mfid = re.search(r'\[FID:([0-9A-Z]+)\]', msg)
            fid = mfid.group(1) if mfid else None
            if not fid:
                return True

            # Offer
            if msg.startswith("FILE META"):
                mname = re.search(r'name="([^"]+)"', msg)
                msize = re.search(r'size=(\d+)', msg)
                msha1 = re.search(r'sha1=([0-9a-fA-F]{40})', msg)
                if mname and msize and msha1:
                    meta = {"name": os.path.basename(mname.group(1)), "size": int(msize.group(1)), "sha1": msha1.group(1).lower(), "from": frm}
                    self._file_offers[fid] = meta
                    # Add to UI list
                    try:
                        self.incoming_list.addItem(f"[{fid}] {frm} → {meta['name']} ({meta['size']} B)")
                    except Exception:
                        pass
                return True

            # Parts
            if msg.startswith("FILE PART"):
                # Only accept parts if we've already sent OK or auto-accept (if you later add it)
                # For now, accept anyway, but you can gate on offers if required.
                mp = re.search(r'FILE PART (\d+)/(\d+)\s+\[FID:[^\]]+\]\s+(.+?)(\s+\[ACK:[0-9A-Za-z]+\])?$', msg)
                if mp:
                    i = int(mp.group(1)); N = int(mp.group(2)); b64 = mp.group(3).strip()
                    b = self._file_rx.setdefault(fid, {"meta": self._file_offers.get(fid, {}), "parts": {}, "N": N, "from": frm})
                    try:
                        b["parts"][i] = base64.b64decode(b64.encode("ascii"), validate=True)
                        b["N"] = N
                    except Exception:
                        pass
                    # If ACK token present, we echo it (so sender's retry engine can stop)
                    mack = re.search(r'\[ACK:([0-9A-Za-z]{4,10})\]', msg)
                    if mack:
                        ack_id = mack.group(1)
                        self._send_protocol_line(f"[ACK:{ack_id}]", frm)
                return True

            if msg.startswith("FILE END"):
                b = self._file_rx.get(fid, {})
                meta = b.get("meta") or self._file_offers.get(fid, {})
                N = b.get("N") or 0
                if not meta or not N or len(b.get("parts", {})) != N:
                    return True
                data = b''.join(b["parts"][i] for i in range(1, N+1))
                if hashlib.sha1(data).hexdigest().lower() != meta.get("sha1",""):
                    return True
                # Save to store/inbox
                def _rc_store():
                    try:
                        base = (os.path.dirname(os.path.abspath(sys.executable)) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__)))
                        store = os.path.join(base, "store"); os.makedirs(store, exist_ok=True); return store
                    except Exception:
                        return "store"
                inbox = os.path.join(_rc_store(), "inbox"); os.makedirs(inbox, exist_ok=True)
                out = os.path.join(inbox, meta["name"])
                basep, ext = os.path.splitext(out); k = 1
                while os.path.exists(out):
                    out = f"{basep}({k}){ext}"; k += 1
                with open(out, "wb") as f:
                    f.write(data)
                # Cleanup + UI
                try:
                    if fid in self._file_offers: del self._file_offers[fid]
                    if fid in self._file_rx: del self._file_rx[fid]
                except Exception: pass
                try:
                    # remove list item
                    for r in range(self.incoming_list.count()-1, -1, -1):
                        if f"[{fid}]" in (self.incoming_list.item(r).text() or ""):
                            self.incoming_list.takeItem(r); break
                except Exception: pass
                self._status(f"Received file from {frm}: {meta.get('name','?')}")
                return True

            return True
        except Exception:
            return False
    # ===== End File Transfer =====

    

    # ---- Positions store (positions.json) ----
    def _load_positions(self):
        try:
            d = load_json('positions.json') or {}
            if isinstance(d, dict):
                return d
        except Exception:
            pass
        return {}

    def _save_positions(self):
        try:
            save_json('positions.json', getattr(self, '_positions', {}))
        except Exception:
            pass

    def _positions_upsert(self, callsign: str, lat: float, lon: float, source: str = 'beacon-fixed'):
        try:
            if not callsign:
                return
            cs = str(callsign).upper().strip()
            lat = float(lat); lon = float(lon)
            now = int(__import__('time').time())
            if not hasattr(self, '_positions') or not isinstance(self._positions, dict):
                self._positions = {}
            entry = self._positions.get(cs) or {}
            hist = entry.get('history') or []
            hist.append({'t': now, 'lat': float(lat), 'lon': float(lon)})
            if len(hist) > 50:
                hist = hist[-50:]
            entry.update({'lat': float(lat), 'lon': float(lon), 'last_update': now, 'source': source, 'history': hist})
            self._positions[cs] = entry
            self._save_positions()
        except Exception:
            pass

    def _positions_prune(self, expiry_sec: int = 3600):
        try:
            now = int(__import__('time').time())
            if not hasattr(self, '_positions') or not isinstance(self._positions, dict):
                return
            removed = []
            for cs, entry in list(self._positions.items()):
                try:
                    last = int(entry.get('last_update') or 0)
                    if now - last > int(expiry_sec):
                        removed.append(cs)
                        self._positions.pop(cs, None)
                except Exception:
                    pass
            if removed:
                self._save_positions()
        except Exception:
            pass

    # ---- Beacon coordinate persistence ----
        # prune link graph parents to match position expiry
        try:
            self._link_graph_prune(expiry_sec=expiry_sec)
        except Exception:
            pass

    def _load_beacon_coords_from_settings(self):
        try:
            s = self._settings_get()
            b = s.get('beacon') or {}
            c = b.get('coords') or {}
            return {
                'enabled': bool(c.get('enabled', False)),
                'lat': c.get('lat', None),
                'lon': c.get('lon', None),
                'last_ts': c.get('last_ts', None)
            }
        except Exception:
            return {'enabled': False, 'lat': None, 'lon': None, 'last_ts': None}

    def _save_beacon_coords_to_settings(self, enabled=None, lat=None, lon=None, last_ts=None):
        try:
            s = self._settings_get()
            b = s.get('beacon') or {}
            c = b.get('coords') or {}
            if enabled is not None: c['enabled'] = bool(enabled)
            if lat is not None: c['lat'] = lat
            if lon is not None: c['lon'] = lon
            if last_ts is not None: c['last_ts'] = last_ts
            b['coords'] = c
            s['beacon'] = b
            self._settings_set(s)
        except Exception:
            pass

    def _purge_self_from_graph(self):
        """Remove our own callsign from graph parents/children and save best-effort."""
        try:
            myc = self.mycall_edit.text().strip().upper()
        except Exception:
            myc = ""
        try:
            # Parents
            if hasattr(self, '_graph_parents') and isinstance(self._graph_parents, dict):
                self._graph_parents.pop(myc, None)
                for k, v in list(self._graph_parents.items()):
                    try:
                        self._graph_parents[k] = [c for c in v if (c or '').upper() != myc]
                    except Exception:
                        pass
            # Save if helper exists
            try:
                self._save_link_graph()
            except Exception:
                pass
        except Exception:
            pass
    def _conditional_add_message(self, *args, **kwargs):
        if getattr(self, '_suppress_next_log', False):
            self._suppress_next_log = False
            return
        try:
            return self.messages_list.addItem(*args, **kwargs)
        except Exception:
            pass
    def _status(self, msg: str = "", ms: int = 2000):
        """Show a transient message in the status bar; create it if missing."""
        try:
            from PyQt5.QtWidgets import QStatusBar
            if not hasattr(self, "status_bar") or self.status_bar is None:
                try:
                    self.status_bar = QStatusBar()
                    self.setStatusBar(self.status_bar)
                except Exception:
                    # Fallback: use built-in statusBar() if available
                    try:
                        self._status(str(msg), int(ms))
                        return
                    except Exception:
                        return
            self._status(str(msg), int(ms))
        except Exception:
            pass
    def _settings_get(self) -> dict:
        try:
            return load_json("settings.json") or {}
        except Exception:
            return {}

    def _settings_set(self, new_settings: dict):
        try:
            save_json("settings.json", new_settings)
        except Exception:
            pass

    def _load_beacon_from_settings(self):
        s = self._settings_get()
        b = s.get("beacon") or {}
        enabled = bool(b.get("enabled", False))
        minutes = int(b.get("minutes", 15))
        return enabled, max(1, minutes)

    def _save_beacon_to_settings(self, enabled: bool, minutes: int):
        s = self._settings_get()
        s["beacon"] = {"enabled": bool(enabled), "minutes": int(minutes)}
        self._settings_set(s)

    def _enable_beacon(self, minutes: int, immediate: bool = False):
        try:
            mins = max(1, int(minutes))
        except Exception:
            mins = 15
        try:
            if not hasattr(self, "beacon_timer"):
                self.beacon_timer = QTimer(self)
                self.beacon_timer.timeout.connect(self._send_beacon)
            try:
                self.beacon_timer.timeout.disconnect()
            except Exception:
                pass
            self.beacon_timer.setSingleShot(False)
            self.beacon_timer.stop()
            self.beacon_timer.setInterval(mins * 60_000)
            self.beacon_timer.timeout.connect(self._send_beacon)
            self.beacon_timer.start()
            try:
                self._status(f'Beacon armed: every {mins} min', 2500)
            except Exception:
                pass
            # Cancel any pending auto-start so user choice persists
            try:
                if hasattr(self, 'auto_beacon_timer') and self.auto_beacon_timer.isActive():
                    self.auto_beacon_timer.stop()
            except Exception:
                pass
            self._save_beacon_to_settings(True, mins)
            if immediate:
                self._send_beacon()
        
            try:
                self._touch_last_tx()
            except Exception:
                pass
        except Exception:
            pass

    def _disable_beacon(self):
        try:
            if hasattr(self, "beacon_timer"):
                self.beacon_timer.stop()
            self._save_beacon_to_settings(False, 0)
        except Exception:
            pass

    def _wire_beacon_buttons(self):
        """Find buttons labeled '5 min', '10 min', '15 min' and wire them to set & send immediately."""
        try:
            from PyQt5.QtWidgets import QPushButton
            for btn in self.findChildren(QPushButton):
                t = btn.text().strip().lower()
                if t in ("5 min", "5mins", "5 minutes", "5m"):
                    try: btn.clicked.disconnect()
                    except Exception: pass
                    btn.clicked.connect(lambda checked=False: self._enable_beacon(5, immediate=True))
                elif t in ("10 min", "10mins", "10 minutes", "10m"):
                    try: btn.clicked.disconnect()
                    except Exception: pass
                    btn.clicked.connect(lambda checked=False: self._enable_beacon(10, immediate=True))
                elif t in ("15 min", "15mins", "15 minutes", "15m"):
                    try: btn.clicked.disconnect()
                    except Exception: pass
                    btn.clicked.connect(lambda checked=False: self._enable_beacon(15, immediate=True))
        except Exception:
            pass

    def _send_beacon(self):
        try:
            try:
                diag_log('TIMER: _send_beacon tick')
            except Exception:
                pass
            me = self.mycall_edit.text().strip().upper() if hasattr(self, 'mycall_edit') else ''
            if not me:
                return
            children = []
            try:
                for cand in ('heard_stations','beacons_heard','link_graph','_beacons','_heard'):
                    if hasattr(self, cand):
                        obj = getattr(self, cand)
                        if isinstance(obj, dict):
                            children.extend(list(obj.keys()))
            except Exception:
                pass
            children = sorted({(c or '').strip().upper() for c in children if isinstance(c, str) and c and (c or '').strip().upper() != me})[:12]
            line = f"..{me}"
            # Optionally append Lat/Lon every 30 minutes or when forced once
            try:
                import time as _t
                if getattr(self, '_beacon_coords_enabled', False) and self._beacon_coords_lat is not None and self._beacon_coords_lon is not None:
                    last = getattr(self, '_beacon_coords_last_ts', None) or 0
                    now = int(_t.time())
                    force_once = bool(getattr(self, '_beacon_coords_force_once', False))
                    if force_once or (now - int(last) >= 1800):
                        line += f" Lat {float(self._beacon_coords_lat):.5f} Lon {float(self._beacon_coords_lon):.5f}"
                        self._beacon_coords_last_ts = now
                        self._save_beacon_coords_to_settings(last_ts=now)
                        try:
                            self._positions_upsert(me, self._beacon_coords_lat, self._beacon_coords_lon, source='beacon-fixed')
                        except Exception:
                            pass
                        if force_once:
                            self._beacon_coords_force_once = False
            except Exception:
                pass
            for c in children:
                line += f" /{c}"
            try:
                self._serial_write_text(line + "\r")
            except Exception:
                pass
        except Exception:
            pass

    def _is_system_noise(self, line: str) -> bool:
        return ("%CONNECT" in line) or ("%DISCONN" in line)

    def _is_valid_ack(self, line: str, src_call: str = "", dst_call: str = "") -> str or None:
        if self._is_system_noise(line):
            return None
        m = self._ACK_TOKEN.search(line)
        if not m:
            return None
        ack = m.group(1)
        try:
            p = getattr(self, "pending_ack", None)
            if p and p.get("id") and ack != p.get("id"):
                return None
            if p and p.get("to") and src_call:
                if src_call.strip().upper() != p["to"].strip().upper():
                    return None
            if hasattr(self, "mycall_edit") and dst_call:
                my = self.mycall_edit.text().strip().upper()
                if my and dst_call.strip().upper() != my:
                    return None
        except Exception:
            pass
        try:
            if hasattr(self, "mycall_edit") and src_call:
                if src_call.strip().upper() == self.mycall_edit.text().strip().upper():
                    return None
        except Exception:
            pass
        return ack
    

    def _ensure_store_paths(self):
        """Ensure 'store/' exists; migrate store/messages-v1.json -> store/messages_v1.json if needed."""
        import os, json
        try:
            if not os.path.isdir('store'):
                os.makedirs('store', exist_ok=True)
            dash = os.path.join('store','messages-v1.json')
            under = os.path.join('store','messages_v1.json')
            if os.path.isfile(dash) and not os.path.isfile(under):
                try:
                    with open(dash,'r',encoding='utf-8') as f: data = json.load(f)
                except Exception:
                    data = None
                if data is not None:
                    try:
                        with open(under,'w',encoding='utf-8') as f: json.dump(data,f,ensure_ascii=False,indent=2)
                    except Exception:
                        pass
        except Exception as e:
            try: diag_log(f"[STORE] ensure/migrate failed: {e}")
            except Exception: pass
    def _utc_now_iso(self):
        import datetime as _dt
        return _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00","Z")

    def _utc_display_hms(self, ts_iso: str) -> str:
        import datetime as _dt
        try:
            s = (ts_iso or "").replace("Z","+00:00")
            t = _dt.datetime.fromisoformat(s).time()
            return f"(UTC) {t.strftime('%H:%M:%S')}"
        except Exception:
            return "(UTC) 00:00:00"
    def _ensure_header_top(self, ts_iso: str):
        """Ensure the UK date header is at index 0.
        - If an existing header is elsewhere or has the wrong text, remove it and place the correct one at 0.
        - Swallow errors so SEND/RX/ACK never break.
        """
        try:
            import datetime as _dt
            s = (ts_iso or '').replace('Z','').split('.')[0]
            d = _dt.datetime.fromisoformat(s).date() if s else _dt.datetime.now().date()
            # Compose header text using existing formatter if present
            try:
                header_txt = "────── " + self._uk_date_str(ts_iso) + " " + "──────"
            except Exception:
                header_txt = f"────── {d.day} {d.strftime('%B')} {d.year} " + "──────"

            # Find any existing header in the list
            existing_idx = None
            for i in range(self.messages_list.count()):
                it = self.messages_list.item(i)
                if it and it.data(Qt.UserRole) == 'dateheader':
                    existing_idx = i
                    break

            # If header exists but not at top or has wrong text -> remove it
            if existing_idx is not None:
                it = self.messages_list.item(existing_idx)
                if existing_idx != 0 or (it and it.text() != header_txt):
                    self.messages_list.takeItem(existing_idx)

            # Ensure header at index 0 with correct text
            top = self.messages_list.item(0) if self.messages_list.count() > 0 else None
            if (not top) or (top.data(Qt.UserRole) != 'dateheader') or (top.text() != header_txt):
                new_it = QListWidgetItem(header_txt)
                try: new_it.setTextAlignment(Qt.AlignHCenter)
                except Exception: pass
                try:
                    from PyQt5.QtGui import QBrush, QColor
                    new_it.setForeground(QBrush(QColor(128,128,128)))
                    f = new_it.font(); f.setBold(True); new_it.setFont(f)
                except Exception: pass
                new_it.setData(Qt.UserRole, 'dateheader')
                self.messages_list.insertItem(0, new_it)
        except Exception as e:
            try:
                diag_log(f"[HEADER] ensure_header_top failed: {e}")
            except Exception:
                pass
    def _uk_date_str(self, ts_iso: str) -> str:
        import datetime as _dt
        try:
            s = (ts_iso or "").replace('Z','').split('.')[0]
            d = _dt.datetime.fromisoformat(s).date() if s else _dt.datetime.now().date()
        except Exception:
            d = _dt.datetime.now().date()
        return f"{d.day} {d.strftime('%B')} {d.year}"
    def _maybe_insert_date_header(self, *args, **kwargs):
        return None

    def _fmt_disp_prefix(self, ts_iso: str) -> str:
        import datetime as _dt
        try:
            if ts_iso:
                s = ts_iso.replace('Z', '+00:00')
                utc_dt = _dt.datetime.fromisoformat(s)
            else:
                utc_dt = _dt.datetime.now(_dt.timezone.utc)
            local_dt = utc_dt.astimezone()
            return f"[{local_dt.strftime('%d-%b-%Y %H:%M:%S')}] "
        except Exception:
            try:
                return f"[{_dt.datetime.now().strftime('%d-%b-%Y %H:%M:%S')}] "
            except Exception:
                return "[--] "
    def _diag(self, msg: str):
        try:
            diag_log(msg)
        except Exception:
            print(msg)

    
    def _message_should_display(self, norm_line: str) -> bool:
        try:
            line = (norm_line or '').strip()
            if not line:
                return False
            # Urgent keywords
            if re.search(r'\b(SOS|MAYDAY|URGENT)\b', line, re.I):
                return True
            m = re.search(r'([A-Z0-9/]+)\s+DE\s+([A-Z0-9/]+)', line, re.I)
            to_cs  = (m.group(1) if m else '').strip().upper()
            frm_cs = (m.group(2) if m else '').strip().upper()
            my = (self.mycall_edit.text().strip().upper() if hasattr(self, 'mycall_edit') else '')
            if to_cs and (to_cs == my or to_cs == 'CQ'):
                return True
            # Whitelist mode
            try:
                fleet = getattr(self, 'fleet', None)
                if fleet and getattr(fleet, 'enabled', False):
                    active = set((fleet.active_fleets or []) if hasattr(fleet, 'active_fleets') else [])
                    members = set()
                    for f in getattr(fleet, 'fleets', []) or []:
                        if f.get('name') in active:
                            for m2 in f.get('members', []) or []:
                                members.add(str(m2).upper())
                    b_to = re.sub(r'-\d+$', '', to_cs)
                    b_fr = re.sub(r'-\d+$', '', frm_cs)
                    if b_to in members or b_fr in members:
                        return True
            except Exception:
                pass
            return False
        except Exception:
            return False
    def _append_rx(self, line: str):
        # MESSAGE FILTER ENFORCED
        try:
            if not self._message_should_display(line):
                return
        except Exception:
            pass
        # Skip UI logging for beacon lines like '..CALL /CHILD ...'
        try:
            _t = (line or '').strip().upper()
            import re as _re
            if _re.match(r'^\.{2}[A-Z0-9]+(\s*/[A-Z0-9]+)*\s*$', _t):
                return
        except Exception:
            pass
        # MESSAGE FILTER APPLIED
        try:
            if not self._message_should_display(line):
                return
        except Exception:
            pass

        import datetime as _dt
        ts = _dt.datetime.now().isoformat(timespec='seconds')
        prefix = self._fmt_disp_prefix(ts)

        it = QListWidgetItem(prefix + line)
        try:
            it.setForeground(QBrush(self.COLOR_RX))
        except Exception:
            pass
        it.setData(Qt.UserRole, 'rx')

        # INSERT INTO UI NOW
        try:
            self.messages_list.insertItem(0, it)
            self.messages_list.scrollToTop()
        except Exception:
            pass

        # Persist to store as UTC for durability
        try:
            _ts = self._utc_now_iso()
            self._messages.append({'line': line, 'role': 'rx', 'ts': _ts, 'ts_display': getattr(self, '_utc_display_hms', lambda s: '')(_ts)})
            self._save_messages_to_store()
        except Exception:
            pass

        it.setData(Qt.UserRole,'rx')

        

        try:

            (_ts:=self._utc_now_iso(), self._messages.append({'line': line, 'role': 'rx', 'ts': _ts, 'ts_display': getattr(self, '_utc_display_hms', lambda s: '')(_ts)})) and None

            self._save_messages_to_store()

        except Exception:

            pass

    
    
    def _persist_tx(self, obj: dict):
        # Persist a message to store, collapsing by ack_id so only the latest status remains.
        try:
            # Normalize timestamp to UTC ISO Z
            _ts = obj.get('ts') or (self._utc_now_iso() if hasattr(self, '_utc_now_iso') else None)
            if isinstance(_ts, str) and _ts.endswith('+00:00'):
                _ts = _ts.replace('+00:00','Z')
            obj['ts'] = _ts
            try:
                obj['ts_display'] = self._utc_display_hms(_ts)
            except Exception:
                pass
        except Exception:
            pass
        try:
            if not hasattr(self, '_messages') or not isinstance(self._messages, list):
                self._messages = []
            # If we have an ack_id, replace the most recent entry with same ack_id instead of appending
            ack_id = str(obj.get('ack_id') or '').strip()
            if ack_id:
                replaced = False
                for idx in range(len(self._messages)-1, -1, -1):
                    try:
                        if str(self._messages[idx].get('ack_id') or '').strip() == ack_id:
                            self._messages[idx] = obj
                            replaced = True
                            break
                    except Exception:
                        pass
                if not replaced:
                    self._messages.append(obj)
            else:
                # No ack_id: fall back to exact-last de-dupe (line+status)
                try:
                    last = self._messages[-1] if self._messages else None
                except Exception:
                    last = None
                if isinstance(last, dict) and \
                   str(last.get('line','')) == str(obj.get('line','')) and \
                   str(last.get('status','')) == str(obj.get('status','')):
                    # skip exact duplicate
                    pass
                else:
                    self._messages.append(obj)
            self._save_messages_to_store()
        except Exception:
            pass

    def _ack_update_ui(self, ack_id: str, new_text: str, status: str):
        it = self._ack_items.get(ack_id)
        if it is None:
            it = QListWidgetItem(self._strip_ack_id(new_text) + self._ticks_for_status(status)); it.setForeground(QBrush(self.COLOR_SENT)); it.setData(Qt.UserRole,'sent')
            import datetime as _dt
            _now = _dt.datetime.now().isoformat(timespec='seconds')
            self._ensure_header_top(_now)
            _idx = 1 if (self.messages_list.count()>0 and self.messages_list.item(0) and self.messages_list.item(0).data(Qt.UserRole)=='dateheader') else 0
            self.messages_list.insertItem(_idx, it)
            self._ack_items[ack_id] = it
        else:
            old = it.text(); prefix = (old.split('] ',1)[0] + '] ') if ('] ' in old) else '';
            it.setText(prefix + self._strip_ack_id(new_text) + self._ticks_for_status(status))
        self.messages_list.scrollToTop()
        self._touch_last_tx()
        self._persist_tx({'line': new_text, 'role': ('tx' if status.startswith('attempt') else ('acked' if status=='ack' else 'tx')), 'ts': datetime.datetime.now().isoformat(timespec='seconds'), 'ack_id': ack_id, 'status': status})

    def _on_serial_thread_line(self, line: str):
        # Step 4: drop self-RX (FROM == MYCALL)
        try:
            norm_step4 = re.sub(r"[\r\n]+", "", (line or "")).strip()
            m4 = _RC_CHAT_RE.match(norm_step4)
            if m4:
                frm4 = (m4.group(2) or "").upper()
                my4  = (self.mycall_edit.text().strip().upper() if hasattr(self, "mycall_edit") else "")
                if frm4 and my4 and frm4 == my4:
                    return
        except Exception:
            pass
        # Step 3: strict ACK check (never accept ACK from MYCALL; must match expected target)
        try:
            norm_step3 = re.sub(r"[\r\n]+", "", (line or "")).strip()
            mchat = _RC_CHAT_RE.match(norm_step3)
            to_cs, frm_cs, msg = (None, None, None)
            if mchat:
                to_cs  = (mchat.group(1) or "").upper()
                frm_cs = (mchat.group(2) or "").upper()
                msg    = (mchat.group(3) or "")
            my = (self.mycall_edit.text().strip().upper() if hasattr(self, "mycall_edit") else "")
            if msg is not None:
                am = _RC_ACK_RE.search(msg)
                if am:
                    aid = am.group(1).upper()
                    # Rule 1: an ACK will never be an ACK if it is from MYCALL
                    if frm_cs and my and frm_cs == my:
                        pass
                    else:
                        exp = getattr(self, "_pending_outbox", {}).get(aid)
                        if exp and frm_cs == (exp.get("target", "") or "").upper() and (not to_cs or to_cs == my):
                            st = (getattr(self, "_ack_states", {}) or {}).get(aid)
                            if st:
                                st.on_ack_received()
                            try:
                                self._append_rx(norm_step3)
                            except Exception:
                                pass
                            return
        except Exception:
            pass
        # Step 2: drop exact TX echoes seen very recently
        try:
            norm = re.sub(r"[\r\n]+", "", (line or "")).strip()
            if _RC_RECENT_TX.seen(norm):
                return
        except Exception:
            pass
        txt = (line or "").strip()
        norm = re.sub(r"[\r\n]+", "", txt).strip()
        # SELF-ECHO GUARD
        try:
            mycs = (self.mycall_edit.text().strip().upper() if hasattr(self, 'mycall_edit') else '')
            if mycs and re.search(rf"\bDE\s+{re.escape(mycs)}\b", norm, re.I):
                return
        except Exception:
            pass
        # --- Suppress local echo of our own control lines (FILE*/ACK) ---
        try:
            m = re.match(r'^([A-Z0-9/]+|CQ)\s+DE\s+([A-Z0-9/]+)\s*(.*)$', norm, re.I)
            if m:
                _to = (m.group(1) or "").strip().upper()
                _frm = (m.group(2) or "").strip().upper()
                _msg = (m.group(3) or "").strip()
                me = (self.mycall_edit.text().strip().upper() if hasattr(self, "mycall_edit") else "")
                if _frm == me and (_msg.startswith("FILE ") or re.search(r'\[ACK:', _msg)):
                    # swallow: don't append or process
                    return
        except Exception:
            pass

        # --- Auto-Relay (always on, silent) ---
        try:
            if " DE " in norm:
                parts = norm.split(" DE ", 1)
                if len(parts) >= 2:
                    target = parts[0].strip().upper()
                    mycall = self.mycall_edit.text().strip().upper() if hasattr(self, "mycall_edit") else ""
                    if target and target != mycall:
                        heard = set()
                        try:
                            if hasattr(self, "_graph_parents") and isinstance(self._graph_parents, dict):
                                heard.update([str(k).upper() for k in self._graph_parents.keys()])
                                for kids in self._graph_parents.values():
                                    if isinstance(kids, (list, tuple)):
                                        heard.update([str(x).upper() for x in kids])
                        except Exception:
                            pass
                        if target in heard:
                            if not hasattr(self, "_relay_cache"):
                                self._relay_cache = {}
                            import time as _time
                            now = _time.time()
                            # Purge cache entries older than 30s
                            self._relay_cache = {k:v for k,v in self._relay_cache.items() if now - v < 30}
                            if norm not in self._relay_cache:
                                self._relay_cache[norm] = now
                                try:
                                    self.send_user_text(norm)
                                except Exception:
                                    pass
        except Exception:
            pass
        m = re.search(r"\[ACK:([A-Za-z0-9]{4,10})\]", norm)
        if m:
            aid = m.group(1).upper()
            m2 = re.search(r"([A-Z0-9/]+)\s+DE\s+([A-Z0-9/]+)", norm, re.I)
            to_cs  = (m2.group(1) if m2 else '').strip().upper()
            frm_cs = (m2.group(2) if m2 else '').strip().upper()
            my = (self.mycall_edit.text().strip().upper() if hasattr(self, 'mycall_edit') else '')
            if frm_cs and my and frm_cs == my:
                return
            st = self._ack_states.get(aid) if hasattr(self, '_ack_states') else None
            if st and (norm in getattr(st, 'echo_texts', set())):
                return
            if st:
                exp = getattr(self, '_pending_outbox', {}).get(aid) if hasattr(self, '_pending_outbox') else None
                if exp:
                    want = (exp.get('target', '') or '').upper()
                    if frm_cs and want and frm_cs != want:
                        return
                st.on_ack_received()
            if self._message_should_display(norm):
                self._append_rx(norm)
            return

        if " DE " in norm:
            self._append_rx(norm)
            return
        try:
            self._scan_for_beacon_line(norm)
        except Exception:
            pass
        if getattr(self, 'monitor_all_check', None) and self.monitor_all_check.isChecked():
            self._append_rx(norm)

    def _next_ack_id(self) -> str:
        import random
        return f"{random.randint(1, 9999):04d}"

    def _serial_is_open(self):
        try:
            return getattr(self, 'ser', None) is not None and self.ser.is_open
        except Exception:
            return False

    def _open_serial(self, port: str, baud: int = 9600):
        if not SERIAL_AVAILABLE:
            QMessageBox.warning(self, 'Serial', 'pyserial is not installed. Install with: pip install pyserial')
            return False
        try:
            if self._serial_is_open():
                self.ser.close()
            self.ser = serial.Serial(port=port, baudrate=baud, timeout=0.1)
            self._status(f'Opened {port} @ {baud} bps')
            return True
        except Exception as e:
            QMessageBox.critical(self, 'Serial', f'Failed to open {port}: {e}')
            self.ser = None
            return False

    def _close_serial(self):
        try:
            if self._serial_is_open():
                p = self.ser.port
                self.ser.close()
                self._status(f'Closed {p}')
        except Exception:
            pass
        self.ser = None

    def _serial_write_bytes(self, data: bytes):
        if not self._serial_is_open():
            raise RuntimeError('Serial is not open')
        self.ser.write(data)

    def _serial_write_text(self, text: str):
        if not self._serial_is_open():
            raise RuntimeError('Serial is not open')
        self.ser.write(text.encode('ascii', errors='ignore'))

    def send_user_text(self, text: str) -> bool:
        """
        Wire SEND -> PTT by writing a full line to the serial device,
        with a short delay to mimic radio PTT keying.
        Returns True if actually written.
        """
        try:
            if not self._serial_is_open():
                self._status('TX blocked: open a COM port first.')
                try:
                    self._diag('[TX] blocked: serial not open')
                except Exception:
                    pass
                return False

            # remember TX for echo suppression
            try:
                _RC_RECENT_TX.note(text)
            except Exception:
                pass

            import time
            # Engage PTT: write the line with CR terminator
            self._serial_write_text(text + "\r")
            self._status('PTT keyed → TX sending...')
            time.sleep(0.2)  # delay before unkey (adjust as needed)

            # Release PTT (device unkeys autonomously after TX in this rig)
            self._status('PTT released after TX')
            return True

        except Exception as e:
            self._status(f'TX error: {e}')
            return False

            # Write user line with CR terminator
            self._serial_write_text(text + "\r")
            self._status('PTT keyed → TX sent → PTT released')
            return True
        except Exception as e:
            self._status(f'TX error: {e}')
            return False

            # Write user line with CR terminator
            self._serial_write_text(text + "\r")
            try:
                self._status('TX sent.')
            except Exception:
                pass
            return True
        except Exception as e:
            try:
                self._status(f'TX error: {e}')
            except Exception:
                pass
            return False

        if not self._serial_is_open():
            raise RuntimeError('Serial is not open')
        self.ser.write(text.encode('ascii', errors='ignore'))

    diag_log('ChatApp init starting')
    def __init__(self):
        self._start_maximized = True  # maximize on first show
        super().__init__()
        self._ensure_color_attrs()
        _install_vt323_font()
        app = QApplication.instance()
        app.setFont(QFont("VT323", 12))
        self.setFont(QFont("VT323", 12))
        _log_font_snapshot("init_after_app_and_window_font", self)
        _log_font_snapshot("init_after_setFont", self)
        self.setWindowTitle("Link500 Teensy Robust Chat v1.4.81.B")
        self.resize(1200, 800)

        self.fleet = FleetManager(os.path.join(app_base_dir(), 'Fleetlist.json'))
        self.beacon_minutes = 15
        self.hb_parent_seen = {}; self.hb_children = {}; self.sent_by_ack = {}
        self._messages = []
        self.ser = None
        # Beacon graph live state
        self._graph_parents = {}
        self._current_parent_for_children = None
        self._last_beacon_heard_ts = None

        self.central_widget = QWidget(); self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)

        # Toolbar + tabs
        self.toolbar = QToolBar("Main Toolbar"); self.addToolBar(Qt.TopToolBarArea, self.toolbar)
        self.tab_widget = QTabWidget(); self.toolbar.addWidget(self.tab_widget)
        # Main tab (home)
        self.main_tab = QWidget(); self.tab_widget.addTab(self.main_tab, "Main")

        # Theme selector
        self.theme_mgr = ThemeManager()
        self.toolbar.addSeparator(); self.toolbar.addWidget(QLabel(" Theme: "))
        self.theme_combo = QComboBox(); self.theme_combo.addItems(list(self.theme_mgr.themes.keys()))
        self.toolbar.addWidget(self.theme_combo)
        self.theme_combo.currentTextChanged.connect(self.apply_theme)

        # Manual ACK tab
        self.ack_tab = QWidget(); self.ack_layout = QHBoxLayout(self.ack_tab); self.ack_layout.setContentsMargins(8,4,8,4)
        self.ack_layout.addWidget(QLabel("ACK pause (s):"))
        self.ack_btns = []
        for val in (9,10,11,12,13):
            b = QPushButton(str(val)); b.setCheckable(True)
            b.clicked.connect(lambda _=False, v=val, btn=b: self._set_ack_pause(v, btn))
            self.ack_layout.addWidget(b); self.ack_btns.append(b)
        self.ack_layout.addStretch()
        self.tab_widget.addTab(self.ack_tab, "Manual ACK")

        # Beacon tab
        self.beacon_tab = QWidget(); bl = QHBoxLayout(self.beacon_tab); bl.setContentsMargins(8,4,8,4)
        bl.addWidget(QLabel("Beacon interval (min):"))
        self.beacon_5_btn = QPushButton("5 min"); self.beacon_10_btn = QPushButton("10 min"); self.beacon_15_btn = QPushButton("15 min")
        self.beacon_5_btn.clicked.connect(lambda: self.set_beacon_interval(5))
        self.beacon_10_btn.clicked.connect(lambda: self.set_beacon_interval(10))
        self.beacon_15_btn.clicked.connect(lambda: self.set_beacon_interval(15))
        bl.addWidget(self.beacon_5_btn); bl.addWidget(self.beacon_10_btn); bl.addWidget(self.beacon_15_btn); bl.addStretch()
        self.tab_widget.addTab(self.beacon_tab, "Beacon")

        # Network map tab
        self.linkmap_tab = QWidget()
        self.tab_widget.addTab(self.linkmap_tab, "Network Map")
        try:
            self.tab_widget.currentChanged.connect(lambda idx: self.on_toolbar_tab_changed(idx) if hasattr(self, 'on_toolbar_tab_changed') else None)
        except Exception:
            pass
        self.tab_widget.setCurrentIndex(0)

        # Content split
        self.content_layout = QHBoxLayout(); self.main_layout.addLayout(self.content_layout)
        self.left_container = QWidget(); self.left_stack = QVBoxLayout(self.left_container); self.content_layout.addWidget(self.left_container, 2)
        self.right_panel = QWidget(); self.right_layout = QVBoxLayout(self.right_panel); self.right_layout.setContentsMargins(0,0,0,0); self.content_layout.addWidget(self.right_panel, 0)

        # Right panel
        self.dial_group = QGroupBox("Dial Frequencies"); dv = QVBoxLayout(self.dial_group)
        for t in ("7.090,3 MHz", "10.148,3 MHz", "14.109 MHz"): dv.addWidget(QLabel(t))
        self.right_layout.addWidget(self.dial_group, 0)
        self.beacon_group = QGroupBox("Beacons Heard"); bv = QVBoxLayout(self.beacon_group)
        self.beacons_list = QListWidget(); bv.addWidget(self.beacons_list)
        self.last_tx_label = QLabel("Last TX: —")

        try:
            if not hasattr(self, 'last_tx_timer'):
                self.last_tx_timer = QTimer(self)
                self.last_tx_timer.setInterval(15000)  # 15s
                self.last_tx_timer.timeout.connect(self._update_last_tx_label)
                self.last_tx_timer.start()
        except Exception:
            pass
        bv.addWidget(self.last_tx_label)
        self.right_layout.addWidget(self.beacon_group, 1)

        # Build left views
        diag_log('Building main left view'); self._build_main_left_view()
        diag_log('Building linkmap left view'); self._build_linkmap_left_view()
        self._show_main_view()

        # Status bar
        # Auto-beacon: timer + restore settings or default enable (15 min) after ~3 minutes
        try:
            self.beacon_timer = QTimer(self)
            self.beacon_timer.timeout.connect(self._send_beacon)
        except Exception:
            self.beacon_timer = None
        try:
            enabled, mins = self._load_beacon_from_settings()
            if enabled:
                # Restore user's last setting
                self._enable_beacon(mins, immediate=False)
            else:
                # Auto-enabled by default after 3 minutes of idle
                self.auto_beacon_timer = QTimer(self)
                self.auto_beacon_timer.setSingleShot(True)
                def _auto_arm():
                    try:
                        # Send one now and arm every 15 minutes
                        self._enable_beacon(15, immediate=True)
                        # Persist so next launch is enabled by default
                        self._save_beacon_to_settings(True, 15)
                        try:
                            self._status('Auto-beacon armed: every 15 min', 2500)
                        except Exception:
                            pass
                    except Exception:
                        pass
                self.auto_beacon_timer.timeout.connect(_auto_arm)
                self.auto_beacon_timer.start(180_000)
        except Exception:
            try:
                self.auto_beacon_timer = QTimer(self)
                self.auto_beacon_timer.setSingleShot(True)
                self.auto_beacon_timer.timeout.connect(lambda: self._enable_beacon(15, immediate=True))
                self.auto_beacon_timer.start(180_000)
            except Exception:
                pass
        try:
            pass
        except Exception:
            pass
        # Global colors
        self.COLOR_SENT = QColor(0,255,0); self.COLOR_RX = QColor(255,165,0)

        # Load settings + messages + beacons
        diag_log('Loading settings'); self.load_settings()
        try:
            self._apply_tx_color_for_theme(getattr(self, 'theme_name', ''))
        except Exception:
            pass
        self._reflect_ack_pause_button()
        diag_log('Updating beacons list'); self._load_link_graph()
        try:
            self._purge_self_from_graph()
        except Exception:
            pass
        self._refresh_beacons_ui(); self.update_beacons_list()

        self._setup_timers()

    # ---------- UI BUILDERS ----------
        # Open window maximized for tablet/PC
        try:
            self.showMaximized()
        except Exception:
            pass

    def _build_main_left_view(self):
        self.main_left = QWidget(); self.left_stack.addWidget(self.main_left)
        self.left_layout = QVBoxLayout(self.main_left)

        self.top_row = QWidget(); self.top_row_layout = QHBoxLayout(self.top_row); self.top_row_layout.setContentsMargins(0,0,0,0); self.top_row_layout.setSpacing(12)
        self.left_layout.addWidget(self.top_row)

        self._ui_serial_section()
        self._ui_fleet_section()
        self.top_row_layout.addStretch(1)

        self._ui_my_row_section()
        self._ui_messages_section()
        self._ui_send_section()
        self._ui_fixed_gps_section()
        self._ui_file_upload_section()

    def _build_linkmap_left_view(self):
        diag_log('Enter _build_linkmap_left_view')
        self.map_left = QWidget(); self.left_stack.addWidget(self.map_left)
        v = QVBoxLayout(self.map_left)
        def _get_mycall(): return base_callsign(self.mycall_edit.text()) if hasattr(self,"mycall_edit") else "MYCALL"
        def _get_live():
            data = load_json("link_graph.json") or {}
            parents = {}
            try:
                if isinstance(data, dict):
                    if isinstance(data.get("parents"), dict):
                        parents = data["parents"]
                    elif isinstance(data.get("graph"), dict):
                        parents = data["graph"]
                    elif isinstance(data.get("beacons"), dict):
                        parents = data["beacons"]
                    else:
                        # if flat list, make them direct parents with no children
                        if isinstance(data.get("nodes"), list):
                            parents = {str(x): [] for x in data["nodes"] if isinstance(x,(str,))}
                elif isinstance(data, list):
                    parents = {str(x): [] for x in data if isinstance(x,(str,))}
            except Exception:
                parents = {}
            # normalize children
            children = {}
            for p, v in (parents.items() if isinstance(parents, dict) else []):
                if isinstance(v, (list,tuple)):
                    children[p] = [str(x) for x in v if isinstance(x,(str,))]
                elif isinstance(v, dict):
                    children[p] = list(v.keys())
                else:
                    children[p] = []
            edges = []
            for p, kids in children.items():
                for c in kids:
                    edges.append((p, c))
            return parents, children, edges
        self.linkmap = LinkMapWidget(_get_mycall, _get_live, lambda: self.theme_mgr.current if hasattr(self,'theme_mgr') else {})
        try:
            self.linkmap.get_metric = self._metric_from_mycall
        except Exception:
            pass
        self.linkmap_scroll = QScrollArea(self)
        self.linkmap_scroll.setWidget(self.linkmap)
        self.linkmap_scroll.setWidgetResizable(True)
        self.linkmap_scroll.setFrameShape(QFrame.NoFrame)
        self.linkmap_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        v.addWidget(self.linkmap_scroll, 1)
        try:
            ctrl = QWidget(self)
            hl = QHBoxLayout(ctrl)
            ctrl.setLayout(hl)
            self.btn_reload_pos = QPushButton('Reload Positions', ctrl)
            self.btn_reload_graph = QPushButton('Reload Links', ctrl)
            self.btn_reload_pos.setFixedWidth(140)
            self.btn_reload_graph.setFixedWidth(120)
            hl.addWidget(self.btn_reload_pos)
            hl.addWidget(self.btn_reload_graph)
            hl.addStretch(1)
            # Size buttons to fit text + padding
            try:
                fm = self.fontMetrics()
                w1 = fm.horizontalAdvance(self.btn_reload_pos.text()) + 24
                w2 = fm.horizontalAdvance(self.btn_reload_graph.text()) + 24
                self.btn_reload_pos.setFixedWidth(w1)
                self.btn_reload_graph.setFixedWidth(w2)
            except Exception:
                pass

            v.addWidget(ctrl, 0)
            def _do_reload_positions():
                try:
                    self._load_positions()
                except Exception:
                    pass
                try:
                    self.linkmap.draw_graph()
                except Exception:
                    pass
            def _do_reload_graph():
                try:
                    self._load_link_graph()
                except Exception:
                    pass
                try:
                    self.linkmap.draw_graph()
                except Exception:
                    pass
            self.btn_reload_pos.clicked.connect(_do_reload_positions)
            self.btn_reload_graph.clicked.connect(_do_reload_graph)
        except Exception:
            pass
    def _show_main_view(self): self.main_left.show(); self.map_left.hide()
    def _show_map_view(self):
        try:
            self.linkmap.reset_view()  # avoid heavy refit; just reset
        except Exception as e:
            try:
                self._status(f"Map render suppressed: {e}", 5000)
            except Exception:
                pass
        self.map_left.show(); self.main_left.hide()

    # ---------- Sections ----------
    def _ui_serial_section(self):
        group = QGroupBox("Serial Port"); v = QVBoxLayout(group)
        row = QHBoxLayout()
        row.addWidget(QLabel("Connection:"))
        self.serial_combo = QComboBox(); row.addWidget(self.serial_combo, 1)
        self.connect_button = QPushButton("Connect"); self.connect_button.clicked.connect(self.toggle_serial); row.addWidget(self.connect_button)
        refresh_btn = QPushButton("Refresh"); refresh_btn.clicked.connect(self.refresh_serial_ports); row.addWidget(refresh_btn)
        disc_btn = QPushButton("Disconnect"); disc_btn.clicked.connect(self.disconnect_serial); row.addWidget(disc_btn)
        v.addLayout(row)
        row2 = QHBoxLayout()
        self.kiss_check = QCheckBox('KISS mode'); row2.addWidget(self.kiss_check)
        def _kiss_toggled(on: bool):
            if not self._serial_is_open():
                QMessageBox.warning(self, 'KISS Mode', 'Select and connect a COM port before toggling KISS mode.')
                self.kiss_check.blockSignals(True)
                self.kiss_check.setChecked(False)
                self.kiss_check.blockSignals(False)
                return
            try:
                if on:
                    # ENTER KISS: ESC (27), then '@K'
                    self._serial_write_bytes(bytes([27]))
                    self._serial_write_text('@K')
                    self._status('Sent ENTER KISS (ESC @K)')
                else:
                    # EXIT KISS: 192,255,192,13
                    self._serial_write_bytes(bytes([192,255,192,13]))
                    self._status('Sent KISS OFF (192,255,192,13)')
            except Exception as e:
                QMessageBox.critical(self, 'KISS Mode', f'Serial write failed: {e}')
                # revert
                self.kiss_check.blockSignals(True)
                self.kiss_check.setChecked(not on)
                self.kiss_check.blockSignals(False)
        try:
            self.kiss_check.toggled.connect(_kiss_toggled)
        except Exception:
            pass
        self.monitor_all_check = QCheckBox("Monitor All Traffic"); row2.addWidget(self.monitor_all_check); row2.addStretch(1)
        v.addLayout(row2)
        self.top_row_layout.addWidget(group, 0)
        self.refresh_serial_ports()

    def _ui_fleet_section(self):
        g = QGroupBox("Fleet Manager"); v = QVBoxLayout(g)
        r0 = QHBoxLayout(); self.fleet_enable_check = QCheckBox("Enable (whitelist)"); r0.addWidget(self.fleet_enable_check); r0.addStretch(1); v.addLayout(r0)
        self.active_fleet_combo = QComboBox(); self.active_fleet_combo.addItems(self.fleet.list_fleet_names())
        v.addWidget(self.active_fleet_combo)
        # Set initial value with signals blocked
        try:
            self.active_fleet_combo.blockSignals(True)
            self.active_fleet_combo.setCurrentText(self.fleet.active_fleets[0])
            self.active_fleet_combo.blockSignals(False)
        except Exception:
            pass
        # Member list before connecting signal to avoid early callback
        self.member_list = QListWidget(); v.addWidget(self.member_list); self._populate_member_list()
        # Now connect change handler
        self.active_fleet_combo.currentTextChanged.connect(self._on_active_fleet_changed)
        r1 = QHBoxLayout()
        add_group_btn = QPushButton("Add Group"); add_group_btn.clicked.connect(self.add_fleet_group); r1.addWidget(add_group_btn)
        add_member_btn = QPushButton("Add Callsign"); add_member_btn.clicked.connect(self.add_fleet_member); r1.addWidget(add_member_btn)
        rm_member_btn = QPushButton("Remove Callsign"); rm_member_btn.clicked.connect(self.remove_fleet_member_btn); r1.addWidget(rm_member_btn); r1.addStretch(1)
        v.addLayout(r1)
        self.top_row_layout.addWidget(g, 1)

        inc = QGroupBox("Incoming Files"); incv = QVBoxLayout(inc)
        self.auto_accept_files = QCheckBox("Auto-accept files"); incv.addWidget(self.auto_accept_files)
        # load persisted auto-accept
        try:
            st = load_json("settings.json") or {}
            self.auto_accept_files.setChecked(bool(st.get("auto_accept_files", False)))
        except Exception: pass
        def _persist_auto_accept(on):
            try:
                st2 = load_json("settings.json") or {}
                st2["auto_accept_files"] = bool(on)
                save_json("settings.json", st2)
            except Exception: pass
        try: self.auto_accept_files.toggled.connect(_persist_auto_accept)
        except Exception: pass

        self.incoming_list = QListWidget(); incv.addWidget(self.incoming_list)
        br = QHBoxLayout(); acc = QPushButton("Accept"); dec = QPushButton("Decline"); rst = QPushButton("Reset Window")
        acc.clicked.connect(self._incoming_accept_selected); dec.clicked.connect(self._incoming_decline_selected); rst.clicked.connect(self._incoming_reset_window)
        br.addWidget(acc); br.addWidget(dec); br.addStretch(1); br.addWidget(rst); incv.addLayout(br)
        self.top_row_layout.addWidget(inc, 2)

    def _ui_my_row_section(self):
        row = QWidget(); h = QHBoxLayout(row); h.setContentsMargins(0,0,0,0)
        h.addWidget(QLabel("Target"))
        self.to_edit = QLineEdit(); self._force_callsign_lineedit(self.to_edit); h.addWidget(self.to_edit)
        h.addSpacing(12); h.addWidget(QLabel("From"))
        self.mycall_edit = QLineEdit(); self._force_callsign_lineedit(self.mycall_edit); h.addWidget(self.mycall_edit)
        h.addStretch(1)
        self.left_layout.addWidget(row)

    def _ui_messages_section(self):
        g = QGroupBox("Messages"); v = QVBoxLayout(g)
        self.messages_list = QListWidget(); v.addWidget(self.messages_list, 10)
        try:
            self._ensure_store_paths()
        except Exception:
            pass
        self._last_header_date_top = None
        clear_btn = QPushButton("Clear Messages"); clear_btn.clicked.connect(self.clear_receive_window); v.addWidget(clear_btn)
        self.left_layout.addWidget(g, 10)

    def _ui_send_section(self):
        g = QGroupBox("Send Message"); h = QHBoxLayout(g)
        self.send_edit = QTextEdit(); fm = QFontMetrics(self.send_edit.font()); self.send_edit.setMinimumHeight(fm.lineSpacing()*4+20); self.send_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed); h.addWidget(self.send_edit, 1)
        
        # --- compact send field (~1.5 lines) ---
        try:
            _fm = QFontMetrics(self.send_edit.font())
            _line = _fm.lineSpacing()
            _pad = self.send_edit.contentsMargins().top() + self.send_edit.contentsMargins().bottom()
            _frame = int(getattr(self.send_edit, 'frameWidth', lambda: 0)()) * 2
            _h = max(24, int(_line * 1.5 + _pad + _frame))
            self.send_edit.setFixedHeight(_h)
            try:
                self.send_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            except Exception:
                pass
            self.send_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        except Exception:
            pass
        col = QVBoxLayout(); send_btn = QPushButton("SEND"); send_btn.clicked.connect(self.send_message); col.addWidget(send_btn, alignment=Qt.AlignRight)
        col.addStretch(1); col.addStretch(1); h.addLayout(col, 0)
        self.left_layout.addWidget(g, 1)

    def _ui_fixed_gps_section(self):
        g = QGroupBox("Fixed GPS (decimal degrees)"); h = QHBoxLayout(g)
        self.fixed_lat_edit = QLineEdit(); self.fixed_lon_edit = QLineEdit()
        h.addWidget(QLabel("Lat:")); h.addWidget(self.fixed_lat_edit); h.addWidget(QLabel("Lon:")); h.addWidget(self.fixed_lon_edit)
        # widths ~30ch
        try:
            fm = QFontMetrics(self.fixed_lat_edit.font())
            w30 = int(fm.averageCharWidth()*30 + 8)
            for _le in (self.fixed_lat_edit, self.fixed_lon_edit):
                _le.setMaxLength(10); _le.setFixedWidth(w30); _le.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        except Exception: pass
        self.send_fix_btn = QPushButton("  SEND FIX POS  "); self.send_fix_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        self.send_fix_btn.clicked.connect(self.save_fixed_gps)
        h.addWidget(self.send_fix_btn)
        # left-justify group
        wrap = QWidget(); hb = QHBoxLayout(wrap); hb.setContentsMargins(0,0,0,0); hb.addWidget(g); hb.addStretch(1)
        self.left_layout.addWidget(wrap)

    def _ui_file_upload_section(self):
        g = QGroupBox("File Upload")
        h = QHBoxLayout(g)
        self.upload_btn = QPushButton("  Upload  "); self.upload_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        self.upload_btn.clicked.connect(self.choose_file_to_send); h.addWidget(self.upload_btn)
        self.file_path_edit = QLineEdit(); self.file_path_edit.setReadOnly(True); h.addWidget(self.file_path_edit)
        try:
            fm = QFontMetrics(self.file_path_edit.font()); w60 = int(fm.averageCharWidth()*60 + 12)
            self.file_path_edit.setFixedWidth(w60); self.file_path_edit.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        except Exception: pass
        self.send_file_btn = QPushButton("  Send File  "); self.send_file_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        self.send_file_btn.clicked.connect(self.send_selected_file); h.addWidget(self.send_file_btn)
        self.remote_label = QLabel("Remote: —"); h.addWidget(self.remote_label)
        # left-justify
        wrap2 = QWidget(); hb2 = QHBoxLayout(wrap2); hb2.setContentsMargins(0,0,0,0); hb2.addWidget(g); hb2.addStretch(1)
        self.left_layout.addWidget(wrap2)

    # ---------- Helpers / persistence ----------
    def _force_callsign_lineedit(self, le):
        le.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        # Accept lowercase too, digits, / and - ; keep max 10 chars
        rx = QRegularExpression(r"^[A-Za-z0-9/-]{0,10}$")
        le.setValidator(QRegularExpressionValidator(rx, le))
        le.setMaxLength(10)
        # Auto-uppercase on user edits
        def _to_upper(_):
            try:
                cur = le.cursorPosition()
                txt = le.text()
                up = txt.upper()
                if up != txt:
                    le.blockSignals(True)
                    le.setText(up)
                    le.blockSignals(False)
                    le.setCursorPosition(cur)
            except Exception:
                pass
        try:
            le.textEdited.connect(_to_upper)
        except Exception:
            pass

    def refresh_serial_ports(self):
        ports = [f"COM{i}" for i in range(1, 17)] if os.name == "nt" else ["/dev/ttyS0","/dev/ttyUSB0"]
        self.serial_combo.clear(); self.serial_combo.addItems(ports)

    def toggle_serial(self):
        
        if self.connect_button.text() == 'Connect':
            port = self.serial_combo.currentText().strip()
            if not port:
                QMessageBox.warning(self, 'Serial', 'Please select a COM port first.')
                return
            if self._open_serial(port):
                self.connect_button.setText('Disconnect')
                self._status('Connected')
                try:
                    self.reader_thread = SerialReaderThread(self)
                    self.reader_thread.line_received.connect(self._on_serial_thread_line)
                    self.reader_thread.start()
                except Exception:
                    pass
        else:
            self.disconnect_serial()

    def disconnect_serial(self):
        
        try:
            if hasattr(self, 'reader_thread') and self.reader_thread is not None:
                self.reader_thread.stop()
                self.reader_thread.wait(500)
                self.reader_thread = None
        except Exception:
            pass
        self._close_serial()
        self.connect_button.setText('Connect')
        self._status('Disconnected')

    def _sync_remote_label(self, *_):
        try:
            tgt = base_callsign(self.to_edit.text().strip().upper()) if hasattr(self,"to_edit") else ""
            self.remote_label.setText(f"Remote: {tgt or '—'}")
        except Exception: pass

    def load_settings(self):
        diag_log('Enter load_settings')
        st = load_json("settings.json") or {}
        self.mycall_edit.setText(st.get("mycall",""))
        self.to_edit.setText("")
        # scrub legacy target key if present
        if "target" in st:
            try:
                del st["target"]
                save_json("settings.json", st)
            except Exception:
                pass
        # Theme load
        tn = st.get("theme", "Light")
        # KISS mode: no persistence (requires live serial)
        try:
            idx = self.theme_combo.findText(tn); 
            if idx >= 0: self.theme_combo.setCurrentIndex(idx)
            self.apply_theme(tn)
        except Exception: pass
        # Remote label
        self._sync_remote_label()
        try: self.to_edit.textChanged.connect(self._sync_remote_label)
        except Exception: pass
        # Persist From (mycall) immediately when changed
        def _persist_mycall_change(_txt:str):
            try:
                st2 = load_json("settings.json") or {}
                st2["mycall"] = self.mycall_edit.text().strip().upper()
                save_json("settings.json", st2)
            except Exception:
                pass
        try:
            self.mycall_edit.textChanged.connect(_persist_mycall_change)
        except Exception:
            pass
        # Fixed GPS load
        gps = load_json("fixed_gps.json") or {}
        try:
            self.fixed_lat_edit.setText(str(gps.get("lat","")))
            self.fixed_lon_edit.setText(str(gps.get("lon","")))
        except Exception: pass
        # Load messages
        self._load_messages_from_store()
        try:
            app = QApplication.instance()
            from PyQt5.QtGui import QFont
            app.setFont(QFont('VT323', getattr(self,'_font_pt',12)))
            self.setFont(QFont('VT323', getattr(self,'_font_pt',12)))
        except Exception:
            pass
    def save_settings(self):
        st = {
            "mycall": self.mycall_edit.text().strip().upper(),
            "beacon_minutes": self.beacon_minutes
        }
        st["auto_accept_files"] = bool(self.auto_accept_files.isChecked()) if hasattr(self,"auto_accept_files") else False
        st["theme"] = self.theme_combo.currentText() if hasattr(self,"theme_combo") else "Light"
        # KISS not persisted
        save_json("settings.json", st)

    def apply_theme(self, name: str):
        self.theme_mgr.apply(self, name)
        try:
            if hasattr(self, 'linkmap') and hasattr(self.linkmap, 'view'):
                bg = QColor(self.theme_mgr.color('panel_bg', '#f5f5f5'))
                self.linkmap.view.setBackgroundBrush(QBrush(bg))
                self.linkmap.draw_graph()
        except Exception:
            pass
        # persist immediately
        try:
            st = load_json("settings.json") or {}
            st["theme"] = name
            save_json("settings.json", st)
        except Exception: pass

    def _set_ack_pause(self, seconds, btn):
        self.manual_ack_pause = int(seconds)
        self._reflect_ack_pause_button()

    def _reflect_ack_pause_button(self):
        v = int(getattr(self, "manual_ack_pause", 10))
        for b in self.ack_btns:
            b.setStyleSheet("background-color: lime; color: black; border: 1px solid lime;" if b.text().strip()==str(v)
                            else "background-color: #000; color: lime; border: 1px solid lime;")
    def set_beacon_interval(self, mins):
        try:
            m = int(mins)
        except Exception:
            m = 15
        self.beacon_minutes = m
        try:
            st = self._settings_get()
            st['beacon'] = {'enabled': True, 'minutes': m}
            self._settings_set(st)
        except Exception:
            pass
        self._enable_beacon(m, immediate=True)

    def update_beacons_list(self):
        # prefer in-memory graph but also accept file-only
        if getattr(self, '_graph_parents', None):
            self._refresh_beacons_ui()
            return
        data = load_json("link_graph.json") or {}
        self.beacons_list.clear()
        parents = data.get("parents") if isinstance(data, dict) else {}
        if isinstance(parents, dict):
            for p, kids in sorted(parents.items()):
                self.beacons_list.addItem(f"..{p}")
                if isinstance(kids, (list,tuple)):
                    for k in kids: self.beacons_list.addItem(f"  /{k}")

    
    # ---- Beacon graph persistence/update ----
    def _load_link_graph(self):
        """Load graph from store/link_graph.json into memory and last_beacon timestamp if present."""
        try:
            data = load_json("link_graph.json") or {}
            parents = data.get("parents") if isinstance(data, dict) else {}
            if isinstance(parents, dict):
                self._graph_parents = {str(k): [str(x) for x in (v or [])] for k, v in parents.items()}
            else:
                self._graph_parents = {}
            ts = data.get("last_beacon_ts")
            if ts:
                try:
                    self._last_beacon_heard_ts = datetime.datetime.fromisoformat(ts)
                except Exception:
                    self._last_beacon_heard_ts = None
        except Exception:
            self._graph_parents = {}
            self._last_beacon_heard_ts = None

    def _save_link_graph(self):
        """Persist current graph to store/link_graph.json (with last_beacon_ts)."""
        try:
            payload = {"parents": self._graph_parents}
            if self._last_beacon_heard_ts:
                payload["last_beacon_ts"] = self._last_beacon_heard_ts.isoformat(timespec="seconds")
            save_json("link_graph.json", payload)
        except Exception:
            pass

    def _refresh_beacons_ui(self):
        """Refresh the Beacons Heard UI from the in-memory graph.
        Parent entries (lime), children (orange), children indented by 2 spaces.
        """
        try:
            from PyQt5.QtWidgets import QListWidgetItem
            from PyQt5.QtGui import QBrush, QColor
            self.beacons_list.clear()
            try:
                myc = self.mycall_edit.text().strip().upper()
            except Exception:
                myc = ""
            parent_brush = QBrush(QColor(50, 205, 50))   # lime green
            child_brush  = QBrush(QColor(255, 165, 0))   # orange
            for p, kids in sorted(self._graph_parents.items()):
                if p.upper() == myc:
                    continue
                itp = QListWidgetItem(p)
                itp.setForeground(parent_brush)
                self.beacons_list.addItem(itp)
                for c in [c for c in kids if (c or '').upper() != myc]:
                    itc = QListWidgetItem("  " + c)
                    itc.setForeground(child_brush)
                    self.beacons_list.addItem(itc)
        except Exception:
            pass
    def _record_parent_beacon(self, parent_cs: str):
        # Ignore our own parent beacons
        try:
            myc = self.mycall_edit.text().strip().upper()
            if base_callsign(parent_cs).upper() == myc:
                return
        except Exception:
            pass
        p = base_callsign(parent_cs)
        if not p:
            return
        if p not in self._graph_parents:
            self._graph_parents[p] = []
        self._current_parent_for_children = p
        self._last_beacon_heard_ts = datetime.datetime.now()
        self._save_link_graph()
        self._refresh_beacons_ui()

    def _record_child_beacon(self, child_cs: str):
        try:
            myc = self.mycall_edit.text().strip().upper()
            if base_callsign(child_cs).upper() == myc:
                return
        except Exception:
            pass
        if not self._current_parent_for_children:
            return
        p = self._current_parent_for_children
        c = base_callsign(child_cs)
        if not c:
            return
        if c not in self._graph_parents.get(p, []):
            self._graph_parents.setdefault(p, []).append(c)
        self._last_beacon_heard_ts = datetime.datetime.now()
        self._save_link_graph()
        self._refresh_beacons_ui()

    def _scan_for_beacon_line(self, line: str):
        """Parse incoming lines for '..PARENT' and '/CHILD' tokens and update graph immediately."""
        try:
            txt = (line or "").strip().upper()
            m_parent = re.match(r'^\.\.\s*([A-Z0-9/]+)', txt)
            if m_parent:
                self._record_parent_beacon(m_parent.group(1))
                return
            m_child = re.match(r'^/\s*([A-Z0-9/]+)', txt) or re.match(r'^\s{0,2}/\s*([A-Z0-9/]+)', txt)
            if m_child:
                self._record_child_beacon(m_child.group(1))
                return
        except Exception:
            pass

    def _clear_graph_if_stale(self, minutes=20):
        """If no beacons heard for N minutes, clear link_graph.json and UI."""
        try:
            now = datetime.datetime.now()
            last = self._last_beacon_heard_ts
            if last is None:
                # derive from file timestamp if present
                data = load_json("link_graph.json") or {}
                ts = data.get("last_beacon_ts")
                if ts:
                    try:
                        last = datetime.datetime.fromisoformat(ts)
                        self._last_beacon_heard_ts = last
                    except Exception:
                        last = None
            if last is None:
                return
            delta = (now - last).total_seconds() / 60.0
            if delta > minutes and self._graph_parents:
                self._graph_parents = {}
                self._current_parent_for_children = None
                # do not reset last timestamp; leave it to indicate last activity
                self._save_link_graph()
                self._refresh_beacons_ui()
                try:
                    if hasattr(self,'linkmap'): self.linkmap.draw_graph()
                except Exception:
                    pass
        except Exception:
            pass
# ---- Messages storage (store/messages_v1.json) ----
    def _messages_store_path(self):
        return store_path('messages_v1.json')

    def _save_messages_to_store(self):
        data = {'version': 1, 'messages': getattr(self, '_messages', [])}
        save_json('messages_v1.json', data)

    
    def _load_messages_from_store(self):
        diag_log('Enter _load_messages_from_store')
        data = load_json('messages_v1.json') or {}
        raw = data.get('messages', [])
        normalized = []
        changed = False
        nowts = self._utc_now_iso() if hasattr(self, '_utc_now_iso') else None
        try:
            for m in raw:
                if isinstance(m, str):
                    normalized.append({'line': m, 'role': 'rx', 'ts': nowts})
                    changed = True
                elif isinstance(m, dict):
                    line = str(m.get('line', ''))
                    role = str(m.get('role', 'sent')).lower()
                    if role not in ('sent', 'rx', 'acked', 'tx'):
                        role = 'sent'; changed = True
                    ts = m.get('ts') or nowts
                    if isinstance(ts, str) and ts.endswith('+00:00'):
                        ts = ts.replace('+00:00', 'Z'); changed = True
                    obj = {'line': line, 'role': role, 'ts': ts}
                    # carry over status/ack_id if present
                    if 'status' in m: obj['status'] = m.get('status')
                    if 'ack_id' in m: obj['ack_id'] = m.get('ack_id')
                    normalized.append(obj)
                else:
                    changed = True
            # ---- COMPACT: keep only latest record per ack_id ----
            compacted = []
            seen = set()
            for m in reversed(normalized):
                aid = str(m.get('ack_id') or '').strip()
                if aid:
                    if aid in seen:
                        continue
                    seen.add(aid)
                compacted.append(m)
            compacted.reverse()
            self._messages = compacted
        except Exception:
            self._messages = []
        self.messages_list.clear()
        for msg in self._messages:

            line = msg.get('line',''); role = (msg.get('role') or '').lower()
            prefix = self._fmt_disp_prefix(msg.get('ts') or msg.get('time') or '')
            item = QListWidgetItem(prefix + line)
            if role == 'acked':
                item.setForeground(QBrush(self.COLOR_ACK)); item.setData(Qt.UserRole, 'acked')
            elif role == 'rx':
                item.setForeground(QBrush(self.COLOR_RX)); item.setData(Qt.UserRole, 'rx')
            else:
                item.setForeground(QBrush(self.COLOR_SENT)); item.setData(Qt.UserRole, 'sent')
            self.messages_list.insertItem(0, item)
        self.messages_list.scrollToTop()
        if changed:
            try:
                save_json('messages_v1.json', {'version': 1, 'messages': self._messages})
            except Exception:
                pass
    def send_message(self):
        
        
        # Robust SEND path with ACK Manager integration and UI safety
        to = (self.to_edit.text() if hasattr(self, 'to_edit') else '').strip().upper()
        me = (self.mycall_edit.text() if hasattr(self, 'mycall_edit') else '').strip().upper()
        msg = (self.send_edit.toPlainText() if hasattr(self, 'send_edit') else '').strip()
        if not to or not me or not msg:
            try:
                QMessageBox.information(self, 'Send', 'Please fill Target, From, and Message.')
            except Exception:
                pass
            return

        try:
            ack_id = self._next_ack_id()
        except Exception:
            # fallback id
            ack_id = "0000"

        base_line = f"{to} DE {me} {msg} [ACK:{ack_id}]"
        first = f"{base_line} (attempt 1/3)"

        # Create/append TX list item safely
        try:
            import datetime as _dt
            now_iso = _dt.datetime.now().isoformat(timespec='seconds')
            it = QListWidgetItem(self._fmt_disp_prefix(now_iso) + self._strip_ack_id(first) + self._ticks_for_status('attempt 1/3'))
            try:
                from PyQt5.QtGui import QBrush
                it.setForeground(QBrush(self.COLOR_SENT)); it.setForeground(QBrush(fg))
            except Exception:
                pass
            it.setData(Qt.UserRole,'sent')
            self.messages_list.insertItem(0, it)
            self.messages_list.scrollToTop()
        except Exception:
            it = None

        # Ensure dict holders
        if not hasattr(self, '_ack_items') or not isinstance(getattr(self, '_ack_items'), dict):
            self._ack_items = {}
        if not hasattr(self, '_ack_states') or not isinstance(getattr(self, '_ack_states'), dict):
            self._ack_states = {}

        self._ack_items[ack_id] = it

        # Persist first attempt
        try:
            self._messages.append({'line': first, 'role': 'tx', 'ts': datetime.datetime.now().isoformat(timespec='seconds'), 'ack_id': ack_id, 'status':'attempt 1/3'})
            self._save_messages_to_store()
        except Exception:
            pass

        # Start ACK state
        try:
            pause = int(getattr(self, 'manual_ack_pause', 12))
        except Exception:
            pause = 12
        try:
            st = AckState(self, ack_id, base_line, pause)
            self._ack_states[ack_id] = st
            st.start()
        except Exception as e:
            try:
                diag_log(f"[ERROR] starting AckState: {type(e).__name__}: {e}")
            except Exception:
                pass
        # Clear the message input after sending
        try:
            self.send_edit.clear()
        except Exception:
            pass

    def add_received_message(self, line: str):
        item = QListWidgetItem(line)
        try: item.setForeground(QBrush(self.COLOR_RX))
        except Exception: pass
        try: item.setData(Qt.UserRole, "rx")
        except Exception: pass
        self.messages_list.insertItem(0, item)
        self.messages_list.scrollToTop()
        # Try auto-ACK to sender if message addressed to me contains an ACK request
        try:
            import re as _re
            m = _re.match(r'^\s*([A-Z0-9\-]+)\s+DE\s+([A-Z0-9\-]+)\s*(.*)$', line.strip(), flags=_re.I)
            if m:
                to_call, frm_call, rest = m.group(1).upper(), m.group(2).upper(), (m.group(3) or '').strip()
                try:
                    self._auto_ack_if_needed(frm_call, to_call, rest)
                except Exception:
                    pass
        except Exception:
            pass

        # Beacon parse/update
        try:
            self._scan_for_beacon_line(line)
        except Exception:
            pass
        try:
            self._messages.append({'line': line, 'role': 'rx', 'ts': datetime.datetime.now().isoformat(timespec='seconds')})
            self._save_messages_to_store()
        except Exception: pass

    def mark_selected_acked(self):
        it = self.messages_list.currentItem()
        if it is None:
            for i in range(self.messages_list.count()-1, -1, -1):
                cand = self.messages_list.item(i)
                if (cand.data(Qt.UserRole) or "").lower() == "sent":
                    it = cand; break
        if it is None: return
        try:
            it.setForeground(QBrush(self.COLOR_ACK))
            it.setData(Qt.UserRole, "acked")
            # persist
            row = self.messages_list.row(it)
            if 0 <= row < len(self._messages):
                self._messages[row]['role'] = 'acked'
                self._save_messages_to_store()
        except Exception: pass

    def clear_receive_window(self):
        # Clear the UI list
        self.messages_list.clear()
        # Clear in-memory history
        self._messages = []
        # Persist empty history to store/messages_v1.json
        try:
            self._save_messages_to_store()
            self._status("Messages cleared and history reset.", 3000)
        except Exception:
            pass

    # ---- Incoming Files (stubs) ----
    def _incoming_selected_sid(self):
        it = self.incoming_list.currentItem()
        return it.text() if it else None
    def _incoming_accept_selected(self): self._status("Accept (stub)")
    def _incoming_decline_selected(self): self._status("Decline (stub)")
    def _incoming_reset_window(self): self.incoming_list.clear(); self._status("Reset window")

    # ---- Fleet actions ----
    def _on_active_fleet_changed(self, name):
        # Guard against early signal before member_list exists
        if not hasattr(self, 'member_list'):
            self.fleet.set_active(name)
            return
        self.fleet.set_active(name); self._populate_member_list()
    def _populate_member_list(self):
        self.member_list.clear()
        name = self.active_fleet_combo.currentText() or "Default"
        self.member_list.addItems(self.fleet.list_members(name))

    def add_fleet_group(self):
        name, ok = QInputDialog.getText(self, "Add Group", "Group name:")
        if ok and name.strip():
            if self.fleet.add_group(name.strip()):
                self.active_fleet_combo.clear(); self.active_fleet_combo.addItems(self.fleet.list_fleet_names())
                self.active_fleet_combo.setCurrentText(name.strip())

    def add_fleet_member(self):
        cs, ok = QInputDialog.getText(self, "Add Callsign", "Callsign:")
        if ok and cs.strip():
            name = self.active_fleet_combo.currentText() or "Default"
            if self.fleet.add_member(name, cs):
                self._populate_member_list()

    def remove_fleet_member_btn(self):
        it = self.member_list.currentItem()
        if not it: return
        name = self.active_fleet_combo.currentText() or "Default"
        if self.fleet.remove_member(name, it.text()):
            self._populate_member_list()

    # ---- File upload stubs ----
    def choose_file_to_send(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select file to send", app_base_dir(), "All Files (*.*)")
        if path:
            self.selected_file_path = path
            try: self.file_path_edit.setText(path)
            except Exception: pass
            try: self._status(f"Selected file: {os.path.basename(path)}", 3000)
            except Exception: pass

    def send_selected_file(self):
        path = getattr(self, "selected_file_path", "")
        if not path:
            QMessageBox.information(self, "Send File", "Please choose a file first.")
            return False
        ok = self.send_file_path(path)
        return bool(ok)

    # ---- Fixed GPS save ----
    def save_fixed_gps(self):
        # Enable 30-minute coordinate beacons based on current fixed lat/lon
        try:
            lat_txt = self.fixed_lat_edit.text().strip() if hasattr(self, 'fixed_lat_edit') else ''
            lon_txt = self.fixed_lon_edit.text().strip() if hasattr(self, 'fixed_lon_edit') else ''
        except Exception:
            lat_txt = ''; lon_txt = ''
        lat_txt = (self.fixed_lat_edit.text().strip() if hasattr(self,'fixed_lat_edit') else '')
        lon_txt = (self.fixed_lon_edit.text().strip() if hasattr(self,'fixed_lon_edit') else '')
        # Persist to JSON
        try:
            lat_val = float(lat_txt) if lat_txt else None
            lon_val = float(lon_txt) if lon_txt else None
        except Exception:
            lat_val = None; lon_val = None
        save_json('fixed_gps.json', {'lat': lat_txt, 'lon': lon_txt})
        try:
            lat_val_f = float(lat_txt); lon_val_f = float(lon_txt)
            self._beacon_coords_enabled = True
            self._beacon_coords_lat = round(lat_val_f, 5)
            self._beacon_coords_lon = round(lon_val_f, 5)
            import time as _t
            self._beacon_coords_last_ts = int(_t.time())
            self._save_beacon_coords_to_settings(True, self._beacon_coords_lat, self._beacon_coords_lon, self._beacon_coords_last_ts)
            # Force immediate beacon with coordinates now; next coords in 30 minutes
            try:
                self._beacon_coords_force_once = True
                try:
                    self._send_beacon()
                except Exception:
                    pass
                try:
                    self._touch_last_tx()
                except Exception:
                    pass
            except Exception:
                pass
        except Exception:
            pass
        # Populate Send box if valid numbers
        if lat_val is not None and lon_val is not None:
            try:
                msg = f"GP POS lat {lat_val:.5f} lon {lon_val:.5f}"
                if hasattr(self, 'send_edit') and self.send_edit is not None:
                    self.send_edit.setPlainText(msg)
            except Exception:
                pass
        try:
            self._status(f"Saved fixed position: lat={lat_txt} lon={lon_txt}", 3000)
        except Exception:
            pass
    def on_send_gps(self):
        """Pre-flight: read a short burst from serial, parse APRS/NMEA, and populate Send box:
        'GP POS lat nn.nnnnn lon nn.nnnnn'."""
        # Helpers local to this method to avoid wide patches
        import re, time, math
        def _nmea_deg(val: str, hemi: str) -> float:
            try:
                if not val or not hemi or '.' not in val: return float('nan')
                deg_len = 2 if hemi.upper() in ('N','S') else 3
                d = int(val[:deg_len]); m = float(val[deg_len:])
                dec = d + m/60.0
                if hemi.upper() in ('S','W'): dec = -dec
                return dec
            except Exception:
                return float('nan')

        NMEA_RMC = re.compile(r'^\$(?:GP|GN|GL|GA)RMC,', re.I)
        NMEA_GGA = re.compile(r'^\$(?:GP|GN|GL|GA)GGA,', re.I)
        APRS_BANG_RE = re.compile(r'[!=@]?(?P<lat>\d{4,5}\.\d+)\s*(?P<lathemi>[NS])[\/\\](?P<lon>\d{5,6}\.\d+)\s*(?P<lonhemi>[EW])', re.I)
        POS_DDMM_RE = re.compile(r'(?P<lat>\d{4,5}\.\d+)\s*([NS])[,/\s]+(?P<lon>\d{5,6}\.\d+)\s*([EW])', re.I)
        POS_DEC_RE = re.compile(r'(?P<lat>[-+]?\d{1,2}\.\d{3,})[,/\s]+(?P<lon>[-+]?\d{1,3}\.\d{3,})')

        def _parse_nmea_latlon(line: str):
            try:
                if NMEA_RMC.match(line):
                    p = line.split(',')
                    if len(p) >= 7:
                        lat = _nmea_deg(p[3], p[4]) if p[3] and p[4] else float('nan')
                        lon = _nmea_deg(p[5], p[6]) if p[5] and p[6] else float('nan')
                        return lat, lon
                if NMEA_GGA.match(line):
                    p = line.split(',')
                    if len(p) >= 6:
                        lat = _nmea_deg(p[2], p[3]) if p[2] and p[3] else float('nan')
                        lon = _nmea_deg(p[4], p[5]) if p[4] and p[5] else float('nan')
                        return lat, lon
            except Exception:
                pass
            return float('nan'), float('nan')

        def _extract_any_latlon(text: str):
            if not text:
                return float('nan'), float('nan')
            m = APRS_BANG_RE.search(text)
            if m:
                try:
                    lat = _nmea_deg(m.group('lat'), m.group('lathemi'))
                    lon = _nmea_deg(m.group('lon'), m.group('lonhemi'))
                    return lat, lon
                except Exception:
                    pass
            m = POS_DDMM_RE.search(text)
            if m:
                try:
                    latdm = m.group('lat'); londm = m.group('lon')
                    lathemi = m.group(2);   lonhemi = m.group(4)
                    lat = _nmea_deg(latdm, lathemi); lon = _nmea_deg(londm, lonhemi)
                    return lat, lon
                except Exception:
                    pass
            m2 = POS_DEC_RE.search(text)
            if m2:
                try:
                    lat = float(m2.group('lat')); lon = float(m2.group('lon'))
                    if abs(lat) <= 90 and abs(lon) <= 180:
                        return lat, lon
                except Exception:
                    pass
            # Scan line-by-line for NMEA
            for raw in (text or '').splitlines():
                s = raw.strip()
                lt, ln = _parse_nmea_latlon(s)
                if not (math.isnan(lt) or math.isnan(ln)):
                    return lt, ln
            return float('nan'), float('nan')

        # Require serial connection
        if not self._serial_is_open():
            try:
                QMessageBox.information(self, 'GPS', 'Connect a COM port first.')
            except Exception:
                pass
            return

        # Flush any old input, then read briefly
        try:
            try:
                self.ser.reset_input_buffer()
            except Exception:
                pass
            buf = b''
            start = time.time()
            while (time.time() - start) < 2.0:  # 2s sniff
                try:
                    if self.ser.in_waiting:
                        buf += self.ser.read(self.ser.in_waiting)
                    else:
                        time.sleep(0.05)
                except Exception:
                    time.sleep(0.05)
            try:
                text = buf.decode('utf-8', errors='replace')
            except Exception:
                text = buf.decode('latin1', errors='replace')
        except Exception:
            text = ''

        lat, lon = _extract_any_latlon(text)
        if not (isinstance(lat, float) and isinstance(lon, float)) or (math.isnan(lat) or math.isnan(lon)):
            # Fallback: if fixed fields are valid, use them
            try:
                lat = float(self.fixed_lat_edit.text().strip())
                lon = float(self.fixed_lon_edit.text().strip())
            except Exception:
                lat, lon = float('nan'), float('nan')

        if math.isnan(lat) or math.isnan(lon) or abs(lat) > 90 or abs(lon) > 180:
            try:
                self._status('GPS parse failed. Enter Fixed GPS or try again.', 4000)
            except Exception:
                pass
            return

        msg = f"GP POS lat {lat:.5f} lon {lon:.5f}"
        try:
            self.send_edit.setPlainText(msg)
            self._status('GPS position inserted into Send box.', 3000)
        except Exception:
            pass

    def on_toolbar_tab_changed(self, idx):
        title = self.tab_widget.tabText(idx)
        if title == "Network Map":
            self._show_map_view()
        else:
            self._show_main_view()

    def on_toolbar_tab_changed(self, idx):
        title = self.tab_widget.tabText(idx)
        if title == "Network Map": self._show_map_view()
        else: self._show_main_view()

    # ---- Timers ----
    # ---- Timers ----
    def _setup_timers(self):
        self.autosave = QTimer(self); self.autosave.setInterval(60_000); self.autosave.timeout.connect(self.save_settings); self.autosave.start()
        self.beacons_refresh = QTimer(self); self.beacons_refresh.setInterval(60_000); self.beacons_refresh.timeout.connect(self.update_beacons_list)
        try:
            self.beacons_refresh.timeout.connect(lambda: self._positions_prune(3600))
        except Exception:
            pass
        self.beacons_refresh.start()
        self.beacon_stale_timer = QTimer(self); self.beacon_stale_timer.setInterval(60_000); self.beacon_stale_timer.timeout.connect(lambda: self._clear_graph_if_stale(20)); self.beacon_stale_timer.start()
    def _mycall_base(self) -> str:
        try:
            return (self.mycall_edit.text() or "").strip().upper().split("-", 1)[0]
        except Exception:
            return ""

    def _should_auto_ack(self, to_call: str) -> bool:
        try:
            my = self._mycall_base()
            base_to = (to_call or "").strip().upper().split("-", 1)[0]
            return bool(my and base_to == my)
        except Exception:
            return False

    def _dedupe_ack(self, ack_id: str) -> bool:
        import time
        now = time.time()
        ttl = float(getattr(self, "_ack_sent_ttl", 600.0))
        last = (self._ack_sent or {}).get(ack_id)
        if last and (now - float(last)) < ttl:
            return False
        (self._ack_sent or {}).__setitem__(ack_id, now)
        return True
    def changeEvent(self, e):
        try:
            from PyQt5.QtCore import QEvent, QTimer
            if e.type() == QEvent.WindowStateChange:
                # After any state change, relock height to current value
                QTimer.singleShot(0, self._nuke_lock_size)
        except Exception:
            pass
        return super().changeEvent(e)

    def _auto_ack_if_needed(self, frm: str, to: str, msg: str) -> bool:
        try:
            import re as _re, zlib
            if not self._should_auto_ack(to):
                return False
            m = _re.search(r'\[ACK:([0-9A-Z]{4,8})\]', msg or "", flags=_re.I)
            ack_id = (m.group(1).upper() if m else None)
            if not ack_id:
                if _re.search(r'(\s\*ACK\b|\s\*A\b|\s\*AY\b)', msg or "", flags=_re.I):
                    h = zlib.adler32((msg or "").encode("utf-8", "ignore")) & 0xFFFFFFFF
                    ack_id = f"{h:08X}"[-4:]
            if not ack_id:
                return False
            if not self._dedupe_ack(ack_id):
                return False
            my = self._mycall_base()
            if not my or not frm:
                return False
            reply = f"{frm} DE {my} ACK {ack_id}"
            try:
                _ = self.send_user_text(reply)
                self._status(f"Auto-ACK sent to {frm} ({ack_id})")
            except Exception:
                pass
            return True
        except Exception:
            return False

def base36(num: int) -> str:
    digits = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    if num == 0: return "0"
    s=""; n=abs(int(num))
    while n: n, r = divmod(n,36); s = digits[r] + s
    return s

def main():
    import sys, os, traceback
    print('[BOOT] start')
    try:
        print('[BOOT] QApplication')
        app = QApplication(sys.argv)
        print('[BOOT] ChatApp()')
        w = ChatApp()
        print('[BOOT] show window')
        try:
            w.showMaximized()
        except Exception:
            w.show()
        print('[BOOT] entering event loop')
        sys.exit(app.exec_())
    except Exception as e:
        print('[BOOT][ERROR]', e)
        tb = traceback.format_exc()
        try:
            with open(os.path.join(app_base_dir(), 'startup_error.log'), 'w', encoding='utf-8') as f:
                f.write(tb)
        except Exception:
            pass
        try:
            QMessageBox.critical(None, 'Startup error', 'An error occurred during startup.\n' + str(e))
        except Exception:
            pass
        raise

if __name__ == "__main__":
    main()