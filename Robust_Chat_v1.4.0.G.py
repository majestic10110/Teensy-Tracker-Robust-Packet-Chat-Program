
# =====================
# Robust Chat v1.4.0 — Production Persistence Pack
# =====================
import os, sys, json, datetime, builtins

# --- Callsign normalization helper for Fleet ---
def _normalize_callsign_ssid(cs: str) -> str:
    try:
        import re as _re
        s = (cs or "").strip().upper()
        # Collapse whitespace
        s = " ".join(s.split())
        # Fold any trailing -<number> into -* (e.g., -1..-99 → -*). Manual '*' is preserved.
        s = _re.sub(r"-(\d{1,3})$", "-*", s)
        return s
    except Exception:
        return cs


# ---- Fixed GPS helpers (defined early) ----
def _fg_store_path(self, filename: str) -> str:
    import os
    try:
        base = _rc_store() if '_rc_store' in globals() or '_rc_store' in dir() else os.path.join(os.getcwd(), "store")
    except Exception:
        base = os.path.join(os.getcwd(), "store")
    try:
        os.makedirs(base, exist_ok=True)
    except Exception:
        pass
    return os.path.join(base, filename)

def _fg_file(self):
    return _fg_store_path(self, "fixed_gps.json")

def _fg_load(self):
    import json, os
    try:
        p = _fg_file(self)
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            lat = str(data.get("lat", "")).strip()
            lon = str(data.get("lon", "")).strip()
            if hasattr(self, "fixed_lat_edit"):
                self.fixed_lat_edit.setText(lat)
            if hasattr(self, "fixed_lon_edit"):
                self.fixed_lon_edit.setText(lon)
    except Exception:
        pass

