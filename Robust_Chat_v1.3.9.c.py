import re
#!/usr/bin/env python3
# -*- coding: utf-8 -*-



# --- Callsign helpers (SSID-aware) ---
def base_callsign(cs: str) -> str:
    cs = (cs or "").strip().upper()
    m = re.match(r"^([A-Z0-9/]+?)(?:-([0-9]{1,2}))?$", cs)
    return m.group(1) if m else cs

"""
LiNK500 Teensy Chat v1.3.9.c Consolidated (Explicit Fleet Mode) (2025-09-12)
- Inline Fleet Manager UI between Serial and Frequencies
- Global dark theme with VT323 and a minimum font size of 14pt (larger elements kept larger)
- Fleet dialogs (Add Group / Add Callsign) enlarged (VT323 14pt, wider inputs)
- Fleet Members list and Active group dropdown at 14pt
- Frequencies labels at 14pt
- "Enable Fleet" and "Active" label at 14pt
"""

import sys, re, time, os, math, tempfile, traceback, random, json, fnmatch
from collections import deque
from datetime import datetime

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer, QUrl
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QTextBrowser, QTextEdit,
    QGroupBox, QCheckBox, QMessageBox, QStatusBar, QSizePolicy, QShortcut,
    QListWidget, QListWidgetItem, QInputDialog, QMenu, QAction
)

# --- Callsign helpers (SSID-aware) ---
def base_callsign(cs: str) -> str:
    cs = (cs or '').strip().upper()
    m = re.match(r'^([A-Z0-9/]+?)(?:-([0-9]{1,2}))?$', cs)
    return m.group(1) if m else cs

    m = re.match(r"^([A-Z0-9/]+?)(?:-([0-9]{1,2}))?$", cs)
    return m.group(1) if m else cs

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
COLOR_DIM  = "#8B8B70"      # muted for dimmed
COLOR_HIGHLIGHT = "#00CC00" # focus/hover
COLOR_BG = "#1A1A1A"        # background
COLOR_PANEL = "#2A2A2A"
COLOR_PRESSED = "#333333"   # pressed
COLOR_TEXT = "#FFFFFF"      # status/messagebox text
COLOR_GPS_BG = "#CC0000"    # GPS SEND red
COLOR_GPS_HOVER = "#FF4D4D" # GPS hover
COLOR_BORDER = COLOR_SENT

# ---- Global stylesheet with 14pt baseline ----
GLOBAL_QSS = f"""
/* Base */
* {{
  font-family: VT323, monospace;
}}
QWidget {{
  background-color: {COLOR_BG};
  color: {COLOR_TEXT};
  font-family: VT323, monospace;
  font-size: 14pt;  /* global minimum */
}}
/* Group boxes / panels */
QGroupBox {{
  color: {COLOR_SENT};
  border: 2px solid {COLOR_BORDER};
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
/* Inputs & lists */
QLineEdit, QTextEdit, QListWidget, QComboBox, QAbstractItemView {{
  background: {COLOR_PANEL};
  color: {COLOR_TEXT};
  border: 2px solid {COLOR_BORDER};
  border-radius: 4px;
}}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus {{
  border: 3px solid {COLOR_HIGHLIGHT};
}}
QComboBox QAbstractItemView {{
  background: {COLOR_PANEL};
  color: {COLOR_TEXT};
  selection-background-color: {COLOR_HIGHLIGHT};
}}
/* Buttons & checkboxes */
QPushButton {{
  background: {COLOR_BG};
  color: {COLOR_SENT};
  border: 2px solid {COLOR_BORDER};
  border-radius: 4px;
  padding: 4px 8px;
}}
QPushButton:hover {{ background: {COLOR_HIGHLIGHT}; color: {COLOR_BG}; }}
QPushButton:pressed {{ background: {COLOR_PRESSED}; }}
QCheckBox, QLabel {{
  color: {COLOR_SENT};
}}
/* Text browser links */
QTextBrowser {{
  background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1A1A1A, stop:1 #2A2A2A);
  color: {COLOR_SENT};
  border: 2px solid {COLOR_BORDER};
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
QTextBrowser a:hover {{ background-color: {COLOR_HIGHLIGHT}; color: {COLOR_BG}; }}
/* Status bar */
QStatusBar, QStatusBar QLabel {{
  background-color: {COLOR_BG};
  color: {COLOR_TEXT};
  border: none;
}}
/* Dialogs inherit global; ensure inputs look right */
QInputDialog QLineEdit {{
  min-width: 320px;
}}
"""

# NMEA & parsing helpers --------------------
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
    if any(math.isnan(x) for x in (lat, lon)):
        return ""
    if abs(lat) > 90 or abs(lon) > 180:
        return ""
    return f"{lat:.5f} {lon:.5f}"

def _haversine_km(lat1, lon1, lat2, lon2):
    from math import radians, sin, cos, asin, sqrt
    R = 6371.0088  # mean Earth radius km
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    return R * c

def _initial_bearing_deg(lat1, lon1, lat2, lon2):
    from math import radians, degrees, sin, cos, atan2
    phi1, phi2 = radians(lat1), radians(lat2)
    dlon = radians(lon2 - lon1)
    x = sin(dlon) * cos(phi2)
    y = cos(phi1)*sin(phi2) - sin(phi1)*cos(phi2)*cos(dlon)
    brng = (degrees(atan2(x, y)) + 360.0) % 360.0
    return brng

