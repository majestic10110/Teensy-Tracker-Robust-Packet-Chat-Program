#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Teensy Tracker Config v0.9.6
- Enter KISS order corrected per operator request:
  * @K FIRST, then %ZS (so the *new* condition is what's saved)
- Permanent KISS unchanged from v0.9.5:
  * ON:  @KP1 then %ZS
  * OFF: @KP0 then %ZS, then send raw C0 FF C0 0D to leave KISS now
"""

import sys, re
from datetime import datetime
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QTextEdit, QGroupBox, QSpinBox,
    QCheckBox, QScrollArea, QMessageBox
)

VERSION = "Teensy Tracker Config v0.9.6"
ESC = b'\x1b'

try:
    import serial
    from serial import Serial
    from serial.tools import list_ports
except Exception:
    serial = None
    Serial = None
    list_ports = None

def safe_int(val, default):
    try: return int(val)
    except Exception: return default

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
                        if sep_idx == -1: break
                        part = buf[:sep_idx]; buf = buf[sep_idx+seplen:]
                        try: text = part.decode('utf-8', errors='replace')
                        except Exception: text = part.decode('latin1', errors='replace')
                        ts = datetime.now().strftime('%H:%M:%S')
                        self.line_received.emit(f"[{ts}] {text}")
                else:
                    self.msleep(25)
            except Exception:
                self.msleep(100)
    def stop(self):
        self._running = False
        self.wait(500)

class ConfigApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(VERSION)
        self.resize(1080, 940)

        self.ser: Serial = None
        self.reader_thread: SerialReaderThread = None

        central = QWidget(); self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # Serial group
        serial_group = QGroupBox("Serial Connection")
        sgl = QGridLayout(serial_group)
        self.port_combo = QComboBox()
        self.baud_combo = QComboBox(); self.baud_combo.addItems([str(x) for x in [9600,19200,38400,57600,115200,230400,460800]]); self.baud_combo.setCurrentText("115200")
        refresh_btn = QPushButton("Refresh Ports"); refresh_btn.clicked.connect(self.refresh_ports)
        self.connect_btn = QPushButton("Connect"); self.connect_btn.clicked.connect(self.open_port)
        self.disconnect_btn = QPushButton("Disconnect"); self.disconnect_btn.setEnabled(False); self.disconnect_btn.clicked.connect(self.close_port)
        self.status_label = QLabel(f"Status: Disconnected  |  {VERSION}")
        sgl.addWidget(QLabel("COM Port"), 0, 0); sgl.addWidget(self.port_combo, 0, 1, 1, 2); sgl.addWidget(refresh_btn, 0, 3)
        sgl.addWidget(QLabel("Baud"), 1, 0); sgl.addWidget(self.baud_combo, 1, 1); sgl.addWidget(self.connect_btn, 1, 2); sgl.addWidget(self.disconnect_btn, 1, 3)
        sgl.addWidget(self.status_label, 2, 0, 1, 4)
        root.addWidget(serial_group)

        # Scrollable content
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        content = QWidget(); cl = QVBoxLayout(content)

        cl.addWidget(self._build_identity_group())
        cl.addWidget(self._build_aprs_group())
        cl.addWidget(self._build_tx_levels_group())
        cl.addWidget(self._build_modem_group())
        cl.addWidget(self._build_ax25_group())
        cl.addWidget(self._build_kiss_host_group())
        cl.addWidget(self._build_misc_group())
        cl.addWidget(self._build_save_group())
        cl.addStretch(1)
        scroll.setWidget(content)
        root.addWidget(scroll)

        # Status log
        self.status_log = QTextEdit(); self.status_log.setReadOnly(True); self.status_log.setMaximumHeight(220)
        self.status_log.setStyleSheet("QTextEdit{background:#111;color:#ddd;font-family:Consolas,monospace;font-size:10pt;}")
        root.addWidget(self.status_log)

        self.refresh_ports()

    # ---------- Serial ----------
    def log(self, msg:str):
        self.status_log.append(msg)
        self.status_log.moveCursor(QtGui.QTextCursor.End)

    def refresh_ports(self):
        self.port_combo.clear()
        if list_ports:
            for p in list_ports.comports():
                self.port_combo.addItem(f"{p.device} — {p.description}", p.device)
        else:
            for i in range(1, 21):
                self.port_combo.addItem(f"COM{i}", f"COM{i}")

    def open_port(self):
        if self.ser and self.ser.is_open: self.close_port()
        port = self.port_combo.currentData() or self.port_combo.currentText()
        baud = safe_int(self.baud_combo.currentText(), 115200)
        try:
            self.ser = serial.Serial(port=port, baudrate=baud, timeout=0.05, rtscts=False, dsrdtr=False)
            self.status_label.setText(f"Status: Connected to {port} @ {baud}  |  {VERSION}")
            self.connect_btn.setEnabled(False); self.disconnect_btn.setEnabled(True)
            self.reader_thread = SerialReaderThread(self.ser)
            self.reader_thread.line_received.connect(self._on_rx_line)
            self.reader_thread.start()
        except Exception as e:
            QMessageBox.critical(self, "Serial Error", f"Could not open {port} @ {baud}\n{e}")
            self.status_label.setText(f"Status: Disconnected  |  {VERSION}")

    def close_port(self):
        try:
            if self.reader_thread:
                self.reader_thread.stop(); self.reader_thread=None
            if self.ser:
                self.ser.close(); self.ser=None
        finally:
            self.connect_btn.setEnabled(True); self.disconnect_btn.setEnabled(False)
            self.status_label.setText(f"Status: Disconnected  |  {VERSION}")

    def _on_rx_line(self, line:str):
        self.log(f"RX: {line}")

    def send_cmd(self, cmd:str):
        if not (self.ser and self.ser.is_open):
            QMessageBox.warning(self, "Not connected", "Open a COM port first."); return
        try:
            line = (cmd + "\r").encode('utf-8', errors='replace')
            self.log(f"TX CMD: {cmd}")
            self.ser.write(ESC + line)
        except Exception as e:
            QMessageBox.critical(self, "Command Error", f"Failed to send '{cmd}'\n{e}")

    def send_raw(self, raw:bytes):
        if not (self.ser and self.ser.is_open):
            QMessageBox.warning(self, "Not connected", "Open a COM port first."); return
        try:
            self.log(f"TX RAW: {raw.hex(' ')}")
            self.ser.write(raw)
        except Exception as e:
            QMessageBox.critical(self, "Write Error", f"Failed to send raw bytes\n{e}")

    # ---------- UI Builders ----------
    def _build_identity_group(self):
        g = QGroupBox("Identity / Paths")
        gl = QGridLayout(g)

        self.mycall_edit = QLineEdit(); self.mycall_edit.setPlaceholderText("MYCALL (e.g., M0OLI)")
        my_apply = QPushButton("Apply (I)")
        my_apply.clicked.connect(lambda: self._apply_text("I", self.mycall_edit.text()))

        self.path_edit = QLineEdit(); self.path_edit.setPlaceholderText("APRS target + path e.g. APRPR5 WIDE1-1")
        ap_apply = QPushButton("Apply (%AP)")
        ap_apply.clicked.connect(lambda: self._apply_text("%AP", self.path_edit.text()))

        row=0
        gl.addWidget(QLabel("MyCALL (I)"), row,0); gl.addWidget(self.mycall_edit, row,1); gl.addWidget(my_apply, row,2); row+=1
        gl.addWidget(QLabel("APRS Path (%AP)"), row,0); gl.addWidget(self.path_edit, row,1); gl.addWidget(ap_apply, row,2); row+=1
        return g

    def _build_aprs_group(self):
        g = QGroupBox("APRS")
        gl = QGridLayout(g)

        self.aprs_mode = QComboBox(); self.aprs_mode.addItems(["0 OFF","1 GPS","2 FIX"])
        a_apply = QPushButton("Apply (%A)"); a_apply.clicked.connect(lambda: self._apply_num("%A", self.aprs_mode.currentIndex()))

        self.aprs_mycall = QLineEdit(); am_apply = QPushButton("Apply (%AM)"); am_apply.clicked.connect(lambda: self._apply_text("%AM", self.aprs_mycall.text()))
        self.aprs_comment = QLineEdit(); ac_apply = QPushButton("Apply (%AC)"); ac_apply.clicked.connect(lambda: self._apply_text("%AC", self.aprs_comment.text()))
        self.aprs_status = QLineEdit(); ar_apply = QPushButton("Apply (%AR)"); ar_apply.clicked.connect(lambda: self._apply_text("%AR", self.aprs_status.text()))
        self.aprs_status_every = QSpinBox(); self.aprs_status_every.setRange(0,20); ae_apply = QPushButton("Apply (%AE)"); ae_apply.clicked.connect(lambda: self._apply_num("%AE", self.aprs_status_every.value()))
        self.aprs_timer = QSpinBox(); self.aprs_timer.setRange(0,30000); self.aprs_timer.setValue(900); ab_apply = QPushButton("Apply (%AB/%AT)"); ab_apply.clicked.connect(lambda: self._apply_num("%AB", self.aprs_timer.value()))
        self.aprs_digi = QComboBox(); self.aprs_digi.addItems(["0 Off","1 WIDE1-1","2 WIDEn-N","3 Special"]); ad_apply = QPushButton("Apply (%AD)"); ad_apply.clicked.connect(lambda: self._apply_num("%AD", self.aprs_digi.currentIndex()))
        self.aprs_valid = QSpinBox(); self.aprs_valid.setRange(10,3600); self.aprs_valid.setValue(1200); av_apply = QPushButton("Apply (%AV)"); av_apply.clicked.connect(lambda: self._apply_num("%AV", self.aprs_valid.value()))
        self.aprs_unproto = QComboBox(); self.aprs_unproto.addItems(["0 Normal","1 %AG for A*","2 %AG for all"]); au_apply = QPushButton("Apply (%AU)"); au_apply.clicked.connect(lambda: self._apply_num("%AU", self.aprs_unproto.currentIndex()))
        self.aprs_symbol = QLineEdit(); ay_apply = QPushButton("Apply (%AY)"); ay_apply.clicked.connect(lambda: self._apply_text("%AY", self.aprs_symbol.text()))
        self.aprs_fix_lat = QLineEdit(); self.aprs_fix_lon = QLineEdit(); self.aprs_fix_lat.setPlaceholderText("5557.98N"); self.aprs_fix_lon.setPlaceholderText("01417.40E")
        ao_apply = QPushButton("Apply (%AO)"); ao_apply.clicked.connect(lambda: self._apply_text("%AO", f"{self.aprs_fix_lat.text().strip()} {self.aprs_fix_lon.text().strip()}"))
        self.aprs_alt_mode = QComboBox(); self.aprs_alt_mode.addItems(["0 Off","1 Uncompressed","2 Both (comp+uncomp)","3 Uncomp even when comp"]); aa_apply = QPushButton("Apply (%AA)"); aa_apply.clicked.connect(lambda: self._apply_num("%AA", self.aprs_alt_mode.currentIndex()))
        self.aprs_freq_beacon = QSpinBox(); self.aprs_freq_beacon.setRange(0,30000); af_apply = QPushButton("Apply (%AF)"); af_apply.clicked.connect(lambda: self._apply_num("%AF", self.aprs_freq_beacon.value()))
        self.aprs_gateway = QComboBox(); self.aprs_gateway.addItems(["NONE","300","R300","R600","1200","HF-DUAL"]); ag_apply = QPushButton("Apply (%AG)"); ag_apply.clicked.connect(lambda: self._apply_text("%AG", self.aprs_gateway.currentText()))
        self.aprs_hf_toggle = QComboBox(); self.aprs_hf_toggle.addItems(["0 Off","1 Toggle(safe)","2 Toggle(force)"]); ah_apply = QPushButton("Apply (%AH)"); ah_apply.clicked.connect(lambda: self._apply_num("%AH", self.aprs_hf_toggle.currentIndex()))
        self.aprs_short = QCheckBox("Compressed Position (%AS=1)"); as_apply = QPushButton("Apply"); as_apply.clicked.connect(lambda: self._apply_num("%AS", 1 if self.aprs_short.isChecked() else 0))

        row=0
        gl.addWidget(QLabel("Mode (%A)"), row,0); gl.addWidget(self.aprs_mode, row,1); gl.addWidget(a_apply, row,2); row+=1
        gl.addWidget(QLabel("APRS MyCALL (%AM)"), row,0); gl.addWidget(self.aprs_mycall, row,1); gl.addWidget(am_apply, row,2); row+=1
        gl.addWidget(QLabel("APRS Comment (%AC)"), row,0); gl.addWidget(self.aprs_comment, row,1); gl.addWidget(ac_apply, row,2); row+=1
        gl.addWidget(QLabel("Status Report (%AR)"), row,0); gl.addWidget(self.aprs_status, row,1); gl.addWidget(ar_apply, row,2); row+=1
        gl.addWidget(QLabel("Status Every (%AE)"), row,0); gl.addWidget(self.aprs_status_every, row,1); gl.addWidget(ae_apply, row,2); row+=1
        gl.addWidget(QLabel("APRS Timer sec (%AB/%AT)"), row,0); gl.addWidget(self.aprs_timer, row,1); gl.addWidget(ab_apply, row,2); row+=1
        gl.addWidget(QLabel("Digipeating (%AD)"), row,0); gl.addWidget(self.aprs_digi, row,1); gl.addWidget(ad_apply, row,2); row+=1
        gl.addWidget(QLabel("GPS Valid sec (%AV)"), row,0); gl.addWidget(self.aprs_valid, row,1); gl.addWidget(av_apply, row,2); row+=1
        gl.addWidget(QLabel("Unproto Cross (%AU)"), row,0); gl.addWidget(self.aprs_unproto, row,1); gl.addWidget(au_apply, row,2); row+=1
        gl.addWidget(QLabel("Symbol (%AY)"), row,0); gl.addWidget(self.aprs_symbol, row,1); gl.addWidget(ay_apply, row,2); row+=1
        gl.addWidget(QLabel("FIX Position (%AO)"), row,0); gl.addWidget(self.aprs_fix_lat, row,1); gl.addWidget(self.aprs_fix_lon, row,2); gl.addWidget(ao_apply, row,3); row+=1
        gl.addWidget(QLabel("Altitude Mode (%AA)"), row,0); gl.addWidget(self.aprs_alt_mode, row,1); gl.addWidget(aa_apply, row,2); row+=1
        gl.addWidget(QLabel("Freq Beacon sec (%AF)"), row,0); gl.addWidget(self.aprs_freq_beacon, row,1); gl.addWidget(af_apply, row,2); row+=1
        gl.addWidget(QLabel("Gateway Modem (%AG)"), row,0); gl.addWidget(self.aprs_gateway, row,1); gl.addWidget(ag_apply, row,2); row+=1
        gl.addWidget(QLabel("HF Mode Toggle (%AH)"), row,0); gl.addWidget(self.aprs_hf_toggle, row,1); gl.addWidget(ah_apply, row,2); row+=1
        gl.addWidget(self.aprs_short, row,0); gl.addWidget(as_apply, row,1); row+=1

        return g

    def _build_tx_levels_group(self):
        g = QGroupBox("Transmit Levels")
        gl = QGridLayout(g)
        self.tx_all = QSpinBox(); self.tx_all.setRange(30,3000); self.tx_all.setValue(300); x_apply = QPushButton("Apply (%X)"); x_apply.clicked.connect(lambda: self._apply_num("%X", self.tx_all.value()))
        self.tx_xa = QSpinBox(); self.tx_xa.setRange(30,3000); self.tx_xa.setValue(300); xa_apply = QPushButton("Apply (%XA)"); xa_apply.clicked.connect(lambda: self._apply_num("%XA", self.tx_xa.value()))
        self.tx_xf = QSpinBox(); self.tx_xf.setRange(30,3000); self.tx_xf.setValue(600); xf_apply = QPushButton("Apply (%XF)"); xf_apply.clicked.connect(lambda: self._apply_num("%XF", self.tx_xf.value()))
        self.tx_xr = QSpinBox(); self.tx_xr.setRange(30,3000); self.tx_xr.setValue(200); xr_apply = QPushButton("Apply (%XR)"); xr_apply.clicked.connect(lambda: self._apply_num("%XR", self.tx_xr.value()))
        row=0
        gl.addWidget(QLabel("All Modes (%X) mVpp"), row,0); gl.addWidget(self.tx_all, row,1); gl.addWidget(x_apply, row,2); row+=1
        gl.addWidget(QLabel("AFSK 300/1200 (%XA)"), row,0); gl.addWidget(self.tx_xa, row,1); gl.addWidget(xa_apply, row,2); row+=1
        gl.addWidget(QLabel("Direct-FSK 9600/19200 (%XF)"), row,0); gl.addWidget(self.tx_xf, row,1); gl.addWidget(xf_apply, row,2); row+=1
        gl.addWidget(QLabel("RPR (%XR)"), row,0); gl.addWidget(self.tx_xr, row,1); gl.addWidget(xr_apply, row,2); row+=1
        return g

    def _build_modem_group(self):
        g = QGroupBox("Modem / Packet Mode")
        gl = QGridLayout(g)
        self.mode_combo = QComboBox(); self.mode_combo.addItems(["300","R300","R600","1200"])
        b_apply = QPushButton("Apply (%B)"); b_apply.clicked.connect(lambda: self._apply_text("%B", self.mode_combo.currentText()))
        self.afsk_center = QSpinBox(); self.afsk_center.setRange(1000,3000); self.afsk_center.setValue(1700); f_apply = QPushButton("Apply (%F)"); f_apply.clicked.connect(lambda: self._apply_num("%F", self.afsk_center.value()))
        self.rpr_center = QSpinBox(); self.rpr_center.setRange(300,2400); self.rpr_center.setValue(1500); l_apply = QPushButton("Apply (%L)"); l_apply.clicked.connect(lambda: self._apply_num("%L", self.rpr_center.value()))
        m_btn = QPushButton("HF Packet Monitor (%M)"); m_btn.clicked.connect(lambda: self.send_cmd("%M"))
        row=0
        gl.addWidget(QLabel("Mode (%B)"), row,0); gl.addWidget(self.mode_combo, row,1); gl.addWidget(b_apply, row,2); row+=1
        gl.addWidget(QLabel("AFSK Center Hz (%F)"), row,0); gl.addWidget(self.afsk_center, row,1); gl.addWidget(f_apply, row,2); row+=1
        gl.addWidget(QLabel("RPR Center Hz (%L)"), row,0); gl.addWidget(self.rpr_center, row,1); gl.addWidget(l_apply, row,2); row+=1
        gl.addWidget(m_btn, row,0); row+=1
        return g

    def _build_ax25_group(self):
        g = QGroupBox("AX.25 Core")
        gl = QGridLayout(g)
        self.echo_check = QCheckBox("Echo (E)"); e_apply = QPushButton("Apply"); e_apply.clicked.connect(lambda: self._apply_num("E", 1 if self.echo_check.isChecked() else 0))
        self.frack = QSpinBox(); self.frack.setRange(1,1500); self.frack.setValue(500); f_apply = QPushButton("Apply (F)"); f_apply.clicked.connect(lambda: self._apply_num("F", self.frack.value()))
        self.retry = QSpinBox(); self.retry.setRange(0,127); self.retry.setValue(12); n_apply = QPushButton("Apply (N)"); n_apply.clicked.connect(lambda: self._apply_num("N", self.retry.value()))
        self.maxframe = QSpinBox(); self.maxframe.setRange(1,7); self.maxframe.setValue(7); o_apply = QPushButton("Apply (O)"); o_apply.clicked.connect(lambda: self._apply_num("O", self.maxframe.value()))
        self.persist = QSpinBox(); self.persist.setRange(0,255); self.persist.setValue(32); p_apply = QPushButton("Apply (P)"); p_apply.clicked.connect(lambda: self._apply_num("P", self.persist.value()))
        self.ptt = QCheckBox("PTT (X)"); self.ptt.setChecked(True); x_apply = QPushButton("Apply"); x_apply.clicked.connect(lambda: self._apply_num("X", 1 if self.ptt.isChecked() else 0))
        self.slot = QSpinBox(); self.slot.setRange(0,127); self.slot.setValue(10); w_apply = QPushButton("Apply (W)"); w_apply.clicked.connect(lambda: self._apply_num("W", self.slot.value()))
        self.nch = QSpinBox(); self.nch.setRange(0,10); self.nch.setValue(10); y_apply = QPushButton("Apply (Y)"); y_apply.clicked.connect(lambda: self._apply_num("Y", self.nch.value()))
        self.flow = QComboBox(); self.flow.addItems(["0 Off/Off","1 On/Off","2 Off/On","3 On/On"]); z_apply = QPushButton("Apply (Z)"); z_apply.clicked.connect(lambda: self._apply_num("Z", self.flow.currentIndex()))
        row=0
        gl.addWidget(self.echo_check, row,0); gl.addWidget(e_apply, row,1); row+=1
        gl.addWidget(QLabel("Frack (F)"), row,0); gl.addWidget(self.frack, row,1); gl.addWidget(f_apply, row,2); row+=1
        gl.addWidget(QLabel("Retry (N)"), row,0); gl.addWidget(self.retry, row,1); gl.addWidget(n_apply, row,2); row+=1
        gl.addWidget(QLabel("MaxFrame (O)"), row,0); gl.addWidget(self.maxframe, row,1); gl.addWidget(o_apply, row,2); row+=1
        gl.addWidget(QLabel("Persistence (P)"), row,0); gl.addWidget(self.persist, row,1); gl.addWidget(p_apply, row,2); row+=1
        gl.addWidget(self.ptt, row,0); gl.addWidget(x_apply, row,1); row+=1
        gl.addWidget(QLabel("Slottime ms (W)"), row,0); gl.addWidget(self.slot, row,1); gl.addWidget(w_apply, row,2); row+=1
        gl.addWidget(QLabel("Max Channels (Y)"), row,0); gl.addWidget(self.nch, row,1); gl.addWidget(y_apply, row,2); row+=1
        gl.addWidget(QLabel("Flow (Z)"), row,0); gl.addWidget(self.flow, row,1); gl.addWidget(z_apply, row,2); row+=1
        return g

    def _build_kiss_host_group(self):
        g = QGroupBox("Host / KISS / Timers")
        gl = QGridLayout(g)
        self.hostmode = QCheckBox("WA8DED Host-Mode (JHOST)"); j_apply = QPushButton("Apply"); j_apply.clicked.connect(lambda: self._apply_num("JHOST", 1 if self.hostmode.isChecked() else 0))
        enter_k = QPushButton("Enter KISS (@K then %ZS)"); enter_k.clicked.connect(self._enter_kiss_sequence)
        self.kiss_perm = QCheckBox("KISS Permanent (@KP1/@KP0)"); kp_apply = QPushButton("Apply"); kp_apply.clicked.connect(self._toggle_kiss_perm_sequence)
        exit_k = QPushButton("Exit KISS Now (C0 FF C0 0D)"); exit_k.clicked.connect(lambda: self.send_raw(bytes([192,255,192,13])))
        self.t2 = QSpinBox(); self.t2.setRange(0,100000); self.t2.setValue(100); t2_apply = QPushButton("Apply (@T2)"); t2_apply.clicked.connect(lambda: self._apply_num("@T2", self.t2.value()))
        self.t3 = QSpinBox(); self.t3.setRange(0,100000); self.t3.setValue(30000); t3_apply = QPushButton("Apply (@T3)"); t3_apply.clicked.connect(lambda: self._apply_num("@T3", self.t3.value()))
        self.uipoll = QCheckBox("UI-Poll (@U)"); u_apply = QPushButton("Apply"); u_apply.clicked.connect(lambda: self._apply_num("@U", 1 if self.uipoll.isChecked() else 0))
        self.callcheck = QCheckBox("Call Check (@V)"); v_apply = QPushButton("Apply"); v_apply.clicked.connect(lambda: self._apply_num("@V", 1 if self.callcheck.isChecked() else 0))
        self.bt_uart = QComboBox(); self.bt_uart.addItems(["9600","38400","115200"]); btu_apply = QPushButton("Apply (!B)"); btu_apply.clicked.connect(lambda: self._apply_text("!B", self.bt_uart.currentText()))
        row=0
        gl.addWidget(self.hostmode, row,0); gl.addWidget(j_apply, row,1); row+=1
        gl.addWidget(enter_k, row,0); gl.addWidget(self.kiss_perm, row,1); gl.addWidget(kp_apply, row,2); row+=1
        gl.addWidget(exit_k, row,0); row+=1
        gl.addWidget(QLabel("Timer2 (@T2) 10ms"), row,0); gl.addWidget(self.t2, row,1); gl.addWidget(t2_apply, row,2); row+=1
        gl.addWidget(QLabel("Timer3 (@T3) 10ms"), row,0); gl.addWidget(self.t3, row,1); gl.addWidget(t3_apply, row,2); row+=1
        gl.addWidget(self.uipoll, row,0); gl.addWidget(u_apply, row,1); row+=1
        gl.addWidget(self.callcheck, row,0); gl.addWidget(v_apply, row,1); row+=1
        gl.addWidget(QLabel("Bluetooth UART (!B)"), row,0); gl.addWidget(self.bt_uart, row,1); gl.addWidget(btu_apply, row,2); row+=1
        return g

    def _build_misc_group(self):
        g = QGroupBox("Misc / Elbug / Diagnostics")
        gl = QGridLayout(g)
        self.elbug = QCheckBox("Elbug (<E)"); e_apply = QPushButton("Apply"); e_apply.clicked.connect(lambda: self._apply_num("<E", 1 if self.elbug.isChecked() else 0))
        self.elbug_speed = QSpinBox(); self.elbug_speed.setRange(20,600); self.elbug_speed.setValue(60); es_apply = QPushButton("Apply (<S)"); es_apply.clicked.connect(lambda: self._apply_num("<S", self.elbug_speed.value()))
        self.elbug_tone = QSpinBox(); self.elbug_tone.setRange(0,1500); self.elbug_tone.setValue(0); et_apply = QPushButton("Apply (<T)"); et_apply.clicked.connect(lambda: self._apply_num("<T", self.elbug_tone.value()))
        self.elbug_dir = QCheckBox("Elbug Reverse (<D=1)"); ed_apply = QPushButton("Apply"); ed_apply.clicked.connect(lambda: self._apply_num("<D", 1 if self.elbug_dir.isChecked() else 0))
        ver_btn = QPushButton("Show Version (V)"); ver_btn.clicked.connect(lambda: self.send_cmd("V"))
        free_buf_btn = QPushButton("Show Free Buffers (@B)"); free_buf_btn.clicked.connect(lambda: self.send_cmd("@B"))
        duplex = QCheckBox("Duplex (@D)"); d_apply = QPushButton("Apply"); d_apply.clicked.connect(lambda: self._apply_num("@D", 1 if duplex.isChecked() else 0))
        flags = QCheckBox("Send Flags in Pauses (@F)"); f2_apply = QPushButton("Apply"); f2_apply.clicked.connect(lambda: self._apply_num("@F", 1 if flags.isChecked() else 0))
        ipoll_len = QSpinBox(); ipoll_len.setRange(1,256); ipoll_len.setValue(60); i_apply = QPushButton("Apply (@I)"); i_apply.clicked.connect(lambda: self._apply_num("@I", ipoll_len.value()))
        row=0
        gl.addWidget(self.elbug, row,0); gl.addWidget(e_apply, row,1); row+=1
        gl.addWidget(QLabel("Elbug Speed (<S) LPM"), row,0); gl.addWidget(self.elbug_speed, row,1); gl.addWidget(es_apply, row,2); row+=1
        gl.addWidget(QLabel("Elbug Side-tone Hz (<T)"), row,0); gl.addWidget(self.elbug_tone, row,1); gl.addWidget(et_apply, row,2); row+=1
        gl.addWidget(self.elbug_dir, row,0); gl.addWidget(ed_apply, row,1); row+=1
        gl.addWidget(ver_btn, row,0); gl.addWidget(free_buf_btn, row,1); row+=1
        gl.addWidget(duplex, row,0); gl.addWidget(d_apply, row,1); row+=1
        gl.addWidget(flags, row,0); gl.addWidget(f2_apply, row,1); row+=1
        gl.addWidget(QLabel("IPOLL max len (@I)"), row,0); gl.addWidget(ipoll_len, row,1); gl.addWidget(i_apply, row,2); row+=1
        return g

    def _build_save_group(self):
        g = QGroupBox("Save / Load / Bootloader")
        hl = QHBoxLayout(g)
        load_btn = QPushButton("Load Settings (%ZL + sweep)"); load_btn.clicked.connect(self.read_device_sweep)
        save_btn = QPushButton("Save (%ZS)"); save_btn.clicked.connect(lambda: self.send_cmd("%ZS"))
        reset_btn = QPushButton("Factory Defaults (%ZK)"); reset_btn.clicked.connect(lambda: self._confirm("%ZK will reset ALL settings. Continue?", lambda: self.send_cmd("%ZK")))
        boot_btn = QPushButton("Enter Bootloader (%R)"); boot_btn.clicked.connect(lambda: self._confirm("Enter bootloader now (%R)?", lambda: self.send_cmd("%R")))
        hl.addWidget(load_btn); hl.addWidget(save_btn); hl.addWidget(reset_btn); hl.addWidget(boot_btn)
        return g

    # ---------- Apply helpers ----------
    def _apply_text(self, cmd:str, text:str):
        text = text.strip()
        if not text:
            QMessageBox.warning(self, "Empty", f"Enter a value for {cmd}."); return
        self.send_cmd(f"{cmd}{text}")

    def _apply_num(self, cmd:str, value:int):
        self.send_cmd(f"{cmd}{int(value)}")

    def _confirm(self, msg, action):
        if QMessageBox.question(self, "Confirm", msg, QMessageBox.Yes|QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            action()

    # ---------- KISS Sequences ----------
    def _enter_kiss_sequence(self):
        """Enter KISS, then save condition as requested: @K -> %ZS."""
        if not (self.ser and self.ser.is_open):
            QMessageBox.warning(self, "Not connected", "Open a COM port first."); return
        self.send_cmd("@K")
        QtCore.QThread.msleep(120)
        # Attempt to save after entering KISS per operator preference.
        # Note: some firmware may ignore ESC after @K; the operator confirmed this device expects @K then %ZS.
        self.send_cmd("%ZS")
        self.log("Entered KISS (@K) and issued %ZS to save state. If no response, exit KISS and try again.")

    def _toggle_kiss_perm_sequence(self):
        """Apply @KP1/@KP0 with save; if disabling, also send raw exit bytes."""
        if not (self.ser and self.ser.is_open):
            QMessageBox.warning(self, "Not connected", "Open a COM port first."); return
        if self.kiss_perm.isChecked():
            self.log("Enabling KISS permanent: @KP1 then %ZS")
            self.send_cmd("@KP1")
            QtCore.QThread.msleep(80)
            self.send_cmd("%ZS")
            self.log("KISS permanent enabled and saved.")
        else:
            self.log("Disabling KISS permanent: @KP0 then %ZS, then exit KISS bytes C0 FF C0 0D")
            self.send_cmd("@KP0")
            QtCore.QThread.msleep(80)
            self.send_cmd("%ZS")
            QtCore.QThread.msleep(100)
            self.send_raw(bytes([192,255,192,13]))
            self.log("KISS permanent disabled, state saved, and exit bytes sent.")

    # ---------- Load Settings ----------
    def read_device_sweep(self):
        if not (self.ser and self.ser.is_open):
            QMessageBox.warning(self, "Not connected", "Open a COM port first."); return
        self.log("=== LOAD SETTINGS: start ===")
        self._flush_io()
        self._query("%ZL")  # load saved first

        CALL_RE = re.compile(r'\b([A-Z0-9]{1,2}\d[A-Z0-9]{1,3}(?:-[0-9]{1,2})?)\b', re.I)
        def parse_call(texts):
            for t in texts:
                m = CALL_RE.search(t)
                if m: return m.group(1).upper()
            return None

        # identity
        my = parse_call(self._query("I"))
        if my: self.mycall_edit.setText(my)
        path = self._query("%AP"); 
        if path: self.path_edit.setText(path[-1])

        # APRS
        mode = self._pick_int(self._query("%A")); 
        if mode is not None and 0<=mode<=2: self.aprs_mode.setCurrentIndex(mode)
        am = parse_call(self._query("%AM")); 
        if am: self.aprs_mycall.setText(am)
        ac = self._query("%AC"); 
        if ac: self.aprs_comment.setText(ac[-1])
        ar = self._query("%AR"); 
        if ar: self.aprs_status.setText(ar[-1])
        ae = self._pick_int(self._query("%AE")); 
        if ae is not None: self.aprs_status_every.setValue(ae)
        ab = self._pick_int(self._query("%AB")); 
        if ab is not None: self.aprs_timer.setValue(ab)
        ad = self._pick_int(self._query("%AD")); 
        if ad is not None and 0<=ad<=3: self.aprs_digi.setCurrentIndex(ad)
        av = self._pick_int(self._query("%AV")); 
        if av is not None: self.aprs_valid.setValue(av)
        au = self._pick_int(self._query("%AU")); 
        if au is not None and 0<=au<=2: self.aprs_unproto.setCurrentIndex(au)
        ay = self._query("%AY"); 
        if ay: self.aprs_symbol.setText(ay[-1])
        # AO (lat lon)
        ao = " ".join(self._query("%AO"))
        m = re.search(r'([0-9]{4}\.[0-9]{2}[NS])\s+([0-9]{5}\.[0-9]{2}[EW])', ao)
        if m:
            self.aprs_fix_lat.setText(m.group(1)); self.aprs_fix_lon.setText(m.group(2))
        aa = self._pick_int(self._query("%AA")); 
        if aa is not None and 0<=aa<=3: self.aprs_alt_mode.setCurrentIndex(aa)
        af = self._pick_int(self._query("%AF")); 
        if af is not None: self.aprs_freq_beacon.setValue(af)
        ag = self._query("%AG")
        for opt in ["NONE","300","R300","R600","1200","HF-DUAL"]:
            if any(opt in ln for ln in ag): self.aprs_gateway.setCurrentText(opt); break
        ah = self._pick_int(self._query("%AH")); 
        if ah is not None and 0<=ah<=2: self.aprs_hf_toggle.setCurrentIndex(ah)
        as_ = self._pick_int(self._query("%AS")); 
        if as_ is not None: self.aprs_short.setChecked(bool(as_))

        # TX levels
        v = self._pick_int(self._query("%XA"));  self.tx_xa.setValue(v if v is not None else self.tx_xa.value())
        v = self._pick_int(self._query("%XF"));  self.tx_xf.setValue(v if v is not None else self.tx_xf.value())
        v = self._pick_int(self._query("%XR"));  self.tx_xr.setValue(v if v is not None else self.tx_xr.value())

        # Modem
        b = self._query("%B")
        for opt in ["300","R300","R600","1200"]:
            if any(opt in ln for ln in b): self.mode_combo.setCurrentText(opt); break
        v = self._pick_int(self._query("%F"));  self.afsk_center.setValue(v if v is not None else self.afsk_center.value())
        v = self._pick_int(self._query("%L"));  self.rpr_center.setValue(v if v is not None else self.rpr_center.value())

        # AX.25
        v = self._pick_int(self._query("E"));   self.echo_check.setChecked(bool(v)) if v is not None else None
        v = self._pick_int(self._query("F"));   self.frack.setValue(v) if v is not None else None
        v = self._pick_int(self._query("N"));   self.retry.setValue(v) if v is not None else None
        v = self._pick_int(self._query("O"));   self.maxframe.setValue(v) if v is not None else None
        v = self._pick_int(self._query("P"));   self.persist.setValue(v) if v is not None else None
        v = self._pick_int(self._query("X"));   self.ptt.setChecked(bool(v)) if v is not None else None
        v = self._pick_int(self._query("W"));   self.slot.setValue(v) if v is not None else None
        v = self._pick_int(self._query("Y"));   self.nch.setValue(v) if v is not None else None
        v = self._pick_int(self._query("Z"));   self.flow.setCurrentIndex(v) if v is not None and 0<=v<=3 else None

        self.log("=== LOAD SETTINGS: complete ===")

    # ---------- Low-level read helpers ----------
    def _flush_io(self):
        if not (self.ser and self.ser.is_open): return
        try:
            self.ser.reset_input_buffer(); self.ser.reset_output_buffer()
        except Exception:
            pass

    def _query(self, cmd:str, timeout_ms=800, idle_ms=200):
        """Send ESC <cmd> and return list of response lines (strings)."""
        if not (self.ser and self.ser.is_open): return []
        try:
            self.ser.write(ESC + (cmd + "\r").encode('utf-8', errors='replace')); self.ser.flush()
            self.log(f"QRY: {cmd}")
        except Exception as e:
            self.log(f"Write error {cmd}: {e}"); return []
        buf=b''; start=QtCore.QTime.currentTime(); last=QtCore.QTime.currentTime()
        while start.msecsTo(QtCore.QTime.currentTime()) < timeout_ms:
            QtCore.QThread.msleep(20)
            try:
                n=self.ser.in_waiting
                if n:
                    chunk=self.ser.read(n)
                    if chunk:
                        buf+=chunk; last=QtCore.QTime.currentTime()
            except Exception: break
            if last.msecsTo(QtCore.QTime.currentTime())>=idle_ms: break
        lines = [x for x in re.split(r'\r\n|\n|\r', buf.decode('utf-8', errors='replace')) if x.strip()]
        for ln in lines:
            self.log(f"  -> {ln}")
        return lines

    def _pick_int(self, lines):
        for ln in lines:
            m = re.search(r'(-?\d+)', ln)
            if m:
                try: return int(m.group(1))
                except Exception: pass
        return None

def main():
    print(VERSION)
    app = QApplication(sys.argv)
    w = ConfigApp(); w.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
