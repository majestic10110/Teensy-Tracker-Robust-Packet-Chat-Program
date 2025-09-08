#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Teensy Tracker Chat v0.9.8 (2025-09-08, fix-echo+clear)
Fixes in this drop:
- Stronger TX echo suppression:
  * Ignore any parsed line whose FRM == MyCALL (your own transmission).
  * Fuzzy match using normalized full line AND normalized message body
    against recently sent items inside a 3.0s echo window.
- Prevents “sent” lines being shown in orange as received.
- SEND box clears immediately on press (even if serial write fails).
- Kept all prior features/retro styling.
"""

import sys, re, time, os
from collections import deque
from datetime import datetime
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QTextEdit, QGroupBox,
    QCheckBox, QMessageBox, QStatusBar, QSizePolicy, QShortcut
)

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

# Colours for 80s retro aesthetic
COLOR_SENT = "#00FF00"     # Bright lime green for sent messages
COLOR_RECV = "#FFA500"     # Orange for received messages
COLOR_CONSOLE = "#00AA00"  # Darker green for console messages (terminal only)
COLOR_HIGHLIGHT = "#00CC00"  # Darker lime green for focused borders and hover
COLOR_BG = "#1A1A1A"       # Near-black for dark mode
COLOR_PRESSED = "#333333"  # Dark grey for pressed buttons
COLOR_TEXT = "#FFFFFF"     # White for QMessageBox text

# QMessageBox stylesheet
MESSAGE_BOX_STYLE = f"""
    QMessageBox {{
        background-color: {COLOR_BG};
        color: {COLOR_TEXT};
        font-family: VT323, monospace;
        font-size: 14pt;
    }}
    QMessageBox QLabel {{
        color: {COLOR_TEXT};
    }}
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
    QMessageBox QPushButton:hover {{
        background-color: {COLOR_HIGHLIGHT};
    }}
    QMessageBox QPushButton:pressed {{
        background-color: {COLOR_PRESSED};
    }}
