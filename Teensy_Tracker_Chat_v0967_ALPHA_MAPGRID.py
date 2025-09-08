#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Teensy Tracker Chat v0.9.67
- Dark theme; high-contrast (white) checkbox indicators
- APRS Beacon toggle: %A1 ON / %A0 OFF (no %ZS from Chat to avoid PTT)
- KISS: Enter KISS (@K). Permanent toggle: ON=@KP1 ; OFF=raw C0 FF C0 0D then @KP0 (no %ZS)
- Sync device state on connect: reads %A and @KP and updates toggles
- Console/monitor lines are hidden from the chat view by default
- Chat: lime sent, orange received
- Only "SEND" and "Send GPS" open TX gate; all ESC commands never key PTT
- Offline MAP GRID with region buttons (World, Europe, Mainland Europe + UK/IE, UK & Ireland, USA, North America, South America)
"""

import sys, re, time, math
from collections import deque
from datetime import datetime
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QRectF, QPointF
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QTextEdit, QGroupBox,
    QCheckBox, QMessageBox, QStatusBar, QTabWidget
)

try:
    import serial
    from serial import Serial
    from serial.tools import list_ports
except Exception:
    serial = None
    Serial = None
    list_ports = None

# --------------------- THEME ---------------------
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
  background-color: #000; color: #32CD32; border: 1px solid #333; border-radius: 4px;
  font-family: Consolas, monospace;
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

/* High-contrast checkboxes */
QCheckBox { color:#fff; }
QCheckBox::indicator {
  width:18px; height:18px;
  border: 1px solid #aaa;
  background: #222;
}
QCheckBox::indicator:checked {
  border: 1px solid #fff;
  background: #fff;          /* white box so the check is obvious */
}
QCheckBox::indicator:unchecked {
  border: 1px solid #666;
  background: #222;
}
QCheckBox:checked { font-weight: 600; }
"""

ESC = b'\x1b'
CALL_RE = r'[A-Z0-9]{1,2}\d[A-Z0-9]{1,3}(?:-[0-9]{1,2})?'
LINE_RE = re.compile(rf'^(?P<to>{CALL_RE}|CQ)\s+DE\s+(?P<frm>{CALL_RE})\s*(?P<msg>.*)$', re.I)

COLOR_SENT = "#32CD32"     # lime
COLOR_RECV = "#FFA500"     # orange

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

