
import sys, os, types, time, re, math

from PyQt5.QtWidgets import QApplication, QLabel, QHBoxLayout, QComboBox, QPushButton, QGroupBox
from PyQt5.QtCore import QTimer

# Import the base app
import importlib.util

BASE_PATH = os.path.join(os.path.dirname(__file__), "Robust_Chat_v1.6.py")
spec = importlib.util.spec_from_file_location("robust_base", BASE_PATH)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

# Helpers to load/save small json
def load_json(name):
    try:
        import json
        base_dir = os.path.dirname(BASE_PATH)
        p = os.path.join(base_dir, name)
        if os.path.isfile(p):
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return None

def save_json(name, data):
    try:
        import json
        base_dir = os.path.dirname(BASE_PATH)
        p = os.path.join(base_dir, name)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def install_gps_ui(w):
    # Find the "Serial Port" group
    serial_group = None
    for gb in w.findChildren(QGroupBox):
        try:
            if gb.title().strip() == "Serial Port":
                serial_group = gb
                break
        except Exception:
            pass
    if not serial_group:
        return

    # Build a row under the TNC COM line: GPS Port combo + Refresh + Read GPS + hint
    v = serial_group.layout()
    if v is None:
        return

    # Transparent container so it blends with theme panel background
    from PyQt5.QtWidgets import QWidget
    from PyQt5.QtCore import Qt
    cont = QWidget(serial_group)
    try:
        cont.setAutoFillBackground(False)
        cont.setAttribute(Qt.WA_TranslucentBackground, True)
        cont.setStyleSheet('background-color: transparent;')
    except Exception:
        pass

    row = QHBoxLayout(cont)
    row.setContentsMargins(0,0,0,0)
    row.setSpacing(8)

    w.gps_label = QLabel('GPS Port:')
    try:
        w.gps_label.setStyleSheet('background-color: transparent;')
    except Exception:
        pass
    row.addWidget(w.gps_label)

    w.gps_port_combo = QComboBox()
    row.addWidget(w.gps_port_combo, 1)

    btn_refresh = QPushButton('Refresh')
    row.addWidget(btn_refresh)

    btn_read = QPushButton('Read GPS')
    row.addWidget(btn_read)

    w.gps_hint_label = QLabel('Auto 15 mins')
    try:
        w.gps_hint_label.setStyleSheet('background-color: transparent;')
    except Exception:
        pass
    row.addWidget(w.gps_hint_label)

    v.addWidget(cont)

    # Methods -------------------------------------------------
    def refresh_gps_ports(self):
        ports = [f"COM{i}" for i in range(1, 17)] if os.name == "nt" else ["/dev/ttyS0","/dev/ttyUSB0"]
        try:
            self.gps_port_combo.clear()
            self.gps_port_combo.addItems(ports)
            st = load_json("settings.json") or {}
            gps = st.get("gps", {}) if isinstance(st, dict) else {}
            saved = gps.get("port", "")
            if saved:
                idx = self.gps_port_combo.findText(saved)
                if idx >= 0:
                    self.gps_port_combo.setCurrentIndex(idx)
        except Exception:
            pass

    
    def read_gps_position(self):
        """Safe GPS reader with full exception guards."""
        try:
            import time, re, math
            try:
                port = self.gps_port_combo.currentText().strip() if hasattr(self, 'gps_port_combo') else ''
            except Exception:
                port = ''
            if not port:
                try:
                    self._status('Select a GPS port first.', 3000)
                except Exception:
                    pass
                return

            # Persist chosen port
            try:
                st = load_json("settings.json") or {}
                if not isinstance(st, dict):
                    st = {}
                gps = st.get("gps", {})
                if not isinstance(gps, dict):
                    gps = {}
                gps["port"] = port
                st["gps"] = gps
                save_json("settings.json", st)
            except Exception:
                pass

            # Baud fallbacks
            bauds = [9600, 4800, getattr(self, '_serial_baud_default', 38400)]
            lat = lon = float('nan')

            def _nmea_deg(val: str, hemi: str) -> float:
                try:
                    if not val or not hemi or '.' not in val:
                        return float('nan')
                    deg_len = 2 if hemi.upper() in ('N','S') else 3
                    d = int(val[:deg_len]); m = float(val[deg_len:])
                    dec = d + m/60.0
                    if hemi.upper() in ('S','W'):
                        dec = -dec
                    return dec
                except Exception:
                    return float('nan')

            NMEA_RMC = re.compile(r'^\$(?:GP|GN|GL|GA)RMC,', re.I)
            NMEA_GGA = re.compile(r'^\$(?:GP|GN|GL|GA)GGA,', re.I)
            POS_DEC_RE = re.compile(r'(?P<lat>[-+]?\d{1,2}\.\d{3,})[,/\s]+(?P<lon>[-+]?\d{1,3}\.\d{3,})')

            try:
                import serial  # pyserial
            except Exception:
                try:
                    self._status('pyserial not available for GPS read.', 3000)
                except Exception:
                    pass
                return

            for b in bauds:
                try:
                    with serial.Serial(port, b, timeout=0.2) as s:
                        start_t = time.time(); buf = b''
                        try:
                            s.reset_input_buffer()
                        except Exception:
                            pass
                        while (time.time() - start_t) < 2.0:
                            try:
                                chunk = s.read(256)
                                if chunk:
                                    buf += chunk
                                    if len(buf) > 8192:
                                        break
                            except Exception:
                                break
                        try:
                            text = buf.decode(errors='ignore')
                        except Exception:
                            text = ''

                        if text:
                            for line in text.splitlines():
                                if NMEA_RMC.match(line):
                                    parts = line.split(',')
                                    if len(parts) >= 7:
                                        lat = _nmea_deg(parts[3], parts[4])
                                        lon = _nmea_deg(parts[5], parts[6])
                                        break
                                if NMEA_GGA.match(line):
                                    parts = line.split(',')
                                    if len(parts) >= 6:
                                        lat = _nmea_deg(parts[2], parts[3])
                                        lon = _nmea_deg(parts[4], parts[5])
                                        break
                            if (math.isnan(lat) or math.isnan(lon)) and POS_DEC_RE.search(text):
                                try:
                                    m = POS_DEC_RE.search(text)
                                    lat = float(m.group('lat')); lon = float(m.group('lon'))
                                except Exception:
                                    pass
                except Exception:
                    continue

                if not (math.isnan(lat) or math.isnan(lon) or abs(lat)>90 or abs(lon)>180):
                    break

            if math.isnan(lat) or math.isnan(lon) or abs(lat)>90 or abs(lon)>180:
                try:
                    self._status('GPS parse failed. Enter Fixed GPS or try again.', 4000)
                except Exception:
                    pass
                return

            try:
                if hasattr(self, 'fixed_lat_edit'):
                    self.fixed_lat_edit.clear()
                if hasattr(self, 'fixed_lon_edit'):
                    self.fixed_lon_edit.clear()
                if hasattr(self, 'fixed_lat_edit'):
                    self.fixed_lat_edit.setText(f"{lat:.5f}")
                if hasattr(self, 'fixed_lon_edit'):
                    self.fixed_lon_edit.setText(f"{lon:.5f}")
                self.save_fixed_gps()

                st2 = load_json("settings.json") or {}
                if not isinstance(st2, dict):
                    st2 = {}
                gps2 = st2.get("gps", {})
                if not isinstance(gps2, dict):
                    gps2 = {}
                import time as _t
                gps2["last_update"] = int(_t.time())
                gps2["lat"] = float(f"{lat:.5f}")
                gps2["lon"] = float(f"{lon:.5f}")
                st2["gps"] = gps2
                save_json("settings.json", st2)
                self._status('GPS position updated.', 3000)
            except Exception:
                pass

        except Exception as _fatal:
            # swallow any unexpected exception to avoid process exit
            try:
                self._status(f'GPS read fatal: {type(_fatal).__name__}', 4000)
            except Exception:
                pass
            return


    # Bind methods to the instance
    w.refresh_gps_ports = types.MethodType(refresh_gps_ports, w)
    w.read_gps_position = types.MethodType(read_gps_position, w)

    # Wire buttons
    btn_refresh.clicked.connect(w.refresh_gps_ports)
    btn_read.clicked.connect(w.read_gps_position)

    # Populate list once
    w.refresh_gps_ports()

    # Start a 15-minute repeating timer + initial kick after 3s
    try:
        w.gps_refresh_timer = QTimer(w)
        w.gps_refresh_timer.setInterval(15 * 60 * 1000)
        w.gps_refresh_timer.timeout.connect(w.read_gps_position)
        QTimer.singleShot(500, lambda: w.gps_refresh_timer.start())
        QTimer.singleShot(3500, w.read_gps_position)
    except Exception:
        pass