"""

def safe_int(val, default):
    try: return int(val)
    except Exception: return default

def _norm(s: str) -> str:
    """Normalize for echo comparison: collapse whitespace, strip, uppercase."""
    return re.sub(r'\s+', ' ', (s or '')).strip().upper()

def _extract_msg_only(text: str) -> str:
    """Return just the message body from a 'TO DE FROM msg' line if it matches."""
    m = LINE_RE.match(text or '')
    if not m:
        return ''
    return (m.group('msg') or '').strip()

class UppercaseLineEdit(QLineEdit):
    """QLineEdit with uppercase text and retro font."""
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
            QLineEdit:focus {{
                border: 3px solid {COLOR_HIGHLIGHT};
            }}
        """)
        fm = QtGui.QFontMetrics(font)
        char_w = fm.horizontalAdvance('M')
        self.setFixedWidth(int(char_w * 11.5))
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def keyPressEvent(self, event: QtGui.QKeyEvent):
        super().keyPressEvent(event)
        self._force_upper()

    def insertFromMimeData(self, source: QtCore.QMimeData):
        text = source.text().upper() if source and source.text() else ""
        super().insert(text)

    def _force_upper(self):
        pos = self.cursorPosition()
        self.setText(self.text().upper())
        self.setCursorPosition(pos)

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
        self.setWindowTitle("Teensy Tracker Robust Packet Chat v0.9.8")
        self.resize(1140, 980)
        self.setStyleSheet(f"background: {COLOR_BG};")  # Dark mode for main window

        self.ser: Serial = None
        self.reader_thread: SerialReaderThread = None

        # Store recent transmissions (normalized)
        # each item: {"full": <norm "TO DE FROM msg">, "msg": <norm msg body>, "ts": epoch}
        self.recent_sent = deque(maxlen=24)
        self.echo_window_s = 3.0  # window for echo filtering

        self._tx_gate = False
        self._tx_count = 0

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(12)

        # Serial controls
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
        sgl = QGridLayout(ser_group)
        sgl.setHorizontalSpacing(8)
        sgl.setVerticalSpacing(8)
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
        self.baud_combo = QComboBox()
        self.baud_combo.addItems([str(x) for x in (9600,19200,38400,57600,115200,230400,460800)])
        self.baud_combo.setCurrentText("115200")
        self.baud_combo.setStyleSheet(self.port_combo.styleSheet())
        self.baud_combo.setFixedWidth(120)
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLOR_BG};
                color: {COLOR_SENT};
                font-family: VT323, monospace;
                font-size: 14pt;
                border: 2px solid {COLOR_SENT};
                border-radius: 4px;
                padding: 4px;
            }}
            QPushButton:hover {{
                background: {COLOR_HIGHLIGHT};
            }}
            QPushButton:pressed {{
                background: {COLOR_PRESSED};
            }}
        """)
        refresh_btn.setFixedWidth(168)
        refresh_btn.clicked.connect(self.refresh_ports)
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.open_port)
        self.connect_btn.setStyleSheet(refresh_btn.styleSheet())
        self.connect_btn.setFixedWidth(168)
        self.disconnect_btn = QPushButton("Disconnect")
        self.disconnect_btn.clicked.connect(self.close_port)
        self.disconnect_btn.setEnabled(False)
        self.disconnect_btn.setStyleSheet(refresh_btn.styleSheet())
        self.disconnect_btn.setFixedWidth(168)
        self.enter_kiss_btn = QPushButton("Enter KISS")
        self.enter_kiss_btn.clicked.connect(self._enter_kiss_mode)
        self.enter_kiss_btn.setStyleSheet(refresh_btn.styleSheet())
        self.enter_kiss_btn.setFixedWidth(168)
        self.enter_kiss_btn.setEnabled(False)
        button_layout.addWidget(refresh_btn)
        button_layout.addWidget(self.connect_btn)
        button_layout.addWidget(self.disconnect_btn)
        button_layout.addWidget(self.enter_kiss_btn)
        button_layout.addStretch(1)  # Center buttons within layout
        sgl.addWidget(self.port_combo, 0, 0)
        sgl.addWidget(self.baud_combo, 1, 0)
        sgl.addLayout(button_layout, 0, 1, 2, 1)
        root.addWidget(ser_group)

        # Target/MyCALL + controls
        ctl = QHBoxLayout()
        ctl.setSpacing(8)
        lbl_to = QLabel("To")
        lbl_from = QLabel("From")
        lbl_to.setStyleSheet(f"QLabel {{ color: {COLOR_SENT}; font-family: VT323, monospace; font-size: 16pt; }}")
        lbl_from.setStyleSheet(lbl_to.styleSheet())
        lbl_to.setAlignment(Qt.AlignRight)
        lbl_from.setAlignment(Qt.AlignRight)
        self.target_edit = UppercaseLineEdit()
        self.target_edit.setPlaceholderText("G4ABC-7 or CQ")
        self.mycall_edit = UppercaseLineEdit()
        self.mycall_edit.setPlaceholderText("M0OLI")
        self.load_btn = QPushButton("Load Callsign")
        self.load_btn.clicked.connect(self.load_mycall)
        self.load_btn.setStyleSheet(refresh_btn.styleSheet())
        self.load_btn.setFixedWidth(198)
        self.hide_mon_check = QCheckBox("Hide device/monitor lines")
        self.hide_mon_check.setChecked(True)
        self.hide_mon_check.setStyleSheet(f"QCheckBox {{ color: {COLOR_SENT}; font-family: VT323, monospace; font-size: 14pt; }}")
        self.kiss_perm_toggle = QCheckBox("KISS Mode (permanent)")
        self.kiss_perm_toggle.toggled.connect(self._toggle_kiss_permanent)
        self.kiss_perm_toggle.setStyleSheet(self.hide_mon_check.styleSheet())
        to_box = QHBoxLayout()
        to_box.setSpacing(4)
        to_box.addWidget(lbl_to)
        to_box.addSpacing(4)
        to_box.addWidget(self.target_edit)
        from_box = QHBoxLayout()
        from_box.setSpacing(4)
        from_box.addWidget(lbl_from)
        from_box.addSpacing(4)
        from_box.addWidget(self.mycall_edit)
        callsign_container = QWidget()
        callsign_layout = QHBoxLayout(callsign_container)
        callsign_layout.setContentsMargins(0, 0, 0, 0)
        callsign_layout.setSpacing(8)
        callsign_layout.addLayout(to_box)
        callsign_layout.addLayout(from_box)
        callsign_layout.addStretch(0)
        ctl.addWidget(callsign_container)
        ctl.addWidget(self.load_btn)
        ctl.addWidget(self.hide_mon_check)
        ctl.addWidget(self.kiss_perm_toggle)
        ctl.addStretch(1)
        root.addLayout(ctl)

        # Received section title
        recv_title = QLabel("Received Messages")
        recv_title.setStyleSheet(f"QLabel {{ color: {COLOR_SENT}; font-family: VT323, monospace; font-size: 18pt; font-weight: bold; }}")
        root.addWidget(recv_title)

        # Chat display
        self.recv_text = QTextEdit()
        self.recv_text.setReadOnly(True)
        self.recv_text.setStyleSheet(f"""
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
        self.recv_text.setMinimumSize(820, 700)
        root.addWidget(self.recv_text, 1)

        # Send section title
        send_title = QLabel("Send Message")
        send_title.setStyleSheet(recv_title.styleSheet())
        root.addWidget(send_title)

        # Send area
        send_row = QHBoxLayout()
        send_row.setSpacing(8)
        self.send_edit = QTextEdit()
        send_font = QtGui.QFont("VT323", 14)
        self.send_edit.setFont(send_font)
        self.send_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {COLOR_BG};
                color: {COLOR_SENT};
                font-family: VT323, monospace;
                border: 2px solid {COLOR_SENT};
                border-radius: 4px;
                padding: 4px;
            }}
            QTextEdit:focus {{
                border: 3px solid {COLOR_HIGHLIGHT};
            }}
        """)
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
            QPushButton:hover {{
                background: {COLOR_SENT};
            }}
            QPushButton:pressed {{
                background: {COLOR_PRESSED};
            }}
        """)
        self.send_btn.setFixedWidth(178)
        self.send_btn.clicked.connect(self.send_message)
        QShortcut(QtGui.QKeySequence("Ctrl+Return"), self, activated=self.send_message)
        QShortcut(QtGui.QKeySequence("Ctrl+Enter"), self, activated=self.send_message)
        send_row.addWidget(self.send_edit, 1)
        send_row.addWidget(self.send_btn)
        root.addLayout(send_row)

        # Status bar
        sb = QStatusBar()
        sb.setStyleSheet(f"QStatusBar {{ background: {COLOR_BG}; color: {COLOR_SENT}; font-family: VT323, monospace; font-size: 14pt; }}")
        self.setStatusBar(sb)
        self.status_label = QtWidgets.QLabel("Disconnected  |  Reminder: turn KISS OFF to chat")
        sb.addWidget(self.status_label)

        self.refresh_ports()

    def refresh_ports(self):
        self.port_combo.clear()
        try:
            if list_ports:
                ports = sorted(list_ports.comports(), key=lambda p: p.device)
                for p in ports:
                    self.port_combo.addItem(f"{p.device} — {p.description}", p.device)
            else:
                for i in range(1,21):
                    self.port_combo.addItem(f"COM{i}", f"COM{i}")
        except Exception:
            for i in range(1,21):
                self.port_combo.addItem(f"COM{i}", f"COM{i}")

    def open_port(self):
        try:
            if self.ser and self.ser.is_open:
                self.close_port()
            port = self.port_combo.currentData() or self.port_combo.currentText()
            baud = safe_int(self.baud_combo.currentText(), 115200)
            self.ser = serial.Serial(
                port=port,
                baudrate=baud,
                timeout=0.05,
                rtscts=False,
                dsrdtr=False
            )
            self.reader_thread = SerialReaderThread(self.ser)
            self.reader_thread.line_received.connect(self._on_line)
            self.reader_thread.start()
            self.connect_btn.setText("Connected...")
            self.connect_btn.setEnabled(False)
            self.disconnect_btn.setEnabled(True)
            self.enter_kiss_btn.setEnabled(True)
            self.status_label.setText(f"Connected {port} @ {baud}  |  Reminder: turn KISS OFF to chat")
        except Exception as e:
            msg = QMessageBox()
            msg.setStyleSheet(MESSAGE_BOX_STYLE)
            msg.setIcon(QMessageBox.Critical)
            msg.setWindowTitle("Serial error")
            msg.setText(f"Failed to open port.\n{e}")
            msg.exec_()
            self.status_label.setText("Disconnected  |  Reminder: turn KISS OFF to chat")

    def close_port(self):
        try:
            if self.reader_thread:
                self.reader_thread.stop()
                self.reader_thread = None
            if self.ser:
                self.ser.close()
                self.ser = None
        finally:
            self.connect_btn.setText("Connect")
            self.connect_btn.setEnabled(True)
            self.disconnect_btn.setEnabled(False)
            self.enter_kiss_btn.setEnabled(False)
            self.status_label.setText("Disconnected  |  Reminder: turn KISS OFF to chat")

    def _write_raw(self, data: bytes):
        if not (self.ser and self.ser.is_open):
            msg = QMessageBox()
            msg.setStyleSheet(MESSAGE_BOX_STYLE)
            msg.setIcon(QMessageBox.Warning)
            msg.setWindowTitle("Not connected")
            msg.setText("Open a COM port first.")
            msg.exec_()
            return False
        try:
            self.ser.write(data)
            return True
        except Exception as e:
            msg = QMessageBox()
            msg.setStyleSheet(MESSAGE_BOX_STYLE)
            msg.setIcon(QMessageBox.Critical)
            msg.setWindowTitle("Write error")
            msg.setText(str(e))
            msg.exec_()
            return False

    def _send_cmd(self, cmd: str):
        return self._write_raw(ESC + (cmd + "\r").encode("utf-8", errors="replace"))

    def _write_line(self, text: str):
        if not self._tx_gate:
            return False
        return self._write_raw((text + "\r").encode("utf-8", errors="replace"))

    def _ptt_guard(self, func):
        try:
            self._send_cmd("X0")
            QtCore.QThread.msleep(80)
        except Exception:
            pass
        try:
            func()
        finally:
            try:
                QtCore.QThread.msleep(80)
                self._send_cmd("X1")
            except Exception:
                pass

    def _enter_kiss_mode(self):
        self._send_cmd("@K")
        QtCore.QThread.msleep(120)
        self._send_cmd("%ZS")
        msg = QMessageBox()
        msg.setStyleSheet(MESSAGE_BOX_STYLE)
        msg.setIcon(QMessageBox.Information)
        msg.setWindowTitle("Entered KISS")
        msg.setText("Entered KISS MODE (@K) and saved with %ZS.\nTo chat again, turn KISS OFF.")
        msg.exec_()
        self.status_label.setText("Entered KISS MODE (@K). Chat requires KISS OFF.")

    def _toggle_kiss_permanent(self, on: bool):
        if on:
            self._send_cmd("@KP1")
            QtCore.QThread.msleep(80)
            self._send_cmd("%ZS")
            self.status_label.setText("KISS Permanent ENABLED (@KP1), saved. Chat requires KISS OFF.")
            msg = QMessageBox()
            msg.setStyleSheet(MESSAGE_BOX_STYLE)
            msg.setIcon(QMessageBox.Question)
            msg.setWindowTitle("Enter KISS now?")
            msg.setText("KISS Permanent is ON and saved.\nDo you also want to ENTER KISS MODE now (@K then %ZS)?")
            msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            msg.setDefaultButton(QMessageBox.No)
            resp = msg.exec_()
            if resp == QMessageBox.Yes:
                self._send_cmd("@K")
                QtCore.QThread.msleep(120)
                self._send_cmd("%ZS")
                msg = QMessageBox()
                msg.setStyleSheet(MESSAGE_BOX_STYLE)
                msg.setIcon(QMessageBox.Information)
                msg.setWindowTitle("Entered KISS")
                msg.setText("Entered KISS MODE (@K) and saved with %ZS.\nTo chat again, turn KISS OFF.")
                msg.exec_()
                self.status_label.setText("Entered KISS MODE (@K). Chat requires KISS OFF.")
        else:
            self._send_cmd("@KP0")
            QtCore.QThread.msleep(80)
            self._send_cmd("%ZS")
            QtCore.QThread.msleep(120)
            self._write_raw(bytes([192,255,192,13]))
            self.status_label.setText("KISS disabled (@KP0) & saved; Exit KISS bytes sent. Ready for chat.")
            msg = QMessageBox()
            msg.setStyleSheet(MESSAGE_BOX_STYLE)
            msg.setIcon(QMessageBox.Information)
            msg.setWindowTitle("KISS OFF")
            msg.setText("KISS disabled (@KP0), saved with %ZS, and exit bytes sent.\nReady for chat.")
            msg.exec_()

    def _on_line(self, line: str):
        # strip leading timestamp we add in reader thread
        content = re.sub(r'^\[\d{2}:\d{2}:\d{2}\]\s*', '', line or '').strip()

        # Filter device/console lines (optionally print to terminal)
        if self._is_device_line(content) or self._looks_like_console(content):
            if not self.hide_mon_check.isChecked():
                print(f"Device/Console: {content}")
            return

        now = time.time()
        norm_in_full = _norm(content)
        norm_in_msg  = _norm(_extract_msg_only(content))

        # If it parses as a chat line, check FRM against MyCALL and echo cache
        m = LINE_RE.match(content)
        if m:
            to  = (m.group('to')  or '').upper()
            frm = (m.group('frm') or '').upper()
            msg = (m.group('msg') or '').strip()

            # 1) If the FRM equals our MyCALL, it's our own transmission: suppress.
            my = (self.mycall_edit.text() or '').upper().strip()
            if my and frm == my:
                # Still keep terminal note for debugging if desired
                print(f"Echo from self suppressed: {content}")
                return

            # 2) Echo cache (full or message-only match within window)
            for item in list(self.recent_sent):
                if now - item["ts"] <= self.echo_window_s:
                    if norm_in_full == item["full"] or (norm_in_msg and norm_in_msg == item["msg"]):
                        print(f"Echo filtered (match recent): {content}")
                        return

            # Not an echo: render as received (orange)
            norm = f"{to} DE {frm}" + (f" {msg}" if msg else "")
            self._append_chat_line(norm, kind="received")
            return

        # Non-standard but not a device line—try echo cache on content as-is
        for item in list(self.recent_sent):
            if now - item["ts"] <= self.echo_window_s and norm_in_full == item["full"]:
                print(f"Echo filtered (loose): {content}")
                return

        self._append_chat_line(content, kind="received")

    def _is_device_line(self, s: str) -> bool:
        if not s:
            return True
        if any(ord(ch) < 32 and ch not in ('\r','\n','\t') for ch in s):
            return True
        pats = [
            r'^fm\s+\S+\s+to\s+\S+\s+ctl\b',
            r'ctl\s+UI\^?\s*pid\s+F0',
            r'^\*\s*[%@].*',
            r'^%[A-Za-z].*',
            r'^cmd:\s',
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
        ]
        for p in pats:
            if re.search(p, s, re.IGNORECASE):
                return True
        if s.strip() in {"RPR>", "OK", "READY"}:
            return True
        return False

    def _looks_like_console(self, s: str) -> bool:
        return self._is_device_line(s) or bool(re.match(r'^(RPR>|OK|READY)$', s.strip(), re.I))

    def send_user_text(self, text: str) -> bool:
        if self._looks_like_console(text):
            msg = QMessageBox()
            msg.setStyleSheet(MESSAGE_BOX_STYLE)
            msg.setIcon(QMessageBox.Warning)
            msg.setWindowTitle("Blocked")
            msg.setText("That text looks like console/device output and will not be transmitted.")
            msg.exec_()
            return False
        self._tx_gate = True
        ok = self._ptt_guard(lambda: self._write_line(text))
        self._tx_gate = False
        if ok:
            self._tx_count += 1
            self.status_label.setText(
                f"TX: {self._tx_count}  |  Connected" if self.connect_btn.isEnabled()==False else f"TX: {self._tx_count}"
            )
        return ok

    def send_message(self):
        target = self.target_edit.text().strip()
        my = self.mycall_edit.text().strip()
        msg_text = self.send_edit.toPlainText().strip()

        if not target:
            mb = QMessageBox()
            mb.setStyleSheet(MESSAGE_BOX_STYLE)
            mb.setIcon(QMessageBox.Warning)
            mb.setWindowTitle("Target missing")
            mb.setText("Enter a Target callsign.")
            mb.exec_()
            return
        if not my:
            mb = QMessageBox()
            mb.setStyleSheet(MESSAGE_BOX_STYLE)
            mb.setIcon(QMessageBox.Warning)
            mb.setWindowTitle("MyCALL missing")
            mb.setText("Enter MyCALL or click Load Callsign.")
            mb.exec_()
            return
        if not msg_text:
            return

        line = f"{target} DE {my} {msg_text}"

        # ✅ Clear the send box immediately on press
        self.send_edit.clear()

        # Transmit
        ok = self.send_user_text(line)

        # Record in echo cache regardless, so any immediate loopback is suppressed
        self.recent_sent.append({
            "full": _norm(line),
            "msg": _norm(msg_text),
            "ts": time.time()
        })

        # Show as SENT (green) in the chat window even if radio doesn't echo
        self._append_chat_line(line, kind="sent")

        # Ensure scroll to bottom
        self.recv_text.verticalScrollBar().setValue(self.recv_text.verticalScrollBar().maximum())

    def _append_chat_line(self, text: str, kind: str):
        color = COLOR_SENT if kind == "sent" else COLOR_RECV
        text_esc = text.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
        html = f'<span style="color:{color}; font-family:VT323,monospace">{text_esc}</span><br>'
        self.recv_text.moveCursor(QtGui.QTextCursor.End)
        self.recv_text.insertHtml(html)
        self.recv_text.moveCursor(QtGui.QTextCursor.End)

    def load_mycall(self):
        if not (self.ser and self.ser.is_open):
            msg = QMessageBox()
            msg.setStyleSheet(MESSAGE_BOX_STYLE)
            msg.setIcon(QMessageBox.Warning)
            msg.setWindowTitle("Not connected")
            msg.setText("Open a COM port first.")
            msg.exec_()
            return
        try:
            if self.reader_thread:
                self.reader_thread.stop()
                self.reader_thread = None
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            self._send_cmd("%ZL")
            QtCore.QThread.msleep(200)
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
                msg = QMessageBox()
                msg.setStyleSheet(MESSAGE_BOX_STYLE)
                msg.setIcon(QMessageBox.Information)
                msg.setWindowTitle("Load Callsign")
                msg.setText("No callsign found.")
                msg.exec_()
        except Exception as e:
            msg = QMessageBox()
            msg.setStyleSheet(MESSAGE_BOX_STYLE)
            msg.setIcon(QMessageBox.Critical)
            msg.setWindowTitle("Load Callsign")
            msg.setText(str(e))
            msg.exec_()
        finally:
            if self.ser and self.ser.is_open:
                self.reader_thread = SerialReaderThread(self.ser)
                self.reader_thread.line_received.connect(self._on_line)
                self.reader_thread.start()

    def _read_for_ms(self, ms: int) -> str:
        buf = b''
        start = QtCore.QTime.currentTime()
        while start.msecsTo(QtCore.QTime.currentTime()) < ms:
            QtCore.QThread.msleep(20)
            try:
                n = self.ser.in_waiting
                if n:
                    buf += self.ser.read(n)
            except Exception:
                break
        try:
            return buf.decode('utf-8', errors='replace')
        except Exception:
            return buf.decode('latin1', errors='replace')

    def _extract_callsign(self, text: str) -> str:
        m = re.search(CALL_RE, text, re.I)
        return m.group(0).upper() if m else ""

def load_vt323_font():
    """Load VT323 font from the application directory or use fallback."""
    font_path = os.path.join(os.path.dirname(__file__), "VT323-Regular.ttf")
    if os.path.exists(font_path):
        font_id = QtGui.QFontDatabase().addApplicationFont(font_path)
        if font_id != -1:
            return True
        else:
            print("Warning: Failed to load VT323 font from file.")
    else:
        print("Warning: VT323-Regular.ttf not found in application directory.")
    return False

def main():
    print("Teensy Tracker Chat v0.9.8 (2025-09-08)")
    app = QApplication(sys.argv)
    if not load_vt323_font():
        print("Using fallback monospace font.")
    w = ChatApp()
    w.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
