#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Teensy Tracker Chat v0.9.11 (2025-09-07)
Changes:
4) Extra-hardening: KISS toggle actions are wrapped with PTT guard (ESC X0 ... ESC X1),
   so unchecking KISS never keys TX. Only the Send box transmits.
5) Added titles above panes: "Received Messages" and "Send Message".
"""

import sys, re, time
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

# Colours
COLOR_SENT = "#32CD32"     # lime
COLOR_RECV = "#FFA500"     # orange
COLOR_CONSOLE = "#40E0D0"  # turquoise

def safe_int(val, default):
    try: return int(val)
    except Exception: return default

class UppercaseLineEdit(QLineEdit):
    """QLineEdit that forces uppercase and uses a larger monospace font and fixed width (~10 chars)."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        font = QtGui.QFont("Consolas")
        font.setPointSize(14)
        self.setFont(font)
        self.setMaxLength(10)
        self.setAlignment(Qt.AlignCenter)  # centered text
        self.setStyleSheet("QLineEdit { background:#000; color:#32CD32; font-family:Consolas,monospace; }")
        # Cap visual width to ~10 characters
        fm = QtGui.QFontMetrics(font)
        char_w = fm.horizontalAdvance('M')
        self.setFixedWidth(int(char_w * 11.5))  # 10 chars + padding
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
                    # split on newline types
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
        self.setWindowTitle("Teensy Tracker Robust Packet Chat v0.9.11")
        self.resize(1140, 980)

        self.ser: Serial = None
        self.reader_thread: SerialReaderThread = None

        # Echo suppression buffer to avoid showing our own sent lines as received
        self.recent_sent = deque(maxlen=12)  # (text, timestamp)
        self.echo_window_s = 1.8

        # TX safety gate: only allow _write_line when set by send_user_text
        self._tx_gate = False
        self._tx_count = 0

        central = QWidget(); self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # Serial controls
        ser_group = QGroupBox("Serial")
        sgl = QGridLayout(ser_group)
        self.port_combo = QComboBox()
        self.baud_combo = QComboBox(); self.baud_combo.addItems([str(x) for x in (9600,19200,38400,57600,115200,230400,460800)]); self.baud_combo.setCurrentText("115200")
        refresh_btn = QPushButton("Refresh"); refresh_btn.clicked.connect(self.refresh_ports)
        self.connect_btn = QPushButton("Connect"); self.connect_btn.clicked.connect(self.open_port)
        self.disconnect_btn = QPushButton("Disconnect"); self.disconnect_btn.clicked.connect(self.close_port); self.disconnect_btn.setEnabled(False)
        sgl.addWidget(QLabel("Port"), 0,0); sgl.addWidget(self.port_combo, 0,1); sgl.addWidget(refresh_btn, 0,2)
        sgl.addWidget(QLabel("Baud"), 1,0); sgl.addWidget(self.baud_combo, 1,1); sgl.addWidget(self.connect_btn, 1,2); sgl.addWidget(self.disconnect_btn, 1,3)
        root.addWidget(ser_group)

        # Target/MyCALL + controls
        ctl = QHBoxLayout()
        lbl_to = QLabel("To")
        lbl_from = QLabel("From")
        self.target_edit = UppercaseLineEdit(); self.target_edit.setPlaceholderText("G4ABC-7 or CQ")
        self.mycall_edit = UppercaseLineEdit(); self.mycall_edit.setPlaceholderText("M0OLI")
        self.load_btn = QPushButton("Load Callsign"); self.load_btn.clicked.connect(self.load_mycall)
        self.hide_mon_check = QCheckBox("Hide device/monitor lines"); self.hide_mon_check.setChecked(True)
        self.kiss_perm_toggle = QCheckBox("KISS Mode (permanent)"); self.kiss_perm_toggle.toggled.connect(self._toggle_kiss_permanent)
        # Tight grouping: label next to field
        to_box = QHBoxLayout(); to_box.addWidget(lbl_to); to_box.addWidget(self.target_edit)
        from_box = QHBoxLayout(); from_box.addWidget(lbl_from); from_box.addWidget(self.mycall_edit)
        left = QHBoxLayout(); left.addLayout(to_box); left.addSpacing(16); left.addLayout(from_box)
        ctl.addLayout(left, 1)
        ctl.addSpacing(16)
        ctl.addWidget(self.load_btn); ctl.addWidget(self.hide_mon_check); ctl.addWidget(self.kiss_perm_toggle)
        root.addLayout(ctl)

        # Received section title
        recv_title = QLabel("Received Messages")
        recv_title.setStyleSheet("QLabel { color:#32CD32; font-weight:600; }")
        root.addWidget(recv_title)

        # Chat display
        self.recv_text = QTextEdit(); self.recv_text.setReadOnly(True)
        self.recv_text.setStyleSheet("QTextEdit { background: #000; color: #32CD32; font-family: Consolas, monospace; font-size: 12pt; }")
        self.recv_text.setMinimumSize(820, 700)
        root.addWidget(self.recv_text, 1)

        # Send section title
        send_title = QLabel("Send Message")
        send_title.setStyleSheet("QLabel { color:#32CD32; font-weight:600; }")
        root.addWidget(send_title)

        # Send area: 3-line QTextEdit + larger red SEND button
        send_row = QHBoxLayout()
        self.send_edit = QTextEdit()
        send_font = QtGui.QFont("Consolas"); send_font.setPointSize(12)  # match output font
        self.send_edit.setFont(send_font)
        self.send_edit.setStyleSheet("QTextEdit { background:#000; color:#32CD32; font-family:Consolas,monospace; }")
        # Approx 3 lines tall
        fm = QtGui.QFontMetrics(send_font)
        self.send_edit.setFixedHeight(fm.lineSpacing() * 3 + 16)
        # Red SEND button
        self.send_btn = QPushButton("SEND")
        self.send_btn.setStyleSheet("QPushButton { background:#C00000; color:white; font-weight:bold; }"
                                    "QPushButton:hover { background:#D02020; }"
                                    "QPushButton:pressed { background:#A00000; }")
        # Make it ~50% larger than a default button
        self.send_btn.setMinimumHeight(44)
        self.send_btn.setMinimumWidth(130)
        self.send_btn.clicked.connect(self.send_message)
        # Shortcut: Ctrl+Enter to send
        QShortcut(QtGui.QKeySequence("Ctrl+Return"), self, activated=self.send_message)
        QShortcut(QtGui.QKeySequence("Ctrl+Enter"), self, activated=self.send_message)

        send_row.addWidget(self.send_edit, 1); send_row.addWidget(self.send_btn)
        root.addLayout(send_row)

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
            self.connect_btn.setEnabled(False); self.disconnect_btn.setEnabled(True)
            self.status_label.setText(f"Connected {port} @ {baud}  |  Reminder: turn KISS OFF to chat")
        except Exception as e:
            QMessageBox.critical(self, "Serial error", f"Failed to open port.\n{e}")
            self.status_label.setText("Disconnected  |  Reminder: turn KISS OFF to chat")

    def close_port(self):
        try:
            if self.reader_thread:
                self.reader_thread.stop(); self.reader_thread = None
            if self.ser:
                self.ser.close(); self.ser = None
        finally:
            self.connect_btn.setEnabled(True); self.disconnect_btn.setEnabled(False)
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
        # ESC-prefixed console command, never RF user payload
        return self._write_raw(ESC + (cmd + "\r").encode("utf-8", errors="replace"))

    def _write_line(self, text: str):
        # Only allowed when _tx_gate is True (set by send_user_text)
        if not self._tx_gate:
            return False
        return self._write_raw((text + "\r").encode("utf-8", errors="replace"))

    # ---------- KISS controls (PTT-guarded) ----------
    def _ptt_guard(self, func):
        """Run console operations with PTT disabled (ESC X0 ... ESC X1)."""
        try:
            self._send_cmd("X0")   # PTT off
            QtCore.QThread.msleep(80)
        except Exception:
            pass
        try:
            func()
        finally:
            try:
                QtCore.QThread.msleep(80)
                self._send_cmd("X1")  # PTT on
            except Exception:
                pass

    def _toggle_kiss_permanent(self, on: bool):
        if on:
            def do_on():
                # Permanently enable KISS, then save. Offer to enter KISS now too.
                self._send_cmd("@KP1")
                QtCore.QThread.msleep(80)
                self._send_cmd("%ZS")
                self.status_label.setText("KISS Permanent ENABLED (@KP1), saved. Chat requires KISS OFF.")
                resp = QMessageBox.question(self, "Enter KISS now?",
                                            "KISS Permanent is ON and saved.\nDo you also want to ENTER KISS MODE now (@K then %ZS)?",
                                            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if resp == QMessageBox.Yes:
                    self._send_cmd("@K")
                    QtCore.QThread.msleep(120)
                    self._send_cmd("%ZS")
                    QMessageBox.information(self, "Entered KISS", "Entered KISS MODE (@K) and saved with %ZS.\nTo chat again, turn KISS OFF.")
            self._ptt_guard(do_on)
        else:
            def do_off():
                # Disable permanent KISS, save, and force immediate exit (raw bytes).
                self._send_cmd("@KP0")
                QtCore.QThread.msleep(80)
                self._send_cmd("%ZS")
                QtCore.QThread.msleep(120)
                self._write_raw(bytes([192,255,192,13]))  # C0 FF C0 0D
                self.status_label.setText("KISS disabled (@KP0) & saved; Exit KISS bytes sent. Ready for chat.")
                QMessageBox.information(self, "KISS OFF", "KISS disabled (@KP0), saved with %ZS, and exit bytes sent.\nReady for chat.")
            self._ptt_guard(do_off)

    # ---------- Incoming handling ----------
    def _on_line(self, line: str):
        # Remove timestamp before logic
        content = re.sub(r'^\[\d{2}:\d{2}:\d{2}\]\s*', '', line).strip()

        # Console/device line?
        is_console = self._is_device_line(content)

        # If hide is ON and this is console output -> drop it entirely
        if self.hide_mon_check.isChecked() and is_console:
            return

        # Echo suppression of our just-sent line (only for non-console)
        if not is_console:
            now = time.time()
            for txt, ts in list(self.recent_sent):
                if now - ts <= self.echo_window_s and content.strip() == txt.strip():
                    return

        # Parse "<TO> DE <FROM> <msg>" including "CQ DE <FROM>" (only for non-console)
        if not is_console:
            m = LINE_RE.match(content)
            if m:
                to = m.group('to').upper()
                frm = m.group('frm').upper()
                msg = m.group('msg').strip()
                norm = f"{to} DE {frm}" + (f" {msg}" if msg else "")
                self._append_chat_line(norm, kind="received")
                return
            # Fallback: plain message
            self._append_chat_line(content, kind="received")
            return

        # Show console line (when not hidden)
        self._append_chat_line(content, kind="console")

    def _is_device_line(self, s: str) -> bool:
        """Heuristics for console/device lines that are not user chat."""
        if not s:
            return True
        # Any control chars (besides CR/LF/TAB) -> treat as console noise
        if any(ord(ch) < 32 and ch not in ('\r','\n','\t') for ch in s):
            return True
        # Common console/monitor formats
        pats = [
            r'^fm\s+\S+\s+to\s+\S+\s+ctl\b',      # monitor frames
            r'ctl\s+UI\^?\s*pid\s+F0',            # explicit control UI pid line
            r'^\*\s*[%@].*',                      # "* %..." or "* @..."
            r'^%[A-Za-z].*',                      # raw ESC echoes
            r'^cmd:\s',                           # "cmd: "
            r'^(MHEARD|HEARD)\b',
            r'^(ID:|VER:|AX|KISS|RPR|BT:|RPR>)\b',
            r'^\(C\)\s',
            r'^\[MON\]',
            r'^[=\-]{3,}$',                       # banners/separators
            r'^\s*=\s*RPR><TNC.*=\s*$',           # "= RPR><TNC V... ="
            r'AX\.25\b',                          # AX.25 banners
            r'SCS\s+GmbH',                        # vendor banner
            r'^\*\s*%Z[SKL].*',                   # echoed save/load/reset
            r'^\*\s*@KP\d?.*',                    # echoed @KP lines
        ]
        for p in pats:
            if re.search(p, s, re.IGNORECASE):
                return True
        # Lone prompts or short tokens or 'busy' UI artifacts
        if s.strip() in {"RPR>", "OK", "READY"}:
            return True
        return False

    # ---------- Outgoing ----------
    def _looks_like_console(self, s: str) -> bool:
        # Reuse console heuristic for outgoing safety check
        return self._is_device_line(s) or bool(re.match(r'^(RPR>|OK|READY)$', s.strip(), re.I))

    def send_user_text(self, text: str) -> bool:
        """Only path that is allowed to send over RF."""
        # Safety: refuse if it looks like console/prompt
        if self._looks_like_console(text):
            QMessageBox.warning(self, "Blocked", "That text looks like console/device output and will not be transmitted.")
            return False
        # Open TX gate, send, then close
        self._tx_gate = True
        ok = self._write_line(text)
        self._tx_gate = False
        if ok:
            self._tx_count += 1
            self.status_label.setText(f"TX: {self._tx_count}  |  Connected" if self.connect_btn.isEnabled()==False else f"TX: {self._tx_count}")
        return ok

    def send_message(self):
        target = self.target_edit.text().strip()
        my = self.mycall_edit.text().strip()
        msg = self.send_edit.toPlainText().strip()
        if not target:
            QMessageBox.warning(self, "Target missing", "Enter a Target callsign."); return
        if not my:
            QMessageBox.warning(self, "MyCALL missing", "Enter MyCALL or click Load Callsign."); return
        if not msg:
            return
        line = f"{target} DE {my} {msg}"
        if self.send_user_text(line):
            self.recent_sent.append((line, time.time()))
            self._append_chat_line(line, kind="sent")
            self.send_edit.clear()

    # ---------- Utilities ----------
    def _append_chat_line(self, text: str, kind: str):
        """Append styled line to chat. kind in {'sent','received','console'}"""
        if kind == "sent":
            color = COLOR_SENT
        elif kind == "console":
            color = COLOR_CONSOLE
        else:
            color = COLOR_RECV
        # escape basic HTML chars
        text_esc = (text.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;"))
        html = f'<span style="color:{color}">{text_esc}</span><br>'
        self.recv_text.moveCursor(QtGui.QTextCursor.End)
        self.recv_text.insertHtml(html)
        self.recv_text.moveCursor(QtGui.QTextCursor.End)

    def load_mycall(self):
        if not (self.ser and self.ser.is_open):
            QMessageBox.warning(self, "Not connected", "Open a COM port first."); return
        try:
            if self.reader_thread:
                self.reader_thread.stop(); self.reader_thread = None
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

def main():
    print("Teensy Tracker Chat v0.9.11 (2025-09-07)")
    app = QApplication(sys.argv)
    w = ChatApp(); w.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
