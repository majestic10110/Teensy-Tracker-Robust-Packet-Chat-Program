#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Teensy Tracker Chat v1.2.8 ACK-RED — HOTFIX 7 (2025-09-12)
Change:
- On the 3rd (final) attempt, we now wait an extra 6s + 0–1s jitter
  *after* transmitting before marking the message as FAILED. This gives
  the ACK time to arrive for the last try.
Keeps HOTFIX6:
- Live RX (no X0/X1 muting), sender-verified ACKs
- Auto-retry up to 3 attempts with fixed 6s + 0–1s jitter between tries
- Mandatory ACK IDs, green→red on ACK, auto-ACK of inbound [ACK:ID]
- Console filtering, heartbeat list, GPS SEND, crash guards
"""

import sys, re, time, os, math, tempfile, traceback, random
from collections import deque
from datetime import datetime
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer, QUrl
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QTextBrowser, QTextEdit,
    QGroupBox, QCheckBox, QMessageBox, QStatusBar, QSizePolicy, QShortcut
)

# ---- Serial (optional if pyserial not installed) ----
try:
    import serial
    from serial import Serial
    from serial.tools import list_ports
except Exception:
    serial = None
    Serial = None
    list_ports = None

ESC = b'\x1b'
CALL_RE = r'[A-Z0-9]{1,2}\d[A-Z0-9]{1,3}(?:-[0-9]{1,2})?'
LINE_RE = re.compile(rf'^(?P<to>{CALL_RE}|CQ)\s+DE\s+(?P<frm>{CALL_RE})\s*(?P<msg>.*)$', re.I)
BEACON_RE = re.compile(rf'^\.(?P<dot>\.)?(?P<call>{CALL_RE})$', re.I)

# ACK detection
ACK_TAG_RE = re.compile(r'\[ACK:([0-9A-Z]{4,8})\]', re.I)
ACK_ONLY_RE = re.compile(r'^\s*ACK\s+([0-9A-Z]{4,8})\s*$', re.I)

# ---- Colours ----
COLOR_SENT = "#00FF00"      # green (sent pending)
COLOR_ACK  = "#FF3333"      # red (ACK received)
COLOR_RECV = "#FFA500"      # orange (received)
COLOR_HIGHLIGHT = "#00CC00" # focus/hover
COLOR_BG = "#1A1A1A"        # background
COLOR_PRESSED = "#333333"   # pressed
COLOR_TEXT = "#FFFFFF"      # status/messagebox text
COLOR_GPS_BG = "#CC0000"    # GPS SEND red
COLOR_GPS_HOVER = "#FF4D4D" # GPS hover

MESSAGE_BOX_STYLE = f"""
    QMessageBox {{
        background-color: {COLOR_BG};
        color: {COLOR_TEXT};
        font-family: VT323, monospace;
        font-size: 14pt;
    }}
    QMessageBox QLabel {{ color: {COLOR_TEXT}; }}
    QMessageBox QPushButton {{
        background-color: {COLOR_BG};
        color: {COLOR_TEXT};
        font-family: VT323, monospace;
        font-size: 14pt;
        border: 2px solid {COLOR_SENT};
        border-radius: 4px;
        padding: 4px;
        min-width: 80px;
    }}
    QMessageBox QPushButton:hover {{ background-color: {COLOR_HIGHLIGHT}; }}
    QMessageBox QPushButton:pressed {{ background-color: {COLOR_PRESSED}; }}