_DIRS_16 = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"]
def _dir16(bearing_deg: float) -> str:
    idx = int((bearing_deg + 11.25) // 22.5) % 16
    return _DIRS_16[idx]

def _fmt_range(my_lat, my_lon, tgt_lat, tgt_lon):
    # Return "DIR miles / km" or empty if coords missing/invalid
    def _isnan(x):
        try:
            return isinstance(x, float) and x != x
        except Exception:
            return True
    if any(v is None for v in (my_lat,my_lon,tgt_lat,tgt_lon)):
        return ""
    if any(_isnan(v) for v in (my_lat,my_lon,tgt_lat,tgt_lon)):
        return ""
    try:
        km = _haversine_km(my_lat, my_lon, tgt_lat, tgt_lon)
        mi = km * 0.621371
        brg = _initial_bearing_deg(my_lat, my_lon, tgt_lat, tgt_lon)
        return f"{_dir16(brg)} {mi:.1f} mi / {km:.1f} km"
    except Exception:
        return ""


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

# ---------------- FLEET / WHITELIST ----------------
class FleetManager:
    def __init__(self, base_dir: str):
        import os
        self.base_dir = base_dir
        self.path = os.path.join(base_dir, "fleetlist.json")
        self.enabled = False
        self.active_fleets = ["Default"]
        self.fleets = [{
            "name": "Default",
            "rules": {"default_action": "show", "autopermit": False},
            "members": []
        }]
        self.load()

    def load(self):
        import json, os
        try:
            if os.path.exists(self.path):
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.enabled = bool(data.get("enabled", False))
                self.active_fleets = list(data.get("active_fleets") or ["Default"])
                self.fleets = list(data.get("fleets") or self.fleets)
            else:
                self.save()
        except Exception as e:
            print(f"[FleetManager.load] {e!r}")
            self.save()

    def save(self):
        import json, os
        try:
            os.makedirs(self.base_dir, exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump({
                    "enabled": self.enabled,
                    "active_fleets": self.active_fleets,
                    "fleets": self.fleets
                }, f, indent=2)
        except Exception as e:
            print(f"[FleetManager.save] {e!r}")

    def list_fleet_names(self):
        return [fleet.get("name", "?") for fleet in self.fleets]

    def _compile_all(self):
        # no-op stub for compatibility
        return


    def get_active_name(self):
        if self.active_fleets and isinstance(self.active_fleets, list):
            return self.active_fleets[0]
        return "Default"

    def get_fleet(self, name: str):
        name = (name or "Default").strip()
        for fl in self.fleets:
            if fl.get("name") == name:
                return fl
        return None

    def list_members(self, name: str):
        fl = self.get_fleet(name)
        if not fl:
            return []
        return list(fl.get("members") or [])

    
    def add_member(self, name_or_callsign, callsign=None, **kwargs):
        """EXPLICIT MODE: store exactly what the user entered (uppercased).
        Supports both call styles:
          add_member(name, callsign)  OR  add_member(callsign, fleet_name=name)
        Returns True if added, False if already present. Never raises.
        """
        try:
            fleet_name_kw = kwargs.get('fleet_name')
            if callsign is None and fleet_name_kw is not None:
                token = (name_or_callsign or '').strip().upper()
                name = (fleet_name_kw or 'Default').strip()
            else:
                name = (name_or_callsign or 'Default').strip()
                token = (callsign or '').strip().upper()

            fl = self.get_fleet(name)
            if not fl:
                fl = {'name': name, 'rules': {'default_action': 'show', 'autopermit': False}, 'members': []}
                self.fleets.append(fl)

            members = fl.setdefault('members', [])
            if token and token not in members:
                members.append(token)
                try:
                    members.sort()
                except Exception:
                    pass
                self.save()
                return True
            return False
        except Exception:
            return False





    def remove_member(self, name_or_callsign, callsign=None, **kwargs) -> bool:
        """Compatibility:
        - remove_member(name, callsign)
        - remove_member(callsign, fleet_name=name)
        Returns True if removed, False otherwise. Never raises.
        """
        try:
            fleet_name_kw = kwargs.get('fleet_name')
            if callsign is None and fleet_name_kw is not None:
                cs = (name_or_callsign or '').strip().upper()
                name = (fleet_name_kw or 'Default').strip()
            else:
                name = (name_or_callsign or 'Default').strip()
                cs = (callsign or '').strip().upper()

            base = base_callsign(cs) if 'base_callsign' in globals() else cs.split('-')[0]
            fl = self.get_fleet(name)
            if not fl:
                return False
            members = fl.get('members') or []
            if base in members:
                members.remove(base)
                self.save()
                return True
            return False
        except Exception:
            return False
    def has_member(self, name: str, callsign: str) -> bool:
        cs = (callsign or "").strip().upper()
        base = base_callsign(cs) if 'base_callsign' in globals() else cs.split('-')[0]
        fl = self.get_fleet(name)
        if not fl:
            return False
        members = fl.get("members") or []
        return base in members

    def _ensure_fleet(self, name: str):
        fl = self.get_fleet(name)
        if fl:
            return fl
        fl = {"name": name, "rules": {"default_action": "show", "autopermit": False}, "members": []}
        self.fleets.append(fl)
        try:
            # keep names sorted but always keep Default first if present
            self.fleets.sort(key=lambda f: (f.get("name") != "Default", f.get("name","")))
        except Exception:
            pass
        self.save()
        return fl

    def set_active(self, name: str) -> bool:
        """Set the active fleet name and persist. Returns True if changed/ok."""
        try:
            name = (name or "Default").strip()
            self._ensure_fleet(name)
            if not isinstance(self.active_fleets, list):
                self.active_fleets = []
            if not self.active_fleets or self.active_fleets[0] != name:
                self.active_fleets = [name]
                self.save()
            return True
        except Exception:
            return False

class UppercaseLineEdit(QLineEdit):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        font = QtGui.QFont("VT323", 16)  # keep larger 16pt for callsign fields
        self.setFont(font)
        self.setMaxLength(10)
        self.setAlignment(Qt.AlignCenter)
        fm = QtGui.QFontMetrics(font)
        self.setFixedWidth(int(fm.horizontalAdvance('M') * 11.5))
        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)

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


class ClickableBrowser(QTextBrowser):
    anchorDoubleClicked = pyqtSignal(QUrl)
    def mouseDoubleClickEvent(self, e):
        pos = e.pos()
        href = self.anchorAt(pos)
        if href:
            self.anchorDoubleClicked.emit(QUrl(href))
            return
        super().mouseDoubleClickEvent(e)

class ChatApp(QMainWindow):




    def _snapshot_member_selection(self):
        try:
            lst = self._get_member_list_widget()
            if lst is None:
                self._sel_snapshot_tokens = []
                return
            items = list(getattr(lst, "selectedItems", lambda: [])())
            if not items:
                curr = getattr(lst, "currentItem", lambda: None)()
                items = [curr] if curr else []
            toks = []
            for it in items:
                tok = (it.data(Qt.UserRole) or it.text() or "").strip().upper()
                if tok:
                    toks.append(tok)
            self._sel_snapshot_tokens = toks
        except Exception:
            self._sel_snapshot_tokens = []

    def _on_member_list_context(self, pos):
        try:
            lst = self._get_member_list_widget()
            if lst is None:
                return
            item = lst.itemAt(pos)
            if item is None:
                return
            base = (item.data(Qt.UserRole) or item.text() or "").strip().upper().split()[0]
            if not base:
                return
            try:
                active = self.fleet.get_active_name()
            except Exception:
                active = "Default"
            menu = QMenu(lst)
            act = QAction(f"Remove {base} from {active}", menu)
            def do_remove():
                ok = False
                try:
                    ok = bool(self.fleet.remove_member(base, fleet_name=active))
                except TypeError:
                    try:
                        ok = bool(self.fleet.remove_member(active, base))
                    except Exception:
                        ok = False
                if ok:
                    try:
                        self._populate_member_list()
                    except Exception:
                        pass
                    self.status_label.setText(f"Removed 1 member(s) from {active}.")
                else:
                    self.status_label.setText("No members were removed.")
            act.triggered.connect(do_remove)
            menu.addAction(act)
            menu.exec_(lst.mapToGlobal(pos))
        except Exception:
            pass

    def eventFilter(self, obj, event):
        try:
            from PyQt5.QtCore import QEvent, Qt
            from PyQt5.QtWidgets import QListWidget
            if isinstance(obj, QListWidget):
                if event.type() == QEvent.ContextMenu:
                    # Manual context menu build (some platforms ignore CustomContextMenuPolicy)
                    pos = event.pos()
                    item = obj.itemAt(pos)
                    if item is not None:
                        base = (item.data(Qt.UserRole) or item.text() or "").strip().upper().split()[0]
                        active = self.fleet.get_active_name() if hasattr(self.fleet,'get_active_name') else 'Default'
                        menu = QMenu(obj)
                        act = QAction(f"Remove {base} from {active}", menu)
                        def do_remove():
                            ok = False
                            try:
                                ok = bool(self.fleet.remove_member(base, fleet_name=active))
                            except TypeError:
                                try:
                                    ok = bool(self.fleet.remove_member(active, base))
                                except Exception:
                                    ok = False
                            if ok:
                                try: self._populate_member_list()
                                except Exception: pass
                                self.status_label.setText(f"Removed 1 member(s) from {active}.")
                            else:
                                self.status_label.setText("No members were removed.")
                        act.triggered.connect(do_remove)
                        menu.addAction(act)
                        menu.exec_(obj.mapToGlobal(pos))
                        return True
        except Exception:
            pass
        return super().eventFilter(obj, event)

    def _get_member_list_widget(self):
        try:
            for name in ("member_list","whitelist_list","fleet_members","membersList","list_members"):
                w = getattr(self, name, None)
                if w is not None:
                    return w
        except Exception:
            pass
        return None

    def _snapshot_member_selection(self):
        try:
            lst = self._get_member_list_widget()
            if lst is None:
                self._sel_snapshot_tokens = []
                return
            items = list(getattr(lst, "selectedItems", lambda: [])())
            if not items:
                curr = getattr(lst, "currentItem", lambda: None)()
                items = [curr] if curr else []
            tokens = []
            import re
            BASE_RE = re.compile(r'^([A-Z0-9/]+)(?:-(\*|[0-9]{1,2}))?$')
            for it in items:
                txt = (it.data(Qt.UserRole) or it.text() or "").strip().upper()
                tok = txt.split()[0] if txt else ""
                mo = BASE_RE.match(tok)
                base = mo.group(1) if mo else tok
                if base:
                    tokens.append(base)
            self._sel_snapshot_tokens = tokens
        except Exception:
            self._sel_snapshot_tokens = []

    def _on_member_list_context(self, pos):
        try:
            lst = self._get_member_list_widget()
            if lst is None:
                return
            item = lst.itemAt(pos)
            if item is None:
                return
            base = (item.data(Qt.UserRole) or "").strip().upper()
            if not base:
                txt = (item.text() or "").strip().upper()
                base = (txt.split()[0] if txt else "")
            if not base:
                return
            try:
                active = self.fleet.get_active_name()
            except Exception:
                active = "Default"
            menu = QMenu(lst)
            act = QAction(f"Remove {base} from {active}", menu)
            def do_remove():
                ok = False
                try:
                    ok = bool(self.fleet.remove_member(base, fleet_name=active))
                except TypeError:
                    try:
                        ok = bool(self.fleet.remove_member(active, base))
                    except Exception:
                        ok = False
                if ok:
                    try:
                        self._populate_member_list()
                    except Exception:
                        pass
                    self.status_label.setText(f"Removed 1 member(s) from {active}.")
                else:
                    self.status_label.setText("No members were removed.")
            act.triggered.connect(do_remove)
            menu.addAction(act)
            menu.exec_(lst.mapToGlobal(pos))
        except Exception:
            pass

    def eventFilter(self, obj, event):
        try:
            lst = self._get_member_list_widget()
            if obj is lst:
                from PyQt5.QtCore import QEvent, Qt
                if event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
                    try:
                        self._snapshot_member_selection()
                    except Exception:
                        pass
                    self._remove_selected_members()
                    return True
        except Exception:
            pass
        return super().eventFilter(obj, event)

    def _on_member_list_context(self, pos):
        try:
            lst = getattr(self, "_get_member_list_widget", lambda: getattr(self, "member_list", None))()
            if lst is None:
                return
            item = lst.itemAt(pos)
            if item is None:
                return
            base = (item.data(Qt.UserRole) or "").strip().upper()
            if not base:
                txt = (item.text() or "").strip().upper()
                base = (txt.split()[0] if txt else "")
            if not base:
                return
            try:
                active = self.fleet.get_active_name()
            except Exception:
                active = "Default"
            menu = QMenu(lst)
            act = QAction(f"Remove {base} from {active}", menu)
            def do_remove():
                ok = False
                try:
                    ok = bool(self.fleet.remove_member(base, fleet_name=active))
                except TypeError:
                    try:
                        ok = bool(self.fleet.remove_member(active, base))
                    except Exception:
                        ok = False
                if ok:
                    try:
                        self._populate_member_list()
                    except Exception:
                        pass
                    self.status_label.setText(f"Removed 1 member(s) from {active}.")
                else:
                    self.status_label.setText("No members were removed.")
            act.triggered.connect(do_remove)
            menu.addAction(act)
            menu.exec_(lst.mapToGlobal(pos))
        except Exception:
            pass

    def eventFilter(self, obj, event):
        # Intercept Delete/Backspace on the member list to remove selected
        try:
            lst = getattr(self, "_get_member_list_widget", lambda: getattr(self, "member_list", None))()
            if obj is lst:
                from PyQt5.QtCore import QEvent, Qt
                if event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
                    # Snapshot then remove
                    try:
                        self._snapshot_member_selection()
                    except Exception:
                        pass
                    self._remove_selected_members()
                    return True
        except Exception:
            pass
        return super().eventFilter(obj, event)

    def _snapshot_member_selection(self):
        """Capture current selection *before* it is potentially cleared by focus change."""
        try:
            lst = getattr(self, "_get_member_list_widget", lambda: getattr(self, "member_list", None))()
            if lst is None:
                self._sel_snapshot_tokens = []
                return
            items = list(getattr(lst, "selectedItems", lambda: [])())
            if not items:
                curr = getattr(lst, "currentItem", lambda: None)()
                items = [curr] if curr else []
            tokens = []
            import re
            BASE_RE = re.compile(r'^([A-Z0-9/]+)(?:-(\*|[0-9]{1,2}))?$')
            for it in items:
                txt = ""
                try:
                    txt = (it.data(Qt.UserRole) or "").strip().upper()
                except Exception:
                    pass
                if not txt:
                    txt = (it.text() or "").strip().upper()
                tok = txt.split()[0] if txt else ""
                mo = BASE_RE.match(tok)
                base = mo.group(1) if mo else tok
                if base:
                    tokens.append(base)
            self._sel_snapshot_tokens = tokens
        except Exception:
            self._sel_snapshot_tokens = []

    def _get_member_list_widget(self):
        try:
            for name in ("member_list","whitelist_list","fleet_members","membersList","list_members"):
                w = getattr(self, name, None)
                if w is not None:
                    return w
        except Exception:
            pass
        return None


    def _remove_selected_members(self):
        # Determine active fleet
        try:
            active = self.fleet.get_active_name()
        except Exception:
            active = (self.fleet.active_fleets[0] if getattr(self.fleet, "active_fleets", None) else "Default")

        lst = self._get_member_list_widget()
        if lst is None:
            QMessageBox.information(self, "Remove", "Member list not available.")
            return

        # Grab selection; if empty, try current item
        items = list(getattr(lst, "selectedItems", lambda: [])())
        if not items:
            curr = getattr(lst, "currentItem", lambda: None)()
            if curr:
                items = [curr]
        if not items:
            QMessageBox.information(self, "Remove", "Select a callsign to remove.")
            return

        import re
        BASE_RE = re.compile(r'^([A-Z0-9/]+)(?:-(\*|[0-9]{1,2}))?$')

        removed = 0
        for it in items:
            # Prefer stored base in UserRole; else parse first token of text
            try:
                base = (it.data(Qt.UserRole) or "").strip().upper()
            except Exception:
                base = ""
            if not base:
                txt = (it.text() or "").strip().upper()
                token = txt.split()[0] if txt else ""
                mo = BASE_RE.match(token)
                base = mo.group(1) if mo else token

            if not base:
                continue

            ok = False
            # Try both API styles
            try:
                ok = bool(self.fleet.remove_member(base, fleet_name=active))
            except TypeError:
                try:
                    ok = bool(self.fleet.remove_member(active, base))
                except Exception:
                    ok = False
            except Exception:
                ok = False

            if ok:
                removed += 1

        # Refresh list
        try:
            self._populate_member_list()
        except Exception:
            pass

        if removed:
            self.status_label.setText(f"Removed {removed} member(s) from {active}.")
        else:
            self.status_label.setText("No members were removed.")

    def _populate_member_list(self):
        """Explicit mode: render tokens exactly as stored."""
        try:
            fname = self.fleet.get_active_name()
        except Exception:
            return
        try:
            members = self.fleet.list_members(fname) or []
        except Exception:
            members = []

        lst = self._get_member_list_widget() if hasattr(self, "_get_member_list_widget") else getattr(self, "member_list", None)
        if lst is None:
            return
        try:
            lst.clear()
        except Exception:
            pass

        from PyQt5.QtWidgets import QListWidgetItem
        for m in members:
            token = (m.get("pattern") if isinstance(m, dict) else str(m)).strip().upper()
            if not token:
                continue
            try:
                item = QListWidgetItem(token)
                item.setData(Qt.UserRole, token)
                lst.addItem(item)
            except Exception:
                pass


    def _remove_selected_members(self):
        active = self.fleet.get_active_name() if getattr(self.fleet, "get_active_name", None) else (self.fleet.active_fleets[0] if self.fleet.active_fleets else "Default")
        lst = getattr(self, "member_list", None)
        if lst is None:
            QMessageBox.information(self, "Remove", "Member list not available.")
            return

        rows = list(getattr(lst, "selectedItems", lambda: [])())
        if not rows:
            curr = getattr(lst, "currentItem", lambda: None)()
            rows = [curr] if curr else []
        if not rows:
            QMessageBox.information(self, "Remove", "Select a callsign to remove.")
            return

        import re
        BASE_RE = re.compile(r'^([A-Z0-9/]+)(?:-(\*|[0-9]{1,2}))?$')

        removed = 0
        for it in rows:
            txt = (it.text() or it.data(Qt.UserRole) or "").strip().upper()
            token = txt.split()[0] if txt else ""
            mo = BASE_RE.match(token)
            base = mo.group(1) if mo else token
            if not base:
                continue
            ok = False
            try:
                ok = bool(self.fleet.remove_member(base, fleet_name=active))
            except TypeError:
                ok = bool(self.fleet.remove_member(active, base))
            except Exception:
                ok = False
            if ok:
                removed += 1

        try:
            self._populate_member_list()
        except Exception:
            pass

        if removed:
            self.status_label.setText(f"Removed {removed} member(s) from {active}.")
        else:
            self.status_label.setText("No members were removed.")


    def _get_member_list_widget(self):
        """Return the QListWidget that holds fleet members. Tries several attribute names,
        and falls back to the first QListWidget with items if ambiguous."""
        try:
            candidates = []
            for name in ("member_list", "whitelist_list", "fleet_members", "membersList", "list_members"):
                w = getattr(self, name, None)
                if w is not None:
                    candidates.append(w)
            # Fallback: scan attributes for any QListWidget-like (duck-typed by methods used)
            if not candidates:
                for name, w in self.__dict__.items():
                    try:
                        if hasattr(w, "selectedItems") and hasattr(w, "count") and hasattr(w, "item"):
                            candidates.append(w)
                    except Exception:
                        pass
            # Prefer one that currently has items
            for w in candidates:
                try:
                    if w.count() > 0:
                        return w
                except Exception:
                    pass
            return candidates[0] if candidates else None
        except Exception:
            return None

    def _on_member_selection_changed(self):
        try:
            lst = self._get_member_list_widget()
            if lst is None:
                self._last_member_selection = []
                return
            sel = lst.selectedItems()
            self._last_member_selection = [ (it.text() or "").strip().upper() for it in sel ]
        except Exception:
            self._last_member_selection = []

    def _on_member_selection_changed(self):
        try:
            lst = getattr(self, "member_list", None)
            if lst is None:
                return
            sel = lst.selectedItems()
            # store texts to survive focus changes
            self._last_member_selection = [ (it.text() or "").strip().upper().split()[0] for it in sel ]
        except Exception:
            self._last_member_selection = []

    def _remove_selected_members(self):
        """Remove selected callsigns from the active fleet (safe, supports single/multi)."""
        try:
            fname = self.fleet.get_active_name()
        except Exception:
            QMessageBox.information(self, "Remove", "No active fleet selected.")
            return

        lst = getattr(self, "member_list", None)
        if lst is None:
            QMessageBox.information(self, "Remove", "Member list not available.")
            return

        sel = lst.selectedItems()
        if not sel:
            curr = lst.currentItem()
            if curr:
                sel = [curr]
        if not sel:
            QMessageBox.information(self, "Remove", "Select a callsign to remove.")
            return

        # Collect base callsigns, in case rows have extra decorations
        targets = []
        for it in sel:
            cs = (it.text() or "").strip().upper().split()[0]
            if cs:
                targets.append(cs)

        removed = 0
        for cs in targets:
            try:
                ok = self.fleet.remove_member(cs, fleet_name=fname)
                if ok:
                    removed += 1
            except Exception:
                pass

        try:
            self._populate_member_list()
        except Exception:
            pass

        if removed:
            self.status_label.setText(f"Removed {removed} member(s) from {fname}.")
        else:
            self.status_label.setText("No members were removed.")


    def _fleet_ui_remove_selected(self):
        # Active fleet name
        try:
            fname = self.fleet.get_active_name()
        except Exception:
            QMessageBox.information(self, "Remove member", "No active fleet selected.")
            return

        # Selection guard
        lst = getattr(self, "member_list", None)
        if lst is None:
            QMessageBox.information(self, "Remove member", "Member list is not available.")
            return
        curr = lst.currentItem()
        if curr is None:
            QMessageBox.information(self, "Remove member", "Select a callsign to remove.")
            return

        # Extract callsign text (strip any decorations)
        cs = (curr.text() or "").strip().upper()
        cs = cs.split()[0]

        # Perform safe remove
        removed = False
        try:
            removed = self.fleet.remove_member(fname, cs)
        except Exception as e:
            QMessageBox.warning(self, "Remove member", f"Could not remove {cs}:\n{e}")
            return

        # Update UI
        if removed:
            try:
                self._populate_member_list()
            except Exception:
                pass
            self.status_label.setText(f"Removed {base_callsign(cs)} from {fname}.")
        else:
            self.status_label.setText(f"{base_callsign(cs)} is not in {fname}.")

    def _update_beacon_hud(self, when_str: str = None):
        """Update the right-side HUD label with the last beacon time, safely on the GUI thread."""
        try:
            if when_str is None:
                try:
                    now_s = datetime.now().strftime('%H:%M:%S')
                except Exception:
                    from datetime import datetime as _dt
                    now_s = _dt.now().strftime('%H:%M:%S')
            else:
                now_s = when_str

            label_text = f"Last Beacon {now_s}"
            # Ensure we update on the GUI thread
            def _do():
                try:
                    if hasattr(self, 'beacon_time_label') and self.beacon_time_label is not None:
                        self.beacon_time_label.setText(label_text)
                except Exception:
                    pass

            if QtCore.QThread.currentThread() is self.thread():
                _do()
            else:
                QtCore.QTimer.singleShot(0, _do)

        except Exception:
            pass

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Robust Chat v1.3.9.c")
        self.resize(1340, 980)

        self.ser: Serial = None
        self.reader_thread: SerialReaderThread = None
        self.recent_sent = deque(maxlen=48)
        self.echo_window_s = 3.0
        self._tx_gate = False
        self._tx_count = 0

        self.ack_counter = 1
        self.chat_items = []
        self.sent_by_ack = {}
        self.retry_timers = {}
        self.auto_ack_enabled = True
        self._last_log_path = ""

        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.fleet = FleetManager(base_dir)
        self.fleet.load()
        self.fleet_only_heartbeat = False
        self.fleet_auto_ack_nonmembers = False

        # My last known position for range/bearing
        self.my_last_lat = float('nan')
        self.my_last_lon = float('nan')

        self.beacon_timer = QTimer(self)
        self.beacon_timer.setInterval(15 * 60 * 1000)
        self.beacon_timer.timeout.connect(self._send_beacon)

        self.HEARTBEAT_TTL_S = 20 * 60
        self.heartbeat_seen = {}
        self.heartbeat_gc_timer = QTimer(self)
        self.heartbeat_gc_timer.setInterval(30 * 1000)
        self.heartbeat_gc_timer.timeout.connect(self._heartbeat_update_view)
        self.heartbeat_gc_timer.start()

        central = QWidget(); self.setCentralWidget(central)
        root = QVBoxLayout(central); root.setSpacing(12)

        # --- Top layout (Serial + Fleet Manager + Frequencies)
        top_layout = QHBoxLayout(); top_layout.setSpacing(12)

        # Serial group
        ser_group = QGroupBox("Serial")
        ser_group.setFont(QtGui.QFont('VT323', 18))
        ser_layout = QHBoxLayout(ser_group); ser_layout.setSpacing(8)

        self.port_combo = QComboBox(); self.port_combo.setFixedWidth(220)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_ports)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.open_port)

        self.disconnect_btn = QPushButton("Disconnect")
        self.disconnect_btn.setEnabled(False); self.disconnect_btn.clicked.connect(self.close_port)

        self.enter_kiss_btn = QPushButton("Enter KISS")
        self.enter_kiss_btn.setEnabled(False); self.enter_kiss_btn.clicked.connect(self._enter_kiss_mode)

        ser_layout.addWidget(self.port_combo)
        ser_layout.addWidget(refresh_btn)
        ser_layout.addWidget(self.connect_btn)
        ser_layout.addWidget(self.disconnect_btn)
        ser_layout.addWidget(self.enter_kiss_btn)
        ser_layout.addStretch(1)

        ser_group.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        QtCore.QTimer.singleShot(0, lambda: ser_group.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Maximum))

        # Fleet Manager UI
        fleet_group = QGroupBox("Fleet Manager")
        fleet_group.setFont(QtGui.QFont('VT323', 18))
        fg_layout = QVBoxLayout(fleet_group); fg_layout.setSpacing(6)
        fg_layout.setContentsMargins(12, 12, 12, 12)

        row1 = QHBoxLayout(); row1.setSpacing(8)
        self.fleet_enabled_check_top = QCheckBox("Enable Fleet")
        self.fleet_enabled_check_top.setChecked(self.fleet.enabled)
        self.fleet_enabled_check_top.toggled.connect(self._toggle_fleet_enabled)
        self.fleet_enabled_check_top.setFont(QtGui.QFont('VT323', 14))

        self.group_combo = QComboBox()
        self._refresh_group_combo()
        self.group_combo.currentTextChanged.connect(self._on_group_changed)
        self.group_combo.setFont(QtGui.QFont('VT323', 14))
        self.group_combo.setMinimumWidth(220)

        add_group_btn = QPushButton("Add Group")
        add_group_btn.clicked.connect(self._add_group_dialog)

        active_label = QLabel("Active:")
        active_label.setFont(QtGui.QFont('VT323', 14))

        row1.addWidget(self.fleet_enabled_check_top)
        row1.addSpacing(8)
        row1.addWidget(active_label)
        row1.addWidget(self.group_combo)
        row1.addWidget(add_group_btn)
        row1.addStretch(1)
        fg_layout.addLayout(row1)

        self.member_list = QListWidget()
        self.member_list.setSelectionMode(self.member_list.ExtendedSelection)
        self.member_list.setFont(QtGui.QFont('VT323', 14))
        fg_layout.addWidget(self.member_list, 1)
        self._populate_member_list()

        row2 = QHBoxLayout(); row2.setSpacing(8)
        add_call_btn = QPushButton("Add Callsign/Pattern")
        add_call_btn.clicked.connect(self._add_callsign_dialog)

        remove_btn = QPushButton("Remove Selected")
        remove_btn.clicked.connect(self._remove_selected_members)

        row2.addWidget(add_call_btn)
        row2.addWidget(remove_btn)
        row2.addStretch(1)
        fg_layout.addLayout(row2)

        # Frequencies
        freq_group = QGroupBox("Frequencies")
        freq_group.setFont(QtGui.QFont('VT323', 18))
        freq_layout = QVBoxLayout(freq_group)
        freq_layout.setSpacing(4)
        freq_layout.setContentsMargins(12, 12, 12, 12)

        for freq in ["7.0903 MHz", "10.1423 MHz", "14.109 MHz"]:
            lbl = QLabel(freq)
            lbl.setFont(QtGui.QFont('VT323', 14))
            freq_layout.addWidget(lbl)

        freq_group.setFixedWidth(250)
        freq_group.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        QtCore.QTimer.singleShot(0, lambda: freq_group.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Maximum))

        self.banner = QLabel("ROBUST CHAT")
        _bf = QtGui.QFont('VT323', 16, QtGui.QFont.Bold)
        self.banner.setFont(_bf)
        self.banner.setAlignment(Qt.AlignCenter)
        self.banner.setStyleSheet(f"color: {COLOR_SENT};")
        try:
            self.banner.setWordWrap(True)
            self.banner.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Maximum)
        except Exception:
            pass
        ser_col_w = QWidget()
        ser_col = QVBoxLayout(ser_col_w); ser_col.setSpacing(6); ser_col.setContentsMargins(0,0,0,0)
        ser_col.addWidget(self.banner)
        ser_col.addWidget(ser_group)
        top_layout.addWidget(ser_col_w, 1, Qt.AlignTop)
        top_layout.addWidget(fleet_group, 1, Qt.AlignTop)
        top_layout.addWidget(freq_group, 0, Qt.AlignTop)
        root.addLayout(top_layout)

        # Callsign + toggles
        ctl = QHBoxLayout(); ctl.setSpacing(8)
        lbl_to = QLabel("To"); lbl_from = QLabel("From")
        lbl_to.setAlignment(Qt.AlignRight); lbl_from.setAlignment(Qt.AlignRight)

        self.target_edit = UppercaseLineEdit(); self.target_edit.setPlaceholderText("G4ABC-7 or CQ")
        self.mycall_edit  = UppercaseLineEdit(); self.mycall_edit.setPlaceholderText("M0OLI")

        self.hide_mon_check = QCheckBox("Hide device/monitor lines"); self.hide_mon_check.setChecked(True)
        self.kiss_perm_toggle = QCheckBox("KISS Mode (permanent)"); self.kiss_perm_toggle.toggled.connect(self._toggle_kiss_permanent)

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

        # Messages + Heartbeat
        title_row = QHBoxLayout(); title_row.setSpacing(8)
        recv_title = QLabel("Messages")
        recv_title.setFont(QtGui.QFont('VT323', 18))
        recv_title.setStyleSheet(f"color: {COLOR_SENT};")
        title_row.addWidget(recv_title)
        title_row.addStretch(1)

        self.fleet_enabled_check = QCheckBox("Fleet whitelist")
        self.fleet_enabled_check.setChecked(self.fleet.enabled)
        self.fleet_enabled_check.toggled.connect(self._toggle_fleet_enabled)
        title_row.addWidget(self.fleet_enabled_check)

        self.fleet_heartbeat_check = QCheckBox("Fleet only in Heartbeat")
        self.fleet_heartbeat_check.setChecked(False)
        self.fleet_heartbeat_check.toggled.connect(self._toggle_fleet_heartbeat)
        title_row.addWidget(self.fleet_heartbeat_check)

        self.clear_recv_btn = QPushButton("Clear Message Window")
        self.clear_recv_btn.clicked.connect(self._clear_receive_window)
        title_row.addWidget(self.clear_recv_btn)
        root.addLayout(title_row)

        recv_heartbeat_layout = QHBoxLayout(); recv_heartbeat_layout.setSpacing(8)

        self.recv_text = ClickableBrowser(); self.recv_text.setReadOnly(True)
        self.recv_text.setMinimumWidth(760)
        self.recv_text.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.recv_text.setOpenLinks(False)
        self.recv_text.anchorClicked.connect(self._on_anchor_clicked)
        self.recv_text.anchorClicked.connect(self._handle_callsign_click)
        recv_heartbeat_layout.addWidget(self.recv_text, 1)

        heartbeat_container = QWidget()
        heartbeat_layout = QVBoxLayout(heartbeat_container); heartbeat_layout.setSpacing(8)
        self.beacon_check = QCheckBox("15 min Beacons")
        self.beacon_check.toggled.connect(self._toggle_beaconing)
        self.heartbeat_text = QTextEdit(); self.heartbeat_text.setReadOnly(True)
        font = QtGui.QFont("VT323", 14)
        fm = QtGui.QFontMetrics(font)
        char_w = fm.horizontalAdvance('M')
        self.heartbeat_text.setFixedWidth(int(char_w * 17.5))
        heartbeat_layout.addWidget(self.beacon_check)
        heartbeat_layout.addWidget(self.heartbeat_text)
        recv_heartbeat_layout.addWidget(heartbeat_container)
        root.addLayout(recv_heartbeat_layout)

        # Send section
        send_title = QLabel("Send Message")
        send_title.setFont(QtGui.QFont('VT323', 18))
        send_title.setStyleSheet(f"color: {COLOR_SENT};")
        root.addWidget(send_title)

        send_row = QHBoxLayout(); send_row.setSpacing(8)

        self.send_edit = QTextEdit()
        self.send_edit.setObjectName("sendEdit")
        self.send_edit.setFont(QtGui.QFont("VT323", 14))
        fm = QtGui.QFontMetrics(self.send_edit.font())
        self.send_edit.setFixedHeight(fm.lineSpacing() * 3 + 16)

        self.send_btn = QPushButton("SEND")
        self.send_btn.setFixedWidth(178)
        self.send_btn.clicked.connect(self.send_message)
        self.sc_send1 = QShortcut(QtGui.QKeySequence("Ctrl+Return"), self, activated=self.send_message)
        self.sc_send2 = QShortcut(QtGui.QKeySequence("Ctrl+Enter"),  self, activated=self.send_message)

        self.gps_btn = QPushButton("GPS SEND")
        self.gps_btn.setFixedWidth(178)
        self.gps_btn.clicked.connect(self.send_gps_position)

        send_row.addWidget(self.send_edit, 1)
        send_row.addWidget(self.send_btn)
        send_row.addWidget(self.gps_btn)
        root.addLayout(send_row)

        # Status bar
        sb = QStatusBar()
        self.setStatusBar(sb)
        self.status_label = QtWidgets.QLabel("Disconnected  |  Reminder: WARNING: Changing KISS condition will PTT, Disconnect Data cable from radio before changing KISS. Turn KISS OFF to chat")
        sb.addWidget(self.status_label)


        # Right-side HUD label for last beacon time
        self.beacon_time_label = QtWidgets.QLabel("Last Beacon —")
        self.beacon_time_label.setMinimumWidth(170)
        self.beacon_time_label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        sb.addPermanentWidget(self.beacon_time_label, 0)
        self.refresh_ports()

    # -------- Fleet Manager UI helpers --------
    def _refresh_group_combo(self):
        names = self.fleet.list_fleet_names()
        self.group_combo.blockSignals(True)
        self.group_combo.clear()
        for n in names:
            self.group_combo.addItem(n)
        if self.fleet.active_fleets:
            active = self.fleet.active_fleets[0]
            idx = self.group_combo.findText(active)
            if idx >= 0:
                self.group_combo.setCurrentIndex(idx)
        self.group_combo.blockSignals(False)


    def _toggle_fleet_enabled(self, on: bool):
        self.fleet.enabled = bool(on)
        self.fleet.save()
        self.fleet_enabled_check.blockSignals(True)
        self.fleet_enabled_check.setChecked(on)
        self.fleet_enabled_check.blockSignals(False)
        self.fleet_enabled_check_top.blockSignals(True)
        self.fleet_enabled_check_top.setChecked(on)
        self.fleet_enabled_check_top.blockSignals(False)
        self.status_label.setText(f"Fleet whitelist {'ENABLED' if on else 'disabled'}.")
        self._rebuild_chat_view()
        self._heartbeat_update_view()

    def _toggle_fleet_heartbeat(self, on: bool):
        self.fleet_only_heartbeat = bool(on)
        self._heartbeat_update_view()

    def _on_group_changed(self, name: str):
        if not name: return
        self.fleet.set_active(name)
        self._populate_member_list()
        self.status_label.setText(f"Active Fleet: {name}")
        self._rebuild_chat_view()
        self._heartbeat_update_view()

    def _add_group_dialog(self):
        dlg = QInputDialog(self)
        dlg.setWindowTitle("Add Group")
        dlg.setLabelText("Group name:")
        dlg.setTextValue("")
        dlg.setFont(QtGui.QFont('VT323', 14))
        le = dlg.findChild(QLineEdit)
        if le:
            le.setFont(QtGui.QFont('VT323', 14))
            le.setMinimumWidth(280)
        if dlg.exec_() == QInputDialog.Accepted:
            name = dlg.textValue().strip()
            if not name:
                return
            if self.fleet.add_group(name):
                self._refresh_group_combo()
                self._populate_member_list()
                self.status_label.setText(f"Group '{name}' created and set active.")

    def _add_callsign_dialog(self):
        active = self.fleet.active_fleets[0] if self.fleet.active_fleets else "Default"
        dlg = QInputDialog(self)
        dlg.setWindowTitle("Add Callsign/Pattern")
        dlg.setLabelText("Enter callsign or pattern (wildcards: * ?):")
        dlg.setTextValue("M0OLI")
        dlg.setFont(QtGui.QFont('VT323', 14))
        le = dlg.findChild(QLineEdit)
        if le:
            le.setFont(QtGui.QFont('VT323', 14))
            le.setMinimumWidth(320)
        if dlg.exec_() == QInputDialog.Accepted:
            txt = dlg.textValue().strip().upper()
            if not txt:
                return
            mode = "glob" if any(ch in txt for ch in "*?") else "exact"
            if self.fleet.add_member(txt, fleet_name=active, mode=mode, action="show", autopermit=True):
                self._populate_member_list()
                self.status_label.setText(f"Added '{txt.upper()}' to Fleet '{active}'.")

    def _remove_selected_members(self):
        active = self.fleet.active_fleets[0] if self.fleet.active_fleets else "Default"
        rows = self.member_list.selectedItems()
        if not rows: return
        for it in rows:
            pat = it.data(Qt.UserRole)
            self.fleet.remove_member(pat, fleet_name=active)
        self._populate_member_list()
        self.status_label.setText(f"Removed {len(rows)} entr{'y' if len(rows)==1 else 'ies'} from Fleet '{active}'.")
        self._rebuild_chat_view()
        self._heartbeat_update_view()

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
                msg = QMessageBox(self)
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
            msg = QMessageBox(self)
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
            for tid in list(self.retry_timers.values()):
                try: tid.stop()
                except Exception: pass
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
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Warning); msg.setWindowTitle("Not connected")
            msg.setText("Open a COM port first."); msg.exec_()
            return False
        try:
            self.ser.write(data); return True
        except Exception as e:
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Critical); msg.setWindowTitle("Write error")
            msg.setText(str(e)); msg.exec_(); return False

    def _send_cmd(self, cmd: str):
        return self._write_raw(ESC + (cmd + "\r").encode("utf-8", errors="replace"))

    def _write_line(self, text: str):
        if not self._tx_gate: return False
        return self._write_raw((text + "\r").encode("utf-8", errors='replace'))

    def _ptt_guard(self, func):
        if not (self.ser and self.ser.is_open):
            msg = QMessageBox(self)
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
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Information); msg.setWindowTitle("Entered KISS")
        msg.setText("Entered KISS MODE (@K) and saved with %ZS.\nTo chat again, turn KISS OFF.")
        msg.exec_()
        self.status_label.setText("Entered KISS MODE (@K). Chat requires KISS OFF.")

    def _toggle_kiss_permanent(self, on: bool):
        if on:
            self._send_cmd("@KP1"); QtCore.QThread.msleep(80); self._send_cmd("%ZS")
            self.status_label.setText("KISS Permanent ENABLED (@KP1), saved. Chat requires KISS OFF.")
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Question); msg.setWindowTitle("Enter KISS now?")
            msg.setText("KISS Permanent is ON and saved.\nDo you also want to ENTER KISS MODE now (@K then %ZS)?")
            msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No); msg.setDefaultButton(QMessageBox.No)
            if msg.exec_() == QMessageBox.Yes:
                self._send_cmd("@K"); QtCore.QThread.msleep(120); self._send_cmd("%ZS")
                info = QMessageBox(self)
                info.setIcon(QMessageBox.Information); info.setWindowTitle("Entered KISS")
                info.setText("Entered KISS MODE (@K) and saved with %ZS.\nTo chat again, turn KISS OFF."); info.exec_()
                self.status_label.setText("Entered KISS MODE (@K). Chat requires KISS OFF.")
        else:
            self._send_cmd("@KP0"); QtCore.QThread.msleep(80); self._send_cmd("%ZS")
            QtCore.QThread.msleep(120); self._write_raw(bytes([192,255,192,13]))
            self.status_label.setText("KISS disabled (@KP0) & saved; Exit KISS bytes sent. Ready for chat.")
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Information); msg.setWindowTitle("KISS OFF")
            msg.setText("KISS disabled (@KP0), saved with %ZS, and exit bytes sent.\nReady for chat.")
            msg.exec_()

    # -------- Beaconing --------
    def _toggle_beaconing(self, on: bool):
        if on:
            if not (self.ser and self.ser.is_open):
                msg = QMessageBox(self)
                msg.setIcon(QMessageBox.Warning); msg.setWindowTitle("Not connected")
                msg.setText("Open a COM port first to enable beaconing."); msg.exec_()
                self.beacon_check.setChecked(False); return
            if not self.mycall_edit.text().strip():
                msg = QMessageBox(self)
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
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Warning); msg.setWindowTitle("MyCALL missing")
            msg.setText("MyCALL is empty. Beaconing stopped."); msg.exec_()
            return
        beacon_text = f"..{mycall}"
        self._tx_gate = True
        ok = self._ptt_guard(lambda: self._write_line(beacon_text))
        self._tx_gate = False
        if ok:
            self._tx_count += 1
            self._update_beacon_hud()
            suffix = " | Beaconing ON (15 min)" if self.beacon_check.isChecked() else ""
            self.status_label.setText(f"TX: {self._tx_count}{suffix}")