def reflow_fixed_and_upload(w):
    """
    Safer reflow:
      - Find Fixed GPS + File Upload groups.
      - Reduce lat/lon edit widths.
      - Create a horizontal row container and insert it EXACTLY where Fixed GPS was.
      - Guard against double-reflow to avoid crashes.
    """
    from PyQt5.QtWidgets import QGroupBox, QWidget, QHBoxLayout, QLineEdit, QSizePolicy
    from PyQt5.QtCore import Qt

    if getattr(w, "_fixed_upload_reflowed", False):
        return

    fixed_group = None
    file_group = None
    for gb in w.findChildren(QGroupBox):
        try:
            title = gb.title().strip()
        except Exception:
            title = ""
        if title.startswith("Fixed GPS"):
            fixed_group = gb
        elif title.startswith("File Upload"):
            file_group = gb

    if fixed_group is None or file_group is None:
        return

    try:
        lat_edit = getattr(w, "fixed_lat_edit", None)
        lon_edit = getattr(w, "fixed_lon_edit", None)
        if lat_edit is None or lon_edit is None:
            edits = fixed_group.findChildren(QLineEdit)
            if len(edits) >= 2:
                lat_edit, lon_edit = edits[0], edits[1]
        for ed in (lat_edit, lon_edit):
            if not ed:
                continue
            sp = ed.sizePolicy()
            sp.setHorizontalPolicy(QSizePolicy.Expanding)
            ed.setSizePolicy(sp)
            ed.setMinimumWidth(110)
            ed.setMaximumWidth(220)
    except Exception:
        pass

    try:
        parent_layout = fixed_group.parentWidget().layout()
    except Exception:
        parent_layout = None
    if parent_layout is None:
        return

    index_of_fixed = None
    try:
        count = parent_layout.count()
        for i in range(count):
            item = parent_layout.itemAt(i)
            wgt = item.widget() if item is not None else None
            if wgt is fixed_group:
                index_of_fixed = i
                break
    except Exception:
        index_of_fixed = None
    if index_of_fixed is None:
        index_of_fixed = parent_layout.count()

    from PyQt5.QtWidgets import QWidget
    row = QWidget(fixed_group.parentWidget())
    row.setObjectName("fixed_upload_row")
    row.setAttribute(Qt.WA_TranslucentBackground, True)
    row.setAutoFillBackground(False)
    h = QHBoxLayout(row)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(12)

    try:
        parent_layout.removeWidget(fixed_group)
    except Exception:
        pass
    try:
        parent_layout.removeWidget(file_group)
    except Exception:
        pass
    fixed_group.setParent(row)
    file_group.setParent(row)

    h.addWidget(fixed_group, 2)
    h.addWidget(file_group, 3)

    try:
        parent_layout.insertWidget(index_of_fixed, row)
    except Exception:
        try:
            parent_layout.addWidget(row)
        except Exception:
            pass

    w._fixed_upload_reflowed = True