"""

# ---- NMEA helpers ----
NMEA_RMC = re.compile(r'^\$(?:GP|GN|GL|GA)RMC,', re.I)
NMEA_GGA = re.compile(r'^\$(?:GP|GN|GL|GA)GGA,', re.I)

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

def _fmt_latlon(lat: float, lon: float) -> str:
    if any(math.isnan(x) for x in (lat, lon)): return ""
    if abs(lat) > 90 or abs(lon) > 180: return ""
    return f"{lat:.5f} {lon:.5f}"

# ---- Position & altitude extraction (APRS + fallbacks) ----
APRS_BANG_RE = re.compile(
    r'[!=@]?(?P<lat>\d{4,5}\.\d+)\s*(?P<lathemi>[NS])[\/\\](?P<lon>\d{5,6}\.\d+)\s*(?P<lonhemi>[EW])',
    re.I
)
POS_DDMM_RE = re.compile(
    r'(?P<lat>\d{4,5}\.\d+)\s*([NS])[,/\s]+(?P<lon>\d{5,6}\.\d+)\s*([EW])',
    re.I
)
POS_DEC_RE = re.compile(
    r'(?P<lat>[-+]?\d{1,2}\.\d{3,})[,/\s]+(?P<lon>[-+]?\d{1,3}\.\d{3,})'
)
ALT_FT_RE = re.compile(r'\bA=(\d{3,6})\b')

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
    for raw in (text or "").splitlines():
        s = raw.strip()
        if NMEA_RMC.match(s) or NMEA_GGA.match(s):
            lt, ln = _parse_nmea_latlon(s)
            if not (math.isnan(lt) or math.isnan(ln)):
                return lt, ln
    return float('nan'), float('nan')

def _extract_alt_m(text: str):
    if not text: return float('nan')
    m = ALT_FT_RE.search(text)
    if not m: return float('nan')
    try:
        feet = int(m.group(1))
        return round(feet * 0.3048)
    except Exception:
        return float('nan')

def _norm(s: str) -> str:
    return re.sub(r'\s+', ' ', (s or '')).strip().upper()

def _extract_msg_only(text: str) -> str:
    m = LINE_RE.match(text or '')
    if not m: return ''
    return (m.group('msg') or '').strip()

def _to_base36(n: int, width: int = 4) -> str:
    digits = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    if n <= 0: return "0".rjust(width, '0')
    s = ""
    while n:
        n, r = divmod(n, 36)
        s = digits[r] + s
    return s.rjust(width, '0')

class UppercaseLineEdit(QLineEdit):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        font = QtGui.QFont("VT323", 16)
        self.setFont(font)
        self.setMaxLength(10)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(f"""
            QLineEdit {{
                background: {COLOR_BG};
                color: {COLOR_SENT};
                font-family: VT323, monospace;
                border: 2px solid {COLOR_SENT};
                border-radius: 4px;
                padding: 4px;
                text-transform: uppercase;
            }}
            QLineEdit:focus {{ border: 3px solid {COLOR_HIGHLIGHT}; }}
        """)
        fm = QtGui.QFontMetrics(font)
        self.setFixedWidth(int(fm.horizontalAdvance('M') * 11.5))
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def keyPressEvent(self, event: QtGui.QKeyEvent):
        super().keyPressEvent(event)
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
                        try:
                            text = part.decode('utf-8', errors='replace')
                        except Exception:
                            text = part.decode('latin1', errors='replace')
                        ts = datetime.now().strftime('%H:%M:%S')
                        self.line_received.emit(f"[{ts}] {text.strip()}")
                else:
                    self.msleep(20)
            except Exception:
                self.msleep(100)
    def stop(self):
        self._running = False
        self.wait(400)

class ChatApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Teensy Tracker Robust Packet Chat v1.2.8 ACK-RED — HOTFIX 7")
        self.resize(1340, 980)
        self.setStyleSheet(f"background: {COLOR_BG};")

        self.ser: Serial = None
        self.reader_thread: SerialReaderThread = None
        self.recent_sent = deque(maxlen=48)
        self.echo_window_s = 3.0
        self._tx_gate = False
        self._tx_count = 0

        # ACK state/model
        self.ack_counter = 1
        self.chat_items = []  # newest first
        self.sent_by_ack = {} # ack_id -> item dict
        self.retry_timers = {} # ack_id -> QTimer
        self.auto_ack_enabled = True

        # diagnostic log (silent)
        self._last_log_path = ""

        # ---------- Beaconing (TX) ----------
        self.beacon_timer = QTimer(self)
        self.beacon_timer.setInterval(15 * 60 * 1000)  # 15 minutes
        self.beacon_timer.timeout.connect(self._send_beacon)

        # ---------- Heartbeat (RX beacons) ----------
        self.HEARTBEAT_TTL_S = 20 * 60  # 20 minutes
        self.heartbeat_seen = {}        # { 'CALL': last_heard_ts }
        self.heartbeat_gc_timer = QTimer(self)
        self.heartbeat_gc_timer.setInterval(30 * 1000)  # refresh every 30s
        self.heartbeat_gc_timer.timeout.connect(self._heartbeat_update_view)
        self.heartbeat_gc_timer.start()

        # ---- ROOT LAYOUT ----
        central = QWidget(); self.setCentralWidget(central)
        root = QVBoxLayout(central); root.setSpacing(12)

        # ----- Top layout (Serial + Frequencies) -----
        top_layout = QHBoxLayout(); top_layout.setSpacing(12)

        # --- Serial controls ---
        ser_group = QGroupBox("Serial")
        ser_group.setStyleSheet(f"""
            QGroupBox {{
                color: {COLOR_SENT};
                font-family: VT323, monospace;
                font-size: 16pt;
                border: 2px solid {COLOR_SENT};
                border-radius: 4px;
                margin-top: 24px;
                padding: 12px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1A1A1A, stop:1 #2A2A2A);
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 6px;
                color: {COLOR_SENT};
                margin-top: 4px;
            }}
        """)
        ser_layout = QHBoxLayout(ser_group); ser_layout.setSpacing(8)

        self.port_combo = QComboBox()
        self.port_combo.setStyleSheet(f"""
            QComboBox {{
                background: {COLOR_BG};
                color: {COLOR_SENT};
                font-family: VT323, monospace;
                font-size: 14pt;
                border: 2px solid {COLOR_SENT};
                border-radius: 4px;
                padding: 4px;
            }}
            QComboBox QAbstractItemView {{
                background: {COLOR_BG};
                color: {COLOR_SENT};
                selection-background-color: {COLOR_HIGHLIGHT};
            }}
        """)
        self.port_combo.setFixedWidth(200)

        def std_btn_style():
            return f"""
                QPushButton {{
                    background: {COLOR_BG};
                    color: {COLOR_SENT};
                    font-family: VT323, monospace;
                    font-size: 14pt;
                    border: 2px solid {COLOR_SENT};
                    border-radius: 4px;
                    padding: 4px;
                }}
                QPushButton:hover {{ background: {COLOR_HIGHLIGHT}; }}
                QPushButton:pressed {{ background: {COLOR_PRESSED}; }}
            """

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setStyleSheet(std_btn_style()); refresh_btn.setFixedWidth(168)
        refresh_btn.clicked.connect(self.refresh_ports)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setStyleSheet(std_btn_style()); self.connect_btn.setFixedWidth(168)
        self.connect_btn.clicked.connect(self.open_port)

        self.disconnect_btn = QPushButton("Disconnect")
        self.disconnect_btn.setStyleSheet(std_btn_style()); self.disconnect_btn.setFixedWidth(168)
        self.disconnect_btn.setEnabled(False); self.disconnect_btn.clicked.connect(self.close_port)

        self.enter_kiss_btn = QPushButton("Enter KISS")
        self.enter_kiss_btn.setStyleSheet(std_btn_style()); self.enter_kiss_btn.setFixedWidth(168)
        self.enter_kiss_btn.setEnabled(False); self.enter_kiss_btn.clicked.connect(self._enter_kiss_mode)

        ser_layout.addWidget(self.port_combo)
        ser_layout.addWidget(refresh_btn)
        ser_layout.addWidget(self.connect_btn)
        ser_layout.addWidget(self.disconnect_btn)
        ser_layout.addWidget(self.enter_kiss_btn)
        ser_layout.addStretch(1)

        ser_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        QtCore.QTimer.singleShot(0, lambda: ser_group.setFixedHeight(ser_group.sizeHint().height()))

        # --- Frequencies box ---
        freq_group = QGroupBox("Frequencies")
        freq_group.setStyleSheet(ser_group.styleSheet())

        freq_layout = QVBoxLayout(freq_group)
        freq_layout.setSpacing(4)
        freq_layout.setContentsMargins(12, 12, 12, 12)

        for freq in ["7.0903 MHz", "10.1423 MHz", "14.109 MHz"]:
            lbl = QLabel(freq)
            lbl.setStyleSheet(f"QLabel {{ color: {COLOR_SENT}; font-family: VT323, monospace; font-size: 14pt; }}")
            freq_layout.addWidget(lbl)

        freq_group.setFixedWidth(250)
        freq_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        QtCore.QTimer.singleShot(0, lambda: freq_group.setFixedHeight(freq_group.sizeHint().height()))

        top_layout.addWidget(ser_group, 1, Qt.AlignTop)
        top_layout.addStretch(1)
        top_layout.addWidget(freq_group, 0, Qt.AlignTop)
        root.addLayout(top_layout)

        # ----- Callsign + toggles -----
        ctl = QHBoxLayout(); ctl.setSpacing(8)
        lbl_to = QLabel("To"); lbl_from = QLabel("From")
        style_lbl = f"QLabel {{ color: {COLOR_SENT}; font-family: VT323, monospace; font-size: 16pt; }}"
        lbl_to.setStyleSheet(style_lbl); lbl_from.setStyleSheet(style_lbl)
        lbl_to.setAlignment(Qt.AlignRight); lbl_from.setAlignment(Qt.AlignRight)

        self.target_edit = UppercaseLineEdit(); self.target_edit.setPlaceholderText("G4ABC-7 or CQ")
        self.mycall_edit  = UppercaseLineEdit(); self.mycall_edit.setPlaceholderText("M0OLI")

        self.hide_mon_check = QCheckBox("Hide device/monitor lines")
        self.hide_mon_check.setChecked(True)
        self.hide_mon_check.setStyleSheet(f"QCheckBox {{ color: {COLOR_SENT}; font-family: VT323, monospace; font-size: 14pt; }}")

        self.kiss_perm_toggle = QCheckBox("KISS Mode (permanent)")
        self.kiss_perm_toggle.setStyleSheet(f"QCheckBox {{ color: {COLOR_SENT}; font-family: VT323, monospace; font-size: 14pt; }}")
        self.kiss_perm_toggle.toggled.connect(self._toggle_kiss_permanent)

        to_box = QHBoxLayout(); to_box.setSpacing(4); to_box.addWidget(lbl_to); to_box.addSpacing(4); to_box.addWidget(self.target_edit)
        from_box = QHBoxLayout(); from_box.setSpacing(4); from_box.addWidget(lbl_from); from_box.addSpacing(4); from_box.addWidget(self.mycall_edit)
        callsign_container = QWidget(); callsign_layout = QHBoxLayout(callsign_container)
        callsign_layout.setContentsMargins(0,0,0,0); callsign_layout.setSpacing(8)
        callsign_layout.addLayout(to_box); callsign_layout.addLayout(from_box); callsign_layout.addStretch(0)

        ctl.addWidget(callsign_container)
        ctl.addWidget(self.hide_mon_check)
        ctl.addWidget(self.kiss_perm_toggle)
        ctl.addStretch(1)
        root.addLayout(ctl)

        # ----- Received + Heartbeat (with Clear button) -----
        title_row = QHBoxLayout(); title_row.setSpacing(8)
        recv_title = QLabel("Messages")
        recv_title.setStyleSheet(f"QLabel {{ color: {COLOR_SENT}; font-family: VT323, monospace; font-size: 18pt; font-weight: bold; }}")
        title_row.addWidget(recv_title)
        title_row.addStretch(1)

        self.clear_recv_btn = QPushButton("Clear Message Window")
        self.clear_recv_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLOR_BG};
                color: {COLOR_SENT};
                font-family: VT323, monospace;
                font-size: 12pt;
                border: 2px solid {COLOR_SENT};
                border-radius: 4px;
                padding: 4px 8px;
            }}
            QPushButton:hover {{ background: {COLOR_HIGHLIGHT}; }}
            QPushButton:pressed {{ background: {COLOR_PRESSED}; }}
        """)
        self.clear_recv_btn.clicked.connect(self._clear_receive_window)
        title_row.addWidget(self.clear_recv_btn)
        root.addLayout(title_row)

        recv_heartbeat_layout = QHBoxLayout(); recv_heartbeat_layout.setSpacing(8)

        self.recv_text = QTextBrowser(); self.recv_text.setReadOnly(True)
        self.recv_text.setStyleSheet(f"""
            QTextBrowser {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1A1A1A, stop:1 #2A2A2A);
                color: {COLOR_SENT};
                font-family: VT323, monospace;
                font-size: 14pt;
                border: 2px solid {COLOR_SENT};
                border-radius: 4px;
                padding: 8px;
            }}
            QTextBrowser a {{
                color: {COLOR_RECV};
                text-decoration: none;
                border: 1px solid {COLOR_RECV};
                padding: 2px;
                border-radius: 3px;
            }}
            QTextBrowser a:hover {{ background-color: {COLOR_HIGHLIGHT}; }}
        """)
        self.recv_text.setMinimumSize(1000, 700)
        self.recv_text.setOpenLinks(False)
        self.recv_text.anchorClicked.connect(self._handle_callsign_click)
        recv_heartbeat_layout.addWidget(self.recv_text, 1)

        # Heartbeat column
        heartbeat_container = QWidget()
        heartbeat_layout = QVBoxLayout(heartbeat_container); heartbeat_layout.setSpacing(8)
        self.beacon_check = QCheckBox("15 min Beacons")
        self.beacon_check.setStyleSheet(f"QCheckBox {{ color: {COLOR_SENT}; font-family: VT323, monospace; font-size: 14pt; }}")
        self.beacon_check.toggled.connect(self._toggle_beaconing)
        self.heartbeat_text = QTextEdit(); self.heartbeat_text.setReadOnly(True)
        self.heartbeat_text.setStyleSheet(f"""
            QTextEdit {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1A1A1A, stop:1 #2A2A2A);
                color: {COLOR_SENT};
                font-family: VT323, monospace;
                font-size: 14pt;
                border: 2px solid {COLOR_SENT};
                border-radius: 4px;
                padding: 8px;
            }}
        """)
        font = QtGui.QFont("VT323", 14)
        fm = QtGui.QFontMetrics(font)
        char_w = fm.horizontalAdvance('M')
        self.heartbeat_text.setFixedWidth(int(char_w * 17.5))
        heartbeat_layout.addWidget(self.beacon_check)
        heartbeat_layout.addWidget(self.heartbeat_text)
        recv_heartbeat_layout.addWidget(heartbeat_container)
        root.addLayout(recv_heartbeat_layout)

        # ----- Send -----
        send_title = QLabel("Send Message")
        send_title.setStyleSheet(recv_title.styleSheet())
        root.addWidget(send_title)

        send_row = QHBoxLayout(); send_row.setSpacing(8)

        self.send_edit = QTextEdit()
        self.send_edit.setObjectName("sendEdit")
        send_font = QtGui.QFont("VT323", 14)
        self.send_edit.setFont(send_font)
        self.send_edit.setStyleSheet(f"""
            QTextEdit#sendEdit {{
                background: {COLOR_BG};
                color: {COLOR_SENT};
                font-family: VT323, monospace;
                border: 2px solid {COLOR_SENT};
                border-radius: 4px;
                padding: 4px;
                outline: none;
            }}
            QTextEdit#sendEdit:focus {{ border: 3px solid {COLOR_HIGHLIGHT}; }}
            QTextEdit#sendEdit::viewport {{ background-color: {COLOR_BG}; }}
        """)
        pal = self.send_edit.palette()
        pal.setColor(QtGui.QPalette.Base, QtGui.QColor(COLOR_BG))
        pal.setColor(QtGui.QPalette.Text, QtGui.QColor(COLOR_SENT))
        pal.setColor(QtGui.QPalette.Highlight, QtGui.QColor(COLOR_HIGHLIGHT))
        pal.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor(COLOR_BG))
        self.send_edit.setPalette(pal)
        self.send_edit.setFrameStyle(QtWidgets.QFrame.NoFrame)

        fm = QtGui.QFontMetrics(send_font)
        self.send_edit.setFixedHeight(fm.lineSpacing() * 3 + 16)

        self.send_btn = QPushButton("SEND")
        self.send_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLOR_HIGHLIGHT};
                color: {COLOR_BG};
                font-family: VT323, monospace;
                font-size: 16pt;
                font-weight: bold;
                border: 2px solid {COLOR_SENT};
                border-radius: 4px;
                padding: 10px;
            }}
            QPushButton:hover {{ background: {COLOR_SENT}; }}
            QPushButton:pressed {{ background: {COLOR_PRESSED}; }}
        """)
        self.send_btn.setFixedWidth(178)
        self.send_btn.clicked.connect(self.send_message)
        self.sc_send1 = QShortcut(QtGui.QKeySequence("Ctrl+Return"), self, activated=self.send_message)
        self.sc_send2 = QShortcut(QtGui.QKeySequence("Ctrl+Enter"),  self, activated=self.send_message)

        self.gps_btn = QPushButton("GPS SEND")
        self.gps_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLOR_GPS_BG};
                color: #FFFFFF;
                font-family: VT323, monospace;
                font-size: 16pt;
                font-weight: bold;
                border: 2px solid #FFFFFF;
                border-radius: 4px;
                padding: 10px;
            }}
            QPushButton:hover {{ background: {COLOR_GPS_HOVER}; }}
            QPushButton:pressed {{ background: {COLOR_PRESSED}; }}
        """)
        self.gps_btn.setFixedWidth(178)
        self.gps_btn.clicked.connect(self.send_gps_position)

        send_row.addWidget(self.send_edit, 1)
        send_row.addWidget(self.send_btn)
        send_row.addWidget(self.gps_btn)
        root.addLayout(send_row)

        # Status bar
        sb = QStatusBar()
        sb.setStyleSheet(f"""
            QStatusBar {{
                background-color: {COLOR_BG};
                color: {COLOR_TEXT};
                font-family: VT323, monospace;
                font-size: 14pt;
                border: none;
            }}
            QStatusBar QLabel {{
                background-color: {COLOR_BG};
                color: {COLOR_TEXT};
                border: none;
            }}
        """)
        self.setStatusBar(sb)
        self.status_label = QtWidgets.QLabel("Disconnected  |  Reminder: WARNING: Changing KISS condition will PTT, Disconnect Data cable from radio before changing KISS. Turn KISS OFF to chat")
        sb.addWidget(self.status_label)

        self.refresh_ports()

    # -------- Serial control --------
    def refresh_ports(self):
        self.port_combo.clear()
        try:
            if list_ports:
                ports = sorted(list_ports.comports(), key=lambda p: p.device)
                for p in ports:
                    self.port_combo.addItem(f"{p.device} — {p.description}", p.device)
            else:
                for i in range(1,21): self.port_combo.addItem(f"COM{i}", f"COM{i}")
        except Exception:
            for i in range(1,21): self.port_combo.addItem(f"COM{i}", f"COM{i}")

    def open_port(self):
        try:
            if serial is None or Serial is None:
                msg = QMessageBox(); msg.setStyleSheet(MESSAGE_BOX_STYLE)
                msg.setIcon(QMessageBox.Critical); msg.setWindowTitle("PySerial not available")
                msg.setText(
                    "PySerial is not installed or failed to import.\n\n"
                    "Install it and restart the app:\n"
                    "  Windows:  py -m pip install pyserial\n"
                    "  macOS/Linux:  python3 -m pip install pyserial"
                )
                msg.exec_()
                self.status_label.setText("Disconnected  |  PySerial missing")
                return

            if self.ser and self.ser.is_open:
                self.close_port()

            port = self.port_combo.currentData() or self.port_combo.currentText()
            baud = 115200
            if not port or not isinstance(port, str):
                raise RuntimeError("No COM port selected.")

            self.ser = serial.Serial(
                port=port,
                baudrate=baud,
                timeout=0.05,
                rtscts=False,
                dsrdtr=False,
                write_timeout=1.0,
            )
            self.reader_thread = SerialReaderThread(self.ser)
            self.reader_thread.line_received.connect(self._on_line)
            self.reader_thread.start()

            self.connect_btn.setText("Connected...")
            self.connect_btn.setEnabled(False)
            self.disconnect_btn.setEnabled(True)
            self.enter_kiss_btn.setEnabled(True)
            self.status_label.setText(f"Connected {port}  |  Reminder: turn KISS OFF to chat")

        except Exception as e:
            print(f"[open_port] Failed to open: {e!r}")
            msg = QMessageBox(); msg.setStyleSheet(MESSAGE_BOX_STYLE)
            msg.setIcon(QMessageBox.Critical); msg.setWindowTitle("Serial error")
            msg.setText(f"Failed to open port.\n\nDetails:\n{e}")
            msg.exec_()
            self.status_label.setText("Disconnected  |  Failed to open port")

    def close_port(self):
        try:
            if self.reader_thread:
                self.reader_thread.stop()
                self.reader_thread = None
            if self.ser:
                self.ser.close()
                self.ser = None
            self.beacon_timer.stop()
        finally:
            # Stop and clear any retry timers
            for tid in list(self.retry_timers.values()):
                try:
                    tid.stop()
                except Exception:
                    pass
            self.retry_timers.clear()
            self.connect_btn.setText("Connect")
            self.connect_btn.setEnabled(True)
            self.disconnect_btn.setEnabled(False)
            self.enter_kiss_btn.setEnabled(False)
            self.beacon_check.setChecked(False)
            self.status_label.setText("Disconnected  |  Reminder: turn KISS OFF to chat")

    # -------- Low-level TX helpers --------
    def _write_raw(self, data: bytes):
        if not (self.ser and self.ser.is_open):
            msg = QMessageBox(); msg.setStyleSheet(MESSAGE_BOX_STYLE)
            msg.setIcon(QMessageBox.Warning); msg.setWindowTitle("Not connected")
            msg.setText("Open a COM port first."); msg.exec_()
            return False
        try:
            self.ser.write(data); return True
        except Exception as e:
            msg = QMessageBox(); msg.setStyleSheet(MESSAGE_BOX_STYLE)
            msg.setIcon(QMessageBox.Critical); msg.setWindowTitle("Write error")
            msg.setText(str(e)); msg.exec_(); return False

    def _send_cmd(self, cmd: str):
        return self._write_raw(ESC + (cmd + "\r").encode("utf-8", errors="replace"))

    def _write_line(self, text: str):
        if not self._tx_gate: return False
        return self._write_raw((text + "\r").encode("utf-8", errors='replace'))

    def _ptt_guard(self, func):
        """No X0/X1 toggling; just run TX safely."""
        if not (self.ser and self.ser.is_open):
            msg = QMessageBox(); msg.setStyleSheet(MESSAGE_BOX_STYLE)
            msg.setIcon(QMessageBox.Warning); msg.setWindowTitle("Not connected")
            msg.setText("Open a COM port first."); msg.exec_()
            return False
        try:
            return bool(func())
        except Exception as e:
            self._show_exception("TX error", e)
            return False

    # -------- KISS / toggles --------
    def _enter_kiss_mode(self):
        self._send_cmd("@K"); QtCore.QThread.msleep(120); self._send_cmd("%ZS")
        msg = QMessageBox(); msg.setStyleSheet(MESSAGE_BOX_STYLE)
        msg.setIcon(QMessageBox.Information); msg.setWindowTitle("Entered KISS")
        msg.setText("Entered KISS MODE (@K) and saved with %ZS.\nTo chat again, turn KISS OFF.")
        msg.exec_()
        self.status_label.setText("Entered KISS MODE (@K). Chat requires KISS OFF.")

    def _toggle_kiss_permanent(self, on: bool):
        if on:
            self._send_cmd("@KP1"); QtCore.QThread.msleep(80); self._send_cmd("%ZS")
            self.status_label.setText("KISS Permanent ENABLED (@KP1), saved. Chat requires KISS OFF.")
            msg = QMessageBox(); msg.setStyleSheet(MESSAGE_BOX_STYLE)
            msg.setIcon(QMessageBox.Question); msg.setWindowTitle("Enter KISS now?")
            msg.setText("KISS Permanent is ON and saved.\nDo you also want to ENTER KISS MODE now (@K then %ZS)?")
            msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No); msg.setDefaultButton(QMessageBox.No)
            if msg.exec_() == QMessageBox.Yes:
                self._send_cmd("@K"); QtCore.QThread.msleep(120); self._send_cmd("%ZS")
                info = QMessageBox(); info.setStyleSheet(MESSAGE_BOX_STYLE)
                info.setIcon(QMessageBox.Information); info.setWindowTitle("Entered KISS")
                info.setText("Entered KISS MODE (@K) and saved with %ZS.\nTo chat again, turn KISS OFF."); info.exec_()
                self.status_label.setText("Entered KISS MODE (@K). Chat requires KISS OFF.")
        else:
            self._send_cmd("@KP0"); QtCore.QThread.msleep(80); self._send_cmd("%ZS")
            QtCore.QThread.msleep(120); self._write_raw(bytes([192,255,192,13]))
            self.status_label.setText("KISS disabled (@KP0) & saved; Exit KISS bytes sent. Ready for chat.")
            msg = QMessageBox(); msg.setStyleSheet(MESSAGE_BOX_STYLE)
            msg.setIcon(QMessageBox.Information); msg.setWindowTitle("KISS OFF")
            msg.setText("KISS disabled (@KP0), saved with %ZS, and exit bytes sent.\nReady for chat.")
            msg.exec_()

    # -------- Beaconing (15-min TX) --------
    def _toggle_beaconing(self, on: bool):
        if on:
            if not (self.ser and self.ser.is_open):
                msg = QMessageBox(); msg.setStyleSheet(MESSAGE_BOX_STYLE)
                msg.setIcon(QMessageBox.Warning); msg.setWindowTitle("Not connected")
                msg.setText("Open a COM port first to enable beaconing."); msg.exec_()
                self.beacon_check.setChecked(False); return
            if not self.mycall_edit.text().strip():
                msg = QMessageBox(); msg.setStyleSheet(MESSAGE_BOX_STYLE)
                msg.setIcon(QMessageBox.Warning); msg.setWindowTitle("MyCALL missing")
                msg.setText("Enter MyCALL in the From field to enable beaconing."); msg.exec_()
                self.beacon_check.setChecked(False); return
            self.beacon_timer.start()
            self._send_beacon()
            self.status_label.setText(f"Beaconing ON (15 min) | Connected {self.port_combo.currentText()}")
        else:
            self.beacon_timer.stop()
            self.status_label.setText(f"Connected {self.port_combo.currentText()}  |  Reminder: turn KISS OFF to chat")

    def _send_beacon(self):
        mycall = self.mycall_edit.text().strip().upper()
        if not mycall:
            self.beacon_timer.stop()
            self.beacon_check.setChecked(False)
            msg = QMessageBox(); msg.setStyleSheet(MESSAGE_BOX_STYLE)
            msg.setIcon(QMessageBox.Warning); msg.setWindowTitle("MyCALL missing")
            msg.setText("MyCALL is empty. Beaconing stopped."); msg.exec_()
            return
        beacon_text = f"..{mycall}"
        self._tx_gate = True
        ok = self._ptt_guard(lambda: self._write_line(beacon_text))
        self._tx_gate = False
        if ok:
            self._tx_count += 1
            self.status_label.setText(
                f"TX: {self._tx_count} | Beaconing ON (15 min) | Connected {self.port_combo.currentText()}"
            )
            self._add_chat_item(kind="sent", text="<Beacon sent>", to="", frm=mycall, ack_id=None, ack=False)

    # -------- APRS helpers --------
    def _aprs_set(self, on: bool, save: bool = False):
        try:
            self._send_cmd("%A1" if on else "%A0")
            QtCore.QThread.msleep(150)
            if save:
                self._send_cmd("%ZS")
                QtCore.QThread.msleep(150)
        except Exception:
            pass

    def _aprs_preflight(self):
        log = []
        missing = []
        snapshot = {"aprs_call": "", "global_call": "", "av": None, "path": ""}

        try:
            self.ser.reset_input_buffer(); self.ser.reset_output_buffer()
        except Exception:
            pass

        self._send_cmd("%AM"); QtCore.QThread.msleep(220)
        am = (self._read_for_ms(900) or "").strip()
        log += ["[AM] (APRS-Mycall)", am if am else "(no reply)"]
        aprs_call = self._extract_callsign(am)
        if "NONE" in am.upper(): aprs_call = ""
        snapshot["aprs_call"] = aprs_call

        self._send_cmd("I"); QtCore.QThread.msleep(220)
        ii = (self._read_for_ms(900) or "").strip()
        log += ["[I] (Global Mycall)", ii if ii else "(no reply)"]
        global_call = self._extract_callsign(ii)
        snapshot["global_call"] = global_call

        if not aprs_call and not global_call:
            missing.append("No APRS callsign: set %AM <CALL-SSID> or I <CALL>.")

        self._send_cmd("%AP"); QtCore.QThread.msleep(220)
        ap = (self._read_for_ms(900) or "").strip()
        log += ["[AP] (APRS path/status)", ap if ap else "(no reply)"]
        snapshot["path"] = ap or ""

        self._send_cmd("%AV"); QtCore.QThread.msleep(220)
        av = (self._read_for_ms(900) or "").strip()
        log += ["[AV] (validity seconds)", av if av else "(no reply)"]
        try:
            snapshot["av"] = int(re.search(r'(-?\d+)', av).group(1))
        except Exception:
            snapshot["av"] = None

        ok = (len(missing) == 0)
        return ok, missing, log, snapshot

    def _query_tnc_position_verbose(self, log_lines):
        try:
            self.ser.reset_input_buffer(); self.ser.reset_output_buffer()
        except Exception:
            pass

        combined = []

        self._send_cmd("%A1"); QtCore.QThread.msleep(250)
        a1 = (self._read_for_ms(1200) or "").strip()
        if a1:
            log_lines += ["[A1 ack]", a1]
            combined.append(a1)

        self._send_cmd("%AI"); QtCore.QThread.msleep(300)
        ai = (self._read_for_ms(1600) or "").strip()
        if ai:
            log_lines += ["[AI]", ai]
            combined.append(ai)

        combo = "\n".join(combined)
        lat, lon = _extract_any_latlon(combo)
        alt_m = _extract_alt_m(combo)

        if math.isnan(lat) or math.isnan(lon):
            self._send_cmd("%AO"); QtCore.QThread.msleep(300)
            ao = (self._read_for_ms(1600) or "").strip()
            if ao:
                log_lines += ["[AO]", ao]
                combined.append(ao)
                combo = "\n".join(combined)
                lat, lon = _extract_any_latlon(combo)
                if math.isnan(alt_m):
                    alt_m = _extract_alt_m(combo)

        return lat, lon, alt_m

    # -------- RX handling --------
    def _on_line(self, line: str):
        content = re.sub(r'^\[\d{2}:\d{2}:\d{2}\]\s*', '', line or '').strip()

        # -- Treat non-beacon dot-lines (e.g., ".X0") as device lines
        if content.startswith('.') and not BEACON_RE.match(content):
            if not self.hide_mon_check.isChecked():
                print(f"Device/Console: {content}")
            return

        if self._is_device_line(content) or self._looks_like_console(content):
            if not self.hide_mon_check.isChecked():
                print(f"Device/Console: {content}")
            return

        now = time.time()
        norm_in_full = _norm(content)
        norm_in_msg  = _norm(_extract_msg_only(content))

        # Heartbeat beacons
        beacon_match = BEACON_RE.match(content)
        if beacon_match:
            call = beacon_match.group('call').upper()
            mycall = self.mycall_edit.text().strip().upper()
            if call == mycall:
                return
            self.heartbeat_seen[call] = now
            self._heartbeat_update_view()
            return

        m = LINE_RE.match(content)
        if m:
            to  = (m.group('to')  or '').upper()
            frm = (m.group('frm') or '').upper()
            msg = (m.group('msg') or '').strip()

            # ACK-only lines from peer — sender-verified
            ack_only = ACK_ONLY_RE.match(msg or "")
            if ack_only:
                ack_id = ack_only.group(1).upper()
                my = (self.mycall_edit.text() or '').upper().strip()
                item = self.sent_by_ack.get(ack_id)
                if item and my and to == my and frm == (item.get("to") or "").upper():
                    self._mark_ack_received(ack_id, from_callsign=frm)
                return  # never render pure ACK lines

            # Normal inbound message
            my = (self.mycall_edit.text() or '').upper().strip()
            if my and frm == my:
                return  # echo from self

            for item in list(self.recent_sent):
                if now - item["ts"] <= self.echo_window_s:
                    if norm_in_full == item["full"] or (norm_in_msg and norm_in_msg == item["msg"]):
                        return  # echo filtered

            # Auto-ACK if the inbound contains an ACK tag
            tag = ACK_TAG_RE.search(msg or "")
            if tag and self.auto_ack_enabled and my:
                ack_id = tag.group(1).upper()
                reply = f"{frm} DE {my} ACK {ack_id}"
                self._tx_gate = True
                self._ptt_guard(lambda: self._write_line(reply))
                self._tx_gate = False
                self._add_chat_item(kind="sent", text=reply, to=frm, frm=my, ack_id=None, ack=False)

            norm = f"{to} DE {frm}" + (f" {msg}" if msg else "")
            self._add_chat_item(kind="received", text=norm, to=to, frm=frm, ack_id=None, ack=False)
            return

        # Fallback
        self._add_chat_item(kind="received", text=content, to="", frm="", ack_id=None, ack=False)

    # -------- Heartbeat maintenance --------
    def _heartbeat_update_view(self):
        now = time.time()
        expired = [c for c, ts in self.heartbeat_seen.items() if now - ts > self.HEARTBEAT_TTL_S]
        for c in expired:
            del self.heartbeat_seen[c]
        items = sorted(self.heartbeat_seen.items(), key=lambda kv: kv[1], reverse=True)
        self.heartbeat_text.setPlainText("\n".join(c for c, ts in items))
        sb = self.heartbeat_text.verticalScrollBar()
        sb.setValue(sb.maximum())

    # -------- Message model/rendering --------
    def _add_chat_item(self, *, kind: str, text: str, to: str, frm: str, ack_id: str, ack: bool):
        item = {
            "kind": kind,
            "text": text or "",
            "ts": datetime.now(),
            "ack": bool(ack),
            "ack_id": ack_id.upper() if ack_id else None,
            "to": (to or "").upper(),
            "frm": (frm or "").upper(),
            "attempt": 1 if (kind == "sent" and ack_id) else None,
            "max_attempts": 3 if (kind == "sent" and ack_id) else None,
            "failed": False,
        }
        if kind == "sent" and item["ack_id"]:
            self.sent_by_ack[item["ack_id"]] = item
        self.chat_items.insert(0, item)
        self._rebuild_chat_view()
        # schedule retry if it's a sent message with ACK pending
        if kind == "sent" and item["ack_id"]:
            self._schedule_retry(item["ack_id"], initial=True)

    def _rebuild_chat_view(self):
        doc = []
        for item in self.chat_items:
            ts = item["ts"].strftime('%H:%M:%S')
            kind = item["kind"]
            color = COLOR_RECV
            if kind == "sent":
                color = COLOR_ACK if item.get("ack") else COLOR_SENT
            text = item["text"]
            # Status suffix for retries/fail
            suffix = ""
            if kind == "sent" and item.get("ack_id") and not item.get("ack"):
                if item.get("failed"):
                    suffix = "  (FAILED)"
                else:
                    a = item.get("attempt") or 1
                    m = item.get("max_attempts") or 3
                    suffix = f"  (attempt {a}/{m})"
            rendered = (text or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;") + suffix
            line_html = f'<span style="color:{color}; font-family:VT323,monospace">[{ts}] {rendered}</span><br>'
            doc.append(line_html)
        self.recv_text.clear()
        if doc:
            self.recv_text.insertHtml("".join(doc))
            self.recv_text.moveCursor(QtGui.QTextCursor.Start)
            sb = self.recv_text.verticalScrollBar()
            sb.setValue(sb.minimum())

    # -------- ACK handling & retries --------
    def _mark_ack_received(self, ack_id: str, from_callsign: str = ""):
        ack_id = (ack_id or "").upper()
        item = self.sent_by_ack.get(ack_id)
        if item and not item.get("ack"):
            item["ack"] = True
            item["failed"] = False
            # cancel retry timer if any
            t = self.retry_timers.pop(ack_id, None)
            if t:
                try: t.stop()
                except Exception: pass
            self._rebuild_chat_view()
            if from_callsign:
                self.status_label.setText(f"ACK {ack_id} verified from {from_callsign}.")
            else:
                self.status_label.setText(f"ACK {ack_id} verified.")
        else:
            self.status_label.setText(f"ACK {ack_id} received (no matching pending message).")

    def _schedule_retry(self, ack_id: str, initial: bool = False):
        """Schedule next action. If attempts left, schedule a resend; if this was the final (3/3),
        schedule a last grace wait (6s + 0–1s jitter) before declaring FAILED."""
        item = self.sent_by_ack.get(ack_id)
        if not item or item.get("ack"):
            return
        a = item.get("attempt") or 1
        m = item.get("max_attempts") or 3

        delay_ms = int(6000 + random.random()*1000)

        # Stop any old timer
        old = self.retry_timers.get(ack_id)
        if old:
            try: old.stop()
            except Exception: pass

        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(delay_ms)

        if a < m:
            # schedule next resend
            timer.timeout.connect(lambda aid=ack_id: self._retry_send(aid))
            next_attempt = a + 1
            self.status_label.setText(f"Waiting for ACK {ack_id}… scheduling retry {next_attempt}/{m} in {delay_ms//1000}s.")
        else:
            # a == m -> we already transmitted final attempt; schedule a final wait before fail
            timer.timeout.connect(lambda aid=ack_id: self._final_fail(aid))
            self.status_label.setText(f"Waiting for ACK {ack_id} after attempt {a}/{m}… final wait {delay_ms//1000}s.")

        self.retry_timers[ack_id] = timer
        self._rebuild_chat_view()
        timer.start()

    def _retry_send(self, ack_id: str):
        item = self.sent_by_ack.get(ack_id)
        if not item or item.get("ack"):
            return  # already done
        a = item.get("attempt") or 1
        m = item.get("max_attempts") or 3
        # resend same line
        line = item["text"]
        self._tx_gate = True
        self._ptt_guard(lambda: self._write_line(line))
        self._tx_gate = False
        # echo filter helper
        self.recent_sent.append({"full": _norm(line), "msg": _norm(_extract_msg_only(line)), "ts": time.time()})
        # bump attempt count
        item["attempt"] = a + 1
        self._rebuild_chat_view()
        # schedule next (either another resend or final wait)
        self._schedule_retry(ack_id)

    def _final_fail(self, ack_id: str):
        item = self.sent_by_ack.get(ack_id)
        if not item or item.get("ack"):
            return
        item["failed"] = True
        t = self.retry_timers.pop(ack_id, None)
        if t:
            try: t.stop()
            except Exception: pass
        self._rebuild_chat_view()
        m = item.get("max_attempts") or 3
        self.status_label.setText(f"No ACK {ack_id} after {m} attempts.")

    # -------- TX high-level --------
    def send_user_text(self, text: str) -> bool:
        try:
            if self._looks_like_console(text):
                msg = QMessageBox(); msg.setStyleSheet(MESSAGE_BOX_STYLE)
                msg.setIcon(QMessageBox.Warning); msg.setWindowTitle("Blocked")
                msg.setText("That text looks like console/device output and will not be transmitted.")
                msg.exec_(); return False
            self._tx_gate = True
            ok = self._ptt_guard(lambda: self._write_line(text))
            self._tx_gate = False
            if ok:
                self._tx_count += 1
                suffix = " | Beaconing ON (15 min)" if self.beacon_check.isChecked() else ""
                self.status_label.setText(f"TX: {self._tx_count}{suffix}")
            return ok
        except Exception as e:
            self._show_exception("Send failed", e)
            return False

    def send_message(self):
        try:
            target = self.target_edit.text().strip()
            my     = self.mycall_edit.text().strip()
            msg_tx = self.send_edit.toPlainText().strip()

            if not target:
                mb = QMessageBox(); mb.setStyleSheet(MESSAGE_BOX_STYLE)
                mb.setIcon(QMessageBox.Warning); mb.setWindowTitle("Target missing")
                mb.setText("Enter a Target callsign."); mb.exec_(); return
            if not my:
                mb = QMessageBox(); mb.setStyleSheet(MESSAGE_BOX_STYLE)
                mb.setIcon(QMessageBox.Warning); mb.setWindowTitle("MyCALL missing")
                mb.setText("Enter MyCALL in the From field."); mb.exec_(); return
            if not msg_tx: return

            # Generate ACK ID
            ack_id = _to_base36(self.ack_counter, width=4)
            self.ack_counter += 1

            msg_with_tag = f"{msg_tx} [ACK:{ack_id}]"
            line = f"{target} DE {my} {msg_with_tag}"

            self._add_chat_item(kind="sent", text=line, to=target, frm=my, ack_id=ack_id, ack=False)
            self.recent_sent.append({"full": _norm(line), "msg": _norm(msg_with_tag), "ts": time.time()})

            tx_ok = self.send_user_text(line)
            if not tx_ok:
                self.status_label.setText("Send blocked or radio not connected (message shown locally).")

            self.send_edit.clear()

        except Exception as e:
            self._show_exception("Unexpected error during Send", e)

    # -------- Save (silent) debug log --------
    def _save_debug_log(self, lines, label="TNC"):
        """Write a small debug log to the system temp folder and remember last path."""
        try:
            tmpdir = tempfile.gettempdir()
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(tmpdir, f"TTC_{label}_log_{ts}.txt")
            with open(path, "w", encoding="utf-8") as f:
                if isinstance(lines, (list, tuple)):
                    f.write("\n".join(str(x) for x in lines))
                else:
                    f.write(str(lines))
            self._last_log_path = path
            return path
        except Exception as e:
            print(f"[save_debug_log] {e!r}")
            return ""

    # -------- GPS SEND (pre-flight + silent log) --------
    def send_gps_position(self):
        if not (self.ser and self.ser.is_open):
            mb = QMessageBox(); mb.setStyleSheet(MESSAGE_BOX_STYLE)
            mb.setIcon(QMessageBox.Warning); mb.setWindowTitle("Not connected")
            mb.setText("Open a COM port first."); mb.exec_(); return

        try:
            if self.reader_thread:
                self.reader_thread.stop(); self.reader_thread = None

            full_log = ["[TNC exchange log]"]

            ok, missing, pflog, snap = self._aprs_preflight()
            full_log += ["[Pre-flight checks]"] + pflog

            if not ok:
                self._save_debug_log(full_log, label="preflight")
                mb = QMessageBox(); mb.setStyleSheet(MESSAGE_BOX_STYLE)
                mb.setIcon(QMessageBox.Critical); mb.setWindowTitle("APRS pre-flight failed")
                mb.setText("\n".join(missing)); mb.exec_()
                self.status_label.setText("APRS pre-flight failed (log saved).")
                return

            lat, lon, alt_m = self._query_tnc_position_verbose(full_log)

            self._send_cmd("%A0"); QtCore.QThread.msleep(250)
            a0 = (self._read_for_ms(600) or "").strip()
            if a0: full_log += ["[A0 ack]", a0]

            self._send_cmd("%ZS"); QtCore.QThread.msleep(250)
            zs = (self._read_for_ms(600) or "").strip()
            if zs: full_log += ["[ZS ack]", zs]

            self._save_debug_log(full_log, label="gps")

            if not (math.isnan(lat) or math.isnan(lon)):
                coord = _fmt_latlon(lat, lon)
                if coord:
                    text = f"Position GPS {coord}" if math.isnan(alt_m) else f"Position GPS {coord} ALT {int(alt_m)} m"
                    self.send_edit.setPlainText(text)
                    self.send_edit.moveCursor(QtGui.QTextCursor.End)
                    self.send_edit.setFocus()
                    self.status_label.setText("GPS position parsed.")
                    return

            self.send_edit.setPlainText("Position GPS (unavailable)")
            self.send_edit.moveCursor(QtGui.QTextCursor.End)
            self.send_edit.setFocus()
            self.status_label.setText("No GPS coordinates parsed (log saved).")

        finally:
            if self.ser and self.ser.is_open:
                self.reader_thread = SerialReaderThread(self.ser)
                self.reader_thread.line_received.connect(self._on_line)
                self.reader_thread.start()

    # -------- Misc UI helpers --------
    def _handle_callsign_click(self, url: QUrl):
        link = url.toString()
        if link.startswith("callsign:"):
            callsign = link[len("callsign:"):].strip()
            if callsign:
                self.target_edit.setText(callsign)
                self.status_label.setText(f"Set To: {callsign}")

    def _clear_receive_window(self):
        self.recv_text.clear()
        self.chat_items.clear()
        self.sent_by_ack.clear()
        # stop timers too
        for t in list(self.retry_timers.values()):
            try: t.stop()
            except Exception: pass
        self.retry_timers.clear()
        self.status_label.setText("Receive window cleared.")

    # -------- Device helpers --------
    def _read_for_ms(self, ms: int) -> str:
        buf = b''; start = QtCore.QTime.currentTime()
        while start.msecsTo(QtCore.QTime.currentTime()) < ms:
            QtCore.QThread.msleep(20)
            try:
                n = self.ser.in_waiting
                if n: buf += self.ser.read(n)
            except Exception: break
        try: return buf.decode('utf-8', errors='replace')
        except Exception: return buf.decode('latin1', errors='replace')

    def _extract_callsign(self, text: str) -> str:
        m = re.search(CALL_RE, text or "", re.I)
        return m.group(0).upper() if m else ""

    def _is_device_line(self, s: str) -> bool:
        if not s: return True
        s2 = s.strip()
        # dot-prefixed lines that are NOT valid beacons are device lines
        if s2.startswith('.') and not BEACON_RE.match(s2):
            return True
        if any(ord(ch) < 32 and ch not in ('\r','\n','\t') for ch in s2): return True
        pats = [
            r'^fm\s+\S+\s+to\s+\S+\s+ctl\b',
            r'ctl\s+UI\^?\s*pid\s+F0',
            r'^\*\s*[%@].*',
            r'^\*.*',
            r'^%[A-Za-z].*',
            r'^cmd:\s',
            r'^cmd>\s*',
            r'^(MHEARD|HEARD)\b',
            r'^(ID:|VER:|AX|KISS|RPR|BT:|RPR>)\b',
            r'^\(C\)\s',
            r'^\[MON\]',
            r'^[=\-]{3,}$',
            r'^\s*=\s*RPR><TNC.*=\s*$',
            r'AX\.25\b',
            r'SCS\s+GmbH',
            r'^\*\s*%Z[SKL].*',
            r'^\*\s*@KP\d?.*',
            r'^\*\s*X[01]\s*$',
            r'^\$(?:GP|GN|GL|GA)[A-Z]{3},',  # NMEA
        ]
        for p in pats:
            if re.search(p, s2, re.IGNORECASE): return True
        if s2.strip() in {"RPR>", "OK", "READY"}: return True
        return False

    def _looks_like_console(self, s: str) -> bool:
        return self._is_device_line(s) or bool(re.match(r'^(RPR>|OK|READY)$', s.strip(), re.I))

    def _show_exception(self, title: str, exc: Exception):
        err = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        msg = QMessageBox(); msg.setStyleSheet(MESSAGE_BOX_STYLE)
        msg.setIcon(QMessageBox.Critical); msg.setWindowTitle(title)
        msg.setText(err); msg.exec_()

# ---- VT323 font loader ----
def load_vt323_font():
    try:
        font_path = os.path.join(os.path.dirname(__file__), "VT323-Regular.ttf")
        if os.path.exists(font_path):
            fid = QtGui.QFontDatabase().addApplicationFont(font_path)
            if fid != -1:
                fams = QtGui.QFontDatabase().applicationFontFamilies(fid)
                if fams:
                    print(f"Loaded font: {fams[0]} from {font_path}")
                return True
            else:
                print("Warning: Failed to load VT323 font from file.")
        else:
            print("Warning: VT323-Regular.ttf not found in application directory.")
    except Exception as e:
        print(f"Font load error: {e!r}")
    return False

def install_excepthook():
    def handler(exc_type, exc, tb):
        err = "".join(traceback.format_exception(exc_type, exc, tb))
        try:
            print(err)
            msg = QMessageBox(); msg.setStyleSheet(MESSAGE_BOX_STYLE)
            msg.setIcon(QMessageBox.Critical); msg.setWindowTitle("Unhandled error")
            msg.setText("An unexpected error occurred.\n\n" + err[-2000:])
            msg.exec_()
        except Exception:
            pass
    sys.excepthook = handler

def main():
    print("Teensy Tracker Chat v1.2.8 ACK-RED — HOTFIX 7 (2025-09-12)")
    app = QApplication(sys.argv)
    install_excepthook()
    if not load_vt323_font():
        print("Using fallback monospace font.")
    w = ChatApp()
    w.showMaximized()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