def _fg_save(self):
    import json
    try:
        payload = {
            "lat": (self.fixed_lat_edit.text().strip() if hasattr(self, "fixed_lat_edit") else ""),
            "lon": (self.fixed_lon_edit.text().strip() if hasattr(self, "fixed_lon_edit") else ""),
        }
        with open(_fg_file(self), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def _fg_parse_dd(text: str, is_lat: bool):
    """Required format: decimal degrees with '.' and optional leading '-'. No N/S/E/W suffixes."""
    try:
        s = str(text or "").strip()
        if not s:
            return False, "empty"
        import re as _re
        if not _re.fullmatch(r'[+-]?(?:\d+(?:\.\d+)?|\.\d+)', s):
            return False, "Use decimal degrees (e.g., 51.50000 or -1.26750)."
        v = float(s)
        lo, hi = (-90.0, 90.0) if is_lat else (-180.0, 180.0)
        if not (lo <= v <= hi):
            return False, f"Out of range ({lo}..{hi})."
        return True, v
    except Exception as e:
        return False, f"{e}"

def _fg_live_validate(self):
    """Color inputs red if invalid/out-of-range; clear style if valid/blank."""
    try:
        # Lat
        if hasattr(self, 'fixed_lat_edit') and self.fixed_lat_edit is not None:
            txt = self.fixed_lat_edit.text() if hasattr(self.fixed_lat_edit, 'text') else ''
            ok1, _ = _fg_parse_dd(txt, True)
            lat_ok = ok1 or (str(txt).strip() == '')
            self.fixed_lat_edit.setStyleSheet('' if lat_ok else 'border: 2px solid #c62828;')
        # Lon
        if hasattr(self, 'fixed_lon_edit') and self.fixed_lon_edit is not None:
            txt = self.fixed_lon_edit.text() if hasattr(self.fixed_lon_edit, 'text') else ''
            ok2, _ = _fg_parse_dd(txt, False)
            lon_ok = ok2 or (str(txt).strip() == '')
            self.fixed_lon_edit.setStyleSheet('' if lon_ok else 'border: 2px solid #c62828;')
    except Exception:
        pass

def _fg_send_fixed_position(self):
    """Insert manual Fixed GPS into the Send box. Validates DD format and range."""
    try:
        lt_txt = ''
        ln_txt = ''
        if hasattr(self, 'fixed_lat_edit') and self.fixed_lat_edit is not None and hasattr(self.fixed_lat_edit, 'text'):
            lt_txt = str(self.fixed_lat_edit.text()).strip()
        if hasattr(self, 'fixed_lon_edit') and self.fixed_lon_edit is not None and hasattr(self.fixed_lon_edit, 'text'):
            ln_txt = str(self.fixed_lon_edit.text()).strip()

        ok_lat, lat_val = _fg_parse_dd(lt_txt, True)
        ok_lon, lon_val = _fg_parse_dd(ln_txt, False)
        if not ok_lat or not ok_lon:
            msg = f"Lat: {lat_val if isinstance(lat_val, str) else 'ok'} | Lon: {lon_val if isinstance(lon_val, str) else 'ok'}"
            if hasattr(self, 'status_label'):
                try:
                    self.status_label.setText(msg)
                except Exception:
                    pass
            _fg_live_validate(self)
            return

        text = f"Position GPS {lat_val:.5f} {lon_val:.5f}"
        if hasattr(self, 'send_edit') and self.send_edit is not None:
            try:
                self.send_edit.setPlainText(text)
                from PyQt5 import QtGui as _QtGui
                self.send_edit.moveCursor(_QtGui.QTextCursor.End)
                self.send_edit.setFocus()
            except Exception:
                pass
        try:
            self.my_last_lat, self.my_last_lon = lat_val, lon_val
        except Exception:
            pass
        _fg_save(self)
        if hasattr(self, 'status_label'):
            try:
                self.status_label.setText("Using manual Fixed GPS.")
            except Exception:
                pass
        _fg_live_validate(self)
    except Exception:
        pass

# Provide alias for compatibility with 1.4.3
try:
    ChatApp.send_fixed_position = lambda self: _fg_send_fixed_position(self)  # noqa: F821 (ChatApp defined later)
except Exception:
    pass
# ---- End Fixed GPS helpers ----


# ---- Paths & logging ----
def _rc_base_dir():
    return (os.path.dirname(os.path.abspath(sys.executable))
            if getattr(sys, "frozen", False)
            else os.path.dirname(os.path.abspath(__file__)))

def _rc_store():
    base = _rc_base_dir()
    store = os.path.join(base, "store")
    try: os.makedirs(store, exist_ok=True)
    except Exception: pass
    return store

def _rc_paths():
    s = _rc_store()
    return (os.path.join(s, "messages_v1.json"),
            os.path.join(s, "persist_debug.log"))

# ---- helper: clear JSON store explicitly ----
def _rc_wipe_json_store():
    try:
        import datetime, json
        jsonp, _ = _rc_paths()
        payload = {
            "version": 1,
            "messages": [],
            "created": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00","Z"),
            "note": "Cleared by user via Clear Message Window."
        }
        with open(jsonp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        _rc_log("CLEAR: JSON store wiped")
        return True
    except Exception as e:
        _rc_log(f"CLEAR ERR: {e!r}")
        return False



def _rc_log(msg: str):
    # Minimal, safe logging
    try:
        _, logp = _rc_paths()
        with open(logp, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] PROD: {msg}\n")
    except Exception:
        pass

# ---- JSON read/write helpers ----
def _rc_read_json():
    jsonp, _ = _rc_paths()
    try:
        with open(jsonp, "r", encoding="utf-8") as f:
            cur = json.load(f)
    except Exception:
        cur = {"version":1,"messages":[]}
    if isinstance(cur, list):
        return cur
    if isinstance(cur, dict):
        return cur.get("messages", [])
    return []

def _rc_write_json(messages_list):
    # messages_list is a list of dicts (oldest-first preferred on disk)
    jsonp, _ = _rc_paths()
    try:
        cur = {"version":1,"messages":messages_list}
        with open(jsonp, "w", encoding="utf-8") as f:
            json.dump(cur, f, ensure_ascii=False, indent=2)
        _rc_log(f"SAVE OK: total {len(messages_list)} -> {jsonp}")
        return True
    except Exception as e:
        _rc_log(f"SAVE ERR: {e!r}")
        return False

def _rc_merge(existing, new_items):
    # Deduplicate by (seq) else (ts, text)
    def _k(d):
        s = d.get("seq")
        return ("seq", s) if isinstance(s, int) else ("tt", d.get("ts"), d.get("text"))
    seen=set(); merged=[]
    for d in existing:
        k=_k(d)
        if k in seen: continue
        seen.add(k); merged.append(d)
    for d in new_items:
        k=_k(d)
        if k in seen: continue
        seen.add(k); merged.append(d)
    return merged

# ---- Convert between on-disk dicts and in-memory items ----
def _rc_disk_to_item(d):
    # Ensure keys exist; try to parse ts
    itm = {
        "kind": d.get("kind"),
        "text": d.get("text"),
        "ack": bool(d.get("ack")),
        "ack_id": d.get("ack_id"),
        "to": d.get("to"),
        "frm": d.get("frm"),
        "attempt": d.get("attempt"),
        "max_attempts": d.get("max_attempts"),
        "failed": bool(d.get("failed")),
        "style": d.get("style"),
        "seq": d.get("seq"),
        "ts": d.get("ts"),
    }
    # Parse ISO timestamp to datetime if possible
    try:
        ts = d.get("ts")
        if isinstance(ts, str):
            # fromisoformat doesn't like trailing Z in older Pythons
            ts2 = ts.rstrip("Z")
            try:
                import datetime as _dt
                itm["ts"] = _dt.datetime.fromisoformat(ts2)
            except Exception:
                itm["ts"] = ts
    except Exception:
        pass
    return itm

def _rc_item_to_disk(it):
    # Convert ts back to iso string
    ts = it.get("ts")
    try:
        ts_iso = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
    except Exception:
        ts_iso = str(ts)
    return {
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
        "seq": it.get("seq"),
    }

def save_messages_now(self):
    # Snapshot memory -> disk (merge with existing). Memory is newest-first in UI;
    # write oldest-first on disk.
    items = list(reversed(getattr(self, "chat_items", []) or []))
    built = [_rc_item_to_disk(it) for it in items]
    if not built:
        _rc_log("SAVE SKIP: no messages in memory")
        return
    existing = _rc_read_json()
    merged = _rc_merge(existing, built)
    _rc_write_json(merged)
    try:
        self.status_label.setText(f"Saved ({len(merged)} total).")
    except Exception:
        pass

# Immediate proof this pack is active
_rc_log("persistence pack loaded; base=" + _rc_base_dir())

# ---- Build-class hook to patch ChatApp at definition time ----
def _rc_patch_chatapp_cls(cls):
    _rc_log("patching ChatApp class")

    old_init = getattr(cls, "__init__", None)
    def __persist_init(self, *a, **kw):
        if old_init:
            old_init(self, *a, **kw)
        # Ensure files exist
        try:
            jsonp, logp = _rc_paths()
            if not os.path.exists(jsonp):
                with open(jsonp, "w", encoding="utf-8") as f:
                    json.dump({"version":1,"messages":[]}, f, ensure_ascii=False, indent=2)
            with open(logp, "a", encoding="utf-8") as _:
                pass
        except Exception:
            pass
        # Load messages from disk into UI (once)
        try:
            disk_msgs = _rc_read_json()  # oldest-first
            mem_items = [_rc_disk_to_item(d) for d in disk_msgs]
            # UI memory likely newest-first; reverse for UI
            try:
                self.chat_items = list(reversed(mem_items))
            except Exception:
                self.chat_items = mem_items
            # Rebuild view if available
            try:
                self._rebuild_chat_view()
            except Exception:
                pass
            # Also force-render into a list/text widget so user sees history
            try:
                _rc_render_ui(self, list(reversed(self.chat_items or [])))
            except Exception:
                pass
            _rc_log(f"loaded {len(mem_items)} messages from disk at startup")
            try:
                self.status_label.setText(f"Loaded {len(mem_items)} messages from disk.")
            except Exception:
                pass
        except Exception as e:
            _rc_log(f"load err: {e!r}")
        # Autosave every 5 minutes
        try:
            from PyQt5.QtCore import QTimer
            self._autosave_timer = QTimer(self)
            self._autosave_timer.setInterval(300000)  # 5 min
            self._autosave_timer.timeout.connect(lambda: save_messages_now(self))
            self._autosave_timer.start()
        except Exception:
            pass
        # Hotkeys: Ctrl+M, F9 = manual save
        try:
            from PyQt5.QtWidgets import QShortcut
            from PyQt5.QtGui import QKeySequence
            sc1 = QShortcut(QKeySequence("Ctrl+M"), self); sc1.activated.connect(lambda: save_messages_now(self))
            sc2 = QShortcut(QKeySequence("F9"), self);     sc2.activated.connect(lambda: save_messages_now(self))
            self._persist_sc1, self._persist_sc2 = sc1, sc2
        except Exception:
            pass
        # Status
        try:
            self.status_label.setText(f"Store: {_rc_store()} (autosave 5 min)")
            try:
                _rc_fix_freq_label(self)
                _rc_fix_freq_header(self)
            except Exception:
                pass
        except Exception:
            pass

    cls.__init__ = __persist_init

    # Save immediately when a message is added
    if hasattr(cls, "_add_chat_item"):
        old_add = getattr(cls, "_add_chat_item")
        def __persist_add(self, *a, **kw):
            try: r = old_add(self, *a, **kw)
            except Exception: r = None
            try:
                # Eager save
                save_messages_now(self)
                # Beacon filter: update Last Beacon ONLY for true beacons
                item = None
                try:
                    if isinstance(getattr(self, 'chat_items', None), list) and self.chat_items:
                        item = self.chat_items[0]
                except Exception:
                    item = None
                myc = _rc_guess_mycall(self)
                if item and _rc_is_beacon_tx(item, myc):
                    _rc_update_last_tx(self, item)
            except Exception as e:
                _rc_log(f"save/beacon err in add: {e!r}")
            return r
        setattr(cls, "_add_chat_item", __persist_add)
        _rc_log("wrapped _add_chat_item for eager save")
    else:
        _rc_log("warning: _add_chat_item not found; add `save_messages_now(self)` after you append to the UI")

    # Clear button: UI + JSON
    if hasattr(cls, "_clear_receive_window"):
        def __persist_clear(self):
            # Clear UI
            try: self.chat_items = []
            except Exception: pass
            try: self._rebuild_chat_view()
            except Exception: pass
            # Wipe JSON
            ok = _rc_wipe_json_store()
            try:
                self.status_label.setText("Message window cleared; persistent log {}.".format("reset" if ok else "NOT reset"))
            except Exception: pass
        setattr(cls, "_clear_receive_window", __persist_clear)
        _rc_log("clear overridden → UI + JSON wiped")

    return cls

_orig_build_class = builtins.__build_class__
def _rc_build_class(func, name, *args, **kwargs):
    cls = _orig_build_class(func, name, *args, **kwargs)
    try:
        if name == "ChatApp":
            cls = _rc_patch_chatapp_cls(cls)
    finally:
        return cls
builtins.__build_class__ = _rc_build_class

# If ChatApp already exists, patch immediately too
if "ChatApp" in globals():
    try:
        ChatApp = _rc_patch_chatapp_cls(ChatApp)
        _rc_log("early patch: ChatApp already existed; patched now")
    except Exception as e:
        _rc_log(f"early patch err: {e!r}")
# =====================


# ===== Autosave debug helpers =====
def __as_base_dir():
    try:
        import os, sys
        if getattr(sys, "frozen", False):
            return os.path.dirname(os.path.abspath(sys.executable))
        return os.path.dirname(os.path.abspath(__file__))
    except Exception:
        return "."

def __as_paths():
    import os
    b = __as_base_dir()
    store = os.path.join(b, "store")
    try: os.makedirs(store, exist_ok=True)
    except Exception: pass
    return store, os.path.join(store, "persist_debug.log"), os.path.join(store, "messages_v1.json")

def __as_log(msg: str):
    try:
        import datetime
        _, logp, _ = __as_paths()
        with open(logp, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass
# ==================================

import re
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# --- Callsign helpers (SSID-aware) ---
BEACON_INTERVAL_MS = 15 * 60 * 1000  # 15 minutes
def base_callsign(cs: str) -> str:
    cs = (cs or "").strip().upper()
    m = re.match(r"^([A-Z0-9/]+?)(?:-([0-9]{1,2}))?$", cs)
    return m.group(1) if m else cs

"""
LiNK500 Teensy Chat v1.4.0.G Consolidated (Explicit Fleet Mode)  (2025-09-17)
- Inline Fleet Manager UI between Serial and Frequencies
- Global dark theme with VT323 and a minimum font size of 14pt (larger elements kept larger)
- Fleet dialogs (Add Group / Add Callsign) enlarged (VT323 14pt, wider inputs)
- Fleet Members list and Active group dropdown at 14pt
- Frequencies labels at 14pt
- "Enable" and "Active" label at 14pt
"""

import sys, re, time, os, math, tempfile, traceback, random, json, fnmatch
from collections import deque
from datetime import datetime

from PyQt5 import QtCore, QtGui, QtWidgets

# --- App base directory (works for .py and PyInstaller .exe) ---

# --- Prelaunch data-file probe (records if files were missing at start) ---
try:
    _RC_PRELAUNCH_MISSING = []
    _RC_PRELAUNCH_BASE = _app_base_dir() if "_app_base_dir" in globals() else (os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__)))
    _RC_PRELAUNCH_FLEET = os.path.join(_RC_PRELAUNCH_BASE, "fleetlist.json")
    _RC_PRELAUNCH_STORE = os.path.join(_RC_PRELAUNCH_BASE, "store")
    _RC_PRELAUNCH_MSG   = os.path.join(_RC_PRELAUNCH_STORE, "messages_v1.json")
    if not os.path.exists(_RC_PRELAUNCH_FLEET):
        _RC_PRELAUNCH_MISSING.append(_RC_PRELAUNCH_FLEET)
    if not os.path.exists(_RC_PRELAUNCH_MSG):
        _RC_PRELAUNCH_MISSING.append(_RC_PRELAUNCH_MSG)
except Exception:
    _RC_PRELAUNCH_MISSING = []

def _app_base_dir():
    try:
        if getattr(sys, 'frozen', False):
            return os.path.dirname(os.path.abspath(sys.executable))
    except Exception:
        pass
    try:
        return _app_base_dir()
    except Exception:
        return os.getcwd()
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer, QUrl
from PyQt5.QtCore import QLocale, QRegularExpression
from PyQt5.QtGui import QRegularExpressionValidator
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QTextBrowser, QTextEdit,
    QGroupBox, QCheckBox, QMessageBox, QStatusBar, QSizePolicy, QShortcut,
    QListWidget, QListWidgetItem, QInputDialog, QMenu, QAction
)
# Calibrated per-character send time (seconds per character)
TIME_PER_CHAR = 0.082  # based on 5.57s / 68 chars

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
        import json
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
        import json
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
        return
        
        # ##__fleet_migrate_ssids__## — migrate numeric SSIDs to BASE-*, preserve BASE entries
        try:
            changed_any = False
            for fl in (self.fleets or []):
                members = [ (str(m) or '').strip().upper() for m in (fl.get('members') or []) ]
                newm = []
                seen_star = set()
                for m in members:
                    parts = m.split('-',1)
                    base = parts[0]
                    if len(parts) == 2 and (parts[1] == '*' or parts[1].isdigit()):
                        if base not in seen_star:
                            newm.append(f"{base}-*"); seen_star.add(base)
                            if parts[1] != '*': changed_any = True
                    else:
                        newm.append(m)
                newm = sorted(set(newm), key=lambda x: (x.split('-',1)[0], x))
                if newm != members:
                    fl['members'] = newm; changed_any = True
            if changed_any:
                try: self.save()
                except Exception: pass
        except Exception:
            pass
    
        except Exception:
            pass
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
        """Add a member:
        - If input has numeric SSID (e.g., M0OLI-11) or explicit wildcard (M0OLI-*) -> store as BASE-*
        - If input has NO SSID (e.g., M0OLI) -> store as BASE (no -*)
        Returns True if anything new was added or normalised. Never raises.
        """
        try:
            fleet_name_kw = kwargs.get('fleet_name') if isinstance(kwargs, dict) else None
            if callsign is None and fleet_name_kw is not None:
                token = (name_or_callsign or '').strip().upper()
                name = (fleet_name_kw or 'Default').strip()
            else:
                name = (name_or_callsign or 'Default').strip()
                token = (callsign or '').strip().upper()
            # Fallback: allow add_member('M0OLI-11') -> Default
            if '-' in name and not token:
                token, name = name, 'Default'
            tok = (token or '').upper().strip()
            if not tok:
                return False
            base = tok.split('-',1)[0]
            ssid = tok.split('-',1)[1] if '-' in tok else ''
            is_star = (ssid == '*') or (ssid.isdigit() and ssid != '')
            canon = f"{base}-*" if is_star else base
            fl = self.get_fleet(name)
            if not fl:
                fl = {"name": name, "rules": {"default_action": "show", "autopermit": False}, "members": []}
                self.fleets.append(fl)
            members = [ (str(m) or '').strip().upper() for m in (fl.get("members") or []) ]
            changed = False
            if canon.endswith('-*'):
                # Ensure at most one BASE-*; keep BASE if it exists
                have_star = any(m.endswith('-*') and m.split('-',1)[0] == base for m in members)
                if not have_star:
                    members.append(canon); changed = True
                # Drop duplicate stars for same base
                dedup = []
                seen_star = False
                for m in members:
                    mbase = m.split('-',1)[0]
                    if m.endswith('-*') and mbase == base:
                        if not seen_star:
                            dedup.append(f"{base}-*")
                            seen_star = True
                        else:
                            changed = True
                        continue
                    dedup.append(m)
                fl["members"] = sorted(set(dedup), key=lambda x: (x.split('-',1)[0], x))
            else:
                if canon not in members:
                    members.append(canon); changed = True
                    fl["members"] = sorted(set(members), key=lambda x: (x.split('-',1)[0], x))
                else:
                    fl["members"] = members
            if changed:
                try: self.save()
                except Exception: pass
            return changed
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

    def add_group(self, name: str) -> bool:
        """
        Create a fleet group if it doesn't exist, set it active, and persist.
        Returns True on success (including when the group already existed).
        """
        try:
            name = (name or "").strip()
            if not name:
                return False

            # If it already exists, just set active and return
            existing = self.get_fleet(name)
            if existing is None:
                # Create a fresh group
                new_fleet = {
                    "name": name,
                    "rules": {"default_action": "show", "autopermit": False},
                    "members": []
                }
                if not hasattr(self, "fleets") or self.fleets is None:
                    self.fleets = []
                self.fleets.append(new_fleet)
                try:
                    # keep names sorted but keep "Default" first
                    self.fleets.sort(key=lambda f: (f.get("name") != "Default", f.get("name","")))
                except Exception:
                    pass

            # Set newly added (or existing) group active and save
            if hasattr(self, "set_active"):
                self.set_active(name)
            if hasattr(self, "save"):
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
                        self.msleep(5)
                        continue
                    buf += data
                    while True:
                        sep_idx = -1
                        seplen = 0
                        for sep in (b'\r\n', b'\n', b'\r'):
                            i = buf.find(sep)
                            if i != -1:
                                sep_idx = i
                                seplen = len(sep)
                                break
                        if sep_idx == -1:
                            break
                        part = buf[:sep_idx]
                        buf = buf[sep_idx + seplen:]
                        try:
                            text = part.decode('utf-8', errors='replace')
                        except Exception:
                            text = part.decode('latin1', errors='replace')
                        try:
                            ts = datetime.now().strftime('%H:%M:%S')
                        except Exception:
                            from datetime import datetime as _dt
                            ts = _dt.now().strftime('%H:%M:%S')
                        self.line_received.emit(f"[{ts}] {text.strip()}")
                        try:
                            ts = datetime.now().strftime('%H:%M:%S')
                        except Exception:
                            from datetime import datetime as _dt
                            ts = _dt.now().strftime('%H:%M:%S')

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
            try:
                self._sync_kiss_perm_from_device()
            except Exception:
                pass

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

            label_text = f"Last TX {now_s}"
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
        self.setWindowTitle("Robust Chat v1.4.0.G")
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

        base_dir = _app_base_dir()
        self.fleet = FleetManager(base_dir)
        self.fleet.load()
        self.fleet_only_heartbeat = False
        self.fleet_auto_ack_nonmembers = False

        # My last known position for range/bearing
        self.my_last_lat = float('nan')
        self.my_last_lon = float('nan')

        self.beacon_timer = QTimer(self)
        self.beacon_timer.setInterval(BEACON_INTERVAL_MS)
        self.beacon_timer.timeout.connect(self._send_beacon)

        self.HEARTBEAT_TTL_S = 20 * 60
        self.heartbeat_seen = {}
        self.heartbeat_gc_timer = QTimer(self)
        self.heartbeat_gc_timer.setInterval(30 * 1000)
        self.heartbeat_gc_timer.timeout.connect(self._heartbeat_update_view)
        self.heartbeat_gc_timer.start()
        # Heartbeat children/parents
        self.hb_children = {}
        self.hb_parent_seen = {}
        self.hb_window_sec = max(getattr(self, 'HEARTBEAT_TTL_S', 1800), 1800)

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
        self.fleet_enabled_check_top = QCheckBox("Enable")
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

        # --- Fixed GPS (manual) ---
        fixed_row = QHBoxLayout(); fixed_row.setSpacing(8)
        fixed_row.addWidget(QLabel("Fixed Position (decimal format):"))
        fixed_row.addWidget(QLabel("Lat:"))
        self.fixed_lat_edit = QLineEdit(); self.fixed_lat_edit.setPlaceholderText("Lat dd.ddddd (e.g., 51.50000)")
        self.fixed_lat_edit.setAlignment(Qt.AlignCenter); self.fixed_lat_edit.setFixedWidth(160)
        _lat_rx = QRegularExpression(r"^-?$|^-?\d{0,2}(\.\d{0,6})?$")
        self.fixed_lat_edit.setValidator(QRegularExpressionValidator(_lat_rx, self))
        fixed_row.addWidget(self.fixed_lat_edit)

        fixed_row.addWidget(QLabel("Lon:"))
        self.fixed_lon_edit = QLineEdit(); self.fixed_lon_edit.setPlaceholderText("Lon dd.ddddd (e.g., -1.26750)")
        self.fixed_lon_edit.setAlignment(Qt.AlignCenter); self.fixed_lon_edit.setFixedWidth(170)
        _lon_rx = QRegularExpression(r"^-?$|^-?\d{0,3}(\.\d{0,6})?$")
        self.fixed_lon_edit.setValidator(QRegularExpressionValidator(_lon_rx, self))
        fixed_row.addWidget(self.fixed_lon_edit)

        self.fixed_send_btn = QPushButton('SEND FIX POS')
        self.fixed_send_btn.setToolTip('Insert validated decimal-degree coordinates into the Send box. Example: 51.50000, -1.26750.')
        self.fixed_send_btn.clicked.connect(lambda: _fg_send_fixed_position(self))
        fixed_row.addWidget(self.fixed_send_btn)
        fixed_row.addStretch(1)

        root.addLayout(fixed_row)

        # load any saved coords, attach validation + save hooks
        _fg_load(self)
        self.fixed_lat_edit.editingFinished.connect(lambda: (_fg_save(self), _fg_live_validate(self)))
        self.fixed_lon_edit.editingFinished.connect(lambda: (_fg_save(self), _fg_live_validate(self)))
        try:
            self.fixed_lat_edit.textEdited.connect(lambda _: _fg_live_validate(self))
            self.fixed_lon_edit.textEdited.connect(lambda _: _fg_live_validate(self))
        except Exception:
            pass
        _fg_live_validate(self)


        
        # ACK pause control row
        
        # ACK pause control row
        ack_row = QHBoxLayout(); ack_row.setSpacing(8)
        ack_label = QLabel("Manual ACK pause (s)")
        ack_label.setFont(QtGui.QFont('VT323', 14))

        self.ack_pause_edit = QLineEdit()
        self.ack_pause_edit.setPlaceholderText("12.0")
        self.ack_pause_edit.setAlignment(Qt.AlignCenter)
        self.ack_pause_edit.setFixedWidth(120)
        try:
            dv = QtGui.QDoubleValidator(0.0, 60.0, 2, self.ack_pause_edit)
            dv.setNotation(QtGui.QDoubleValidator.StandardNotation)
            self.ack_pause_edit.setValidator(dv)
        except Exception:
            pass

        ack_row.addStretch(1)
        ack_row.addWidget(ack_label)
        ack_row.addWidget(self.ack_pause_edit)
        root.addLayout(ack_row)

        # Load & persist ACK pause to %USERPROFILE%\.robust_chat\settings.json
        try:
            self._appdir = os.path.join(os.path.expanduser("~"), ".robust_chat")
            os.makedirs(self._appdir, exist_ok=True)
            self._settings_file = os.path.join(self._appdir, "settings.json")
        except Exception:
            self._settings_file = None

        def _load_settings():
            cfg = {}
            try:
                if self._settings_file and os.path.exists(self._settings_file):
                    import json as _json
                    with open(self._settings_file, "r", encoding="utf-8") as _f:
                        cfg = _json.load(_f) or {}
            except Exception:
                cfg = {}
            return cfg

        def _save_settings(cfg):
            try:
                if not self._settings_file:
                    return
                import json as _json
                with open(self._settings_file, "w", encoding="utf-8") as _f:
                    _json.dump(cfg, _f, ensure_ascii=False, indent=2)
            except Exception:
                pass

        # Initialize from settings; default 12.0 if blank
        try:
            cfg0 = _load_settings()
            v = float(cfg0.get("ack_pause_seconds", 12.0))
            self.ack_pause_edit.setText(str(v))
        except Exception:
            self.ack_pause_edit.setText("12.0")

        # Persist changes on manual edit
        try:
            def _on_ack_pause_changed():
                try:
                    txt = self.ack_pause_edit.text().strip() or "12.0"
                    valf = float(txt)
                except Exception:
                    return
                cfg = _load_settings()
                cfg["ack_pause_seconds"] = valf
                _save_settings(cfg)
            self.ack_pause_edit.editingFinished.connect(_on_ack_pause_changed)
        except Exception:
            pass

        # Load & persist ACK pause to ~/.robust_chat/settings.json

        # Load & persist ACK pause to %USERPROFILE%\.robust_chat\settings.json
        try:
            self._appdir = os.path.join(os.path.expanduser("~"), ".robust_chat")
            os.makedirs(self._appdir, exist_ok=True)
            self._settings_file = os.path.join(self._appdir, "settings.json")
        except Exception:
            self._settings_file = None

        def _load_settings():
            cfg = {}
            try:
                if self._settings_file and os.path.exists(self._settings_file):
                    import json as _json
                    with open(self._settings_file, "r", encoding="utf-8") as _f:
                        cfg = _json.load(_f) or {}
            except Exception:
                cfg = {}
            return cfg

        def _save_settings(cfg):
            try:
                if not self._settings_file:
                    return
                import json as _json
                with open(self._settings_file, "w", encoding="utf-8") as _f:
                    _json.dump(cfg, _f, ensure_ascii=False, indent=2)
            except Exception:
                pass

        # Initialize spinbox from settings
        try:
            cfg0 = _load_settings()
            v = float(cfg0.get("ack_pause_seconds", 6.0))
            self.ack_pause_edit.setText(str(v))
        except Exception:
            pass

        # Persist changes on value change
        try:
            def _on_ack_pause_changed():
                try:
                    txt = self.ack_pause_edit.text().strip() or "12.0"
                    valf = float(txt)
                except Exception:
                    return
                cfg = _load_settings()
                cfg["ack_pause_seconds"] = valf
                _save_settings(cfg)
            self.ack_pause_edit.editingFinished.connect(_on_ack_pause_changed)
        except Exception:
            pass

    
        # Status bar
        sb = QStatusBar()
        self.setStatusBar(sb)
        self.status_label = QtWidgets.QLabel("Disconnected  |  Reminder: WARNING: Changing KISS condition will PTT, Disconnect Data cable from radio before changing KISS. Turn KISS OFF to chat")
        sb.addWidget(self.status_label)

        # Right-side HUD label for last beacon time
        self.beacon_time_label = QtWidgets.QLabel("Last TX —")
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
            # Query KISS Permanent before starting reader thread
            try:
                self._query_kp_sync_raw()
            except Exception:
                pass
            # Now start background reader
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

    def _sync_kiss_perm_from_device(self):
        """
        Query device for KISS Permanent state using @KP and update the UI checkbox without triggering writes.
        Expects reply containing 'KP1' or 'KP0'.
        """
        try:
            if not (self.ser and self.ser.is_open):
                return
            # Ask device for KISS Permanent status
            self._send_cmd("@KP")
            QtCore.QThread.msleep(150)
            text = ""
            try:
                # Prefer existing reader if available
                text = (self._read_for_ms(600) or "")
            except Exception:
                # Minimal fallback reader
                try:
                    deadline = QtCore.QTime.currentTime().addMSecs(600)
                    buf = []
                    while QtCore.QTime.currentTime() < deadline:
                        if self.ser.in_waiting:
                            try:
                                chunk = self.ser.read(self.ser.in_waiting).decode("utf-8", errors="replace")
                                buf.append(chunk)
                            except Exception:
                                break
                        QtCore.QThread.msleep(20)
                    text = "".join(buf)
                except Exception:
                    text = ""

            text_u = (text or "").upper()
            if "KP1" in text_u:
                val = True
            elif "KP0" in text_u:
                val = False
            else:
                return  # Unknown reply format; don't change UI

            try:
                self.kiss_perm_toggle.blockSignals(True)
                self.kiss_perm_toggle.setChecked(val)
            finally:
                self.kiss_perm_toggle.blockSignals(False)

            self.status_label.setText(("KISS Permanent ON" if val else "KISS Permanent OFF") + f" | Connected {self.port_combo.currentText()}")
        except Exception:
            pass

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
        # De-duplication guard: drop identical consecutive lines within 300 ms
        try:
            import time as _t
            now_m = _t.monotonic()
            raw = (line or "")
            if getattr(self, "_last_recv_line", None) == raw and (now_m - getattr(self, "_last_recv_mono", 0.0)) <= 0.3:
                return
            self._last_recv_line = raw
            self._last_recv_mono = now_m
        except Exception:
            pass

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
            
            # Heartbeat children: ensure parent bucket and timestamp
            try:
                self.hb_parent_seen[call] = now
                self.hb_children.setdefault(call, {})
            except Exception:
                pass
            # Auto H* with explicit return target "DE <MYCALL>"
            try:
                mycall_val = (self.mycall_edit.text() or "").strip().upper() if hasattr(self, "mycall_edit") else ""
                if mycall_val:
                    my_base = mycall_val.split("-",1)[0]
                    key = f"_hstar_last_query_{call}"
                    last = float(getattr(self, key, 0.0) or 0.0)
                    if (now - last) >= 120.0:
                        setattr(self, key, now)
                        qline = f"{call} H* DE <{my_base}>"
                        self._tx_gate = True
                        ok = self._ptt_guard(lambda: self._write_line(qline))
                        self._tx_gate = False
                        if ok:
                            try:
                                self._tx_count += 1
                                self._update_beacon_hud()
                            except Exception:
                                pass
            except Exception:
                pass
            self._heartbeat_update_view()
            return


        m = LINE_RE.match(content)
        if m:

            # H* flow and 1-hop child relays -> heartbeat column only
            try:
                _msg_str = (msg or "").strip()
                _msg_upper = _msg_str.upper()
                my = (self.mycall_edit.text() or "").strip().upper() if hasattr(self, "mycall_edit") else ""
                my_base = my.split("-",1)[0] if my else ""

                if _msg_upper.startswith("H*"):
                    import re as _re_de, time as _t
                    mde = _re_de.search(r"DE\s*<\s*([A-Z0-9\-]+)\s*>", _msg_upper)
                    reply_to = None
                    if mde:
                        reply_to = (mde.group(1) or "").split("-",1)[0]
                    elif my and (to == my):
                        reply_to = (frm or "").split("-",1)[0]
                    if my_base and reply_to:
                        now_ts = _t.time()
                        win = float(getattr(self, "hb_window_sec", getattr(self, "HEARTBEAT_TTL_S", 1800)))
                        heard_recent = sorted([c for c, ts in (self.heartbeat_seen or {}).items() if (now_ts - ts) <= win])
                        # Send parent anchor once addressed
                        pline = f"{reply_to} ..<{my_base}>"
                        self._tx_gate = True
                        ok = self._ptt_guard(lambda: self._write_line(pline))
                        self._tx_gate = False
                        if ok:
                            try:
                                self._tx_count += 1
                                self._update_beacon_hud()
                            except Exception:
                                pass
                            self.hb_parent_seen[my_base] = now_ts
                            self.hb_children.setdefault(my_base, {})
                        # Then bare '/<child>' lines
                        children = heard_recent if heard_recent else ["(none)"]
                        for c in children:
                            cline = f"/<{c}>"
                            self._tx_gate = True
                            ok = self._ptt_guard(lambda l=cline: self._write_line(l))
                            self._tx_gate = False
                            if ok:
                                try:
                                    self._tx_count += 1
                                    self._update_beacon_hud()
                                except Exception:
                                    pass
                                self.hb_children.setdefault(my_base, {})[c] = now_ts
                                self._heartbeat_update_view()
                        return

                # Child '/<CALL>' line -> attach under parent=frm
                if _msg_str.startswith('/') and '<' in _msg_str:
                    try:
                        inner = _msg_str[_msg_str.index('<')+1 : _msg_str.index('>')].strip().upper()
                    except Exception:
                        inner = _msg_str.lstrip('/').strip().upper()
                    parent = (frm or "").strip().upper().split('-',1)[0]
                    child  = (inner or "").split('-',1)[0]
                    now_ts = time.time()
                    self.hb_parent_seen[parent] = max(now_ts, float(self.hb_parent_seen.get(parent, 0) or 0))
                    bucket = self.hb_children.setdefault(parent, {})
                    bucket[child] = now_ts
                    # prune by window
                    win = float(getattr(self, "hb_window_sec", getattr(self, "HEARTBEAT_TTL_S", 1800)))
                    for _c, _ts in list(bucket.items()):
                        if (now_ts - _ts) > win:
                            bucket.pop(_c, None)
                    self._heartbeat_update_view()
                    return
            except Exception:
                pass

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
            "base_delay_sec": getattr(self, "_last_send_time_sec", None),
        }
        if kind == "sent" and item["ack_id"]:
            self.sent_by_ack[item["ack_id"]] = item
        self.chat_items.insert(0, item)
        self._rebuild_chat_view()
        if kind == "sent" and item["ack_id"]:
            self._schedule_retry(item["ack_id"], initial=True, base_delay_sec=item.get("base_delay_sec"))

    
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

    def _schedule_retry(self, ack_id: str, initial: bool = False, base_delay_sec: float = None):
        # Manual ACK pause (seconds) + per-message base delay from char-count timing
        ack_pause = 6.0
        try:
            ack_pause = float(float(self.ack_pause_edit.text().strip() or "12.0"))
        except Exception:
            pass
        base_delay = float(base_delay_sec) if base_delay_sec is not None else 0.0
        item = self.sent_by_ack.get(ack_id)
        if not item or item.get("ack"):
            return
        a = item.get("attempt") or 1
        m = item.get("max_attempts") or 3
        BEACON_INTERVAL_MS = int((base_delay + ack_pause) * 1000 + random.random()*1000)
        old = self.retry_timers.get(ack_id)
        if old:
            try: old.stop()
            except Exception: pass
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(BEACON_INTERVAL_MS)
        if a < m:
            timer.timeout.connect(lambda aid=ack_id: self._retry_send(aid))
            next_attempt = a + 1
            self.status_label.setText(f"Waiting for ACK {ack_id}… scheduling retry {next_attempt}/{m} in {BEACON_INTERVAL_MS//1000}s.")
        else:
            timer.timeout.connect(lambda aid=ack_id: self._final_fail(aid))
            self.status_label.setText(f"Waiting for ACK {ack_id} after attempt {a}/{m}… final wait {BEACON_INTERVAL_MS//1000}s.")
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

            # --- Character-based transmit timing (prefix + user text + suffix) ---
            try:
                _to = (self.target_edit.text() if hasattr(self,'target_edit') else self.to_edit.text()).strip()
                _my = (self.mycall_edit.text() if hasattr(self,'mycall_edit') else '').strip()
                _typed = (self.send_edit.toPlainText() if hasattr(self.send_edit, 'toPlainText') else self.send_edit.text()).strip()
                _ack = f"[ACK:{ack_id:04d}]"
                _prefix = f"{_to} DE {_my} " if _to and _my else ''
                full_msg_for_timing = (_prefix + _typed + ' ' + _ack).rstrip()
                char_count = len(full_msg_for_timing)        # COUNT SPACES too
                send_time_sec = char_count * float(TIME_PER_CHAR)
            except Exception:
                words = len((_typed or '').split())
                send_time_sec = 5.5 * max(1.0, words/12.0)

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
        # Remember original button label so we can restore it
        try:
                self._gps_btn_orig_text = self.gps_btn.text()
        except Exception:
                self._gps_btn_orig_text = 'GPS SEND'
        # Show loading state immediately and flush UI
        try:
            self.gps_btn.setText("Loading...")
            self.gps_btn.setEnabled(False)
            self.gps_btn.repaint()
            QApplication.processEvents()
        except Exception:
            pass
        # UI: show loading state on the GPS button
        try:
            self.gps_btn.setText("Loading...")
            self.gps_btn.setEnabled(False)
        except Exception:
            pass
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
            # Always restore GPS button text and enabled state
            try:
                label = getattr(self, "_gps_btn_orig_text", None) or "GPS SEND"
                self.gps_btn.setText(label)
                self.gps_btn.setEnabled(True)
            except Exception:
                pass
            # If port still open and no reader thread, restart it (we stopped it at the top)
            try:
                if self.ser and getattr(self.ser, "is_open", False):
                    if self.reader_thread is None or not self.reader_thread.isRunning():
                        self.reader_thread = SerialReaderThread(self.ser)
                        self.reader_thread.line_received.connect(self._on_line)
                        self.reader_thread.start()
            except Exception:
                pass
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

        # Revert GPS button UI state
        try:
            self.gps_btn.setText("GPS SEND")
            self.gps_btn.setEnabled(True)
        except Exception:
            pass

        try:
            self.gps_btn.setText("GPS SEND"); self.gps_btn.setEnabled(True)
        except Exception:
            pass

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
    print("Link500 Teensy Robust Chat v1.4.0.G (2025-09-15)")
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
        import json
        home = os.path.expanduser("~")
        appdir = os.path.join(home, ".robust_chat")
        try:
            os.makedirs(appdir, exist_ok=True)
        except Exception:
            pass
        return os.path.join(appdir, "fleetlist.json")
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