# Beacon notice suppressed (moved to HUD)
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

        beacon_match = BEACON_RE.match(content)
        if beacon_match:
            call = beacon_match.group('call').upper()
            mycall = self.mycall_edit.text().strip().upper()
            if call == mycall:
                return
            if self.fleet_only_heartbeat and self.fleet.enabled:
                pol = self.fleet.match(call, "", mycall)
                if (pol.get("action") or "show") == "hide":
                    return
            self.heartbeat_seen[call] = now
            self._heartbeat_update_view()
            return

        m = LINE_RE.match(content)
        if m:
            to  = (m.group('to')  or '').upper()
            frm = (m.group('frm') or '').upper()
            msg = (m.group('msg') or '').strip()

            # Try extract target lat/lon from message text and append range/bearing
            tlat, tlon = _extract_any_latlon(msg)
            if not (math.isnan(tlat) or math.isnan(tlon) or math.isnan(self.my_last_lat) or math.isnan(self.my_last_lon)):
                rngtxt = _fmt_range(self.my_last_lat, self.my_last_lon, tlat, tlon)
                if rngtxt:
                    msg = (msg + f"  —  {rngtxt}") if msg else rngtxt

            ack_only = ACK_ONLY_RE.match(msg or "")
            if ack_only:
                ack_id = ack_only.group(1).upper()
                my = (self.mycall_edit.text() or '').upper().strip()
                item = self.sent_by_ack.get(ack_id)
                if item and my and to == my and frm == (item.get("to") or "").upper():
                    self._mark_ack_received(ack_id, from_callsign=frm)
                return

            my = (self.mycall_edit.text() or '').upper().strip()
            if my and frm == my:
                slat, slon = _extract_any_latlon(msg)
                if not (math.isnan(slat) or math.isnan(slon)):
                    self.my_last_lat, self.my_last_lon = slat, slon
                return

            for item in list(self.recent_sent):
                if now - item["ts"] <= self.echo_window_s:
                    if norm_in_full == item["full"] or (norm_in_msg and norm_in_msg == item["msg"]):
                        return

            pol = self.fleet.match(frm, to, my) if self.fleet.enabled else {"action":"show","autopermit":False}
            action = (pol.get("action") or "show").lower()

            tag = ACK_TAG_RE.search(msg or "")
            if tag and self.auto_ack_enabled and my:
                allow_auto = True
                if self.fleet.enabled and not self.fleet_auto_ack_nonmembers:
                    allow_auto = bool(pol.get("autopermit", False))
                if allow_auto:
                    ack_id = tag.group(1).upper()
                    reply = f"{frm} DE {my} ACK {ack_id}"
                    self._tx_gate = True
                    self._ptt_guard(lambda: self._write_line(reply))
                    self._tx_gate = False
                    self._add_chat_item(kind="sent", text=reply, to=frm, frm=my, ack_id=None, ack=False)

            if action == "hide" and not (my and to == my):
                return

            norm = f"{to} DE {frm}" + (f" {msg}" if msg else "")
            style = "dim" if action == "dim" and not (my and to == my) else None
            self._add_chat_item(kind="received", text=norm, to=to, frm=frm, ack_id=None, ack=False, style=style)
            return

        self._add_chat_item(kind="received", text=content, to="", frm="", ack_id=None, ack=False)

    # -------- Heartbeat maintenance --------

    def _heartbeat_update_view(self):
        now = time.time()
        expired = [c for c, ts in self.heartbeat_seen.items() if now - ts > self.HEARTBEAT_TTL_S]
        for c in expired:
            del self.heartbeat_seen[c]
        items = self.heartbeat_seen.items()
        if self.fleet_only_heartbeat and self.fleet.enabled:
            mycall = (self.mycall_edit.text() or '').strip().upper()
            items = [(c, ts) for c, ts in items if (self.fleet.match(c, "", mycall).get("action") or "show") != "hide"]
        items = sorted(items, key=lambda kv: kv[1], reverse=True)
        self.heartbeat_text.setPlainText("\n".join(c for c, ts in items))
        sb = self.heartbeat_text.verticalScrollBar()
        sb.setValue(sb.maximum())

    # -------- Message model/rendering --------
    def _add_chat_item(self, *, kind: str, text: str, to: str, frm: str, ack_id: str, ack: bool, style: str=None):
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
            "style": style or None,
        }
        if kind == "sent" and item["ack_id"]:
            self.sent_by_ack[item["ack_id"]] = item
        self.chat_items.insert(0, item)
        self._rebuild_chat_view()
        if kind == "sent" and item["ack_id"]:
            self._schedule_retry(item["ack_id"], initial=True)

    
    def _on_anchor_clicked(self, url: QUrl):
        if url.scheme() != "cs":
            return
        cs = url.path().strip("/").upper()
        my = (self.mycall_edit.text() or "").strip().upper()
        if base_callsign(cs) == base_callsign(my):
            return
        # Single-click: show menu to add to whitelist (exact or base)
        menu = QMenu(self)
        act_add_exact = QAction(f"Add {cs} to whitelist", self)
        base = base_callsign(cs)
        act_add_base  = QAction(f"Add {base} (base) to whitelist", self)
        menu.addAction(act_add_exact)
        if base != cs:
            menu.addAction(act_add_base)
        chosen = menu.exec_(QCursor.pos())
        if not chosen:
            return
        if chosen is act_add_exact:
            self._fleet_add_member(cs)
        elif chosen is act_add_base:
            self._fleet_add_member(base)

    def _on_anchor_double_click(self, url: QUrl):
        if url.scheme() != "cs":
            return
        cs = url.path().strip("/").upper()
        my = (self.mycall_edit.text() or "").strip().upper()
        if base_callsign(cs) == base_callsign(my):
            return
        self.to_edit.setText(cs)
        self.status_label.setText(f"TO set to {cs}")
    def _rebuild_chat_view(self):

        # Build a fresh HTML doc with sticky, centered date headers.
        # Messages are stored newest-first (index 0 newest). We'll insert a header
        # once per date, which naturally puts today's header at the very top.
        doc = []
        seen_dates = set()
        for item in self.chat_items:
            d = item["ts"].date()
            if d not in seen_dates:
                seen_dates.add(d)
                date_str = item["ts"].strftime("%A, %d %B %Y")
                doc.append(
                    '<div style="text-align:center; color:#888; margin:8px 0 6px 0;'
                    ' font-family:VT323,monospace">--- ' + date_str + ' ---</div>'
                )
            ts = item["ts"].strftime('%H:%M:%S')
            kind = item["kind"]
            style = item.get("style")
            color = COLOR_RECV
            if kind == "sent":
                color = COLOR_ACK if item.get("ack") else COLOR_SENT
            elif style == "dim":
                color = COLOR_DIM
            text = item["text"]
            suffix = ""
            if kind == "sent" and item.get("ack_id") and not item.get("ack"):
                if item.get("failed"):
                    suffix = "  (FAILED)"
                else:
                    a = item.get("attempt") or 1
                    mmax = item.get("max_attempts") or 3
                    suffix = f"  (attempt {a}/{mmax})"
            # Left-justified lines, full width
            rendered = (text or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;") + suffix
            line_html = f'<div style="color:{color}; font-family:VT323,monospace; text-align:left">[{ts}] {rendered}</div>'
            doc.append(line_html)

        # Replace the view content, keep scroll pinned to top (newest at top)
        self.recv_text.clear()
        if doc:
            self.recv_text.insertHtml("".join(doc))
            self.recv_text.moveCursor(QtGui.QTextCursor.Start)
            sb = self.recv_text.verticalScrollBar()
            sb.setValue(sb.minimum())
    def _mark_ack_received(self, ack_id: str, from_callsign: str = ""):
        ack_id = (ack_id or "").upper()
        item = self.sent_by_ack.get(ack_id)
        if item and not item.get("ack"):
            item["ack"] = True
            item["failed"] = False

            # stop legacy retry timer (if any)
            t = self.retry_timers.pop(ack_id, None) if hasattr(self, "retry_timers") else None
            if t:
                try:
                    t.stop()
                except Exception:
                    pass

            # stop any PTT-driven ack timers and clear state
            try:
                self._clear_ack_timers(ack_id)
            except Exception:
                pass

            # stop pending TX timer if present in state
            try:
                st = self._ack_states.get(ack_id) if hasattr(self, "_ack_states") else None
                if st and st.get("tx"):
                    try:
                        st["tx"].stop()
                    except Exception:
                        pass
                    st["tx"] = None
                if hasattr(self, "_ack_states"):
                    self._ack_states.pop(ack_id, None)
            except Exception:
                pass

            # cancel any pending start-after-TX timer (legacy)
            try:
                t0 = self.tx_end_timers.pop(ack_id, None) if hasattr(self, "tx_end_timers") else None
                if t0:
                    try:
                        t0.stop()
                    except Exception:
                        pass
            except Exception:
                pass

            try:
                self._rebuild_chat_view()
            except Exception:
                pass

            if from_callsign:
                self.status_label.setText(f"ACK {ack_id} verified from {from_callsign}.")
            else:
                self.status_label.setText(f"ACK {ack_id} verified.")
        else:
            self.status_label.setText(f"ACK {ack_id} received (no matching pending message).")

    def _schedule_retry(self, ack_id: str, initial: bool = False):
        item = self.sent_by_ack.get(ack_id)
        if not item or item.get("ack"):
            return
        a = item.get("attempt") or 1
        m = item.get("max_attempts") or 3
        delay_ms = int(6000 + random.random()*1000)
        old = self.retry_timers.get(ack_id)
        if old:
            try: old.stop()
            except Exception: pass
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(delay_ms)
        if a < m:
            timer.timeout.connect(lambda aid=ack_id: self._retry_send(aid))
            next_attempt = a + 1
            self.status_label.setText(f"Waiting for ACK {ack_id}… scheduling retry {next_attempt}/{m} in {delay_ms//1000}s.")
        else:
            timer.timeout.connect(lambda aid=ack_id: self._final_fail(aid))
            self.status_label.setText(f"Waiting for ACK {ack_id} after attempt {a}/{m}… final wait {delay_ms//1000}s.")
        self.retry_timers[ack_id] = timer
        self._rebuild_chat_view()
        timer.start()

    def _retry_send(self, ack_id: str):
        item = self.sent_by_ack.get(ack_id)
        if not item or item.get("ack"):
            return
        a = item.get("attempt") or 1
        m = item.get("max_attempts") or 3
        line = item["text"]
        self._tx_gate = True
        self._ptt_guard(lambda: self._write_line(line))
        self._tx_gate = False
        self.recent_sent.append({"full": _norm(line), "msg": _norm(_extract_msg_only(line)), "ts": time.time()})
        item["attempt"] = a + 1
        self._rebuild_chat_view()
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
                msg = QMessageBox(self)
                msg.setIcon(QMessageBox.Warning); msg.setWindowTitle("Blocked")
                msg.setText("That text looks like console/device output and will not be transmitted.")
                msg.exec_(); return False
            self._tx_gate = True
            ok = self._ptt_guard(lambda: self._write_line(text))
            self._tx_gate = False
            if ok:
                self._tx_count += 1
                self._update_beacon_hud()
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
                mb = QMessageBox(self)
                mb.setIcon(QMessageBox.Warning); mb.setWindowTitle("Target missing")
                mb.setText("Enter a Target callsign."); mb.exec_(); return
            if not my:
                mb = QMessageBox(self)
                mb.setIcon(QMessageBox.Warning); mb.setWindowTitle("MyCALL missing")
                mb.setText("Enter MyCALL in the From field."); mb.exec_(); return
            if not msg_tx: return

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

    # -------- GPS SEND --------
    def send_gps_position(self):
        if not (self.ser and self.ser.is_open):
            mb = QMessageBox(self)
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
                mb = QMessageBox(self)
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
                    self.my_last_lat, self.my_last_lon = lat, lon
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
            callsign = link[len("callsign:"):].strip().upper()
            if not callsign:
                return
            mb = QMessageBox(self)
            mb.setWindowTitle("Callsign action")
            mb.setText(f"{callsign}")
            btn_set = mb.addButton("Set To", QMessageBox.AcceptRole)
            btn_add = mb.addButton("Add to Fleet (active)", QMessageBox.ActionRole)
            mb.addButton("Cancel", QMessageBox.RejectRole)
            mb.exec_()
            if mb.clickedButton() == btn_set:
                self.target_edit.setText(callsign)
                self.status_label.setText(f"Set To: {callsign}")
            elif mb.clickedButton() == btn_add:
                active = self.fleet.active_fleets[0] if self.fleet.active_fleets else "Default"
                ok = self.fleet.add_member(callsign, fleet_name=active, mode="exact", action="show", autopermit=True)
                if ok:
                    self._populate_member_list()
                    self.status_label.setText(f"Added {callsign} to Fleet '{active}'.")

    def _clear_receive_window(self):
        self.recv_text.clear()
        self.chat_items.clear()
        self.sent_by_ack.clear()
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
            r'^\$(?:GP|GN|GL|GA)[A-Z]{3},',
        ]
        for p in pats:
            if re.search(p, s2, re.IGNORECASE): return True
        if s2.strip() in {"RPR>", "OK", "READY"}: return True
        return False

    def _looks_like_console(self, s: str) -> bool:
        return self._is_device_line(s) or bool(re.match(r'^(RPR>|OK|READY)$', s.strip(), re.I))

    def _show_exception(self, title: str, exc: Exception):
        err = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        msg = QMessageBox(self)
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
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Critical)
            msg.setWindowTitle("Unhandled error")
            msg.setText("An unexpected error occurred.\n\n" + err[-2000:])
            msg.exec_()
        except Exception:
            pass
    sys.excepthook = handler