def tweak_upload_and_messages(w):
    """
    Adjust UI post-build:
      • Extend File Upload path field to end of row/column.
      • Increase stretch for File Upload group relative to Fixed GPS.
      • Restore multi-line wrap for Messages list (no horizontal scroll).
    """
    try:
        from PyQt5.QtWidgets import QGroupBox, QLineEdit, QSizePolicy, QWidget, QHBoxLayout, QListView
        from PyQt5.QtCore import Qt

        # --- File Upload group ---
        file_group = None
        for gb in w.findChildren(QGroupBox):
            try:
                if gb.title().strip().startswith("File Upload"):
                    file_group = gb
                    break
            except Exception:
                pass

        if file_group is not None:
            edits = file_group.findChildren(QLineEdit)
            if edits:
                path_edit = edits[0]
                sp = path_edit.sizePolicy()
                sp.setHorizontalPolicy(QSizePolicy.Expanding)
                path_edit.setSizePolicy(sp)
                try:
                    path_edit.setMinimumWidth(300)
                    path_edit.setMaximumWidth(16777215)
                except Exception:
                    pass

            row = w.findChild(QWidget, "fixed_upload_row")
            if row is not None:
                lay = row.layout()
                if isinstance(lay, QHBoxLayout):
                    try:
                        lay.setStretch(0, 2)
                        lay.setStretch(1, 3)
                    except Exception:
                        pass

        # --- Messages wrap ---
        msgs = getattr(w, "messages_list", None)
        if msgs is not None:
            try:
                msgs.setWordWrap(True)
            except Exception:
                pass
            try:
                msgs.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            except Exception:
                pass
            try:
                msgs.setUniformItemSizes(False)
                msgs.setResizeMode(QListView.Adjust)
            except Exception:
                pass
    except Exception:
        pass