# =====================
# Robust Chat v1.4.0 — Autosave + Fleet Manager width cap (pre‑main)
# - Auto‑saves messages every 5 minutes to <base>\store\messages_v1.json
# - File → Save Message Log (Ctrl+M) to force a save on demand
# - Preserves dict {"version":1,"messages":[...]} or list [...] schemas
# - Caps Fleet Manager panel width to "Add Group" button width + padding
# =====================
try:
    import os, sys, json
    from datetime import datetime
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QAction, QLabel, QPushButton, QWidget
    from PyQt5.QtGui import QKeySequence
except Exception as _e_rc_imp:
    pass
else:
    # ---- Paths & schema helpers
    def __rc_base_dir():
        try:
            if getattr(sys, "frozen", False):
                return os.path.dirname(os.path.abspath(sys.executable))
            return os.path.dirname(os.path.abspath(__file__))
        except Exception:
            return os.getcwd()

    def __rc_store_path():
        base = __rc_base_dir()
        store = os.path.join(base, "store")
        try:
            os.makedirs(store, exist_ok=True)
        except Exception:
            pass
        return os.path.join(store, "messages_v1.json")

    def __rc_read(path):
        if not os.path.exists(path):
            return [], "dict"
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data, "list"
            if isinstance(data, dict) and isinstance(data.get("messages", []), list):
                return data["messages"], "dict"
        except Exception:
            pass
        return [], "dict"

    def __rc_write(path, records, fmt):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if fmt == "list":
                payload = records
            else:
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if not isinstance(data, dict):
                        data = {"version": 1, "messages": []}
                except Exception:
                    data = {"version": 1, "messages": []}
                data["messages"] = records
                payload = data
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[v1.4.0 write] {e!r}")

    
    def __rc_load_saved(self):
        """Load messages from store/messages_v1.json into self.chat_items (newest-first)."""
        path = getattr(self, "_msg_store_path", None) or __rc_store_path()
        # Read with schema awareness
        recs, fmt = __rc_read(path)
        if not isinstance(recs, list) or not recs:
            return 0
        # Convert oldest-first on disk to newest-first in memory
        restored = []
        last_seq = 0
        for d in recs:
            try:
                t = d.get("ts")
                try:
                    from datetime import datetime as _dt
                    ts = _dt.fromisoformat(t) if isinstance(t, str) else t
                except Exception:
                    ts = None
                seq = d.get("seq")
                if isinstance(seq, int) and seq > last_seq:
                    last_seq = seq
                restored.append({
                    "kind": d.get("kind"),
                    "text": d.get("text"),
                    "ts": ts,
                    "ack": bool(d.get("ack")),
                    "ack_id": d.get("ack_id"),
                    "to": d.get("to"),
                    "frm": d.get("frm"),
                    "attempt": d.get("attempt"),
                    "max_attempts": d.get("max_attempts"),
                    "failed": bool(d.get("failed")),
                    "style": d.get("style"),
                    "seq": seq,
                })
            except Exception:
                pass
        restored.reverse()  # newest first
        # Only replace in-memory items if empty or explicitly smaller
        try:
            current = getattr(self, "chat_items", [])
        except Exception:
            current = []
        self.chat_items = restored
        try:
            self._rebuild_chat_view()
        except Exception:
            pass
        if last_seq:
            try:
                self._seq_next = last_seq + 1
            except Exception:
                pass
        return len(restored)


    def __rc_clear_disk_messages(self):
        """Clear store/messages_v1.json in-place, preserving schema (dict/list)."""
        path = getattr(self, "_msg_store_path", None) or __rc_store_path()
        try:
            # Detect current schema
            recs, fmt = __rc_read(path)
        except Exception:
            recs, fmt = [], "dict"
        try:
            import os, json
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if fmt == "list":
                payload = []  # empty list
            else:
                # dict schema
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if not isinstance(data, dict):
                        data = {"version": 1, "messages": []}
                except Exception:
                    data = {"version": 1, "messages": []}
                data["messages"] = []  # clear
                payload = data
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            try:
                self.status_label.setText(f"Messages cleared on disk → {path}")
            except Exception:
                pass
        except Exception as e:
            print(f"[v1.4.0 clear disk] {e!r}")