def main():
    print("Link500 Teensy Robust Chat v1.3.9.c Consolidated (Explicit Fleet Mode) (2025-09-12)")
    app = QApplication(sys.argv)
    load_vt323_font()
    try:
        app.setStyleSheet(GLOBAL_QSS)
    except Exception:
        pass
    w = ChatApp()
    try:
        base_font = QtGui.QFont()
        base_font.setPointSize(14)
        app.setFont(base_font)
    except Exception:
        pass
    try:
        w.setMinimumSize(960, 600)
        w.showMaximized()
    except Exception:
        w.show()
    sys.exit(app.exec_())
    load_vt323_font()
    try:
        app.setStyleSheet(GLOBAL_QSS)
    except Exception:
        pass
    w = ChatApp()
    try:
        base_font = QtGui.QFont()
        base_font.setPointSize(14)
        app.setFont(base_font)
    except Exception:
        pass
    try:
        w.setMinimumSize(960, 600)
        w.showMaximized()
    except Exception:
        w.show()
    sys.exit(app.exec_())


    def _cardinal(self, bearing):
        dirs = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"]
        return dirs[int((bearing + 11.25)//22.5) % 16]


    def _fleet_path(self) -> str:
        import os, json
        home = os.path.expanduser("~")
        appdir = os.path.join(home, ".robust_chat")
        try:
            os.makedirs(appdir, exist_ok=True)
        except Exception:
            pass
        return os.path.join(appdir, "fleetlist.json")

    def _ensure_fleet_storage(self):
        self._fleet_file = self._fleet_path()
        if not os.path.exists(self._fleet_file):
            default = {
                "enabled": False,
                "active_fleets": ["Default"],
                "fleets": [{
                    "name": "Default",
                    "rules": {"default_action": "show", "autopermit": False},
                    "members": []
                }]
            }
            try:
                with open(self._fleet_file, "w", encoding="utf-8") as f:
                    json.dump(default, f, indent=2)
                QMessageBox.information(self, "Fleet list created",
                                        f"Fleet list was created at:\n{self._fleet_file}")
            except Exception as e:
                QMessageBox.warning(self, "Fleet list error",
                                    f"Could not create fleet list:\n{e}")
                self._load_fleet()

    def _load_fleet(self):
        import json
        self.fleet = {
            "enabled": False,
            "active_fleets": ["Default"],
            "fleets": [{
                "name": "Default",
                "rules": {"default_action": "show", "autopermit": False},
                "members": []
            }]
        }
        try:
            with open(self._fleet_file, "r", encoding="utf-8") as f:
                self.fleet = json.load(f)
        except Exception:
            pass

    def _save_fleet(self):
        import json
        try:
            with open(self._fleet_file, "w", encoding="utf-8") as f:
                json.dump(self.fleet, f, indent=2)
        except Exception as e:
            QMessageBox.warning(self, "Save error", f"Could not save fleet list:\n{e}")

    def _current_fleet_dict(self):
        try:
            name = (self.fleet.get("active_fleets") or ["Default"])[0]
            for fl in self.fleet.get("fleets", []):
                if fl.get("name") == name:
                    return fl
        except Exception:
            pass
        return self.fleet["fleets"][0]

    def _fleet_add_member(self, cs: str):
        cs = (cs or "").strip().upper()
        # normalize to base so SSID/no-SSID are equivalent
        base = base_callsign(cs)
        add = base
        fl = self._current_fleet_dict()
        members = fl.setdefault("members", [])
        if add not in members:
            members.append(add)
            try:
                members.sort()
            except Exception:
                pass
            self._save_fleet()
            self.status_label.setText(f"Added {add} to whitelist.")
        else:
            self.status_label.setText(f"{add} already in whitelist.")


if __name__ == "__main__":
    main()



# =====================
# PERSISTENCE & LOG VIEW PATCH v1.0 (2025-09-13)
# - Restores messages on startup (persisted to store/messages_v1.json)
# - Adds date separator lines (YYYY-MM-DD)
# - Adds sequential message numbers [#0001]
# - Clear Message Window also deletes persisted file
# This patch monkey-patches ChatApp methods after class definition to avoid conflicts.
# =====================
try:
    import os, json
    from datetime import datetime
    from types import MethodType

    def _persist_write_all(self):
        try:
            data = []
            for it in reversed(self.chat_items):  # oldest-first on disk
                ts = it.get("ts")
                ts_iso = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
                data.append({
                    "kind": it.get("kind"),
                    "text": it.get("text"),
                    "ts": ts_iso,
                    "ack": bool(it.get("ack")),
                    "ack_id": it.get("ack_id"),
                    "to": it.get("to"),
                    "frm": it.get("frm"),
                    "attempt": it.get("attempt"),
                    "max_attempts": it.get("max_attempts"),
                    "failed": bool(it.get("failed")),
                    "style": it.get("style"),
                    "seq": it.get("seq", None),
                })
            with open(self._msg_store_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[persist_write_all] {e!r}")

    def _persist_append(self, item):
        try:
            try:
                with open(self._msg_store_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, list):
                    data = []
            except Exception:
                data = []
            ts = item.get("ts")
            ts_iso = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
            rec = {
                "kind": item.get("kind"),
                "text": item.get("text"),
                "ts": ts_iso,
                "ack": bool(item.get("ack")),
                "ack_id": item.get("ack_id"),
                "to": item.get("to"),
                "frm": item.get("frm"),
                "attempt": item.get("attempt"),
                "max_attempts": item.get("max_attempts"),
                "failed": bool(item.get("failed")),
                "style": item.get("style"),
                "seq": item.get("seq", None),
            }
            data.append(rec)
            if len(data) > 5000:
                data = data[-5000:]
            with open(self._msg_store_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[persist_append] {e!r}")
            _persist_write_all(self)

    def _load_persisted_messages(self):
        try:
            if not os.path.exists(self._msg_store_path):
                return
            with open(self._msg_store_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                return
            restored = []
            last_seq = 0
            for d in data:
                try:
                    ts = datetime.fromisoformat(d.get("ts"))
                except Exception:
                    ts = datetime.now()
                seq = d.get("seq") or 0
                if isinstance(seq, str) and seq.isdigit():
                    seq = int(seq)
                last_seq = max(last_seq, int(seq) if isinstance(seq, int) else 0)
                restored.append({
                    "kind": d.get("kind"),
                    "text": d.get("text") or "",
                    "ts": ts,
                    "ack": bool(d.get("ack")),
                    "ack_id": d.get("ack_id"),
                    "to": (d.get("to") or "").upper(),
                    "frm": (d.get("frm") or "").upper(),
                    "attempt": d.get("attempt"),
                    "max_attempts": d.get("max_attempts"),
                    "failed": bool(d.get("failed")),
                    "style": d.get("style"),
                    "seq": int(seq) if isinstance(seq, int) and seq > 0 else None,
                })
            # Newest-first in memory
            self.chat_items = list(reversed(restored))
            # Rebuild ack index
            self.sent_by_ack.clear()
            for it in self.chat_items:
                if it.get("kind") == "sent" and it.get("ack_id"):
                    self.sent_by_ack[it["ack_id"]] = it
            # Reset sequence counter
            self._seq_next = int(last_seq) + 1 if last_seq else (len(self.chat_items) + 1)
            # Render
            try:
                self._rebuild_chat_view()
            except Exception:
                pass
        except Exception as e:
            print(f"[load_persisted_messages] {e!r}")

    # --- Patch __init__ to set up paths and load persisted messages
    _orig_init = ChatApp.__init__
    def _patched_init(self, *a, **kw):
        _orig_init(self, *a, **kw)
        try:
            self._store_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "store")
            os.makedirs(self._store_dir, exist_ok=True)
        except Exception:
            self._store_dir = os.path.dirname(os.path.abspath(__file__))
        self._msg_store_path = os.path.join(self._store_dir, "messages_v1.json")
        self._seq_next = 1
        _load_persisted_messages(self)

    ChatApp.__init__ = _patched_init
    ChatApp._persist_write_all = MethodType(_persist_write_all, ChatApp)
    ChatApp._persist_append = MethodType(_persist_append, ChatApp)
    ChatApp._load_persisted_messages = MethodType(_load_persisted_messages, ChatApp)

    # --- Wrap _add_chat_item to assign seq and persist after original behavior
    _orig_add = ChatApp._add_chat_item
    def _patched_add(self, *args, **kwargs):
        _orig_add(self, *args, **kwargs)
        try:
            # newest item is at index 0
            if self.chat_items:
                it = self.chat_items[0]
                if it.get("seq") is None:
                    it["seq"] = self._seq_next
                    self._seq_next += 1
                self._persist_append(it)
        except Exception as e:
            print(f"[patched_add seq/persist] {e!r}")
    ChatApp._add_chat_item = _patched_add

    # --- Replace _rebuild_chat_view to add date separators + numbering
    def _patched_rebuild(self):
        doc = []
        last_day = None
        for item in self.chat_items:
            try:
                ts_obj = item.get("ts")
                ts = ts_obj.strftime('%H:%M:%S') if hasattr(ts_obj, "strftime") else str(ts_obj)
                day = ts_obj.date() if hasattr(ts_obj, "date") else None
            except Exception:
                ts = ""
                day = None
            if day is not None and day != last_day:
                ds = ts_obj.strftime('%Y-%m-%d') if hasattr(ts_obj, "strftime") else ""
                doc.append(f'<div style="color:{COLOR_SENT};border-top:1px dashed {COLOR_BORDER};margin:6px 0;padding-top:6px;">— {ds} —</div>')
                last_day = day

            kind = item.get("kind")
            style = item.get("style")
            color = COLOR_RECV
            if kind == "sent":
                color = COLOR_ACK if item.get("ack") else COLOR_SENT
            elif style == "dim":
                color = COLOR_DIM
            text = item.get("text") or ""
            suffix = ""
            if kind == "sent" and item.get("ack_id") and not item.get("ack"):
                if item.get("failed"):
                    suffix = "  (FAILED)"
                else:
                    a = item.get("attempt") or 1
                    m = item.get("max_attempts") or 3
                    suffix = f"  (attempt {a}/{m})"
            seq = item.get("seq")
            prefix = f"[#{seq:04d}] " if isinstance(seq, int) and seq > 0 else ""
            safe = (prefix + text).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
            # Try to make callsigns clickable when they appear as tokens "TO DE FROM ..."
            # (use existing behavior where available; here we just colorize)
            line = f'<span style="color:{color}">[{ts}] {safe}{suffix}</span>'
            doc.append(line)
        html = "<br/>\n".join(doc)
        try:
            self.recv_text.setHtml(html)
        except Exception:
            try:
                self.recv_text.setPlainText(re.sub("<[^>]+>", "", html))
            except Exception:
                pass

    ChatApp._rebuild_chat_view = _patched_rebuild

    # --- Extend Clear button behavior to delete persisted file
    _orig_clear = ChatApp._clear_receive_window
    def _patched_clear(self):
        _orig_clear(self)
        try:
            if hasattr(self, "_msg_store_path") and os.path.exists(self._msg_store_path):
                os.remove(self._msg_store_path)
        except Exception as e:
            print(f"[patched_clear] {e!r}")
    ChatApp._clear_receive_window = _patched_clear

except Exception as _e_patch:
    try:
        print(f"[persistence_patch] install error: {_e_patch!r}")
    except Exception:
        pass



# =====================
# UI & Rendering Enhancements PATCH v1.1 (2025-09-13)
# Adds:
#  - Priority highlighting (yellow background, bold black text) for MAYDAY/SOS/PRIORITY/MEDICAL/WX ALERT
#  - Callsign lanes (TO ← FROM header row above message body)
#  - Right-aligned ACK badge
#  - "Reload Messages" menu item
#  - History cap setting (self._msg_store_limit)
#  - "Archive & Clear" button beside Clear Message Window
# =====================
try:
    from PyQt5.QtWidgets import QAction, QPushButton
    import os, json, re
    from datetime import datetime

    PRIORITY_WORDS = ("MAYDAY","SOS","PRIORITY","MEDICAL","WX","WX ALERT","WX-ALERT","DISTRESS")
    CALL_RE = r'[A-Z0-9]{1,2}\d[A-Z0-9]{1,3}(?:-[0-9]{1,2})?'
    LINE_RE2 = re.compile(rf'^(?P<to>{CALL_RE}|CQ)\s+DE\s+(?P<frm>{CALL_RE})\s*(?P<msg>.*)$', re.I)

    # Extend __init__ again to add menu, archive button, and history cap
    _orig_init_v11 = ChatApp.__init__
    def _patched_init_v11(self, *a, **kw):
        _orig_init_v11(self, *a, **kw)
        # history cap
        try:
            if not hasattr(self, "_msg_store_limit"):
                self._msg_store_limit = 5000
        except Exception:
            pass
        # File menu with Reload
        try:
            mb = self.menuBar()
            mfile = mb.addMenu("File")
            act_reload = QAction("Reload Messages", self)
            act_reload.triggered.connect(self._load_persisted_messages)
            mfile.addAction(act_reload)
        except Exception as e:
            print(f"[menu install] {e!r}")
        # Place Archive & Clear button beside Clear
        try:
            parent_layout = self.clear_recv_btn.parentWidget().layout()
            self.archive_btn = QPushButton("Archive & Clear")
            def _do_archive():
                try:
                    self._archive_and_clear()
                except Exception as e:
                    print(f"[archive btn] {e!r}")
            self.archive_btn.clicked.connect(_do_archive)
            parent_layout.addWidget(self.archive_btn)
        except Exception as e:
            print(f"[archive button] {e!r}")

    ChatApp.__init__ = _patched_init_v11

    # Archive function
    def _archive_and_clear(self):
        try:
            # Ensure archive folder
            base_dir = os.path.dirname(os.path.abspath(__file__))
            arch_dir = os.path.join(base_dir, "archive")
            os.makedirs(arch_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_path = os.path.join(arch_dir, f"messages_{ts}.json")
            # Write current persisted content if exists; else serialize from chat_items
            data = []
            try:
                if os.path.exists(self._msg_store_path):
                    with open(self._msg_store_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                else:
                    for it in reversed(self.chat_items):
                        t = it.get("ts")
                        tiso = t.isoformat() if hasattr(t, "isoformat") else str(t)
                        data.append({
                            "kind": it.get("kind"),
                            "text": it.get("text"),
                            "ts": tiso,
                            "ack": bool(it.get("ack")),
                            "ack_id": it.get("ack_id"),
                            "to": it.get("to"),
                            "frm": it.get("frm"),
                            "attempt": it.get("attempt"),
                            "max_attempts": it.get("max_attempts"),
                            "failed": bool(it.get("failed")),
                            "style": it.get("style"),
                            "seq": it.get("seq"),
                        })
            except Exception:
                pass
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            # Now clear window (also removes messages_v1.json)
            try:
                self._clear_receive_window()
            except Exception:
                pass
            try:
                self.status_label.setText(f"Archived to {os.path.basename(out_path)} and cleared.")
            except Exception:
                pass
        except Exception as e:
            print(f"[archive_and_clear] {e!r}")
    ChatApp._archive_and_clear = _archive_and_clear

    # Update persistence cap to respect self._msg_store_limit
    _orig_append_v11 = ChatApp._persist_append
    def _patched_append_v11(self, item):
        try:
            _orig_append_v11(self, item)
            # Enforce cap on disk (rewrite with last N if needed)
            if hasattr(self, "_msg_store_limit") and os.path.exists(self._msg_store_path):
                import json
                with open(self._msg_store_path, "r", encoding="utf-8") as f:
                    arr = json.load(f)
                if isinstance(arr, list) and len(arr) > int(self._msg_store_limit):
                    arr = arr[-int(self._msg_store_limit):]
                    with open(self._msg_store_path, "w", encoding="utf-8") as f:
                        json.dump(arr, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[append cap] {e!r}")
    ChatApp._persist_append = _patched_append_v11

    # Replace renderer again to add lanes, priority highlight, ack badge
    def _patched_rebuild_v11(self):
        doc = []
        last_day = None
        for item in self.chat_items:
            try:
                ts_obj = item.get("ts")
                ts = ts_obj.strftime('%H:%M:%S') if hasattr(ts_obj, "strftime") else str(ts_obj)
                day = ts_obj.date() if hasattr(ts_obj, "date") else None
            except Exception:
                ts = ""
                day = None
            if day is not None and day != last_day:
                ds = ts_obj.strftime('%Y-%m-%d') if hasattr(ts_obj, "strftime") else ""
                doc.append(f'<div style="color:{COLOR_SENT};border-top:1px dashed {COLOR_BORDER};margin:6px 0;padding-top:6px;">— {ds} —</div>')
                last_day = day

            kind = item.get("kind")
            style = item.get("style")
            color = COLOR_RECV
            if kind == "sent":
                color = COLOR_ACK if item.get("ack") else COLOR_SENT
            elif style == "dim":
                color = COLOR_DIM

            raw_text = item.get("text") or ""
            seq = item.get("seq")
            prefix = f"[#{seq:04d}] " if isinstance(seq, int) and seq > 0 else ""

            # Detect to/from/message
            to_cs, frm_cs, body = "", "", raw_text
            m = LINE_RE2.match(raw_text.strip())
            if m:
                to_cs = (m.group("to") or "").upper()
                frm_cs = (m.group("frm") or "").upper()
                body = (m.group("msg") or "").strip()

            # Priority highlighting?
            def is_priority(s):
                S = s.upper()
                return any(w in S for w in PRIORITY_WORDS)
            priority = is_priority(raw_text)

            # ACK badge (right-aligned)
            ack_badge = ""
            if item.get("ack_id"):
                aid = item["ack_id"]
                ack_badge = f'<span style="float:right; border:1px solid {COLOR_BORDER}; padding:1px 4px; border-radius:3px; opacity:0.85;">ACK:{aid}</span>'

            # Build lanes row (callsigns header)
            if to_cs or frm_cs:
                lanes = (
                    f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                    f'  <div style="min-width:180px;"><span style="color:{COLOR_SENT};">TO</span> <b>{to_cs}</b></div>'
                    f'  <div style="text-align:center;flex:1;"><span style="opacity:0.6;">{ts}</span></div>'
                    f'  <div style="min-width:220px;text-align:right;"><span style="color:{COLOR_SENT};">DE</span> <b>{frm_cs}</b>{ack_badge}</div>'
                    f'</div>'
                )
            else:
                # No parse — just place timestamp and badge
                lanes = (
                    f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                    f'  <div style="min-width:180px;"></div>'
                    f'  <div style="text-align:center;flex:1;"><span style="opacity:0.6;">{ts}</span></div>'
                    f'  <div style="min-width:220px;text-align:right;">{ack_badge}</div>'
                    f'</div>'
                )

            # Body line (with priority style if any)
            safe_body = (prefix + body).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
            if priority:
                body_html = f'<div style="margin:2px 0;padding:4px 6px; background:#FFFF00; color:#000000; font-weight:700; border-radius:3px;"><span style="color:#000000;">{safe_body}</span></div>'
            else:
                body_html = f'<div style="margin:2px 0;"><span style="color:{color}">{safe_body}</span></div>'

            # Combine
            doc.append(lanes)
            doc.append(body_html)

        html = "<br/>\n".join(doc)
        try:
            self.recv_text.setHtml(html)
        except Exception:
            try:
                import re as _re
                self.recv_text.setPlainText(_re.sub("<[^>]+>", "", html))
            except Exception:
                pass

    ChatApp._rebuild_chat_view = _patched_rebuild_v11

except Exception as _e_patch2:
    try:
        print(f"[enhancements_patch] install error: {_e_patch2!r}")
    except Exception:
        pass



# =====================
# Persistence Hardening Patch v1.1.1 (2025-09-13)
# Ensures the JSON appears by:
#  - Creating the "store" folder next to the script (if missing)
#  - Setting a periodic flush timer (every 30s) to write all messages to disk
#  - Emitting a status message with the exact file path upon first successful write
#  - Adding "File → Open Store Folder" to open the folder in Explorer
# =====================
try:
    import os, json, sys
    from datetime import datetime
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QAction
    from types import MethodType

    # ---- helpers ----
    def _ensure_store_path(self):
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        except Exception:
            base_dir = os.getcwd()
        try:
            self._store_dir = os.path.join(base_dir, "store")
            os.makedirs(self._store_dir, exist_ok=True)
        except Exception:
            self._store_dir = base_dir
        self._msg_store_path = os.path.join(self._store_dir, "messages_v1.json")
        if not hasattr(self, "_seq_next"):
            self._seq_next = 1

    def _persist_write_all_hardened(self):
        try:
            if not hasattr(self, "_msg_store_path") or not self._msg_store_path:
                _ensure_store_path(self)
            data = []
            for it in reversed(getattr(self, "chat_items", [])):  # oldest-first
                ts = it.get("ts")
                ts_iso = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
                data.append({
                    "kind": it.get("kind"),
                    "text": it.get("text"),
                    "ts": ts_iso,
                    "ack": bool(it.get("ack")),
                    "ack_id": it.get("ack_id"),
                    "to": it.get("to"),
                    "frm": it.get("frm"),
                    "attempt": it.get("attempt"),
                    "max_attempts": it.get("max_attempts"),
                    "failed": bool(it.get("failed")),
                    "style": it.get("style"),
                    "seq": it.get("seq", None),
                })
            with open(self._msg_store_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            # Show once
            if not getattr(self, "_persist_path_announced", False):
                try:
                    self.status_label.setText(f"Persistence: {self._msg_store_path}")
                except Exception:
                    pass
                self._persist_path_announced = True
        except Exception as e:
            try:
                print(f"[persist_write_all_hardened] {e!r}")
            except Exception:
                pass

    def _persist_append_hardened(self, item):
        try:
            if not hasattr(self, "_msg_store_path") or not self._msg_store_path:
                _ensure_store_path(self)
            try:
                with open(self._msg_store_path, "r", encoding="utf-8") as f:
                    arr = json.load(f)
                if not isinstance(arr, list):
                    arr = []
            except Exception:
                arr = []
            ts = item.get("ts")
            ts_iso = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
            rec = {
                "kind": item.get("kind"),
                "text": item.get("text"),
                "ts": ts_iso,
                "ack": bool(item.get("ack")),
                "ack_id": item.get("ack_id"),
                "to": item.get("to"),
                "frm": item.get("frm"),
                "attempt": item.get("attempt"),
                "max_attempts": item.get("max_attempts"),
                "failed": bool(item.get("failed")),
                "style": item.get("style"),
                "seq": item.get("seq", None),
            }
            arr.append(rec)
            # Cap
            limit = int(getattr(self, "_msg_store_limit", 5000) or 5000)
            if len(arr) > limit:
                arr = arr[-limit:]
            with open(self._msg_store_path, "w", encoding="utf-8") as f:
                json.dump(arr, f, ensure_ascii=False, indent=2)
            if not getattr(self, "_persist_path_announced", False):
                try:
                    self.status_label.setText(f"Persistence: {self._msg_store_path}")
                except Exception:
                    pass
                self._persist_path_announced = True
        except Exception as e:
            try:
                print(f"[persist_append_hardened] {e!r}")
            except Exception:
                pass
            _persist_write_all_hardened(self)

    # ---- patch init to enforce path, timer and menu ----
    _orig_init_p = ChatApp.__init__
    def _patched_init_p(self, *a, **kw):
        _orig_init_p(self, *a, **kw)
        _ensure_store_path(self)
        # periodic flush
        try:
            self._persist_timer = QTimer(self)
            self._persist_timer.setInterval(30 * 1000)  # 30s
            self._persist_timer.timeout.connect(lambda: _persist_write_all_hardened(self))
            self._persist_timer.start()
        except Exception as e:
            print(f"[persist timer] {e!r}")
        # File → Open Store Folder
        try:
            mb = self.menuBar()
            mfile = None
            for i in range(mb.children().__len__()):
                pass
            # Create or reuse "File" menu
            try:
                mfile = next((m for m in mb.findChildren(type(mb.addMenu('x')))), None)
            except Exception:
                mfile = mb.addMenu("File")
            act_open = QAction("Open Store Folder", self)
            def _open_folder():
                folder = getattr(self, "_store_dir", None) or os.path.dirname(os.path.abspath(__file__))
                try:
                    if sys.platform.startswith("win"):
                        os.startfile(folder)
                    elif sys.platform == "darwin":
                        import subprocess; subprocess.call(["open", folder])
                    else:
                        import subprocess; subprocess.call(["xdg-open", folder])
                except Exception as e:
                    print(f"[open store folder] {e!r}")
            act_open.triggered.connect(_open_folder)
            mfile.addAction(act_open)
        except Exception as e:
            print(f"[menu open folder] {e!r}")
        # Ensure existing loader runs at startup
        try:
            if hasattr(self, "_load_persisted_messages"):
                self._load_persisted_messages()
        except Exception as e:
            print(f"[initial load persisted] {e!r}")

    ChatApp.__init__ = _patched_init_p

    # ---- wrap add to call hardened append ----
    if hasattr(ChatApp, "_add_chat_item"):
        _orig_add_p = ChatApp._add_chat_item
        def _patched_add_p(self, *args, **kwargs):
            _orig_add_p(self, *args, **kwargs)
            try:
                if self.chat_items:
                    it = self.chat_items[0]
                    if it.get("seq") is None:
                        it["seq"] = getattr(self, "_seq_next", 1)
                        self._seq_next = it["seq"] + 1
                    _persist_append_hardened(self, it)
            except Exception as e:
                print(f"[patched_add_p] {e!r}")
        ChatApp._add_chat_item = _patched_add_p

    # ---- ensure clear removes file ----
    if hasattr(ChatApp, "_clear_receive_window"):
        _orig_clear_p = ChatApp._clear_receive_window
        def _patched_clear_p(self):
            _orig_clear_p(self)
            try:
                if hasattr(self, "_msg_store_path") and os.path.exists(self._msg_store_path):
                    os.remove(self._msg_store_path)
            except Exception:
                pass
        ChatApp._clear_receive_window = _patched_clear_p

except Exception as _e_harden:
    try:
        print(f"[persistence_hardening] install error: {_e_harden!r}")
    except Exception:
        pass



# =====================
# Persistence Inline FIX (post-class, robust; folder-relative)
# - Saves to "<script folder>\\store\\messages.json"
# - Immediate write on start + every add + 10s timer
# - File -> Force Save Now
# - Clear deletes messages.json
# - Status shows path; one-time popup confirms path
# =====================
try:
    import os, sys, json
    from datetime import datetime
    from types import MethodType
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QAction, QMessageBox

    def __persist__ensure_store_path(self):
        try:
            base_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        except Exception:
            base_dir = os.getcwd()
        store_dir = os.path.join(base_dir, "store")
        try:
            os.makedirs(store_dir, exist_ok=True)
        except Exception:
            pass
        self._store_dir = store_dir
        self._msg_store_path = os.path.join(store_dir, "messages.json")
        if not hasattr(self, "_seq_next"):
            self._seq_next = 1
        return self._msg_store_path

    def __persist__write_all(self):
        try:
            path = __persist__ensure_store_path(self)
            data = []
            for it in reversed(getattr(self, "chat_items", [])):  # oldest-first
                ts = it.get("ts")
                ts_iso = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
                data.append({
                    "kind": it.get("kind"),
                    "text": it.get("text"),
                    "ts": ts_iso,
                    "ack": bool(it.get("ack")),
                    "ack_id": it.get("ack_id"),
                    "to": it.get("to"),
                    "frm": it.get("frm"),
                    "attempt": it.get("attempt"),
                    "max_attempts": it.get("max_attempts"),
                    "failed": bool(it.get("failed")),
                    "style": it.get("style"),
                    "seq": it.get("seq", None),
                })
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            try:
                self.status_label.setText(f"Saved messages → {path}")
            except Exception:
                pass
            if not getattr(self, "_persist_dialog_shown", False):
                self._persist_dialog_shown = True
                try:
                    dlg = QMessageBox(self)
                    dlg.setWindowTitle("Message Log Location")
                    dlg.setIcon(QMessageBox.Information)
                    dlg.setText(f"Messages are being saved to:\n{path}")
                    dlg.setStandardButtons(QMessageBox.Ok)
                    dlg.exec_()
                except Exception:
                    pass
        except Exception as e:
            try:
                print(f"[persist write_all] {e!r}")
            except Exception:
                pass

    def __persist__append(self, item):
        try:
            path = __persist__ensure_store_path(self)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    arr = json.load(f)
                if not isinstance(arr, list):
                    arr = []
            except Exception:
                arr = []
            ts = item.get("ts")
            ts_iso = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
            rec = {
                "kind": item.get("kind"),
                "text": item.get("text"),
                "ts": ts_iso,
                "ack": bool(item.get("ack")),
                "ack_id": item.get("ack_id"),
                "to": item.get("to"),
                "frm": item.get("frm"),
                "attempt": item.get("attempt"),
                "max_attempts": item.get("max_attempts"),
                "failed": bool(item.get("failed")),
                "style": item.get("style"),
                "seq": item.get("seq", None),
            }
            arr.append(rec)
            cap = int(getattr(self, "_msg_store_limit", 5000) or 5000)
            if len(arr) > cap:
                arr = arr[-cap:]
            with open(path, "w", encoding="utf-8") as f:
                json.dump(arr, f, ensure_ascii=False, indent=2)
            try:
                self.status_label.setText(f"Saved messages → {path}")
            except Exception:
                pass
        except Exception as e:
            try:
                print(f"[persist append] {e!r}")
            except Exception:
                pass
            __persist__write_all(self)

    # --- Patch __init__ to enable persistence
    _orig___init__ = ChatApp.__init__
    def _patched___init__(self, *a, **kw):
        _orig___init__(self, *a, **kw)
        # Ensure paths and initial write (creates folder/file)
        __persist__ensure_store_path(self)
        __persist__write_all(self)
        # File menu: Force Save Now
        try:
            mb = self.menuBar()
            mfile = mb.addMenu("File")
            act_force = QAction("Force Save Now", self)
            act_force.triggered.connect(lambda: __persist__write_all(self))
            mfile.addAction(act_force)
        except Exception as e:
            print(f"[persist menu] {e!r}")
        # Timer every 10s
        try:
            self._persist_timer = QTimer(self)
            self._persist_timer.setInterval(10_000)
            self._persist_timer.timeout.connect(lambda: __persist__write_all(self))
            self._persist_timer.start()
        except Exception as e:
            print(f"[persist timer] {e!r}")
        # Status hint that persistence is on
        try:
            self.status_label.setText(f"Persistence ON → {self._msg_store_path}")
        except Exception:
            pass

    ChatApp.__init__ = _patched___init__
    ChatApp._persist_ensure_store_path = MethodType(__persist__ensure_store_path, ChatApp)
    ChatApp._persist_write_all = MethodType(__persist__write_all, ChatApp)
    ChatApp._persist_append = MethodType(__persist__append, ChatApp)

    # --- Patch _add_chat_item to append to disk
    if hasattr(ChatApp, "_add_chat_item"):
        _orig__add_chat_item = ChatApp._add_chat_item
        def _patched__add_chat_item(self, *args, **kwargs):
            _orig__add_chat_item(self, *args, **kwargs)
            try:
                if self.chat_items:
                    it = self.chat_items[0]
                    if it.get("seq") is None:
                        it["seq"] = getattr(self, "_seq_next", 1)
                        self._seq_next = it["seq"] + 1
                    __persist__append(self, it)
            except Exception as e:
                print(f"[persist add] {e!r}")
        ChatApp._add_chat_item = _patched__add_chat_item

    # --- Patch _clear_receive_window to delete file
    if hasattr(ChatApp, "_clear_receive_window"):
        _orig__clear = ChatApp._clear_receive_window
        def _patched__clear(self):
            _orig__clear(self)
            try:
                path = __persist__ensure_store_path(self)
                if os.path.exists(path):
                    os.remove(path)
                self.status_label.setText("Receive window cleared and messages.json removed.")
            except Exception as e:
                print(f"[persist clear] {e!r}")
        ChatApp._clear_receive_window = _patched__clear

except Exception as _pe:
    try:
        print(f"[persistence inline fix] install error: {_pe!r}")
    except Exception:
        pass