def move_padlock_to_upload_row(w):
    """
    Move the Secure Pad padlock button from the bottom of the left column
    into the same row as the File Upload section (to the far right).
    """
    try:
        btn = getattr(w, "secure_btn", None)
        if btn is None:
            return
        # Find our combined row
        row = w.findChild(QWidget, "fixed_upload_row")
        if row is None or row.layout() is None:
            return
        lay = row.layout()

        # Detach from previous parent layout if any
        try:
            # remove from content_layout if that's where it sits
            parent_lay = w.content_layout
            parent_lay.removeWidget(btn)
        except Exception:
            pass

        # Tweak size to fit inline nicely
        try:
            btn.setFlat(False)
            btn.setFixedHeight(28)
            btn.setFixedWidth(36)
            btn.setToolTip("Open Secure Pad")
        except Exception:
            pass

        # Add as last widget on the row
        btn.setParent(row)
        lay.addWidget(btn, 0, Qt.AlignVCenter)
    except Exception:
        pass




def hook_messages_insert_top_with_timestamp(w):
    """
    Patch QListWidget so ALL additions (addItem/insertItem) are:
      - normalized to have a unified timestamp: "Oct 14 2025 [12:06.19]  text"
      - inserted at the TOP (index 0)
      - stripped of any leading [HH:MM:SS] or old stamps
    Applies to both SENT and RECEIVED messages.
    """
    try:
        from PyQt5.QtWidgets import QListWidgetItem
        from PyQt5.QtCore import Qt
        import re, datetime

        if not hasattr(w, "messages_list") or w.messages_list is None:
            return
        if getattr(w, "_msgs_hooked", False):
            return

        lst = w.messages_list
        orig_add = lst.addItem
        orig_insert = lst.insertItem

        stamp_re = re.compile(r'^(?:\w{3}\s+\d{1,2}\s+\d{4}\s\[\d{2}:\d{2}\.\d{2}\]\s+)')
        bracket_time_re = re.compile(r'^\[\d{2}:\d{2}:\d{2}\]\s*')

        def _fmt_prefix():
            now = datetime.datetime.now()
            return now.strftime("%b %d %Y [%H:%M.%S]")

        def _normalize_item(arg):
            # Return a QListWidgetItem with cleaned text and a timestamp prefix
            if isinstance(arg, QListWidgetItem):
                it = arg
            else:
                it = QListWidgetItem(str(arg))

            txt = it.text()
            # If already in our unified format, keep as-is
            if not stamp_re.match(txt):
                # Strip stray [HH:MM:SS] (received) or any old stamp
                txt = bracket_time_re.sub('', txt)
                # Prepend current unified timestamp
                txt = f"{_fmt_prefix()}  {txt}"
                it.setText(txt)
            return it

        def addItem_hook(arg):
            try:
                it = _normalize_item(arg)
                lst.insertItem(0, it)
                lst.scrollToTop()
            except Exception:
                try:
                    orig_add(arg)
                except Exception:
                    pass

        def insertItem_hook(row, arg):
            # Ignore 'row' and always insert at the top with normalized timestamp
            try:
                it = _normalize_item(arg)
                orig_insert(0, it)
                lst.scrollToTop()
            except Exception:
                try:
                    orig_insert(row, arg)
                except Exception:
                    pass

        # Patch both
        lst.addItem = addItem_hook
        lst.insertItem = insertItem_hook
        # Retro-normalize existing items once
        try:
            count = lst.count()
            for i in range(count):
                it = lst.item(i)
                if it:
                    txt = it.text()
                    # remove bare [HH:MM:SS] or re-stamp
                    if bracket_time_re.match(txt) or not stamp_re.match(txt):
                        core = bracket_time_re.sub('', txt)
                        it.setText(f"{_fmt_prefix()}  {core}")
        except Exception:
            pass
        w._msgs_hooked = True
    except Exception:
        pass