def __rc_force_save(self):
        path = getattr(self, "_msg_store_path", None) or __rc_store_path()
        recs, fmt = __rc_read(path)
        built = []
        for it in reversed(getattr(self, "chat_items", []) or []):
            ts = it.get("ts")
            try:
                ts_iso = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
            except Exception:
                ts_iso = datetime.now().isoformat()
            built.append({
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
                "seq": it.get("seq"),
            })
        __rc_write(path, built, fmt)
        try:
            self.status_label.setText(f"Saved {len(built)} messages → {path}")
        except Exception:
            pass

# ---- Patch ChatApp
if "ChatApp" in globals() and hasattr(ChatApp, "__init__"):
    __rc_orig_init = ChatApp.__init__
    def __rc_patched_init(self, *a, **kw):
        __rc_orig_init(self, *a, **kw)
        # 1) Canonical path + announce
        self._msg_store_path = __rc_store_path()
        try:
            self.status_label.setText(f"Message store → {self._msg_store_path}")
        except Exception:
            pass

        # 2) File menu with Save Message Log (Ctrl+M)
        try:
            mb = self.menuBar()
            mfile = mb.addMenu("File")
            act_save = QAction("Save Message Log", self)
            act_save.setShortcut(QKeySequence("Ctrl+M"))
            act_save.triggered.connect(lambda: __rc_force_save(self))
            mfile.addAction(act_save)
        except Exception as e:
            print(f"[v1.4.0 menu] {e!r}")

        # 3) Autosave every 5 minutes
        try:
            self._rc_timer = QTimer(self)
            self._rc_timer.setInterval(300000)  # 5 minutes
            self._rc_timer.timeout.connect(lambda: __rc_force_save(self))
            self._rc_timer.start()
        except Exception as e:
            print(f"[v1.4.0 autosave] {e!r}")

        
        # 4) Fleet Manager width reduction → 75% of original (post‑layout)
        try:
            from PyQt5.QtCore import QTimer
            from PyQt5.QtWidgets import QGroupBox
            def _shrink_fleet():
                try:
                    # Prefer a group box titled 'Fleet' (case‑insensitive)
                    targets = []
                    for gb in self.findChildren(QGroupBox):
                        try:
                            if "fleet" in str(gb.title()).lower():
                                targets.append(gb)
                        except Exception:
                            pass
                    # Fallback: any widget with an objectName mentioning fleet/whitelist/group
                    if not targets:
                        for w in self.findChildren(QWidget):
                            n = (getattr(w, "objectName", lambda: "")() or "").lower()
                            if any(k in n for k in ("fleet", "whitelist", "group")):
                                targets.append(w)
                    # Apply a ~25% reduction to each target's width
                    for w in targets:
                        try:
                            hint = w.sizeHint().width()
                        except Exception:
                            hint = w.width() or 0
                        if hint and hint > 0:
                            new_max = max(1, int(hint * 0.85))
                            w.setMaximumWidth(new_max)
                except Exception as e:
                    print(f"[v1.4.0 fleet shrink] {e!r}")
            # Run after layouts stabilize
            _t = QTimer(self)
            _t.setSingleShot(True)
            _t.setInterval(500)
            _t.timeout.connect(_shrink_fleet)
            # Also cap serial/port combo widths
            try:
                from PyQt5.QtWidgets import QComboBox
                for cb in self.findChildren(QComboBox):
                    try:
                        name = (getattr(cb, 'objectName', lambda: '')() or '').lower()
                        text = ''
                        try:
                            text = str(cb.currentText()).lower()
                        except Exception:
                            pass
                        if any(k in name for k in ('serial','port','combo')) or 'com' in text:
                            cb.setMaximumWidth(200)  # fixed cap
                    except Exception:
                        pass
            except Exception as e:
                print(f"[v1.4.0 serial cap] {e!r}")
            _t.start()
            self._fleet_shrink_timer = _t
        except Exception as e:
            print(f"[v1.4.0 fleet shrink init] {e!r}")
    
        # 4) Shrink Fleet Manager + Serial group boxes to contents
        try:
            from PyQt5.QtCore import QTimer
            from PyQt5.QtWidgets import QGroupBox
            def _shrink_boxes():
                try:
                    targets = []
                    for gb in self.findChildren(QGroupBox):
                        title = str(gb.title()).lower()
                        if "fleet" in title or "serial" in title:
                            targets.append(gb)
                    for gb in targets:
                        hint = gb.sizeHint().width()
                        if hint and hint > 0:
                            new_max = max(1, int(hint + 20))
                            gb.setMaximumWidth(new_max)
                except Exception as e:
                    print(f"[v1.4.0 shrink boxes] {e!r}")
            _t2 = QTimer(self)
            _t2.setSingleShot(True)
            _t2.setInterval(800)
            _t2.timeout.connect(_shrink_boxes)
            _t2.start()
            self._shrink_timer = _t2
        except Exception as e:
            print(f"[v1.4.0 shrink init] {e!r}")
    
        # 5) UI polish: rename "Enable Fleet" -> "Enable" and shrink Fleet/Serial group boxes to contents
        try:
            from PyQt5.QtCore import QTimer
            from PyQt5.QtWidgets import QGroupBox, QCheckBox, QWidget, QLayout

            def _compact_groupbox_titles():
                # Rename any checkbox reading "Enable Fleet" (case-insensitive) to "Enable"
                try:
                    for cb in self.findChildren(QCheckBox):
                        try:
                            if "enable fleet" in str(cb.text()).strip().lower():
                                cb.setText("Enable")
                        except Exception:
                            pass
                except Exception:
                    pass

            def _sum_children_width(gb: QGroupBox) -> int:
                # Estimate the width needed by summing child size hints in the top-level layout
                pad = 20  # extra pixels for aesthetics
                try:
                    lay = gb.layout()
                    if isinstance(lay, QLayout):
                        total = 0
                        # Sum width of first-level widgets in the layout
                        for i in range(lay.count()):
                            it = lay.itemAt(i)
                            w = it.widget()
                            if w is not None:
                                try:
                                    total += max(1, w.sizeHint().width())
                                except Exception:
                                    total += 1
                        # Add layout spacing * (count-1)
                        try:
                            total += max(0, lay.spacing()) * max(0, lay.count()-1)
                        except Exception:
                            pass
                        return total + pad
                except Exception:
                    pass
                # Fallback: current width + pad
                try:
                    return max(1, gb.sizeHint().width()) + pad
                except Exception:
                    return 240  # safe default

            def _shrink_specific_groups():
                try:
                    targets = []
                    for gb in self.findChildren(QGroupBox):
                        try:
                            title = str(gb.title()).strip().lower()
                        except Exception:
                            title = ""
                        if not title:
                            continue
                        if "fleet" in title or "serial" in title:
                            targets.append(gb)
                    for gb in targets:
                        try:
                            needed = _sum_children_width(gb)
                            if needed and needed > 0:
                                # Do not grow; only reduce if current max is larger
                                gb.setMaximumWidth(needed)
                        except Exception:
                            pass
                except Exception as e:
                    print(f"[v1.4.0 compact groups] {e!r}")

            # Run after layouts settle
            _ui_timer = QTimer(self)
            _ui_timer.setSingleShot(True)
            _ui_timer.setInterval(600)
            _ui_timer.timeout.connect(_compact_groupbox_titles)
            _ui_timer.timeout.connect(_shrink_specific_groups)
            _ui_timer.start()
            self._ui_compact_timer = _ui_timer
        except Exception as e:
            print(f"[v1.4.0 ui compact init] {e!r}")
        ChatApp.__init__ = __rc_patched_init
    if hasattr(ChatApp, "_clear_receive_window"):
        __rc_orig_clear = ChatApp._clear_receive_window
        def __rc_patched_clear(self):
            __rc_orig_clear(self)  # clears the UI
            try:
                __rc_clear_disk_messages(self)  # clears the JSON file
            except Exception as e:
                print(f"[v1.4.0 clear hook] {e!r}")
        ChatApp._clear_receive_window = __rc_patched_clear


# =====================

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
    import json
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
            self._store_dir = os.path.join(_app_base_dir(), "store")
            os.makedirs(self._store_dir, exist_ok=True)
        except Exception:
            self._store_dir = _app_base_dir()
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
    import json, re
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
            base_dir = _app_base_dir()
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
    import json, sys
    from datetime import datetime
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QAction
    from types import MethodType

    # ---- helpers ----
    def _ensure_store_path(self):
        try:
            base_dir = _app_base_dir()
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
                folder = getattr(self, "_store_dir", None) or _app_base_dir()
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

def _get_ack_pause_value(self):
            """Return the ACK pause value as float; default to 12.0 if blank/invalid (and reflect it in the field)."""
            try:
                txt = self.ack_pause_edit.text().strip()
                if not txt:
                    self.ack_pause_edit.setText("12.0")
                    return 12.0
                val = float(txt)
                return val
            except Exception:
                self.ack_pause_edit.setText("12.0")
                return 12.0


# =====================
# Data Files Self‑Check (v1.4.0)
# - Verifies the presence of "fleetlist.json" and "store/messages_v1.json"
# - Prompts to auto-create if missing
# - Adds "File → Check Data Files" menu item
# =====================
try:
    import json, sys, os
    from PyQt5.QtWidgets import QMessageBox, QAction
    from types import MethodType

    def _data_self_check(self):
        try:
            base = _app_base_dir() if "_app_base_dir" in globals() else (os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__)))
            fleet_path = os.path.join(base, "fleetlist.json")
            store_dir = os.path.join(base, "store")
            msgs_path = os.path.join(store_dir, "messages_v1.json")

            missing = []
            if not os.path.exists(fleet_path):
                missing.append(fleet_path)
            if not os.path.exists(msgs_path):
                missing.append(msgs_path)

            if missing:
                # Ask to create missing files
                msg = QMessageBox(self)
                msg.setIcon(QMessageBox.Warning)
                msg.setWindowTitle("Robust Chat: Data Files Missing")
                listing = "\\n".join(missing)
                msg.setText(f"The following data files are missing:\\n\\n{listing}\\n\\nCreate them now?")
                msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
                if msg.exec_() == QMessageBox.Yes:
                    try:
                        os.makedirs(store_dir, exist_ok=True)
                    except Exception:
                        pass
                    # Create minimal fleet
                    if not os.path.exists(fleet_path):
                        try:
                            with open(fleet_path, "w", encoding="utf-8") as f:
                                json.dump({
                                    "enabled": False,
                                    "active_fleets": ["Default"],
                                    "fleets": [{
                                        "name": "Default",
                                        "rules": {"default_action": "show", "autopermit": False},
                                        "members": []
                                    }]
                                }, f, indent=2)
                        except Exception as e:
                            print(f"[selfcheck] fleet create error: {e!r}")
                    # Create minimal messages
                    if not os.path.exists(msgs_path):
                        try:
                            with open(msgs_path, "w", encoding="utf-8") as f:
                                json.dump([], f, ensure_ascii=False, indent=2)
                        except Exception as e:
                            print(f"[selfcheck] messages create error: {e!r}")
                    # Inform done
                    done = QMessageBox(self)
                    done.setWindowTitle("Robust Chat: Data Files Created")
                    done.setIcon(QMessageBox.Information)
                    done.setText("Required data files were created.\nYou can start using the app.")
                    done.exec_()
                    try:
                        self.status_label.setText(f"Data files OK → {fleet_path} | {msgs_path}")
                    except Exception:
                        pass
                else:
                    try:
                        self.status_label.setText("Data files missing — see warning dialog.")
                    except Exception:
                        pass
            else:
                try:
                    self.status_label.setText(f"Data files OK → {fleet_path} | {msgs_path}")
                except Exception:
                    pass
        except Exception as e:
            print(f"[selfcheck] {e!r}")

    # Patch ChatApp.__init__ to run self-check and add menu item
    if "ChatApp" in globals() and hasattr(ChatApp, "__init__"):
        _orig_init_sc = ChatApp.__init__
        def _patched_init_sc(self, *a, **kw):
            _orig_init_sc(self, *a, **kw)
            try:
                # Add menu item
                mb = self.menuBar()
                file_menu = None
                try:
                    # Try to find an existing "File" menu
                    for m in mb.findChildren(type(mb.addMenu("x"))):
                        if hasattr(m, "title") and str(m.title()).lower() == "file":
                            file_menu = m; break
                except Exception:
                    pass
                if file_menu is None:
                    file_menu = mb.addMenu("File")
                act_check = QAction("Check Data Files", self)
                act_check.triggered.connect(lambda: _data_self_check(self))
                file_menu.addAction(act_check)
            except Exception as e:
                print(f"[selfcheck menu] {e!r}")
            # Run on startup
            try:
                _data_self_check(self)
            except Exception as e:
                print(f"[selfcheck run] {e!r}")
        
            # If files were missing at launch, show a clear alert now
            try:
                if isinstance(globals().get("_RC_PRELAUNCH_MISSING", []), list) and _RC_PRELAUNCH_MISSING:
                    from PyQt5.QtWidgets import QMessageBox
                    msg = QMessageBox(self)
                    msg.setIcon(QMessageBox.Warning)
                    msg.setWindowTitle("Robust Chat: Data Files Missing at Startup")
                    listing = "\n".join(_RC_PRELAUNCH_MISSING)
                    msg.setText(f"The following data files were missing when the app started:\n\n{listing}\n\nThey may have been created automatically. Use File → Check Data Files to verify.")
                    msg.exec_()
            except Exception as e:
                print(f"[prelaunch notice] {e!r}")
    ChatApp.__init__ = _patched_init_sc