# --------- Map Grid ----------
class GridMapView(QtWidgets.QGraphicsView):
    """
    Offline lat/lon grid with region presets.
    Scene coords: x=lon*scale_deg, y=-lat*scale_deg (North is up).
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QtWidgets.QGraphicsScene(self)
        self.setScene(self.scene)
        self.setBackgroundBrush(Qt.black)
        self.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.TextAntialiasing)
        self.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)

        self.scale_deg = 6.0

        # World rect (lon -180..180, lat -90..90)
        self.world_rect = QtCore.QRectF(-180*self.scale_deg, -90*self.scale_deg,
                                        360*self.scale_deg, 180*self.scale_deg)

        # Region bounds (minLon, maxLon, minLat, maxLat)
        self.bounds = {
            "world":           (-180,  180,  -90,   90),
            "europe":          ( -30,   50,   35,   72),
            "europe_incl_uk":  ( -30,   35,   35,   72),  # mainland+UK/IE
            "uk_ireland":      ( -11,    2,   49,   60),
            "usa":             (-130,  -70,   24,   50),
            "north_america":   (-170,  -50,    5,   83),
            "south_america":   ( -92,  -30,  -56,   13),
        }

        # markers (optional usage)
        self.own_pos = None
        self.peers = {}

        self.zoom_world()

    def ll_to_xy(self, lat, lon) -> QPointF:
        return QPointF(lon * self.scale_deg, -lat * self.scale_deg)

    def rect_from_bounds(self, min_lon, max_lon, min_lat, max_lat) -> QRectF:
        x = min_lon * self.scale_deg
        y = -max_lat * self.scale_deg
        w = (max_lon - min_lon) * self.scale_deg
        h = (max_lat - min_lat) * self.scale_deg
        return QRectF(x, y, w, h)

    def drawBackground(self, painter: QtGui.QPainter, rect: QtCore.QRectF):
        painter.save()
        painter.fillRect(rect, Qt.black)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, False)

        grid_col = QtGui.QColor("#00ff00")  # lime
        lab_col  = QtGui.QColor("#00ffff")  # cyan
        painter.setPen(QtGui.QPen(grid_col, 1))

        step = 10
        vis = rect.intersected(self.world_rect)

        lon_min = vis.left()  / self.scale_deg
        lon_max = vis.right() / self.scale_deg
        lat_max = -vis.top()   / self.scale_deg
        lat_min = -vis.bottom()/ self.scale_deg

        lon_start = int(math.floor(lon_min / step) * step)
        lon_end   = int(math.ceil (lon_max / step) * step)
        lat_start = int(math.floor(lat_min / step) * step)
        lat_end   = int(math.ceil (lat_max / step) * step)

        for lon in range(lon_start, lon_end + 1, step):
            p1 = self.ll_to_xy(lat_min, lon)
            p2 = self.ll_to_xy(lat_max, lon)
            painter.drawLine(p1, p2)

        for lat in range(lat_start, lat_end + 1, step):
            p1 = self.ll_to_xy(lat, lon_min)
            p2 = self.ll_to_xy(lat, lon_max)
            painter.drawLine(p1, p2)

        painter.setRenderHint(QtGui.QPainter.TextAntialiasing, True)
        painter.setPen(lab_col)
        f = painter.font(); f.setPointSize(8); painter.setFont(f)

        y_lab = int(vis.bottom() - 4)
        for lon in range(lon_start, lon_end + 1, step):
            pt = self.ll_to_xy(lat_min, lon)
            painter.drawText(int(pt.x() - 12), y_lab, f"{lon}°")

        x_lab = int(vis.left() + 4)
        for lat in range(lat_start, lat_end + 1, step):
            pt = self.ll_to_xy(lat, lon_min)
            painter.drawText(x_lab, int(pt.y() + 4), f"{lat}°")

        painter.restore()

    # preset zooms
    def zoom_to_bounds(self, key: str):
        if key not in self.bounds:
            return
        min_lon, max_lon, min_lat, max_lat = self.bounds[key]
        rect = self.rect_from_bounds(min_lon, max_lon, min_lat, max_lat)
        self.fitInView(rect, Qt.KeepAspectRatio)

    def zoom_world(self):              self.zoom_to_bounds("world")
    def zoom_europe(self):             self.zoom_to_bounds("europe")
    def zoom_europe_incl_ukie(self):   self.zoom_to_bounds("europe_incl_uk")
    def zoom_uk_ireland(self):         self.zoom_to_bounds("uk_ireland")
    def zoom_us(self):                 self.zoom_to_bounds("usa")
    def zoom_na(self):                 self.zoom_to_bounds("north_america")
    def zoom_sa(self):                 self.zoom_to_bounds("south_america")

    # disable wheel zoom
    def wheelEvent(self, event: QtGui.QWheelEvent):
        event.ignore()

# ---------------- Main App ----------------
class ChatApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Teensy Tracker Robust Packet Chat v0.9.67")
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

        # Top bar (right-justified Send GPS)
        topbar = QHBoxLayout()
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

        # Top controls: To / From / Load / APRS / KISS
        ctl = QHBoxLayout()
        lab_to = QLabel("To"); lab_from = QLabel("From")
        lab_to.setStyleSheet("color:#ccc;"); lab_from.setStyleSheet("color:#ccc;")
        self.target_edit = UppercaseLineEdit(); self.target_edit.setPlaceholderText("TARGET")
        self.mycall_edit = UppercaseLineEdit(); self.mycall_edit.setPlaceholderText("MYCALL")
        self.target_edit.setFixedWidth(180); self.mycall_edit.setFixedWidth(180)
        self.load_btn = QPushButton("Load Callsign"); self.load_btn.clicked.connect(self.load_mycall)

        self.aprs_beacon_check = QCheckBox("APRS Beacon")
        self.aprs_beacon_check.setChecked(False)
        self.aprs_beacon_check.toggled.connect(self._on_aprs_toggle)

        self.btn_kiss_enter = QPushButton("Enter KISS (@K)"); self.btn_kiss_enter.clicked.connect(self._enter_kiss_mode)
        self.kiss_perm_toggle = QCheckBox("KISS Permanent (@KP1)"); self.kiss_perm_toggle.toggled.connect(self._toggle_kiss_permanent)

        ctl.addWidget(lab_to);   ctl.addWidget(self.target_edit)
        ctl.addSpacing(12)
        ctl.addWidget(lab_from); ctl.addWidget(self.mycall_edit)
        ctl.addSpacing(12)
        ctl.addWidget(self.load_btn)
        ctl.addSpacing(12)
        ctl.addWidget(self.aprs_beacon_check)
        ctl.addWidget(self.btn_kiss_enter); ctl.addWidget(self.kiss_perm_toggle)
        root.addLayout(ctl)

        # Tabs
        self.tabs = QTabWidget()
        self.chat_tab = QWidget()
        self.map_tab = QWidget()
        self.tabs.addTab(self.chat_tab, "Chat")
        self.tabs.addTab(self.map_tab, "MAP GRID")
        root.addWidget(self.tabs, 1)

        # Chat tab
        cl = QVBoxLayout(self.chat_tab)
        title_recv = QLabel("Received Messages"); title_send = QLabel("Send Message")
        title_recv.setStyleSheet("color:#fff;background:#222; padding:4px 6px;")
        title_send.setStyleSheet("color:#fff;background:#222; padding:4px 6px;")
        self.recv_text = QTextEdit(); self.recv_text.setReadOnly(True)
        self.recv_text.setStyleSheet("QTextEdit { background:#000; color:#32CD32; font-family:Consolas,monospace; font-size:12pt; }")
        self.recv_text.setMinimumHeight(380)

        self.send_edit = QTextEdit()
        self.send_edit.setMaximumHeight(90)
        self.send_edit.setStyleSheet("QTextEdit { background:#000; color:#32CD32; font-family:Consolas,monospace; font-size:12pt; }")
        btn_send = QPushButton("SEND"); btn_send.setStyleSheet("QPushButton { background:#b00020; color:#fff; font-weight:bold; }")
        btn_send.setFixedHeight(40); btn_send.clicked.connect(self.send_message)

        send_row = QHBoxLayout()
        send_row.addWidget(self.send_edit, 1)
        send_row.addWidget(btn_send)

        cl.addWidget(title_recv)
        cl.addWidget(self.recv_text, 1)
        cl.addWidget(title_send)
        cl.addLayout(send_row)

        # MAP GRID tab
        ml = QVBoxLayout(self.map_tab)
        self.map_widget = GridMapView(self.map_tab)
        ml.addWidget(self.map_widget, 1)
        # Region buttons
        row_regions = QHBoxLayout()
        def add_btn(txt, slot):
            b = QPushButton(txt); b.clicked.connect(slot); row_regions.addWidget(b)
        add_btn("World",  self.map_widget.zoom_world)
        add_btn("Europe", self.map_widget.zoom_europe)
        add_btn("Mainland Europe + UK/IE", self.map_widget.zoom_europe_incl_ukie)
        add_btn("UK & Ireland", self.map_widget.zoom_uk_ireland)
        add_btn("USA",    self.map_widget.zoom_us)
        add_btn("North America", self.map_widget.zoom_na)
        add_btn("South America", self.map_widget.zoom_sa)
        row_regions.addStretch(1)
        ml.addLayout(row_regions)
        # Default to World view
        QtCore.QTimer.singleShot(0, self.map_widget.zoom_world)

        # Status bar
        sb = QStatusBar(); self.setStatusBar(sb)
        self.status_label = QtWidgets.QLabel("Disconnected  |  Reminder: turn KISS OFF to chat")
        sb.addWidget(self.status_label)

        self.refresh_ports()

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
            # After connect, sync KISS/APRS toggles from device without PTT
            QtCore.QTimer.singleShot(120, self._sync_device_state)
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
        # ESC + ASCII command + CR; never opens TX gate
        return self._write_raw(ESC + (cmd + "\r").encode("utf-8", errors="replace"))

    def _write_line(self, text: str):
        # Only allowed when TX gate is opened by send_user_text/send_gps
        if not self._tx_gate:
            return False
        return self._write_raw((text + "\r").encode("utf-8", errors="replace"))

    # ---------- Queries (no PTT) ----------
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

    def _query_lines(self, cmd: str, wait_ms: int = 600):
        if not (self.ser and self.ser.is_open): return []
        try:
            self._send_cmd(cmd)
            QtCore.QThread.msleep(50)
            text = self._read_for_ms(wait_ms)
        except Exception:
            return []
        return [ln.strip() for ln in re.split(r'\r\n|\n|\r', text) if ln.strip()]

    def _sync_device_state(self):
        # APRS %A (0/1/2). Treat ON as 1 (GPS mode)
        a_lines = self._query_lines("%A", 600)
        aprs_mode = None
        for ln in a_lines:
            m = re.search(r'(-?\d+)', ln)
            if m:
                try: aprs_mode = int(m.group(1)); break
                except: pass
        if aprs_mode is not None:
            self.aprs_beacon_check.blockSignals(True)
            self.aprs_beacon_check.setChecked(aprs_mode == 1)
            self.aprs_beacon_check.blockSignals(False)

        # KISS permanent @KP (0/1)
        kp_lines = self._query_lines("@KP", 600)
        kp = None
        for ln in kp_lines:
            m = re.search(r'(-?\d+)', ln)
            if m:
                try: kp = int(m.group(1)); break
                except: pass
        if kp is not None:
            self.kiss_perm_toggle.blockSignals(True)
            self.kiss_perm_toggle.setChecked(kp == 1)
            self.kiss_perm_toggle.blockSignals(False)

    # ---------- KISS / APRS ----------
    def _enter_kiss_mode(self):
        if not (self.ser and self.ser.is_open):
            QMessageBox.warning(self, "Not connected", "Open a COM port first."); return
        self._send_cmd("@K")
        QMessageBox.information(
            self, "KISS Mode",
            "Entered KISS MODE (@K).\nRemember: Chat requires KISS OFF."
        )

    def _toggle_kiss_permanent(self, on: bool):
        if not (self.ser and self.ser.is_open):
            QMessageBox.warning(self, "Not connected", "Open a COM port first.")
            self.kiss_perm_toggle.blockSignals(True)
            self.kiss_perm_toggle.setChecked(not on)
            self.kiss_perm_toggle.blockSignals(False)
            return

        if on:
            self._send_cmd("@KP1")
            QMessageBox.information(
                self, "KISS Permanent",
                "KISS Permanent ENABLED (@KP1).\nUse 'Enter KISS (@K)' to switch now.\n(No %ZS sent from Chat.)"
            )
        else:
            # Exit any current KISS session and clear permanent
            self._write_raw(bytes([192,255,192,13]))  # C0 FF C0 0D
            self._send_cmd("@KP0")
            QMessageBox.information(
                self, "KISS Permanent",
                "KISS Permanent DISABLED (@KP0).\nSent KISS EXIT (C0 FF C0 0D)."
            )

    def _on_aprs_toggle(self, on: bool):
        if not (self.ser and self.ser.is_open):
            QMessageBox.warning(self, "Not connected", "Open a COM port first.")
            self.aprs_beacon_check.blockSignals(True)
            self.aprs_beacon_check.setChecked(not on)
            self.aprs_beacon_check.blockSignals(False)
            return
        if on:
            self._send_cmd("%A1")
            QMessageBox.information(
                self, "APRS Beacon",
                "APRS beaconing enabled (%A1).\nIn chat mode this may be noisy for QSOs.\nRecommended OFF, or use 10.147.3 MHz for HF beacons."
            )
            self._append_chat_line("[APRS] Beaconing ON (GPS)", kind="sent")
        else:
            self._send_cmd("%A0")
            self._append_chat_line("[APRS] Beaconing OFF", kind="sent")

    # ---------- Incoming handling ----------
    def _on_line(self, line: str):
        content = re.sub(r'^\[\d{2}:\d{2}:\d{2}\]\s*', '', line).strip()

        # Hide console/device lines entirely
        if self._is_device_line(content):
            return

        # Echo suppression against our own sent line
        now = time.time()
        for txt, ts in list(self.recent_sent):
            if now - ts <= self.echo_window_s and content.strip() == txt.strip():
                return

        # Parse "<TO> DE <FROM> <msg>" including CQ
        m = LINE_RE.match(content)
        if m:
            to = m.group('to').upper(); frm = m.group('frm').upper(); msg = m.group('msg').strip()
            norm = f"{to} DE {frm}" + (f" {msg}" if msg else "")
            self._append_chat_line(norm, kind="received")
            # Basic coordinate sniff for plotting
            self._maybe_plot_from_text(frm, msg)
            return

        # Fallback plain line as received
        self._append_chat_line(content, kind="received")

    def _is_device_line(self, s: str) -> bool:
        if not s: return True
        if any(ord(ch) < 32 and ch not in ('\r','\n','\t') for ch in s): return True
        pats = [
            r'^fm\s+\S+\s+to\s+\S+\s+ctl\b',
            r'^\*\s*%.', r'^\*\s*@K(P1)?\b',
            r'^%[A-Za-z].', r'^cmd:\s', r'^(MHEARD|HEARD)\b',
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
        color = COLOR_SENT if kind == "sent" else COLOR_RECV
        text_esc = (text.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;"))
        html = f'<span style="color:{color}">{text_esc}</span><br>'
        self.recv_text.moveCursor(QtGui.QTextCursor.End)
        self.recv_text.insertHtml(html)
        self.recv_text.moveCursor(QtGui.QTextCursor.End)

    def _extract_callsign(self, text: str) -> str:
        m = re.search(CALL_RE, text, re.I); return m.group(0).upper() if m else ""

    def _maybe_plot_from_text(self, frm: str, msg: str):
        if not msg: return
        m = re.search(r'lat\s*=\s*(-?\d+(?:\.\d+)?)\s*[,;]\s*lon\s*=\s*(-?\d+(?:\.\d+)?)', msg, re.I)
        if m:
            lat = float(m.group(1)); lon = float(m.group(2))
            try: self.map_widget.set_peer(frm, lat, lon)
            except Exception: pass
            return
        m = re.search(r'(\d+(?:\.\d+)?)\s*([NS])\s+(\d+(?:\.\d+)?)\s*([EW])', msg, re.I)
        if m:
            lat = float(m.group(1)); lat = lat if m.group(2).upper()=='N' else -lat
            lon = float(m.group(3)); lon = lon if m.group(4).upper()=='E' else -lon
            try: self.map_widget.set_peer(frm, lat, lon)
            except Exception: pass

    # ---------- Load MyCALL (no PTT) ----------
    def load_mycall(self):
        if not (self.ser and self.ser.is_open):
            QMessageBox.warning(self, "Not connected", "Open a COM port first."); return
        try:
            if self.reader_thread: self.reader_thread.stop(); self.reader_thread=None
            self.ser.reset_input_buffer(); self.ser.reset_output_buffer()
            # Ask for stored params then query %i and fallback I
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

    # ---------- GPS SEND (PTT) ----------
    def send_gps(self):
        if not (self.ser and self.ser.is_open):
            QMessageBox.warning(self, "Not connected", "Open a COM port first."); return
        # Try to read a short burst and parse NMEA
        text = self._read_for_ms(800)
        lat, lon = self._parse_nmea_latlon(text)
        if lat is None or lon is None:
            QMessageBox.information(self, "GPS", "No GPS fix found from device stream (GGA/RMC)."); return
        # update map
        try: self.map_widget.set_own(lat, lon)
        except Exception: pass
        # build and send message
        target = self.target_edit.text().strip()
        my = self.mycall_edit.text().strip()
        if not target or not my:
            QMessageBox.warning(self, "Missing calls", "Enter both Target and MyCALL to transmit."); return
        pos_text = f"lat={lat:.5f} lon={lon:.5f}"
        line = f"{target} DE {my} {pos_text}"
        self._tx_gate = True
        ok = self._write_line(line)
        self._tx_gate = False
        if ok:
            self.recent_sent.append((line, time.time()))
            self._append_chat_line("[GPS sent] " + pos_text, kind="sent")

    def _parse_nmea_latlon(self, blob: str):
        if not blob: return (None, None)
        lat = lon = None
        for raw in blob.splitlines():
            line = raw.strip()
            if not line.startswith(("$GPRMC", "$GNRMC", "$GPGGA", "$GNGGA")):
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
            head = ddm.split('.')[0] if '.' in ddm else ddm
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

def main():
    print("Teensy Tracker Chat v0.9.67")
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setStyleSheet(DARK_QSS)
    w = ChatApp(); w.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()