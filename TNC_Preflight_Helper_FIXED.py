#!/usr/bin/env python3
# TNC_Preflight_Helper_FIXED.py
# GUI preflight sequence for Teensy/LiNK500 TNC.
# Runs a 7-step quiet setup over serial safely before starting your main chat app.

import sys
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QLabel, QPushButton, QComboBox,
    QHBoxLayout, QVBoxLayout, QGroupBox, QListWidget, QListWidgetItem,
    QMessageBox, QCheckBox, QWidget
)
import serial
from serial.tools import list_ports

ESC = b"\x1b"
CR  = b"\x0d"

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
        self.resize(640, 420)
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
        self.baud_box.setCurrentText("115200")
        self.connect_btn = QPushButton("Open Port")

        hl.addWidget(QLabel("Port:"))
        hl.addWidget(self.port_box, 1)
        hl.addWidget(self.refresh_btn)
        hl.addSpacing(12)
        hl.addWidget(QLabel("Baud:"))
        hl.addWidget(self.baud_box)
        hl.addSpacing(12)
        hl.addWidget(self.connect_btn)

        # --- Checklist group ---
        mid = QGroupBox("Preflight Checklist")
        mv = QVBoxLayout(mid)
        self.steps_list = QListWidget()
        self._step_texts = [
            "PTT OFF (ESC X 0)",
            "Exit KISS (C0 FF C0 0D)",
            "Monitor OFF (ESC MN)",
            "Save (%ZS)",
            "Echo OFF (ESC E0)",
            "Save (ESC %ZS)",
            "PTT ON (ESC X 1)",
        ]
        for t in self._step_texts:
            self.steps_list.addItem(QListWidgetItem("• " + t + " …"))

        ctl_layout = QHBoxLayout()
        self.start_btn = QPushButton("Start Preflight")
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.exit_btn = QPushButton("Exit")
        self.ptt_guard = QCheckBox("Force PTT OFF at start (ESC X 0)")
        self.ptt_guard.setChecked(True)
        ctl_layout.addWidget(self.start_btn)
        ctl_layout.addWidget(self.cancel_btn)
        ctl_layout.addStretch(1)
        ctl_layout.addWidget(self.ptt_guard)
        ctl_layout.addSpacing(16)
        ctl_layout.addWidget(self.exit_btn)
        mv.addWidget(self.steps_list, 1)
        mv.addLayout(ctl_layout)

        # --- Status line ---
        self.status = QLabel("Disconnected.")
        self.status.setStyleSheet("color: #555;")

        # --- Layout setup ---
        central = QWidget()
        vv = QVBoxLayout(central)
        vv.addWidget(top)
        vv.addWidget(mid, 1)
        vv.addWidget(self.status)
        self.setCentralWidget(central)

        # --- Connections ---
        self.refresh_btn.clicked.connect(self._refresh_ports)
        self.connect_btn.clicked.connect(self._toggle_connect)
        self.start_btn.clicked.connect(self._start_preflight_clicked)
        self.cancel_btn.clicked.connect(self._cancel_preflight)
        self.exit_btn.clicked.connect(self.close)

        self._refresh_ports()

    def _open_serial(self, port, baud):
        try:
            self.ser = serial.Serial(port=port, baudrate=baud, timeout=0.2, write_timeout=0.5)
            self._connected = True
            return True
        except Exception as e:
            QMessageBox.critical(self, "Open Failed", str(e))
            return False

    def _close_serial(self):
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
        self.ser = None
        self._connected = False

    def _serial_write(self, b):
        try:
            if self.ser:
                self.ser.write(b)
                self.ser.flush()
        except Exception:
            pass

    def _refresh_ports(self):
        cur = self.port_box.currentText()
        self.port_box.clear()
        for dev, name in list_serial_ports():
            self.port_box.addItem(name, dev)
        idx = self.port_box.findText(cur)
        if idx >= 0:
            self.port_box.setCurrentIndex(idx)
        elif self.port_box.count() > 0:
            self.port_box.setCurrentIndex(0)

    def _toggle_connect(self):
        if not self._connected:
            dev = self.port_box.currentData()
            if not dev:
                QMessageBox.warning(self, "No Port", "Select a port first.")
                return
            baud = int(self.baud_box.currentText())
            if self._open_serial(dev, baud):
                self._connected = True
                self.connect_btn.setText("Close Port")
                self.status.setText(f"Connected to {dev} @ {baud}")
                self.port_box.setEnabled(False)
                self.refresh_btn.setEnabled(False)
        else:
            if self._running:
                QMessageBox.information(self, "Busy", "Cancel preflight first.")
                return
            self._close_serial()
            self.connect_btn.setText("Open Port")
            self.port_box.setEnabled(True)
            self.refresh_btn.setEnabled(True)
            self.status.setText("Disconnected.")

    def _start_preflight_clicked(self):
        if not self._connected or not self.ser:
            QMessageBox.warning(self, "Not Connected", "Open a port first.")
            return
        if self._running:
            return
        self._running = True
        self._canceled = False
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
            (lambda: self._send_cmd("MN", esc=True), 2),
            (lambda: self._send_cmd("%ZS", esc=False), 3),
            (lambda: self._send_cmd("E0", esc=True), 4),
            (lambda: self._send_cmd("%ZS", esc=True), 5),
            (lambda: self._send_cmd("X 1", esc=True), 6),
        ]
        self._run_steps_with_timer(steps, 1000)

    def _cancel_preflight(self):
        self._canceled = True
        self._running = False
        self.cancel_btn.setEnabled(False)
        self.start_btn.setEnabled(True)
        self.status.setText("Canceled.")

    def _kiss_exit_bytes(self):
        self._serial_write(bytes([0xC0, 0xFF, 0xC0, 0x0D]))

    def _send_cmd(self, cmd, esc=False):
        payload = (ESC if esc else b"") + cmd.encode("ascii", "ignore") + CR
        self._serial_write(payload)

    def _tick_step(self, idx, ok=True):
        item = self.steps_list.item(idx)
        if not item: return
        base = self._step_texts[idx]
        item.setText(("✓ " if ok else "✗ ") + base)

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
                return
            try:
                fn, idx = steps[i]
                fn()
                self._tick_step(idx, True)
            except Exception:
                self._tick_step(idx, False)
            QTimer.singleShot(delay, lambda: _do(i+1))
        _do(0)


def main():
    app = QApplication(sys.argv)
    w = PreflightWindow()
    w.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
