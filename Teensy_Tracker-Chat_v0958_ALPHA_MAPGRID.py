
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Teensy Tracker Chat v0.9.58 (Send GPS top bar; tidy layout)
- Pure black MAP GRID background; lime grid; cyan labels; zoom buttons; world/europe/us presets
- Cleaned layout: no ghost widgets/tabs; toolbar wires after map widget creation
- Chat: lime sent, orange received, turquoise console (hideable)
- Uppercase To/From fields (centered, ~10ch), only Send/GPS sends PTT
- KISS: @K, @KP1 + %ZS; off = C0 FF C0 0D, @KP0, %ZS
"""

import sys, re, time, math
from collections import deque
from datetime import datetime
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QRectF, QPointF
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QTextEdit, QGroupBox,
    QCheckBox, QMessageBox, QStatusBar, QTabWidget, QSpacerItem, QSizePolicy
)

try:
    import serial
    from serial import Serial
    from serial.tools import list_ports
except Exception:
    serial = None
    Serial = None
    list_ports = None


DARK_QSS = """
/* Base */
* { background-color: #222; color: #fff; }
QMainWindow, QWidget { background-color: #222; color: #fff; }
QGroupBox {
  border: 1px solid #333; border-radius: 6px; margin-top: 12px;
}
QGroupBox::title {
  subcontrol-origin: margin; subcontrol-position: top left;
  padding: 0 6px; color: #fff; background: transparent;
}
QLabel { color: #fff; }

/* Buttons */
QPushButton {
  background-color: #444; color: #fff; border: 1px solid #333;
  border-radius: 6px; padding: 6px 10px;
}
QPushButton:hover { background-color: #555; }
QPushButton:pressed { background-color: #333; }
QPushButton:disabled { color: #888; border-color: #2a2a2a; background: #2a2a2a; }

/* Inputs */
QLineEdit, QTextEdit, QPlainTextEdit {
  background-color: #000; color: #fff; border: 1px solid #333; border-radius: 4px;
}
QComboBox, QSpinBox {
  background-color: #111; color: #fff; border: 1px solid #333; border-radius: 4px;
}
QComboBox QAbstractItemView {
  background-color: #222; color: #fff; selection-background-color: #444;
}

/* Tabs */
QTabWidget::pane { border: 1px solid #333; background: #333; }
QTabBar::tab {
  background: #333; color: #fff; padding: 6px 12px; border: 1px solid #333; border-bottom-color: #333;
}
QTabBar::tab:selected { background: #3a3a3a; }
QTabBar::tab:hover { background: #3f3f3f; }

/* Status bar */
QStatusBar { background: #222; color: #ccc; border-top: 1px solid #333; }
QStatusBar QLabel { color: #ccc; }

/* Scrollbars */
QScrollBar:vertical, QScrollBar:horizontal {
  background: #222; border: 1px solid #333; border-radius: 4px;
}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
  background: #444; min-height: 20px; min-width: 20px; border-radius: 4px;
}
QScrollBar::add-line, QScrollBar::sub-line { background: none; border: none; }
"""
ESC = b'\x1b'
CALL_RE = r'[A-Z0-9]{1,2}\d[A-Z0-9]{1,3}(?:-[0-9]{1,2})?'
LINE_RE = re.compile(rf'^(?P<to>{CALL_RE}|CQ)\s+DE\s+(?P<frm>{CALL_RE})\s*(?P<msg>.*)$', re.I)

COLOR_SENT = "#32CD32"     # lime
COLOR_RECV = "#FFA500"     # orange
COLOR_CONSOLE = "#40E0D0"  # turquoise

def safe_int(val, default):
    try: return int(val)
    except Exception: return default

class UppercaseLineEdit(QLineEdit):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        font = QtGui.QFont("Consolas"); font.setPointSize(16)
        self.setFont(font)
        self.setMaxLength(10)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("QLineEdit { background:#000; color:#32CD32; font-family:Consolas,monospace; }")
        self.textChanged.connect(self._force_upper)

    def _force_upper(self, *_):
        pos = self.cursorPosition()
        self.setText(self.text().upper())
        self.setCursorPosition(pos)

    def insertFromMimeData(self, source: QtCore.QMimeData):
        text = source.text().upper() if source and source.text() else ""
        super().insert(text)

class SerialReaderThread(QThread):
    line_received = pyqtSignal(str)
    def __init__(self, ser: Serial):
        super().__init__()
        self.ser = ser
        self._running = True
    def run(self):
        buf = b''
        while self._running:
            try:
                if self.ser and self.ser.is_open and self.ser.in_waiting:
                    data = self.ser.read(self.ser.in_waiting)
                    if not data:
                        self.msleep(5); continue
                    buf += data
                    while True:
                        sep_idx = -1; seplen = 0
                        for sep in (b'\r\n', b'\n', b'\r'):
                            i = buf.find(sep)
                            if i != -1:
                                sep_idx = i; seplen = len(sep); break
                        if sep_idx == -1:
                            break
                        part = buf[:sep_idx]; buf = buf[sep_idx+seplen:]
                        try: text = part.decode('utf-8', errors='replace')
                        except Exception: text = part.decode('latin1', errors='replace')
                        ts = datetime.now().strftime('%H:%M:%S')
                        self.line_received.emit(f"[{ts}] {text.strip()}")
                else:
                    self.msleep(20)
            except Exception:
                self.msleep(100)
    def stop(self):
        self._running = False
        self.wait(400)

# ---------------- Map Grid ----------------
class GridMapView(QtWidgets.QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("QGraphicsView { background-color:#000; border:none; }")
        self.scene = QtWidgets.QGraphicsScene(self)
        self.setScene(self.scene)
        self.setBackgroundBrush(QtGui.QBrush(Qt.black))
        self.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.TextAntialiasing)
        self.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)
        self.scale(1.0, 1.0)

        # World rect in scene coords: lon [-180,180], lat [-90,90] -> x=lon*scale, y=-lat*scale
        self.scale_deg = 6.0  # pixels per degree
        self.world_rect = QRectF(-180*self.scale_deg, -90*(-self.scale_deg), 360*self.scale_deg, 180*(-self.scale_deg))
        # But we actually want height positive; so build explicitly:
        self.world_rect = QRectF(-180*self.scale_deg, -90*self.scale_deg, 360*self.scale_deg, 180*self.scale_deg)

        # Marker storage
        self.own_pos = None  # (lat, lon)
        self.peers = {}      # call -> (lat, lon)

        # Fit initially
        self.fitInView(self.world_rect, Qt.KeepAspectRatio)

    # Coordinate transforms
    def ll_to_xy(self, lat, lon) -> QPointF:
        x = lon * self.scale_deg
        y = -lat * self.scale_deg
        return QPointF(x, y)

    # Drawing background grid and labels
    def drawBackground(self, painter: QtGui.QPainter, rect: QtCore.QRectF):
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing, False)

        grid_col = QtGui.QColor("#00ff00")  # lime
        lab_col = QtGui.QColor("#00ffff")   # cyan
        pen_grid = QtGui.QPen(grid_col, 1, Qt.SolidLine)
        painter.setPen(pen_grid)

        step = 10  # degrees
        vis = rect.intersected(self.world_rect)

        lon_min = vis.left() / self.scale_deg
        lon_max = vis.right() / self.scale_deg
        lat_max = -vis.top() / self.scale_deg
        lat_min = -vis.bottom() / self.scale_deg

        lon_start = int(math.floor(lon_min / step) * step)
        lon_end   = int(math.ceil(lon_max / step) * step)
        lat_start = int(math.floor(lat_min / step) * step)
        lat_end   = int(math.ceil(lat_max / step) * step)

        # vertical (longitude)
        for lon in range(lon_start, lon_end + 1, step):
            p1 = self.ll_to_xy(lat_min, lon)
            p2 = self.ll_to_xy(lat_max, lon)
            painter.drawLine(p1, p2)
        # horizontal (latitude)
        for lat in range(lat_start, lat_end + 1, step):
            p1 = self.ll_to_xy(lat, lon_min)
            p2 = self.ll_to_xy(lat, lon_max)
            painter.drawLine(p1, p2)

        # Labels
        painter.setRenderHint(QtGui.QPainter.TextAntialiasing, True)
        painter.setPen(lab_col)
        f = painter.font(); f.setPointSize(8); painter.setFont(f)
        y_lab = vis.bottom() - 4
        for lon in range(lon_start, lon_end + 1, step):
            pt = self.ll_to_xy(lat_min, lon)
            painter.drawText(int(pt.x()-10), int(y_lab), f"{lon}°")
        x_lab = vis.left() + 4
        for lat in range(lat_start, lat_end + 1, step):
            pt = self.ll_to_xy(lat, lon_min)
            painter.drawText(int(x_lab), int(pt.y()+4), f"{lat}°")

        painter.restore()

        # Draw markers and range lines on foreground-ish stage
        self._draw_markers()

    def _draw_markers(self):
        # Clear previous items (markers/lines), but keep background grid (handled by drawBackground)
        for item in list(self.scene.items()):
            if isinstance(item, QtWidgets.QGraphicsPathItem) or isinstance(item, QtWidgets.QGraphicsTextItem) or isinstance(item, QtWidgets.QGraphicsLineItem):
                self.scene.removeItem(item)

        # Draw own position
        if self.own_pos:
            lat, lon = self.own_pos
            self._draw_triangle(lat, lon, "#00ff00")  # green
            self._label_call(lat, lon, "ME", "#ffffff")

        # Draw peers and lines
        if self.own_pos:
            lat0, lon0 = self.own_pos
        for call, (lat, lon) in self.peers.items():
            self._draw_triangle(lat, lon, "#ff3333")  # red
            self._label_call(lat, lon, call, "#ffffff")
            if self.own_pos:
                p1 = self.ll_to_xy(lat0, lon0)
                p2 = self.ll_to_xy(lat, lon)
                line = self.scene.addLine(p1.x(), p1.y(), p2.x(), p2.y(), QtGui.QPen(QtGui.QColor("#888888"), 1))
                # distance label (km)
                d = self._haversine_km(lat0, lon0, lat, lon)
                mid = QPointF((p1.x()+p2.x())/2, (p1.y()+p2.y())/2)
                t = self.scene.addText(f"{d:.0f} km", QtGui.QFont("Consolas", 8))
                t.setDefaultTextColor(QtGui.QColor("#cccccc"))
                t.setPos(mid + QPointF(6, -6))

    def _draw_triangle(self, lat, lon, color):
        p = self.ll_to_xy(lat, lon)
        size = 6
        path = QtGui.QPainterPath()
        path.moveTo(p.x(), p.y()-size)
        path.lineTo(p.x()-size, p.y()+size)
        path.lineTo(p.x()+size, p.y()+size)
        path.closeSubpath()
        item = QtWidgets.QGraphicsPathItem(path)
        item.setBrush(QtGui.QBrush(QtGui.QColor(color)))
        item.setPen(QtGui.QPen(QtGui.QColor(color)))
        self.scene.addItem(item)

    def _label_call(self, lat, lon, text, color="#ffffff"):
        p = self.ll_to_xy(lat, lon)
        item = self.scene.addText(text, QtGui.QFont("Consolas", 9))
        item.setDefaultTextColor(QtGui.QColor(color))
        item.setPos(p + QPointF(8, -16))

    def _haversine_km(self, lat1, lon1, lat2, lon2):
        R = 6371.0
        phi1 = math.radians(lat1); phi2 = math.radians(lat2)
        dphi = math.radians(lat2-lat1); dl = math.radians(lon2-lon1)
        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dl/2)**2
        return 2*R*math.asin(math.sqrt(a))

    # Public API
    def set_own(self, lat, lon):
        self.own_pos = (lat, lon); self.viewport().update()

    def set_peer(self, call, lat, lon):
        self.peers[call] = (lat, lon); self.viewport().update()

    def clear_peers(self):
        self.peers.clear(); self.viewport().update()

    # Preset views
    def zoom_world(self):
        self.fitInView(self.world_rect, Qt.KeepAspectRatio)

    def zoom_europe(self):
        r = QRectF((-11)*self.scale_deg, -60*self.scale_deg, (50)*self.scale_deg, (45)*self.scale_deg)  # lon -11..39, lat 35..80 approx
        self.fitInView(r, Qt.KeepAspectRatio)

    def zoom_us(self):
        r = QRectF((-130)*self.scale_deg, -50*self.scale_deg, (60)*self.scale_deg, (30)*self.scale_deg)  # lon -130..-70, lat 20..50
        self.fitInView(r, Qt.KeepAspectRatio)

    # Buttons
    def zoom_in(self):
        self.scale(1.25, 1.25)
    def zoom_out(self):
        self.scale(0.8, 0.8)
    def reset_view(self):
        self.zoom_world()

    # Disable wheel zoom to prevent accidental zooming
    def wheelEvent(self, event: QtGui.QWheelEvent):
        event.ignore()

# ---------------- Main App ----------------
class ChatApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Teensy Tracker Robust Packet Chat v0.9.58")
        self.resize(1200, 900)

        self.ser: Serial = None
        self.reader_thread: SerialReaderThread = None
        self.recent_sent = deque(maxlen=12)
        self.echo_window_s = 1.8
        self._tx_gate = False
        self._tx_count = 0

        self._build_ui()

    def _build_ui(self):
        central = QWidget(); self.setCentralWidget(central)
        root = QVBoxLayout(central)

        

        # Top bar with right-justified Send GPS
        topbar = QHBoxLayout()
        topbar.setContentsMargins(0, 0, 0, 0)
        topbar.addStretch(1)
        self.btn_send_gps_top = QPushButton("Send GPS")
        self.btn_send_gps_top.setObjectName("btnSendGPS")
        self.btn_send_gps_top.setStyleSheet("QPushButton#btnSendGPS { background:#b00020; color:#fff; font-weight:bold; }")
        self.btn_send_gps_top.clicked.connect(self.send_gps)
        topbar.addWidget(self.btn_send_gps_top, 0, Qt.AlignRight)
        root.addLayout(topbar)

# Serial group
        serial_group = QGroupBox("Serial")
        sgl = QGridLayout(serial_group)
        self.port_combo = QComboBox()
        self.baud_combo = QComboBox(); self.baud_combo.addItems([str(x) for x in (9600,19200,38400,57600,115200,230400,460800)]); self.baud_combo.setCurrentText("115200")
        btn_refresh = QPushButton("Refresh"); btn_refresh.clicked.connect(self.refresh_ports)
        self.btn_connect = QPushButton("Connect"); self.btn_connect.clicked.connect(self.open_port)
        self.btn_disconnect = QPushButton("Disconnect"); self.btn_disconnect.clicked.connect(self.close_port); self.btn_disconnect.setEnabled(False)
        sgl.addWidget(QLabel("Port"), 0,0); sgl.addWidget(self.port_combo, 0,1); sgl.addWidget(btn_refresh, 0,2)
        sgl.addWidget(QLabel("Baud"), 1,0); sgl.addWidget(self.baud_combo, 1,1); sgl.addWidget(self.btn_connect, 1,2); sgl.addWidget(self.btn_disconnect, 1,3)
        root.addWidget(serial_group)

        # Top controls: To / From / Load / Hide / KISS
        ctl = QHBoxLayout()
        lab_to = QLabel("To"); lab_from = QLabel("From")
        lab_to.setStyleSheet("color:#ccc;"); lab_from.setStyleSheet("color:#ccc;")
        self.target_edit = UppercaseLineEdit(); self.target_edit.setPlaceholderText("TARGET")
        self.mycall_edit = UppercaseLineEdit(); self.mycall_edit.setPlaceholderText("MYCALL")
        self.target_edit.setFixedWidth(180); self.mycall_edit.setFixedWidth(180)
        self.load_btn = QPushButton("Load Callsign"); self.load_btn.clicked.connect(self.load_mycall)
        self.hide_mon_check = QCheckBox("Hide device/monitor lines"); self.hide_mon_check.setChecked(True)
        self.btn_kiss_enter = QPushButton("Enter KISS (@K)"); self.btn_kiss_enter.clicked.connect(self._enter_kiss_mode)
        self.kiss_perm_toggle = QCheckBox("KISS Permanent (@KP1)"); self.kiss_perm_toggle.toggled.connect(self._toggle_kiss_permanent)
        ctl.addWidget(lab_to); ctl.addWidget(self.target_edit)
        ctl.addSpacing(12)
        ctl.addWidget(lab_from); ctl.addWidget(self.mycall_edit)
        ctl.addSpacing(12)
        ctl.addWidget(self.load_btn); ctl.addWidget(self.hide_mon_check); ctl.addWidget(self.btn_kiss_enter); ctl.addWidget(self.kiss_perm_toggle)
        root.addLayout(ctl)

        # Tabs
        self.tabs = QTabWidget()
        self.chat_tab = QWidget()
        self.map_tab = QWidget()
        self.tabs.addTab(self.chat_tab, "Chat")
        self.tabs.addTab(self.map_tab, "MAP GRID")
        root.addWidget(self.tabs, 1)
# --- Chat tab ---
        cl = QVBoxLayout(self.chat_tab)
        title_recv = QLabel("Received Messages"); title_send = QLabel("Send Message")
        title_recv.setStyleSheet("color:#fff;background:#222; padding:4px 6px;")  # black title on black aligns to your request
        title_send.setStyleSheet("color:#fff;background:#222; padding:4px 6px;")
        self.recv_text = QTextEdit(); self.recv_text.setReadOnly(True)
        self.recv_text.setStyleSheet("QTextEdit { background:#000; color:#32CD32; font-family:Consolas,monospace; font-size:12pt; }")
        self.recv_text.setMinimumHeight(380)

        send_row = QVBoxLayout()
        self.send_edit = QTextEdit()
        self.send_edit.setMaximumHeight(90)
        self.send_edit.setStyleSheet("QTextEdit { background:#000; color:#32CD32; font-family:Consolas,monospace; font-size:12pt; }")
        btn_send = QPushButton("SEND"); btn_send.setStyleSheet("QPushButton { background:#b00020; color:#fff; font-weight:bold; }")
        btn_send.setFixedHeight(40); btn_send.clicked.connect(self.send_message)

        sr_line = QHBoxLayout()
        sr_line.addWidget(self.send_edit, 1)
        sr_line.addWidget(btn_send)

        cl.addWidget(title_recv)
        cl.addWidget(self.recv_text, 1)
        cl.addWidget(title_send)
        cl.addLayout(sr_line)

        # --- MAP GRID tab ---
        ml = QVBoxLayout(self.map_tab)
        # Map view first
        self.map_widget = GridMapView(self.map_tab)
        ml.addWidget(self.map_widget, 1)
        # Toolbar
        tb = QHBoxLayout()
        btn_world = QPushButton("World"); btn_world.clicked.connect(self.map_widget.zoom_world)
        btn_eu = QPushButton("Europe"); btn_eu.clicked.connect(self.map_widget.zoom_europe)
        btn_us = QPushButton("US"); btn_us.clicked.connect(self.map_widget.zoom_us)
        tb.addWidget(btn_world); tb.addWidget(btn_eu); tb.addWidget(btn_us)
        tb.addStretch(1)
        btn_zoom_out = QPushButton("-"); btn_zoom_out.setFixedWidth(34); btn_zoom_out.clicked.connect(self.map_widget.zoom_out)
        btn_zoom_in = QPushButton("+"); btn_zoom_in.setFixedWidth(34); btn_zoom_in.clicked.connect(self.map_widget.zoom_in)
        btn_reset = QPushButton("Reset"); btn_reset.clicked.connect(self.map_widget.reset_view)
        tb.addWidget(btn_zoom_out); tb.addWidget(btn_zoom_in); tb.addWidget(btn_reset)
        ml.addLayout(tb)

        # Status bar
        sb = QStatusBar(); self.setStatusBar(sb)
        self.status_label = QtWidgets.QLabel("Disconnected  |  Reminder: turn KISS OFF to chat")
        sb.addWidget(self.status_label)

        self.refresh_ports()

    
    # ---------- GPS SEND ----------
    def send_gps(self):
        """Read a short burst from serial to try to parse NMEA (GGA/RMC). Then send as text."""
        if not (self.ser and self.ser.is_open):
            QMessageBox.warning(self, "Not connected", "Open a COM port first."); return
        text = self._read_for_ms(800)
        lat, lon = self._parse_nmea_latlon(text)
        if lat is None or lon is None:
            QMessageBox.information(self, "GPS", "No GPS fix found from device stream (GGA/RMC)."); return
        self.map_widget.set_own(lat, lon)
        target = self.target_edit.text().strip()
        my = self.mycall_edit.text().strip()
        if not target or not my:
            QMessageBox.warning(self, "Missing calls", "Enter both Target and MyCALL to transmit."); return
        pos_text = f"lat={lat:.5f} lon={lon:.5f}"
        line = f"{target} DE {my} {pos_text}"
        if self.send_user_text(line):
            self.recent_sent.append((line, time.time()))
            self._append_chat_line("[GPS sent] " + pos_text, kind="sent")

    def _parse_nmea_latlon(self, blob: str):
        if not blob: return (None, None)
        lat = lon = None
        for raw in blob.splitlines():
            line = raw.strip()
            if not line.startswith(("$GPRMC", "$GNRMC", "$GPRMC,", "$GPGGA", "$GNGGA")):
                continue
            parts = line.split(',')
            try:
                if line.startswith(("$GPRMC", "$GNRMC")) and len(parts) >= 7:
                    status = parts[2].upper() if parts[2] else ""
                    if status != "A":
                        continue
                    ddm_lat = parts[3]; ns = parts[4].upper()
                    ddm_lon = parts[5]; ew = parts[6].upper()
                    lat = self._nmea_to_deg(ddm_lat, ns)
                    lon = self._nmea_to_deg(ddm_lon, ew)
                elif line.startswith(("$GPGGA", "$GNGGA")) and len(parts) >= 6:
                    ddm_lat = parts[2]; ns = parts[3].upper()
                    ddm_lon = parts[4]; ew = parts[5].upper()
                    lat = self._nmea_to_deg(ddm_lat, ns)
                    lon = self._nmea_to_deg(ddm_lon, ew)
            except Exception:
                continue
            if lat is not None and lon is not None:
                return (lat, lon)
        return (None, None)

    def _nmea_to_deg(self, ddm: str, hemi: str):
        if not ddm or not hemi: return None
        try:
            if len(ddm) < 4: return None
            if '.' in ddm:
                head = ddm.split('.')[0]
            else:
                head = ddm
            if len(head) in (4,5):
                deg_digits = len(head) - 2
            else:
                deg_digits = 2 if len(head) <= 7 else 3
            deg = float(ddm[:deg_digits])
            minutes = float(ddm[deg_digits:])
            val = deg + minutes/60.0
            if hemi in ('S','W'): val = -val
            return val
        except Exception:
            return None

    # ---------- Serial helpers ----------
    def refresh_ports(self):
        self.port_combo.clear()
        try:
            if list_ports:
                for p in sorted(list_ports.comports(), key=lambda x: x.device):
                    self.port_combo.addItem(f"{p.device} — {p.description}", p.device)
            else:
                for i in range(1,21): self.port_combo.addItem(f"COM{i}", f"COM{i}")
        except Exception:
            for i in range(1,21): self.port_combo.addItem(f"COM{i}", f"COM{i}")

    def open_port(self):
        try:
            if self.ser and self.ser.is_open: self.close_port()
            port = self.port_combo.currentData() or self.port_combo.currentText()
            baud = safe_int(self.baud_combo.currentText(), 115200)
            self.ser = serial.Serial(port=port, baudrate=baud, timeout=0.05, rtscts=False, dsrdtr=False)
            self.reader_thread = SerialReaderThread(self.ser)
            self.reader_thread.line_received.connect(self._on_line)
            self.reader_thread.start()
            self.btn_connect.setEnabled(False); self.btn_disconnect.setEnabled(True)
            self.status_label.setText(f"Connected {port} @ {baud}  |  Reminder: turn KISS OFF to chat")
        except Exception as e:
            QMessageBox.critical(self, "Serial error", f"Failed to open port.\n{e}")
            self.status_label.setText("Disconnected  |  Reminder: turn KISS OFF to chat")

    def close_port(self):
        try:
            if self.reader_thread: self.reader_thread.stop(); self.reader_thread=None
            if self.ser: self.ser.close(); self.ser=None
        finally:
            self.btn_connect.setEnabled(True); self.btn_disconnect.setEnabled(False)
            self.status_label.setText("Disconnected  |  Reminder: turn KISS OFF to chat")

    def _write_raw(self, data: bytes):
        if not (self.ser and self.ser.is_open):
            QMessageBox.warning(self, "Not connected", "Open a COM port first.")
            return False
        try:
            self.ser.write(data); return True
        except Exception as e:
            QMessageBox.critical(self, "Write error", str(e)); return False

    def _send_cmd(self, cmd: str):
        return self._write_raw(ESC + (cmd + "\r").encode("utf-8", errors="replace"))

    def _write_line(self, text: str):
        if not self._tx_gate:  # only Send path opens gate
            return False
        return self._write_raw((text + "\r").encode("utf-8", errors="replace"))

    # ---------- KISS ----------
    def _enter_kiss_mode(self):
        self._send_cmd("@K")
        self._send_cmd("%ZS")
        self.status_label.setText("Entered KISS MODE (@K, saved). Chat requires KISS OFF.")
        QMessageBox.information(self, "KISS Mode", "Entered KISS MODE (@K) and saved (%ZS).\nChat requires KISS OFF.")

    def _toggle_kiss_permanent(self, on: bool):
        if on:
            self._send_cmd("@KP1"); self._send_cmd("%ZS")
            QMessageBox.information(self, "KISS Permanent", "KISS Permanent ENABLED (@KP1) and saved (%ZS).\nUse 'Enter KISS (@K)' to enter now.")
        else:
            # Exit KISS (raw) and save KP0
            self._write_raw(bytes([192,255,192,13]))
            self._send_cmd("@KP0"); self._send_cmd("%ZS")
            self.status_label.setText("KISS OFF; saved. Ready for chat.")

    # ---------- Incoming handling ----------
    def _on_line(self, line: str):
        content = re.sub(r'^\[\d{2}:\d{2}:\d{2}\]\s*', '', line).strip()
        is_console = self._is_device_line(content)

        if self.hide_mon_check.isChecked() and is_console:
            return

        if not is_console:
            now = time.time()
            for txt, ts in list(self.recent_sent):
                if now - ts <= self.echo_window_s and content.strip() == txt.strip():
                    return

            m = LINE_RE.match(content)
            if m:
                to = m.group('to').upper(); frm = m.group('frm').upper(); msg = m.group('msg').strip()
                norm = f"{to} DE {frm}" + (f" {msg}" if msg else "")
                self._append_chat_line(norm, kind="received")
                # Try to parse coords for plotting (very basic patterns)
                self._maybe_plot_from_text(frm, msg)
                return
            self._append_chat_line(content, kind="received")
            return

        self._append_chat_line(content, kind="console")

    def _is_device_line(self, s: str) -> bool:
        if not s: return True
        if any(ord(ch) < 32 and ch not in ('\r','\n','\t') for ch in s): return True
        pats = [
            r'^fm\s+\S+\s+to\s+\S+\s+ctl\b',
            r'^\*\s*%.*', r'^\*\s*@K(P1)?\b',
            r'^%[A-Za-z].*', r'^cmd:\s', r'^(MHEARD|HEARD)\b',
            r'^(ID:|VER:|AX|KISS|RPR|BT:|RPR>)\b',
            r'^\(C\)\s', r'^\[MON\]', r'^[=\-]{3,}$',
            r'^\s*=\s*RPR><TNC.*=\s*$', r'AX\.25\b', r'SCS\s+GmbH',
        ]
        for p in pats:
            if re.search(p, s, re.IGNORECASE): return True
        if s.strip() in {"RPR>", "OK", "READY"}: return True
        return False

    # ---------- Outgoing ----------
    def _looks_like_console(self, s: str) -> bool:
        return self._is_device_line(s) or bool(re.match(r'^(RPR>|OK|READY)$', s.strip(), re.I))

    def send_user_text(self, text: str) -> bool:
        if self._looks_like_console(text):
            QMessageBox.warning(self, "Blocked", "That text looks like console/device output and will not be transmitted.")
            return False
        self._tx_gate = True
        ok = self._write_line(text)
        self._tx_gate = False
        if ok:
            self._tx_count += 1
            self.status_label.setText(f"TX: {self._tx_count}  |  Connected" if self.btn_connect.isEnabled()==False else f"TX: {self._tx_count}")
        return ok

    def send_message(self):
        target = self.target_edit.text().strip()
        my = self.mycall_edit.text().strip()
        msg = self.send_edit.toPlainText().strip()
        if not target: QMessageBox.warning(self, "Target missing", "Enter a Target callsign."); return
        if not my: QMessageBox.warning(self, "MyCALL missing", "Enter MyCALL or click Load Callsign."); return
        if not msg: return
        line = f"{target} DE {my} {msg}"
        if self.send_user_text(line):
            self.recent_sent.append((line, time.time()))
            self._append_chat_line(line, kind="sent")
            self.send_edit.clear()

    # ---------- Chat helpers ----------
    def _append_chat_line(self, text: str, kind: str):
        color = COLOR_SENT if kind == "sent" else (COLOR_CONSOLE if kind == "console" else COLOR_RECV)
        text_esc = (text.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;"))
        html = f'<span style="color:{color}">{text_esc}</span><br>'
        self.recv_text.moveCursor(QtGui.QTextCursor.End)
        self.recv_text.insertHtml(html)
        self.recv_text.moveCursor(QtGui.QTextCursor.End)

    def _extract_callsign(self, text: str) -> str:
        m = re.search(CALL_RE, text, re.I); return m.group(0).upper() if m else ""

    def _maybe_plot_from_text(self, frm: str, msg: str):
        if not msg: return
        # Simple patterns: "lat=51.5 lon=-0.1" or "51.5N 000.1W"
        m = re.search(r'lat\s*=\s*(-?\d+(?:\.\d+)?)\s*[,\s;]+lon\s*=\s*(-?\d+(?:\.\d+)?)', msg, re.I)
        if m:
            lat = float(m.group(1)); lon = float(m.group(2))
            self.map_widget.set_peer(frm, lat, lon); return
        m = re.search(r'(\d+(?:\.\d+)?)\s*([NS])\s+(\d+(?:\.\d+)?)\s*([EW])', msg, re.I)
        if m:
            lat = float(m.group(1)); lat = lat if m.group(2).upper()=='N' else -lat
            lon = float(m.group(3)); lon = lon if m.group(4).upper()=='E' else -lon
            self.map_widget.set_peer(frm, lat, lon); return

    # ---------- Load MyCALL ----------
    def load_mycall(self):
        if not (self.ser and self.ser.is_open):
            QMessageBox.warning(self, "Not connected", "Open a COM port first."); return
        try:
            if self.reader_thread: self.reader_thread.stop(); self.reader_thread=None
            self.ser.reset_input_buffer(); self.ser.reset_output_buffer()
            self._send_cmd("%ZL"); QtCore.QThread.msleep(200)
            self._send_cmd("%i")
            text = self._read_for_ms(1200)
            call = self._extract_callsign(text) or ""
            if not call:
                self._send_cmd("I")
                text2 = self._read_for_ms(1200)
                call = self._extract_callsign(text2) or ""
            if call:
                self.mycall_edit.setText(call)
                self.status_label.setText(f"MyCALL: {call}")
            else:
                QMessageBox.information(self, "Load Callsign", "No callsign found.")
        except Exception as e:
            QMessageBox.critical(self, "Load Callsign", str(e))
        finally:
            if self.ser and self.ser.is_open:
                self.reader_thread = SerialReaderThread(self.ser)
                self.reader_thread.line_received.connect(self._on_line)
                self.reader_thread.start()

    def _read_for_ms(self, ms: int) -> str:
        buf = b''; start = QtCore.QTime.currentTime()
        while start.msecsTo(QtCore.QTime.currentTime()) < ms:
            QtCore.QThread.msleep(20)
            try:
                n = self.ser.in_waiting
                if n: buf += self.ser.read(n)
            except Exception:
                break
        try: return buf.decode('utf-8', errors='replace')
        except Exception: return buf.decode('latin1', errors='replace')

def main():
    print("Teensy Tracker Chat v0.9.58 (Send GPS top bar; tidy layout)")
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setStyleSheet(DARK_QSS)
    w = ChatApp(); w.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
