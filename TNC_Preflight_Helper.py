#!/usr/bin/env python3
import sys
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QLabel, QPushButton, QComboBox,
    QHBoxLayout, QVBoxLayout, QGroupBox, QListWidget, QListWidgetItem,
    QMessageBox, QCheckBox, QWidget, QLineEdit
)
import serial
from serial.tools import list_ports

ESC = b"\x1b"
CR  = b"\r"

def list_serial_ports():
    ports = []
    for p in list_ports.comports():
        name = f"{p.device} - {p.description}" if p.description else p.device
        ports.append((p.device, name))
    return ports

class PreflightWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TNC Preflight Helper")
        self.resize(720, 460)
        self.ser = None
        self._connected = False
        self._running = False
        self._canceled = False

        # --- Serial Port group ---
        top = QGroupBox("Serial Port")
        hl = QHBoxLayout(top)

        self.port_box = QComboBox()
        self.refresh_btn = QPushButton("Refresh")
        self.baud_box = QComboBox()
        self.baud_box.addItems(["9600","19200","38400","57600","115200"])
        self.baud_box.setCurrentText("38400")
        self.call_edit = QLineEdit()
        self.call_edit.setPlaceholderText("MYCALL (e.g. M0OLI)")
        self.call_edit.setMaxLength(9)  # basecall up to 6, optional -SSID; we'll strip SSID before use
        self.connect_btn = QPushButton("Open Port")

        hl.addWidget(QLabel("Port:"))
        hl.addWidget(self.port_box, 1)
        hl.addWidget(self.refresh_btn)
        hl.addSpacing(12)
        hl.addWidget(QLabel("Baud:"))
        hl.addWidget(self.baud_box)
        hl.addSpacing(12)
        hl.addWidget(QLabel("MyCall:"))
        hl.addWidget(self.call_edit)
        hl.addSpacing(12)
        hl.addWidget(self.connect_btn)

        # --- Checklist group ---
        mid = QGroupBox("Preflight Checklist")
        mv = QVBoxLayout(mid)
        self.steps_list = QListWidget()
        self._step_texts = [
            "PTT OFF (ESC X 0)",
            "Exit KISS (C0 FF C0 0D)",
            "Set Mode RPR R300 (ESC %B R300)",
            "Set Center 1500 Hz (ESC %L 1500)",
            "Set TXDelay 700 ms (ESC T 70)",
            "Set TX Tail 50 ms (ESC %N 5)",
            "Monitor ON filtered (ESC MIUSC - MYCALL)",
            "Echo OFF (ESC E0)",
            "Store Settings (ESC %ZS)",
            "PTT ON (ESC X 1)",
        ]
        for t in self._step_texts:
            self.steps_list.addItem(QListWidgetItem("• " + t + " …"))
        mv.addWidget(self.steps_list)

        # --- Actions group ---
        bot = QGroupBox("Actions")
        bl = QHBoxLayout(bot)
        self.ptt_guard = QCheckBox("Force PTT OFF before start")
        self.ptt_guard.setChecked(True)
        self.start_btn = QPushButton("Start Preflight")
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        bl.addWidget(self.ptt_guard)
        bl.addStretch(1)
        bl.addWidget(self.start_btn)
        bl.addWidget(self.cancel_btn)

        # --- Status ---
        self.status = QLabel("Select port and press Open Port.")
        self.status.setWordWrap(True)

        # --- Main layout ---
        cw = QWidget()
        lay = QVBoxLayout(cw)
        lay.addWidget(top)
        lay.addWidget(mid, 1)
        lay.addWidget(bot)
        lay.addWidget(self.status)
        self.setCentralWidget(cw)

        # Wire up
        self.refresh_btn.clicked.connect(self._refresh_ports)
        self.connect_btn.clicked.connect(self._toggle_port)
        self.start_btn.clicked.connect(self._start_preflight)
        self.cancel_btn.clicked.connect(self._cancel_preflight)

        self._refresh_ports()

    # ---------- Serial helpers ----------
    def _refresh_ports(self):
        self.port_box.clear()
        for dev, name in list_serial_ports():
            self.port_box.addItem(name, dev)

    def _open_serial(self, port, baud):
        try:
            self.ser = serial.Serial(port, baudrate=baud, timeout=0.2)
            self._connected = True
            return True
        except Exception as e:
            QMessageBox.critical(self, "Serial Error", f"Could not open {port} @ {baud}:\n{e}")
            self._connected = False
            self.ser = None
            return False

    def _close_serial(self):
        try:
            if self.ser:
                self.ser.close()
        finally:
            self.ser = None
            self._connected = False

    def _serial_write(self, b):
        if not (self.ser and self._connected):
            return
        try:
            self.ser.write(b)
            self.ser.flush()
        except Exception as e:
            QMessageBox.critical(self, "Serial Error", f"Write failed:\n{e}")
            self._close_serial()

    # ---------- Buttons ----------
    def _toggle_port(self):
        if not self._connected:
            idx = self.port_box.currentIndex()
            port = self.port_box.itemData(idx)
            if not port:
                QMessageBox.warning(self, "Port", "Please select a serial port.")
                return
            try:
                baud = int(self.baud_box.currentText())
            except Exception:
                baud = 38400
            if self._open_serial(port, baud):
                self.connect_btn.setText("Close Port")
                self.status.setText(f"Connected to {port} @ {baud}.")
        else:
            self._close_serial()
            self.connect_btn.setText("Open Port")
            self.status.setText("Port closed.")

    def _start_preflight(self):
        if not (self._connected and self.ser):
            QMessageBox.information(self, "Port", "Open a serial port first.")
            return
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.status.setText("Running preflight…")
        self.steps_list.clear()
        for t in self._step_texts:
            self.steps_list.addItem(QListWidgetItem("• " + t + " …"))

        
        steps = []
        if self.ptt_guard.isChecked():
            steps.append((lambda: self._send_cmd("X 0", esc=True), 0))

        steps += [
            (lambda: self._kiss_exit_bytes(), 1),
            (lambda: self._send_cmd("%B R300", esc=True), 2),
            (lambda: self._send_cmd("%L 1500", esc=True), 3),
            (lambda: self._send_cmd("T 70", esc=True), 4),
            (lambda: self._send_cmd("%N 5", esc=True), 5),
            (lambda: self._send_monitor_cmd(), 6),
            (lambda: self._send_cmd("E0", esc=True), 7),
            (lambda: self._send_cmd("%ZS", esc=True), 8),
            (lambda: self._send_cmd("X 1", esc=True), 9),
        ]
        self._run_steps_with_timer(steps, 900)
    

    def _cancel_preflight(self):
        self._canceled = True
        self._running = False
        self.cancel_btn.setEnabled(False)
        self.start_btn.setEnabled(True)
        self.status.setText("Canceled.")

    def _kiss_exit_bytes(self):
        self._serial_write(bytes([0xC0, 0xFF, 0xC0, 0x0D]))

    def _send_monitor_cmd(self):
        # Build MIUSC with optional negative filter for own call
        base = self.call_edit.text().strip().upper()
        if '-' in base:
            base = base.split('-')[0]
        base = ''.join(ch for ch in base if ch.isalnum())[:6]
        cmd = "MIUSC" + (f" - {base}" if base else "")
        self._send_cmd(cmd, esc=True)

    def _send_cmd(self, cmd, esc=False):
        payload = (ESC if esc else b"") + cmd.encode("ascii", "ignore") + CR
        self._serial_write(payload)

    def _run_steps_with_timer(self, steps, delay):
        def _do(i=0):
            if self._canceled or not self._connected or not self.ser:
                self._running = False
                self.cancel_btn.setEnabled(False)
                self.start_btn.setEnabled(True)
                return
            if i >= len(steps):
                self._running = False
                self.cancel_btn.setEnabled(False)
                self.start_btn.setEnabled(True)
                self.status.setText("Preflight complete.")
                # Mark all steps as done
                self.steps_list.clear()
                for t in self._step_texts:
                    self.steps_list.addItem(QListWidgetItem("✓ " + t))
                return
            fn, idx = steps[i]
            try:
                fn()
                self._mark_step(idx, True)
            except Exception:
                self._mark_step(idx, False)
            QTimer.singleShot(delay, lambda: _do(i+1))
        _do(0)

    def _mark_step(self, idx, ok=True):
        # Update the list row to show success/fail
        try:
            item = self.steps_list.item(idx)
            base = self._step_texts[idx]
            item.setText(("✓ " if ok else "✗ ") + base)
        except Exception:
            pass

def main():
    app = QApplication(sys.argv)
    w = PreflightWindow()
    w.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