except Exception as _e_selfcheck:
    try:
        print(f"[selfcheck install] {_e_selfcheck!r}")
    except Exception:
        pass


# =====================
# Persistence CORE v1.4.0 (canonical & idempotent)
# This overrides any earlier persistence monkey patches to ensure a single, reliable flow.
# =====================
try:
    import json, os, sys
    from datetime import datetime
    from PyQt5.QtCore import QTimer
    from types import MethodType

    def __rc_base_dir():
        try:
            if getattr(sys, 'frozen', False):
                return os.path.dirname(os.path.abspath(sys.executable))
        except Exception:
            pass
        try:
            return os.path.dirname(os.path.abspath(__file__))
        except Exception:
            return os.getcwd()

    def __rc_store_path(self):
        base = __rc_base_dir()
        store_dir = os.path.join(base, "store")
        try:
            os.makedirs(store_dir, exist_ok=True)
        except Exception:
            pass
        self._store_dir = store_dir
        self._msg_store_path = os.path.join(store_dir, "messages_v1.json")
        if not hasattr(self, "_seq_next"):
            self._seq_next = 1
        return self._msg_store_path

    def __rc_load(self):
        try:
            path = getattr(self, "_msg_store_path", None) or __rc_store_path(self)
            if not os.path.exists(path):
                return
            with open(path, "r", encoding="utf-8") as f:
                arr = json.load(f)
            if not isinstance(arr, list):
                return
            # Convert JSON records to chat_items in current in-memory format
            restored = []
            last_seq = 0
            for d in arr:
                try:
                    t = d.get("ts")
                    try:
                        ts = datetime.fromisoformat(t) if isinstance(t, str) else t
                    except Exception:
                        ts = datetime.now()
                    seq = d.get("seq")
                    if isinstance(seq, int) and seq > last_seq:
                        last_seq = seq
                    restored.append({
                        "kind": d.get("kind"),
                        "text": d.get("text"),
                        "ts": ts,
                        "ack": bool(d.get("ack")),
                        "ack_id": d.get("ack_id"),
                        "to": d.get("to"),
                        "frm": d.get("frm"),
                        "attempt": d.get("attempt"),
                        "max_attempts": d.get("max_attempts"),
                        "failed": bool(d.get("failed")),
                        "style": d.get("style"),
                        "seq": seq,
                    })
                except Exception:
                    pass
            # Oldest-first on disk; we want newest-first in UI memory
            restored.reverse()
            self.chat_items = restored
            if last_seq > 0:
                self._seq_next = last_seq + 1
            try:
                self._rebuild_chat_view()
            except Exception:
                pass
        except Exception as e:
            print(f"[rc_load] {e!r}")

    def __rc_dump_all(self):
        try:
            path = getattr(self, "_msg_store_path", None) or __rc_store_path(self)
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
        except Exception as e:
            print(f"[rc_dump_all] {e!r}")

    def __rc_append(self, item):
        try:
            path = getattr(self, "_msg_store_path", None) or __rc_store_path(self)
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
            # Cap to 5000
            if len(arr) > 5000:
                arr = arr[-5000:]
            with open(path, "w", encoding="utf-8") as f:
                json.dump(arr, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[rc_append] {e!r}")

    # Hook into ChatApp lifecycle
    if "ChatApp" in globals() and hasattr(ChatApp, "__init__"):
        __orig_init = ChatApp.__init__
        def __patched_init(self, *a, **kw):
            __orig_init(self, *a, **kw)
            try:
                __rc_store_path(self)
                __rc_load(self)
                # Timer flush (15s)
                try:
                    self._rc_timer = QTimer(self)
                    self._rc_timer.setInterval(15_000)
                    self._rc_timer.timeout.connect(lambda: __rc_dump_all(self))
                    self._rc_timer.start()
                except Exception as e:
                    print(f"[rc_timer] {e!r}")
                # Status hint
                try:
                    self.status_label.setText(f"Persistence ON → {self._msg_store_path}")
                except Exception:
                    pass
            except Exception as e:
                print(f"[rc_init] {e!r}")
        ChatApp.__init__ = __patched_init

        # Patch add message to ensure append-to-disk on every new item
        if hasattr(ChatApp, "_add_chat_item"):
            __orig_add = ChatApp._add_chat_item
            def __patched_add(self, *args, **kwargs):
                __orig_add(self, *args, **kwargs)
                try:
                    if self.chat_items:
                        it = self.chat_items[0]
                        if it.get("seq") is None:
                            it["seq"] = getattr(self, "_seq_next", 1)
                            self._seq_next = it["seq"] + 1
                        __rc_append(self, it)
                except Exception as e:
                    print(f"[rc_add] {e!r}")
            ChatApp._add_chat_item = __patched_add

        # Make Clear button also remove the file
        if hasattr(ChatApp, "_clear_receive_window"):
            __orig_clear = ChatApp._clear_receive_window
            def __patched_clear(self):
                __orig_clear(self)
                try:
                    path = getattr(self, "_msg_store_path", None) or __rc_store_path(self)
                    if os.path.exists(path):
                        os.remove(path)
                    try:
                        self.status_label.setText("Receive window cleared and messages_v1.json removed.")
                    except Exception:
                        pass
                except Exception as e:
                    print(f"[rc_clear] {e!r}")
            ChatApp._clear_receive_window = __patched_clear

except Exception as _rc_e:
    try:
        print(f"[rc_core] {_rc_e!r}")
    except Exception:
        pass


# =====================
# Persistence Diagnostics v1.4.0-dbg
#  - Logs every write/append with record counts to store/persist_debug.log
#  - Adds File → Force Save Now  (Ctrl+S) to flush immediately
#  - Shows a popup if a write fails (so silent failures are visible)
# =====================
try:
    import os, sys, json
    from datetime import datetime
    from PyQt5.QtWidgets import QAction, QMessageBox
    from PyQt5.QtGui import QKeySequence

    def __rc_dbg_base():
        try:
            if getattr(sys, 'frozen', False):
                base = os.path.dirname(os.path.abspath(sys.executable))
            else:
                base = os.path.dirname(os.path.abspath(__file__))
        except Exception:
            base = os.getcwd()
        store = os.path.join(base, "store")
        try:
            os.makedirs(store, exist_ok=True)
        except Exception:
            pass
        return base, store, os.path.join(store, "persist_debug.log")

    def __rc_dbg(msg: str):
        try:
            _base, _store, logp = __rc_dbg_base()
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(logp, "a", encoding="utf-8") as lf:
                lf.write(f"[{stamp}] {msg}\n")
        except Exception:
            pass

    # Wrap previously defined core functions if present
    def __rc_dbg_wrap_dump(self):
        try:
            path = getattr(self, "_msg_store_path", None)
            n = len(getattr(self, "chat_items", []) or [])
            __rc_dbg(f"DUMP_ALL → path={path} items={n}")
        except Exception:
            pass
        try:
            __rc_dump_all(self)  # call core
            try:
                self.status_label.setText(f"Saved {len(self.chat_items)} messages → {self._msg_store_path}")
            except Exception:
                pass
        except Exception as e:
            __rc_dbg(f"DUMP_ALL ERROR: {e!r}")
            try:
                m = QMessageBox(self); m.setIcon(QMessageBox.Critical)
                m.setWindowTitle("Robust Chat: Save Error")
                m.setText(f"Could not write messages to:\n{getattr(self, '_msg_store_path', '')}\n\n{e!r}")
                m.exec_()
            except Exception:
                pass

    def __rc_dbg_wrap_append(self, item):
        try:
            path = getattr(self, "_msg_store_path", None)
            txt = str((item or {}).get("text", ""))[:60].replace("\n"," ")
            __rc_dbg(f"APPEND → path={path} preview='{txt}'")
        except Exception:
            pass
        try:
            __rc_append(self, item)  # call core
        except Exception as e:
            __rc_dbg(f"APPEND ERROR: {e!r}")
            try:
                m = QMessageBox(self); m.setIcon(QMessageBox.Critical)
                m.setWindowTitle("Robust Chat: Append Error")
                m.setText(f"Could not append message to:\n{getattr(self, '_msg_store_path', '')}\n\n{e!r}")
                m.exec_()
            except Exception:
                pass

    # Hook menu + shortcuts and replace core calls with dbg wrappers
    if "ChatApp" in globals() and hasattr(ChatApp, "__init__"):
        __orig_init_dbg = ChatApp.__init__
        def __patched_init_dbg(self, *a, **kw):
            __orig_init_dbg(self, *a, **kw)
            try:
                mb = self.menuBar()
                file_menu = None
                try:
                    for m in mb.findChildren(type(mb.addMenu("x"))):
                        if hasattr(m, "title") and str(m.title()).lower() == "file":
                            file_menu = m; break
                except Exception:
                    pass
                if file_menu is None:
                    file_menu = mb.addMenu("File")
                act_force = QAction("Force Save Now", self)
                try:
                    act_force.setShortcut(QKeySequence("Ctrl+S"))
                except Exception:
                    pass
                act_force.triggered.connect(lambda: __rc_dbg_wrap_dump(self))
                file_menu.addAction(act_force)
            except Exception as e:
                print(f"[dbg menu] {e!r}")
        ChatApp.__init__ = __patched_init_dbg

        # Replace add hook to call dbg wrapper (which forwards to core)
        if hasattr(ChatApp, "_add_chat_item"):
            __orig_add_dbg = ChatApp._add_chat_item
            def __patched_add_dbg(self, *args, **kwargs):
                __orig_add_dbg(self, *args, **kwargs)
                try:
                    if self.chat_items:
                        it = self.chat_items[0]
                        if it.get("seq") is None:
                            it["seq"] = getattr(self, "_seq_next", 1)
                            self._seq_next = it["seq"] + 1
                        __rc_dbg_wrap_append(self, it)
                except Exception as e:
                    __rc_dbg(f"ADD WRAP ERROR: {e!r}")
            ChatApp._add_chat_item = __patched_add_dbg

except Exception as _rc_dbg_e:
    try:
        print(f"[rc_dbg] {_rc_dbg_e!r}")
    except Exception:
        pass


# =====================
# Schema Compatibility v1.4.0
# - Support both list[...] and dict{"messages":[...]} file formats
# - Preserve whichever format is detected (no silent format flip)
# =====================
try:
    import json, os
    from datetime import datetime

    def __rc_read_store(self, path):
        """Load from path; return (records_list, format_tag)
        format_tag ∈ {"list","dict","empty"}
        """
        try:
            if not os.path.exists(path):
                return [], "empty"
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Newer format: plain list of records
            if isinstance(data, list):
                return data, "list"
            # Older/starter format: dict with "messages"
            if isinstance(data, dict):
                msgs = data.get("messages", [])
                if isinstance(msgs, list):
                    return msgs, "dict"
            # Fallback
            return [], "empty"
        except Exception as e:
            try:
                print(f"[schema read] {e!r}")
            except Exception:
                pass
            return [], "empty"

    def __rc_write_store(self, path, records, fmt):
        """Write records back in same format we read (list vs dict)."""
        try:
            if fmt == "list":
                payload = records
            elif fmt == "dict":
                # Try to load existing dict to preserve other keys
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if not isinstance(data, dict):
                        data = {"version": 1, "messages": []}
                except Exception:
                    data = {"version": 1, "messages": []}
                data["messages"] = records
                payload = data
            else:  # "empty" or unknown → default to dict to match your starter
                payload = {"version": 1, "messages": records}
            # Ensure directory
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception as e:
            try:
                print(f"[schema write] {e!r}")
            except Exception:
                pass

    # Monkey-patch the core functions if present from v1.4.0
    if "__rc_append" in globals():
        _orig_append = __rc_append
        def __rc_append(self, item):
            # Read existing + detect format
            path = getattr(self, "_msg_store_path", None)
            recs, fmt = __rc_read_store(self, path)
            # Convert current item
            try:
                ts = item.get("ts")
                ts_iso = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
            except Exception:
                ts_iso = datetime.now().isoformat()
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
            recs.append(rec)
            if len(recs) > 5000:
                recs = recs[-5000:]
            __rc_write_store(self, path, recs, fmt)

    if "__rc_dump_all" in globals():
        _orig_dump = __rc_dump_all
        def __rc_dump_all(self):
            path = getattr(self, "_msg_store_path", None)
            # read to preserve existing format
            recs_existing, fmt = __rc_read_store(self, path)
            # rebuild array from memory (oldest-first)
            recs = []
            for it in reversed(getattr(self, "chat_items", []) or []):
                ts = it.get("ts")
                ts_iso = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
                recs.append({
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
            __rc_write_store(self, path, recs, fmt)

    if "__rc_load" in globals():
        _orig_load = __rc_load
        def __rc_load(self):
            # canonical path
            path = getattr(self, "_msg_store_path", None)
            recs, fmt = __rc_read_store(self, path)
            # convert to in-memory format (newest-first)
            restored = []
            last_seq = 0
            for d in recs:
                try:
                    t = d.get("ts")
                    try:
                        ts = datetime.fromisoformat(t) if isinstance(t, str) else t
                    except Exception:
                        ts = datetime.now()
                    seq = d.get("seq")
                    if isinstance(seq, int) and seq > last_seq:
                        last_seq = seq
                    restored.append({
                        "kind": d.get("kind"),
                        "text": d.get("text"),
                        "ts": ts,
                        "ack": bool(d.get("ack")),
                        "ack_id": d.get("ack_id"),
                        "to": d.get("to"),
                        "frm": d.get("frm"),
                        "attempt": d.get("attempt"),
                        "max_attempts": d.get("max_attempts"),
                        "failed": bool(d.get("failed")),
                        "style": d.get("style"),
                        "seq": seq,
                    })
                except Exception:
                    pass
            restored.reverse()
            self.chat_items = restored
            if last_seq > 0:
                self._seq_next = last_seq + 1
            try:
                self._rebuild_chat_view()
            except Exception:
                pass

except Exception as _e_schema:
    try:
        print(f"[schema compat] {_e_schema!r}")
    except Exception:
        pass




# =====================
# FINAL RESTORE: File menu + 5‑min autosave (runs last, before main)
# Ensures the File menu (with Save Message Log / Ctrl+M) is present
# and the autosave timer is running, even if earlier patches were overridden.
# Also logs autosave events to store/persist_debug.log for visibility.
# =====================
try:
    import os, sys, json
    from datetime import datetime
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QAction
    from PyQt5.QtGui import QKeySequence
except Exception as _e_restore:
    pass
else:
    def __final_log(s: str):
        try:
            # write to <base>\store\persist_debug.log
            base = os.path.dirname(os.path.abspath(sys.executable)) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
            store = os.path.join(base, "store")
            os.makedirs(store, exist_ok=True)
            lp = os.path.join(store, "persist_debug.log")
            with open(lp, "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {s}\n")
        except Exception:
            pass

    if "ChatApp" in globals() and hasattr(ChatApp, "__init__"):
        __prev_init_restore = ChatApp.__init__
        def __final_init(self, *a, **kw):
            __prev_init_restore(self, *a, **kw)
            # Ensure we know the store path and show it
            try:
                if not getattr(self, "_msg_store_path", None):
                    # try helper from earlier patches
                    try:
                        path = __rc_store_path()
                    except Exception:
                        base = os.path.dirname(os.path.abspath(sys.executable)) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
                        store = os.path.join(base, "store")
                        os.makedirs(store, exist_ok=True)
                        path = os.path.join(store, "messages_v1.json")
                    self._msg_store_path = path
                try:
                    self.status_label.setText(f"Autosave active → {self._msg_store_path}")
                except Exception:
                    pass
            except Exception as e:
                print(f"[final restore: path] {e!r}")

            # Ensure File menu exists and has Save Message Log (Ctrl+M)
            try:
                mb = self.menuBar()
                # Some platforms hide native menubar; ensure it's visible in-window
                try:
                    mb.setNativeMenuBar(False)
                except Exception:
                    pass
                mfile = None
                # reuse existing "File" if present
                for m in mb.children():
                    try:
                        if hasattr(m, "title") and str(m.title()).strip().lower() == "file":
                            mfile = m; break
                    except Exception:
                        pass
                if mfile is None:
                    mfile = mb.addMenu("File")
                # Add/replace Save Message Log action
                act_text = "Save Message Log"
                found = False
                for act in getattr(mfile, "actions", lambda: [])():
                    try:
                        if str(act.text()).strip() == act_text:
                            act.triggered.disconnect()
                            act.triggered.connect(lambda: __rc_force_save(self))
                            act.setShortcut(QKeySequence("Ctrl+M"))
                            found = True
                            break
                    except Exception:
                        pass
                if not found:
                    act_save = QAction(act_text, self)
                    act_save.setShortcut(QKeySequence("Ctrl+M"))
                    act_save.triggered.connect(lambda: __rc_force_save(self))
                    mfile.addAction(act_save)
            except Exception as e:
                print(f"[final restore: menu] {e!r}")

            # Start/restart autosave timer (5 minutes)
            try:
                if hasattr(self, "_final_autosave_timer") and self._final_autosave_timer is not None:
                    self._final_autosave_timer.stop()
                self._final_autosave_timer = QTimer(self)
                self._final_autosave_timer.setInterval(300000)  # 5 min
                self._final_autosave_timer.timeout.connect(lambda: (__final_log("autosave tick"), __rc_force_save(self)))
                self._final_autosave_timer.start()
                __final_log("autosave timer started")
            except Exception as e:
                print(f"[final restore: autosave] {e!r}")

            # Kick an initial save after 10s so users can verify without waiting 5 min
            try:
                t = QTimer(self); t.setSingleShot(True); t.setInterval(10000)
                def _kick():
                    __final_log("initial autosave kick")
                    try:
                        __rc_force_save(self)
                    except Exception as e:
                        print(f"[final restore: initial save] {e!r}")
                t.timeout.connect(_kick); t.start()
                self._final_initial_kick = t
            except Exception as e:
                print(f"[final restore: kick] {e!r}")

        ChatApp.__init__ = __final_init
# =====================


# =====================
# LAST-WINS STARTUP HOOK (v1.4.0 fixfinal)
# Ensures File menu, load-on-start, and autosave are active.
# Also writes to store/persist_debug.log for visibility.
# =====================
try:
    import os, sys, json
    from datetime import datetime
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QAction
    from PyQt5.QtGui import QKeySequence
except Exception as _e_fixfinal:
    pass
else:
    def __ff_base_dir():
        try:
            if getattr(sys, 'frozen', False):
                return os.path.dirname(os.path.abspath(sys.executable))
            return os.path.dirname(os.path.abspath(__file__))
        except Exception:
            return os.getcwd()

    def __ff_paths():
        base = __ff_base_dir()
        store = os.path.join(base, "store")
        try: os.makedirs(store, exist_ok=True)
        except Exception: pass
        msgp = os.path.join(store, "messages_v1.json")
        logp = os.path.join(store, "persist_debug.log")
        return base, store, msgp, logp

    def __ff_log(s):
        try:
            _, _, _, logp = __ff_paths()
            with open(logp, "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {s}\n")
        except Exception:
            pass

    def __ff_read(path):
        if not os.path.exists(path):
            return [], "dict"
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list): return data, "list"
            if isinstance(data, dict) and isinstance(data.get("messages", []), list):
                return data["messages"], "dict"
        except Exception as e:
            __ff_log(f"read error: {e!r}")
        return [], "dict"

    def __ff_write(path, records, fmt):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if fmt == "list":
                payload = records
            else:
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if not isinstance(data, dict): data = {"version":1,"messages":[]}
                except Exception: data = {"version":1,"messages":[]}
                data["messages"] = records
                payload = data
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            __ff_log(f"write ok: {len(records)} recs -> {path}")
        except Exception as e:
            __ff_log(f"write error: {e!r}")

    def __ff_force_save(self):
        _, _, msgp, _ = __ff_paths()
        recs, fmt = __ff_read(msgp)
        built = []
        for it in reversed(getattr(self, "chat_items", []) or []):
            ts = it.get("ts")
            try: ts_iso = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
            except Exception: ts_iso = datetime.now().isoformat()
            built.append({
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
                "seq": it.get("seq"),
            })
        __ff_write(msgp, built, fmt)
        try: self.status_label.setText(f"Saved {len(built)} messages → {msgp}")
        except Exception: pass

    def __ff_load(self):
        _, _, msgp, _ = __ff_paths()
        recs, fmt = __ff_read(msgp)
        if not recs:
            __ff_log("no records to load")
            return 0
        restored = []
        last_seq = 0
        for d in recs:
            try:
                t = d.get("ts")
                try:
                    from datetime import datetime as _dt
                    ts = _dt.fromisoformat(t) if isinstance(t, str) else t
                except Exception:
                    ts = None
                seq = d.get("seq")
                if isinstance(seq, int) and seq > last_seq: last_seq = seq
                restored.append({
                    "kind": d.get("kind"),
                    "text": d.get("text"),
                    "ts": ts, "ack": bool(d.get("ack")),
                    "ack_id": d.get("ack_id"), "to": d.get("to"), "frm": d.get("frm"),
                    "attempt": d.get("attempt"), "max_attempts": d.get("max_attempts"),
                    "failed": bool(d.get("failed")), "style": d.get("style"), "seq": seq,
                })
            except Exception: pass
        restored.reverse()
        self.chat_items = restored
        try: self._rebuild_chat_view()
        except Exception: pass
        if last_seq:
            try: self._seq_next = last_seq + 1
            except Exception: pass
        return len(restored)

    if "ChatApp" in globals() and hasattr(ChatApp, "__init__"):
        __base_init_ff = ChatApp.__init__
        def __patched_init_ff(self, *a, **kw):
            __base_init_ff(self, *a, **kw)
            # Ensure in-window File menu and wire Save (Ctrl+M)
            try:
                mb = self.menuBar()
                try: mb.setNativeMenuBar(False)
                except Exception: pass
                mfile = mb.addMenu("File")
                act_save = QAction("Save Message Log", self)
                act_save.setShortcut(QKeySequence("Ctrl+M"))
                act_save.triggered.connect(lambda: __ff_force_save(self))
                mfile.addAction(act_save)
            except Exception as e:
                __ff_log(f"menu error: {e!r}")
            # Load on startup
            try:
                n = __ff_load(self)
                __ff_log(f"loaded {n} records on startup")
                if n:
                    try: self.status_label.setText(f"Loaded {n} messages")
                    except Exception: pass
            except Exception as e:
                __ff_log(f"load error: {e!r}")
            # Initial save after 10s
            try:
                t = QTimer(self); t.setSingleShot(True); t.setInterval(10000)
                t.timeout.connect(lambda: (__ff_log('initial autosave'), __ff_force_save(self)))
                t.start(); self._ff_kick = t
            except Exception as e:
                __ff_log(f"kick error: {e!r}")
            # Autosave every 5 min
            try:
                if hasattr(self, "_ff_timer") and self._ff_timer is not None:
                    self._ff_timer.stop()
                self._ff_timer = QTimer(self)
                self._ff_timer.setInterval(300000)
                self._ff_timer.timeout.connect(lambda: (__ff_log('autosave tick'), __ff_force_save(self)))
                self._ff_timer.start()
                __ff_log("autosave started")
            except Exception as e:
                __ff_log(f"timer error: {e!r}")
        ChatApp.__init__ = __patched_init_ff
# =====================



# =====================
# TOP TOOLBAR ENFORCER (v1.4.0 toolbar)
# - Adds a persistent top QToolBar with: [File ▼] [Save Log]
# - File button opens the same File menu as the menubar (InstantPopup)
# - Save Log triggers the same manual save routine
# =====================
try:
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QToolBar, QToolButton, QAction, QMenu
    from PyQt5.QtGui import QKeySequence
except Exception as _e_toolbar:
    pass
else:
    if "ChatApp" in globals() and hasattr(ChatApp, "__init__"):
        __prev_init_toolbar = ChatApp.__init__
        def __patched_init_toolbar(self, *a, **kw):
            __prev_init_toolbar(self, *a, **kw)

            # Ensure we have a File menu in the in-window menubar
            try:
                mb = self.menuBar()
                try:
                    mb.setNativeMenuBar(False)  # force it inside the window
                except Exception:
                    pass
                file_menu = None
                for m in getattr(mb, "actions", lambda: [])():
                    try:
                        if str(m.text()).strip("& ").lower() == "file":
                            file_menu = m.menu()
                            break
                    except Exception:
                        pass
                if file_menu is None:
                    file_menu = mb.addMenu("File")
                # Ensure Save action exists
                save_action = None
                for act in file_menu.actions():
                    try:
                        if str(act.text()).strip() in ("Save Message Log", "Save Log"):
                            save_action = act
                            break
                    except Exception:
                        pass
                if save_action is None:
                    save_action = QAction("Save Log", self)
                    try:
                        save_action.setShortcut(QKeySequence("Ctrl+M"))
                    except Exception:
                        pass
                    # Wire up to whichever save routine exists
                    def _save_now():
                        try:
                            if "__ff_force_save" in globals():
                                __ff_force_save(self); return
                        except Exception: pass
                        try:
                            if "__rc_force_save" in globals():
                                __rc_force_save(self); return
                        except Exception: pass
                    save_action.triggered.connect(_save_now)
                    file_menu.addAction(save_action)
            except Exception as e:
                try: self.status_label.setText(f"Toolbar init menu error: {e!r}")
                except Exception: pass

            # Build a dedicated top toolbar
            try:
                tb = QToolBar("Main Toolbar", self)
                tb.setObjectName("main_toolbar")
                tb.setMovable(False)
                try: tb.setIconSize(tb.iconSize())  # keep default
                except Exception: pass

                # File toolbutton (dropdown opens File menu)
                file_btn = QToolButton(self)
                file_btn.setText("File")
                file_btn.setPopupMode(QToolButton.InstantPopup)
                try: file_btn.setMenu(file_menu)
                except Exception: 
                    # Create an empty menu if needed
                    m = QMenu("File", self)
                    m.addAction(save_action)
                    file_btn.setMenu(m)

                # Save Log action (as a toolbar button)
                tb.addWidget(file_btn)
                tb.addSeparator()
                tb.addAction(save_action)

                # Ensure toolbar is placed at the very top
                self.addToolBar(Qt.TopToolBarArea, tb)
            except Exception as e:
                try: self.status_label.setText(f"Toolbar init error: {e!r}")
                except Exception: pass

        ChatApp.__init__ = __patched_init_toolbar
# =====================



# =====================
# UNIVERSAL MENU + TOOLBAR ENFORCER (v1.4.0 toolbar2)
# Works for both QMainWindow and QWidget-based windows.
# - Ensures a visible File menu
# - Adds a Save Log action (Ctrl+M)
# - Adds either a QToolBar (for QMainWindow) or a top widget row with File ▼ + Save Log
# =====================
try:
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import (
        QMenuBar, QMenu, QAction, QToolBar, QToolButton,
        QWidget, QHBoxLayout, QVBoxLayout
    )
    from PyQt5.QtGui import QKeySequence
except Exception as _e_toolbar2:
    pass
else:
    if "ChatApp" in globals() and hasattr(ChatApp, "__init__"):
        __prev_init_tb2 = ChatApp.__init__
        def __patched_init_toolbar2(self, *a, **kw):
            __prev_init_tb2(self, *a, **kw)

            # Helper: resolve save function
            def _do_save_now():
                try:
                    if "__ff_force_save" in globals():
                        __ff_force_save(self); return
                except Exception: pass
                try:
                    if "__rc_force_save" in globals():
                        __rc_force_save(self); return
                except Exception: pass
                try:
                    self.status_label.setText("Save function not available.")
                except Exception: pass

            # Ensure we have a File menu and Save Log action
            def _ensure_file_menu_and_action():
                # Try menubar (QMainWindow)
                file_menu = None
                try:
                    if hasattr(self, "menuBar"):
                        mb = self.menuBar()
                        try: mb.setNativeMenuBar(False)
                        except Exception: pass
                        try: mb.show()
                        except Exception: pass
                        # Find or create "File"
                        try:
                            # PyQt5 QMenuBar doesn't expose actions() as a method on all styles
                            acts = getattr(mb, "actions", lambda: [])()
                            for a in acts:
                                try:
                                    if str(a.text()).strip("& ").lower() == "file":
                                        file_menu = a.menu(); break
                                except Exception: pass
                        except Exception:
                            pass
                        if file_menu is None:
                            file_menu = mb.addMenu("File")
                except Exception:
                    pass
                # If no QMainWindow menubar, create a top QMenuBar widget in layout
                if file_menu is None:
                    try:
                        cw = self if hasattr(self, "layout") else self.centralWidget()
                    except Exception:
                        cw = self
                    if cw is None or not hasattr(cw, "layout") or cw.layout() is None:
                        lay = QVBoxLayout(); cw = self
                        try: cw.setLayout(lay)
                        except Exception: pass
                    else:
                        lay = cw.layout()
                    # create a QMenuBar widget
                    mbw = None
                    try:
                        # try to find existing
                        for child in cw.findChildren(QMenuBar):
                            mbw = child; break
                    except Exception:
                        pass
                    if mbw is None:
                        mbw = QMenuBar(cw)
                        if isinstance(lay, QVBoxLayout):
                            lay.insertWidget(0, mbw)
                        else:
                            try: lay.addWidget(mbw)
                            except Exception: pass
                    file_menu = QMenu("File", mbw)
                    mbw.addMenu(file_menu)
                # Ensure Save Log action
                save_action = None
                try:
                    for act in file_menu.actions():
                        try:
                            if str(act.text()).strip() in ("Save Message Log","Save Log"):
                                save_action = act; break
                        except Exception:
                            pass
                except Exception:
                    pass
                if save_action is None:
                    save_action = QAction("Save Log", self)
                    try: save_action.setShortcut(QKeySequence("Ctrl+M"))
                    except Exception: pass
                    save_action.triggered.connect(_do_save_now)
                    try: file_menu.addAction(save_action)
                    except Exception: pass
                return file_menu, save_action

            def _ensure_toolbar(file_menu, save_action):
                # If QMainWindow, add a proper QToolBar
                if hasattr(self, "addToolBar"):
                    try:
                        tb = QToolBar("Main Toolbar", self)
                        tb.setObjectName("main_toolbar")
                        tb.setMovable(False)
                        # File dropdown button
                        btn = QToolButton(self)
                        btn.setText("File")
                        btn.setPopupMode(QToolButton.InstantPopup)
                        try: btn.setMenu(file_menu)
                        except Exception:
                            # create a tiny menu if needed
                            m = QMenu("File", self)
                            m.addAction(save_action)
                            btn.setMenu(m)
                        tb.addWidget(btn)
                        tb.addSeparator()
                        tb.addAction(save_action)
                        self.addToolBar(Qt.TopToolBarArea, tb)
                        return True
                    except Exception:
                        pass
                # Non-QMainWindow fallback: insert a top row with buttons
                try:
                    cw = self if hasattr(self, "layout") else self.centralWidget()
                    lay = cw.layout() if cw and hasattr(cw, "layout") else None
                    row = QWidget(cw)
                    h = QHBoxLayout(row); h.setContentsMargins(4,4,4,4); h.setSpacing(8)
                    # File dropdown as a toolbutton
                    btn = QToolButton(row); btn.setText("File")
                    try:
                        btn.setPopupMode(QToolButton.InstantPopup); btn.setMenu(file_menu)
                    except Exception:
                        pass
                    row.setObjectName("top_toolbar_row")
                    h.addWidget(btn); 
                    # Save action as a clickable proxy button
                    save_btn = QToolButton(row); save_btn.setText("Save Log")
                    try: save_btn.setShortcut(QKeySequence("Ctrl+M"))
                    except Exception: pass
                    save_btn.clicked.connect(_do_save_now)
                    h.addWidget(save_btn)
                    if lay is None:
                        lay = QVBoxLayout(cw); cw.setLayout(lay)
                    lay.insertWidget(0, row, 0, Qt.AlignTop)
                    return True
                except Exception:
                    return False

            file_menu, save_action = _ensure_file_menu_and_action()
            ok_tb = _ensure_toolbar(file_menu, save_action)
            try:
                if ok_tb:
                    self.status_label.setText("Toolbar/Menu ready")
                else:
                    self.status_label.setText("Toolbar/Menu could not be created")
            except Exception:
                pass

        ChatApp.__init__ = __patched_init_toolbar2
# =====================



# =====================
# AUTOSAVE POLICY: single 5‑min timer, NO initial 10‑second save (v1.4.0 nokick)
# =====================
try:
    from PyQt5.QtCore import QTimer
except Exception as _e_nokick:
    pass
else:
    if "ChatApp" in globals() and hasattr(ChatApp, "__init__"):
        __prev_init_nokick = ChatApp.__init__
        def __patched_init_nokick(self, *a, **kw):
            __prev_init_nokick(self, *a, **kw)

            # 1) Stop/remove any existing "initial kick" timers (10s saves)
            for attr in ("_ff_kick", "_final_initial_kick"):
                try:
                    t = getattr(self, attr, None)
                    if t is not None:
                        try: t.stop()
                        except Exception: pass
                        setattr(self, attr, None)
                except Exception:
                    pass

            # 2) Stop any existing autosave timers so we only keep ONE
            for attr in ("_ff_timer", "_final_autosave_timer", "_as_timer", "_rc_timer", "_sb_timer", "_final_timer"):
                try:
                    t = getattr(self, attr, None)
                    if t is not None:
                        try: t.stop()
                        except Exception: pass
                        setattr(self, attr, None)
                except Exception:
                    pass

            # 3) Start a single 5‑minute autosave timer
            def _do_save_now():
                try:
                    if "__ff_force_save" in globals():
                        __ff_force_save(self); return
                except Exception: pass
                try:
                    if "__rc_force_save" in globals():
                        __rc_force_save(self); return
                except Exception: pass
                # No-op fallback: status hint
                try:
                    self.status_label.setText("Save function not available.")
                except Exception:
                    pass

            try:
                self._autosave5_timer = QTimer(self)
                self._autosave5_timer.setInterval(300000)  # 5 minutes
                self._autosave5_timer.timeout.connect(autosave_callback)
                self._autosave5_timer.start()
                print("[Autosave] Timer started")
                __as_log("autosave timer started")
                from PyQt5.QtCore import QTimer as __QtTimer
                __QtTimer.singleShot(1000, lambda: self._autosave5_timer.start() if not self._autosave5_timer.isActive() else None)
                try:
                    self.status_label.setText("Autosave active (1 min for testing).")
                except Exception:
                    pass
            except Exception as e:
                try:
                    self.status_label.setText(f"Autosave timer error: {e!r}")
                except Exception:
                    pass

        ChatApp.__init__ = __patched_init_nokick
# =====================



# =====================
# MINIMAL CLEAN PATCH (v1.4.0 minimal_clean)
# - Remove/hide prior toolbars/save buttons
# - Single 5-minute autosave
# - Clear Message Window: SAVE first, then CLEAR UI, keep JSON
# =====================
try:
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QWidget, QPushButton
except Exception as _e_minimal:
    pass
else:
    # --- Helpers expected from earlier patches; provide minimal fallbacks
    def __mc_store_path():
        try:
            import os, sys
            if getattr(sys, "frozen", False):
                base = os.path.dirname(os.path.abspath(sys.executable))
            else:
                base = os.path.dirname(os.path.abspath(__file__))
            import os
            store = os.path.join(base, "store")
            os.makedirs(store, exist_ok=True)
            return os.path.join(store, "messages_v1.json")
        except Exception:
            return "messages_v1.json"

    

def __mc_force_save(self):
    """
    Safe writer with logging:
    - Builds from self.chat_items (preferred). If empty, tries to extract visible text
      from common 'messages' widgets as a very last resort (text only).
    - Skips writing if nothing to write (never overwrites JSON with empty).
    - Merges and de-duplicates with existing file.
    """
    try:
        import json, os
        from datetime import datetime
        # Resolve store path
        try:
            path = getattr(self, "_msg_store_path", None)
        except Exception:
            path = None
        if not path:
            _, _, path = __as_paths()
        # Gather records from in-memory chat_items
        chat_items = list(reversed(getattr(self, "chat_items", []) or []))
        built = []
        for it in chat_items:
            ts = it.get("ts")
            try: ts_iso = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
            except Exception: ts_iso = datetime.now().isoformat()
            built.append({
                "kind": it.get("kind"), "text": it.get("text"), "ts": ts_iso,
                "ack": bool(it.get("ack")), "ack_id": it.get("ack_id"),
                "to": it.get("to"), "frm": it.get("frm"),
                "attempt": it.get("attempt"), "max_attempts": it.get("max_attempts"),
                "failed": bool(it.get("failed")), "style": it.get("style"),
                "seq": it.get("seq"),
            })
        # Fallback: if nothing in chat_items, attempt to sniff from a QTextEdit/QPlainTextEdit
        wrote_from_text = False
        if not built:
            try:
                from PyQt5.QtWidgets import QTextEdit, QPlainTextEdit, QListWidget
                # Prefer a list of messages if present
                lsts = self.findChildren(QListWidget)
                if lsts:
                    lines = []
                    for i in range(lsts[0].count()):
                        try:
                            lines.append(str(lsts[0].item(i).text()))
                        except Exception:
                            pass
                    if lines:
                        for ln in lines:
                            built.append({"kind": "text", "text": ln, "ts": datetime.now().isoformat()})
                        wrote_from_text = True
                if not built:
                    edits = self.findChildren(QPlainTextEdit) + self.findChildren(QTextEdit)
                    if edits:
                        tx = str(edits[0].toPlainText())
                        lines = [ln for ln in tx.splitlines() if ln.strip()]
                        for ln in lines[-200:]:  # cap to last 200 lines
                            built.append({"kind": "text", "text": ln, "ts": datetime.now().isoformat()})
                        if lines:
                            wrote_from_text = True
            except Exception:
                pass
        # If still nothing, do not overwrite
        if not built:
            __as_log("autosave: no messages in memory/UI; skipping write (JSON untouched)")
            try: self.status_label.setText("Autosave: nothing to write (JSON untouched)")
            except Exception: pass
            return
        # Read existing file
        try:
            with open(path, "r", encoding="utf-8") as f:
                cur = json.load(f)
        except Exception:
            cur = {"version": 1, "messages": []}
        if isinstance(cur, list):
            existing = cur; fmt = "list"
        else:
            if not isinstance(cur, dict):
                cur = {"version": 1, "messages": []}
            existing = cur.get("messages", []); fmt = "dict"
        # Merge + dedupe
        def _key(d):
            s = d.get("seq")
            return ("seq", s) if isinstance(s, int) else ("tt", d.get("ts"), d.get("text"))
        seen = set(); merged = []
        for d in existing:
            k = _key(d); 
            if k in seen: continue
            seen.add(k); merged.append(d)
        for d in built:
            k = _key(d); 
            if k in seen: continue
            seen.add(k); merged.append(d)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(merged if fmt=="list" else {**cur, "messages": merged}, f, ensure_ascii=False, indent=2)
        msg = f"autosave write: {'UI-scan' if wrote_from_text else 'chat_items'} -> {len(built)} new / {len(merged)} total"
        __as_log(msg + f" → {path}")
        try: self.status_label.setText(msg)
        except Exception: pass
    except Exception as e:
        __as_log(f"autosave error: {e!r}")

    try:
        if "__rc_force_save" in globals():
            __rc_force_save(self); return
    except Exception: pass

    try:
        import json, os
        from datetime import datetime
        path = getattr(self, "_msg_store_path", None) or __mc_store_path()

        # Build new records from memory (oldest-first on disk)
        chat = list(reversed(getattr(self, "chat_items", []) or []))
        built = []
        for it in chat:
            ts = it.get("ts")
            try: ts_iso = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
            except Exception: ts_iso = datetime.now().isoformat()
            built.append({
                "kind": it.get("kind"), "text": it.get("text"), "ts": ts_iso,
                "ack": bool(it.get("ack")), "ack_id": it.get("ack_id"),
                "to": it.get("to"), "frm": it.get("frm"),
                "attempt": it.get("attempt"), "max_attempts": it.get("max_attempts"),
                "failed": bool(it.get("failed")), "style": it.get("style"),
                "seq": it.get("seq"),
            })

        # If no in-memory messages, DO NOT overwrite existing JSON
        if not built:
            try:
                self.status_label.setText("No messages in window — JSON left unchanged.")
            except Exception:
                pass
            return

        # Read existing file
        try:
            with open(path, "r", encoding="utf-8") as f:
                cur = json.load(f)
        except Exception:
            cur = {"version": 1, "messages": []}

        # Extract existing records as list
        if isinstance(cur, list):
            existing = cur
            fmt = "list"
        else:
            if not isinstance(cur, dict):
                cur = {"version": 1, "messages": []}
            existing = cur.get("messages", [])
            fmt = "dict"

        # Merge & dedupe (keep order oldest->newest). Key: seq, else (ts,text)
        def _key(d):
            s = d.get("seq")
            return ("seq", s) if isinstance(s, int) else ("tt", d.get("ts"), d.get("text"))

        seen = set()
        merged = []

        for d in existing:
            k = _key(d)
            if k in seen: 
                continue
            seen.add(k); merged.append(d)

        for d in built:
            k = _key(d)
            if k in seen:
                continue
            seen.add(k); merged.append(d)

        # Write back preserving schema
        if fmt == "list":
            payload = merged
        else:
            cur["messages"] = merged
            payload = cur

        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        try:
            self.status_label.setText(f"Saved {len(built)} new / {len(merged)} total → {path}")
        except Exception:
            pass
    except Exception:
        pass

        try:
            if "__rc_force_save" in globals():
                __rc_force_save(self); return
        except Exception: pass
        # Minimal fallback writer
        try:
            import json, os
            from datetime import datetime
            path = getattr(self, "_msg_store_path", None) or __mc_store_path()
            built = []
            for it in reversed(getattr(self, "chat_items", []) or []):
                ts = it.get("ts")
                try: ts_iso = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
                except Exception: ts_iso = datetime.now().isoformat()
                built.append({
                    "kind": it.get("kind"), "text": it.get("text"), "ts": ts_iso,
                    "ack": bool(it.get("ack")), "ack_id": it.get("ack_id"),
                    "to": it.get("to"), "frm": it.get("frm"),
                    "attempt": it.get("attempt"), "max_attempts": it.get("max_attempts"),
                    "failed": bool(it.get("failed")), "style": it.get("style"),
                    "seq": it.get("seq"),
                })
            # schema-preserving write
            try:
                with open(path, "r", encoding="utf-8") as f:
                    cur = json.load(f)
            except Exception:
                cur = {"version": 1, "messages": []}
            if isinstance(cur, list):
                payload = built
            else:
                if not isinstance(cur, dict):
                    cur = {"version": 1, "messages": []}
                cur["messages"] = built
                payload = cur
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            try:
                self.status_label.setText(f"Saved {len(built)} messages → {path}")
            except Exception:
                pass
        except Exception:
            pass

    if "ChatApp" in globals() and hasattr(ChatApp, "__init__"):
        __old_init = ChatApp.__init__
        def __mc_init(self, *a, **kw):
            __old_init(self, *a, **kw)
            # -- Kill/hide previously injected overlays/toolbars/save buttons if present
            try:
                names = [
                    "overlay_toolbar_row","wrapped_top_toolbar_row","forced_top_toolbar_row",
                    "row_save_log_above_messages","btn_save_log_centered_top",
                    "btn_save_log_serial","btn_save_log_serial2","btn_save_log_center",
                    "btn_save_log","main_toolbar"
                ]
                for nm in names:
                    for w in self.findChildren(QWidget):
                        try:
                            if w.objectName() == nm:
                                w.hide(); w.setParent(None)
                        except Exception:
                            pass
            except Exception:
                pass

            # -- Ensure single 5-minute autosave (disable older timers if any)
            try:
                for attr in ("_ff_timer","_final_autosave_timer","_as_timer","_rc_timer","_sb_timer","_autosave5_timer"):
                    try:
                        t = getattr(self, attr, None)
                        if t is not None:
                            t.stop()
                            setattr(self, attr, None)
                    except Exception:
                        pass

                from PyQt5.QtCore import QTimer as __QtTimerClass
                self._autosave5_timer = __QtTimerClass(self)
                self._autosave5_timer.setInterval(300000)  # 5 minutes

                def autosave_callback():
                    try:
                        print("[Autosave] Timer triggered")
                    except Exception:
                        pass
                    try:
                        __as_log("autosave tick")
                    except Exception:
                        pass
                    try:
                        __mc_force_save(self)
                    except Exception as e:
                        try:
                            print(f"[Autosave] Error in callback: {e!r}")
                        except Exception:
                            pass
                        try:
                            __as_log(f"autosave error: {e!r}")
                        except Exception:
                            pass
                        try:
                            self.status_label.setText(f"Autosave error: {e!r}")
                        except Exception:
                            pass

                self._autosave5_timer.timeout.connect(autosave_callback)
                self._autosave5_timer.start()
                try:
                    print("[Autosave] Timer started")
                except Exception:
                    pass
                try:
                    __as_log("autosave timer started")
                except Exception:
                    pass
                try:
                    self.status_label.setText("Autosave active (1 min for testing).")
                except Exception:
                    pass
                # Late-start safety: re-check after 1s
                try:
                    from PyQt5.QtCore import QTimer as __QtTimer
                    __QtTimer.singleShot(1000, lambda: self._autosave5_timer.start() if not self._autosave5_timer.isActive() else None)
                except Exception:
                    pass

            except Exception as e:
                try:
                    self.status_label.setText(f"Autosave timer error: {e!r}")
                except Exception:
                    pass


            # -- Hook Clear: SAVE first, then clear UI, DO NOT delete JSON
            if hasattr(ChatApp, "_clear_receive_window"):
                __orig_clear = ChatApp._clear_receive_window
                

def __mc_clear(self2):
    # UI-only clear: do NOT save, do NOT touch disk
    try:
        self2.chat_items = []
    except Exception:
        pass
    try:
        self2._rebuild_chat_view()
    except Exception:
        pass
    try:
        self2.status_label.setText("Window cleared (UI only). JSON untouched.")
    except Exception:
        pass
ChatApp._clear_receive_window = __mc_clear

ChatApp.__init__ = __mc_init
# =====================



# =====================
# v1.4.0 autosave post-init fix (safe override)
# =====================
try:
    from PyQt5.QtCore import QTimer
except Exception:
    QTimer = None

if QTimer and "ChatApp" in globals() and hasattr(ChatApp, "__init__"):
    __prev_init_autosavefix = ChatApp.__init__

    def __patched_init_autosavefix(self, *a, **kw):
        __prev_init_autosavefix(self, *a, **kw)

        # Stop any existing autosave timers to avoid duplicates
        for attr in ("_ff_timer","_final_autosave_timer","_as_timer","_rc_timer","_sb_timer","_autosave5_timer","_autosave_diag_timer"):
            try:
                t = getattr(self, attr, None)
                if t is not None:
                    t.stop()
                    setattr(self, attr, None)
            except Exception:
                pass

        # Create a robust 1-minute autosave with diagnostics
        try:
            self._autosave_diag_timer = QTimer(self)
            self._autosave_diag_timer.setInterval(300000)  # 5 minutes
            def autosave_callback():
                try:
                    print("[Autosave] Timer triggered")
                except Exception:
                    pass
                try:
                    __as_log("autosave tick")
                except Exception:
                    pass
                try:
                    __mc_force_save(self)
                except Exception as e:
                    try:
                        print(f"[Autosave] Error in callback: {e!r}")
                    except Exception:
                        pass
                    try:
                        __as_log(f"autosave error: {e!r}")
                    except Exception:
                        pass
                    try:
                        self.status_label.setText(f"Autosave error: {e!r}")
                    except Exception:
                        pass
            self._autosave_diag_timer.timeout.connect(autosave_callback)
            self._autosave_diag_timer.start()
            try:
                print("[Autosave] Timer started")
            except Exception:
                pass
            try:
                __as_log("autosave timer started")
            except Exception:
                pass
            try:
                self.status_label.setText("Autosave active (1 min for testing).")
            except Exception:
                pass
        except Exception as e:
            try:
                print(f"[Autosave] Setup error: {e!r}")
            except Exception:
                pass
            try:
                __as_log(f"timer setup error: {e!r}")
            except Exception:
                pass
            try:
                self.status_label.setText(f"Autosave setup error: {e!r}")
            except Exception:
                pass

    ChatApp.__init__ = __patched_init_autosavefix


# =====================
# UI RENDER ADDON (ensure messages appear in the window on startup)
# =====================
def _rc_render_ui(self, items_newest_first):
    # Best-effort: show items in the visible message widget.
    # Tries a QListWidget first; falls back to a (QPlain)TextEdit.
    try:
        from PyQt5.QtWidgets import QListWidget, QListWidgetItem, QPlainTextEdit, QTextEdit
    except Exception:
        return
    # Prefer a QListWidget
    try:
        lst = None
        # Common attribute names
        for nm in ("messages_list", "message_list", "lst_messages", "lst_chat", "chat_list"):
            try:
                w = getattr(self, nm, None)
                if isinstance(w, QListWidget):
                    lst = w
                    break
            except Exception:
                pass
        if lst is None:
            # Fallback: pick the first QListWidget
            lsts = self.findChildren(QListWidget)
            if lsts:
                lst = lsts[0]
        if lst is not None:
            lst.clear()
            for it in items_newest_first:
                ts = it.get("ts")
                ts_str = ""
                try:
                    ts_str = ts.strftime("%Y-%m-%d %H:%M:%S") if hasattr(ts, "strftime") else str(ts or "")
                except Exception:
                    ts_str = str(ts or "")
                who = (it.get("frm") or it.get("to") or "").strip()
                kind = it.get("kind") or ""
                text = it.get("text") or ""
                ack = it.get("ack_id") or ""
                line = f"[{ts_str}] {kind.upper()} {who}: {text}"
                if ack:
                    line += f"  (ACK:{ack})"
                try:
                    lst.addItem(QListWidgetItem(line))
                except Exception:
                    pass
            try:
                lst.scrollToTop()
            except Exception:
                pass
            return
    except Exception:
        pass
    # Fallback: dump to the first text editor
    try:
        editors = self.findChildren(QPlainTextEdit) + self.findChildren(QTextEdit)
        if editors:
            ed = editors[0]
            lines = []
            for it in items_newest_first:
                ts = it.get("ts")
                try:
                    ts_str = ts.strftime("%Y-%m-%d %H:%M:%S") if hasattr(ts, "strftime") else str(ts or "")
                except Exception:
                    ts_str = str(ts or "")
                who = (it.get("frm") or it.get("to") or "").strip()
                kind = it.get("kind") or ""
                text = it.get("text") or ""
                ack = it.get("ack_id") or ""
                line = f"[{ts_str}] {kind.upper()} {who}: {text}"
                if ack:
                    line += f"  (ACK:{ack})"
                lines.append(line)
            try:
                ed.setPlainText("\n".join(lines))
                ed.moveCursor(ed.textCursor().End)
            except Exception:
                pass
    except Exception:
        pass
# =====================


# =====================
# BEACON FILTER (v1.4.0)
# =====================
def _rc_guess_mycall(self):
    # Try common attribute names
    for nm in ("my_call","mycall","MyCall","callsign","own_callsign","myCall","MYCALL"):
        try:
            val = getattr(self, nm, None)
            if isinstance(val, str) and val.strip():
                return val.strip()
        except Exception:
            pass
    # Try settings-like dicts
    for nm in ("settings","config","cfg","app_settings"):
        try:
            obj = getattr(self, nm, None)
            if isinstance(obj, dict):
                for key in ("my_call","mycall","callsign","own_callsign","MYCALL","MyCall"):
                    v = obj.get(key)
                    if isinstance(v, str) and v.strip():
                        return v.strip()
        except Exception:
            pass
    return None

def _rc_is_beacon_tx(item, mycall):
    try:
        if not item: return False
        if (item.get("kind") or "").lower() != "sent":
            return False
        txt = (item.get("text") or "").upper()
        if not mycall:
            return False
        mc = str(mycall).upper().strip()
        # Beacon condition: message contains <MYCALL> literally (case-insensitive)
        return f"<{mc}>" in txt
    except Exception:
        return False

def _rc_update_last_tx(self, item):
    # Update a "Last Beacon" label/value if present; otherwise status
    try:
        import datetime as _dt
        ts = item.get("ts")
        try:
            ts_str = ts.strftime("%Y-%m-%d %H:%M:%S") if hasattr(ts, "strftime") else str(ts or "")
        except Exception:
            ts_str = str(ts or "")
        # Prefer a specific label if it exists
        from PyQt5.QtWidgets import QLabel
        # Common attribute names for the label
        for nm in ("last_tx_label","lbl_last_tx","label_last_tx","lblLastTx","lastTxLabel","last_beacon_label","lbl_last_beacon","label_last_beacon","lblLastBeacon","lastBeaconLabel"):
            try:
                w = getattr(self, nm, None)
                if isinstance(w, QLabel):
                    w.setText(f"Last TX: {ts_str}")
                    return
            except Exception:
                pass
        # Fallback: search for a QLabel whose text starts with "Last Beacon"
        try:
            labels = self.findChildren(QLabel)
            for lab in labels:
                try:
                    if str(lab.text()).strip().lower().startswith("last tx") or str(lab.text()).strip().lower().startswith("last beacon"):
                        lab.setText(f"Last TX: {ts_str}")
                        return
                except Exception:
                    pass
        except Exception:
            pass
        # Ultimate fallback: status line
        try:
            self.status_label.setText(f"Last TX: {ts_str}")
        except Exception:
            pass
    except Exception:
        pass
# =====================


# =====================
# UI LABEL TWEAK: "Frequencies" -> "Frequencies D-USB"
# =====================
def _rc_fix_freq_label(self):
    try:
        from PyQt5.QtWidgets import QLabel
    except Exception:
        return
    try:
        # 1) Try common attribute names first
        for nm in ("frequencies_label","lbl_frequencies","label_frequencies","lblFrequencies","frequenciesLabel"):
            try:
                w = getattr(self, nm, None)
                if isinstance(w, QLabel):
                    w.setText("Frequencies D-USB")
                    return
            except Exception:
                pass
        # 2) Fallback: scan all labels for exact "Frequencies" (optionally with colon)
        try:
            labs = self.findChildren(QLabel)
        except Exception:
            labs = []
        target_texts = {"frequencies", "frequencies:"}
        for lab in labs:
            try:
                t = str(lab.text()).strip().lower()
                if t in target_texts:
                    lab.setText("Frequencies D-USB")
                    return
            except Exception:
                pass
    except Exception:
        pass
# =====================



# =====================
# UI HEADER TWEAK: Section title "Frequencies" -> "Frequencies D-USB"
# =====================
def _rc_fix_freq_header(self):
    try:
        from PyQt5.QtWidgets import QGroupBox, QTabWidget, QLabel
    except Exception:
        return
    target = {"frequencies", "frequencies:"}

    # 1) QGroupBox titles (most common for section headers)
    try:
        # Try common attribute names
        for nm in ("frequencies_group", "group_frequencies", "grp_frequencies", "frequenciesGroup", "gbFrequencies"):
            try:
                gb = getattr(self, nm, None)
                if isinstance(gb, QGroupBox):
                    gb.setTitle("Frequencies D-USB")
                    return
            except Exception:
                pass
        # Fallback: scan all groupboxes for matching title
        try:
            gbs = self.findChildren(QGroupBox)
        except Exception:
            gbs = []
        for gb in gbs:
            try:
                t = str(gb.title()).strip().lower()
                if t in target:
                    gb.setTitle("Frequencies D-USB")
                    return
            except Exception:
                pass
    except Exception:
        pass

    # 2) QTabWidget tab text
    try:
        tabs = self.findChildren(QTabWidget)
    except Exception:
        tabs = []
    for tw in tabs:
        try:
            for i in range(tw.count()):
                t = str(tw.tabText(i)).strip().lower()
                if t in target:
                    tw.setTabText(i, "Frequencies D-USB")
                    return
        except Exception:
            pass

    # 3) Fallback: header as a standalone QLabel (already handled by _rc_fix_freq_label)
    try:
        _rc_fix_freq_label(self)
    except Exception:
        pass
# =====================