def compact_top_sections(w):
    """
    Reduce the vertical footprint of the top three sections by setting a fixed pixel height,
    while keeping enough padding so the section titles remain readable.
    """
    try:
        from PyQt5.QtWidgets import QGroupBox
        TARGETS = {
            "Serial Port": 250,
            "Fleet Manager": 250,
            "Incoming Files": 250,
        }
        for gb in w.findChildren(QGroupBox):
            try:
                title = gb.title().strip()
            except Exception:
                title = ""
            if title in TARGETS:
                h = TARGETS[title]
                # Tighten inner spacing but add extra top margin for the title
                try:
                    lay = gb.layout()
                    if lay:
                        lay.setContentsMargins(6, 20, 6, 6)  # top=20 for title clearance
                        lay.setSpacing(6)
                except Exception:
                    pass
                # Ensure QGroupBox reserves vertical space for title across themes
                try:
                    cur_ss = gb.styleSheet() if hasattr(gb, 'styleSheet') else ''
                    add = 'QGroupBox{padding-top:18px;}'
                    if add not in cur_ss:
                        gb.setStyleSheet((cur_ss + ' ' + add).strip())
                except Exception:
                    pass
                # Fix height
                try:
                    gb.setMinimumHeight(h)
                    gb.setMaximumHeight(h)
                except Exception:
                    pass
    except Exception:
        pass


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    try:
        w = base.ChatApp()
    except Exception as e:
        print('ChatApp init error:', e)
        raise
    try:
        hook_messages_insert_top_with_timestamp(w)
    except Exception:
        pass
    try:
        w.setWindowTitle("Robust Chat v1.6.1")
    except Exception:
        pass

    # After base UI is built, install GPS row into Serial group
    install_gps_ui(w)

    from PyQt5.QtCore import QTimer as _QT
    def _safe_reflow():
        try:
            reflow_fixed_and_upload(w)
        except Exception:
            try:
                w._status('Layout reflow skipped (safe mode).', 3000)
            except Exception:
                pass
    _QT.singleShot(50, _safe_reflow)

    def _tweak():
        try:
            tweak_upload_and_messages(w)
        except Exception:
            pass
    _QT.singleShot(120, _tweak)

    # Hook messages list to insert newest at top + timestamp
    _QT.singleShot(180, lambda: hook_messages_insert_top_with_timestamp(w))

    # Move padlock inline with File Upload row
    _QT.singleShot(200, lambda: move_padlock_to_upload_row(w))

    # Compact the three top sections by ~3 rows
    _QT.singleShot(260, lambda: compact_top_sections(w))

    # Show as the base app would
    try:
        w.show()
    except Exception:
        pass
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
