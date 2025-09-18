
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
LinkmapViewer v5 — Uniform triangles (18px) + edge routing
- All triangle icons are the same size (18 px)
- Lines are trimmed at triangle borders (no entry)
- If a line would cross any callsign label (except its own endpoints),
  it is rerouted with a single diagonal bend to avoid collisions
- Labels centered under triangles with overlap avoidance
"""

import os, sys, json, math, argparse
from PyQt5 import QtCore, QtGui, QtWidgets

DARK_BG  = "#0b0f14"
PANEL_BG = "#0f1621"
FG_TEXT  = "#00FF00"  # callsign text green
EDGE_QCOLOR = QtGui.QColor(0, 200, 0, 210)  # green lines

C_CYAN   = QtGui.QColor("#00FFFF")  # mycall
C_RED    = QtGui.QColor("#FF3B30")  # parent
C_ORANGE = QtGui.QColor("#FFA500")  # child

TRI_RADIUS = 18  # uniform triangle size for all roles

class LinkGraph:
    def __init__(self, path):
        self.path = path
        self.mycall = "ME"
        self.nodes = []  # [{'label','role'}]
        self.edges = []  # [(src, dst)]
        self.load()

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {"mycall":"ME","heard":{}}
        self.mycall = (data.get("mycall") or "ME").upper()
        heard = data.get("heard", {}) or {}

        self.nodes = [{"label": self.mycall, "role": "center"}]
        self.edges = []

        parent_index = {}
        for p, pdata in heard.items():
            pi = len(self.nodes)
            self.nodes.append({"label": p, "role": "parent"})
            parent_index[p] = pi
            self.edges.append((0, pi))  # center -> parent (first along line)

            for c in (pdata.get("children") or {}).keys():
                ci = len(self.nodes)
                self.nodes.append({"label": c, "role": "child"})
                self.edges.append((pi, ci))  # parent -> child (branch outward)

def equilateral_triangle(center_x, center_y, radius, rotation=0.0):
    pts = []
    for k in range(3):
        ang = rotation + k * (2*math.pi/3)
        x = center_x + radius * math.cos(ang)
        y = center_y + radius * math.sin(ang)
        pts.append(QtCore.QPointF(x, y))
    return pts

def trim_segment(x1, y1, x2, y2, r1, r2, margin=8.0):
    """Shorten line by r1 and r2 (+margin) from each end."""
    dx, dy = x2 - x1, y2 - y1
    dist = math.hypot(dx, dy) or 1.0
    ux, uy = dx / dist, dy / dist
    nx1 = x1 + (r1 + margin) * ux
    ny1 = y1 + (r1 + margin) * uy
    nx2 = x2 - (r2 + margin) * ux
    ny2 = y2 - (r2 + margin) * uy
    return nx1, ny1, nx2, ny2

def segment_intersects_rect(x1, y1, x2, y2, rect: QtCore.QRectF) -> bool:
    """Check if segment intersects rect (including passing through)."""
    # Quick reject: both points on one side
    if x1 < rect.left() and x2 < rect.left(): return False
    if x1 > rect.right() and x2 > rect.right(): return False
    if y1 < rect.top() and y2 < rect.top(): return False
    if y1 > rect.bottom() and y2 > rect.bottom(): return False
    # If either endpoint inside rect → treat as intersecting
    if rect.contains(QtCore.QPointF(x1,y1)) or rect.contains(QtCore.QPointF(x2,y2)): return True
    # Check intersection with each edge of rect
    edges = [
        (rect.left(), rect.top(), rect.right(), rect.top()),
        (rect.right(), rect.top(), rect.right(), rect.bottom()),
        (rect.right(), rect.bottom(), rect.left(), rect.bottom()),
        (rect.left(), rect.bottom(), rect.left(), rect.top())
    ]
    for ax, ay, bx, by in edges:
        if segments_intersect(x1, y1, x2, y2, ax, ay, bx, by):
            return True
    return False

def ccw(ax, ay, bx, by, cx, cy):
    return (cy - ay) * (bx - ax) > (by - ay) * (cx - ax)

def segments_intersect(x1, y1, x2, y2, x3, y3, x4, y4):
    # Proper segment intersection using CCW test
    return (ccw(x1,y1,x3,y3,x4,y4) != ccw(x2,y2,x3,y3,x4,y4)) and (ccw(x1,y1,x2,y2,x3,y3) != ccw(x1,y1,x2,y2,x4,y4))

class GraphView(QtWidgets.QWidget):
    def __init__(self, graph: LinkGraph, parent=None):
        super().__init__(parent)
        self.graph = graph
        self.setMouseTracking(True)
        self._pan = False
        self._last = QtCore.QPointF(0,0)
        self._offset = QtCore.QPointF(0,0)
        self._zoom = 1.0
        self.setMinimumSize(1200, 800)
        self.setAutoFillBackground(True)
        pal = self.palette(); pal.setColor(self.backgroundRole(), QtGui.QColor(DARK_BG)); self.setPalette(pal)

        # VT323 font if bundled; fallback to Consolas
        self._font = QtGui.QFont("VT323", 20)
        try:
            base = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
            ttf = os.path.join(base, "VT323-Regular.ttf")
            if os.path.exists(ttf):
                fid = QtGui.QFontDatabase.addApplicationFont(ttf)
                fams = QtGui.QFontDatabase.applicationFontFamilies(fid)
                if fams:
                    self._font = QtGui.QFont(fams[0], 22)
        except Exception:
            pass
        if self._font.family().lower() not in {"vt323"}:
            self._font = QtGui.QFont("Consolas", 16)

        self._positions = {}
        self._label_boxes = []  # list[(QRectF, idx)]
        self._recalc_needed = True

        self._timer = QtCore.QTimer(self); self._timer.setInterval(200); self._timer.timeout.connect(self.update); self._timer.start()

    def sizeHint(self): return QtCore.QSize(1360, 900)
    def resetView(self): self._offset = QtCore.QPointF(0,0); self._zoom = 1.0; self._recalc_needed = True; self.update()

    def wheelEvent(self, ev: QtGui.QWheelEvent):
        delta = ev.angleDelta().y() / 120.0
        factor = 1.15 ** delta
        old = self._zoom
        self._zoom = max(0.5, min(3.5, self._zoom * factor))
        mouse = ev.pos()
        self._offset = mouse - (mouse - self._offset) * (self._zoom / old)
        self.update()

    def mousePressEvent(self, ev: QtGui.QMouseEvent):
        if ev.button() == QtCore.Qt.RightButton:
            self._pan = True; self._last = ev.pos(); self.setCursor(QtCore.Qt.ClosedHandCursor)

    def mouseMoveEvent(self, ev: QtGui.QMouseEvent):
        if self._pan:
            delta = ev.pos() - self._last
            self._offset += delta
            self._last = ev.pos()
            self.update()

    def mouseReleaseEvent(self, ev: QtGui.QMouseEvent):
        if ev.button() == QtCore.Qt.RightButton:
            self._pan = False; self.setCursor(QtCore.Qt.ArrowCursor)

    def _compute_layout(self, w, h):
        # Parent and child assignments
        parents = [i for i,n in enumerate(self.graph.nodes) if n["role"]=="parent"]
        kids_by_parent = {i: [] for i in parents}
        for (src, dst) in self.graph.edges:
            if self.graph.nodes[src]["role"]=="parent" and self.graph.nodes[dst]["role"]=="child":
                kids_by_parent[src].append(dst)

        cx, cy = w/2.0, h/2.0
        pos = {0: (cx, cy)}

        # Parent ring
        pcount = max(1, len(parents))
        r1 = max(260, min(w,h) * 0.36)
        for k, i in enumerate(parents):
            ang = (k / pcount) * math.tau - math.pi/2
            pos[i] = (cx + r1*math.cos(ang), cy + r1*math.sin(ang))

        # Children outward, on an arc centered at parent's angle
        for pi, kids in kids_by_parent.items():
            pcx, pcy = pos[pi]
            pang = math.atan2(pcy - cy, pcx - cx)
            count = max(1, len(kids))
            r2 = r1 + 140 + min(100, count*6)
            arc = max(math.radians(30), min(math.radians(120), count*math.radians(10)))
            start = pang - arc/2.0
            for j, ci in enumerate(kids):
                t = j/(count-1) if count>1 else 0.5
                ang = start + t*arc
                pos[ci] = (cx + r2*math.cos(ang), cy + r2*math.sin(ang))

        # Build label boxes centered under triangles
        fm = QtGui.QFontMetrics(self._font)
        boxes = []
        for i, node in enumerate(self.graph.nodes):
            x, y = pos.get(i, (cx, cy))
            text = node["label"]
            wtxt = fm.horizontalAdvance(text); htxt = fm.height()
            box_w = wtxt + 8; box_h = htxt + 6
            rect = QtCore.QRectF(x - box_w/2.0, y + TRI_RADIUS + 10, box_w, box_h)
            boxes.append([rect, i])

        # Resolve label overlaps (downward/outward bias)
        def collide(a: QtCore.QRectF, b: QtCore.QRectF) -> bool:
            return a.intersects(b)

        cx, cy = w/2.0, h/2.0
        for _ in range(36):
            moved = False
            for ia in range(len(boxes)):
                ra, ia_idx = boxes[ia]
                for ib in range(ia+1, len(boxes)):
                    rb, ib_idx = boxes[ib]
                    if collide(ra, rb):
                        ax, ay = ra.center().x(), ra.center().y()
                        bx, by = rb.center().x(), rb.center().y()
                        # push down and out
                        ra.translate(0, 9); rb.translate(0, -9)
                        ra.translate((ax - cx)*0.02, (ay - cy)*0.02)
                        rb.translate((bx - cx)*0.02, (by - cy)*0.02)
                        boxes[ia][0] = ra; boxes[ib][0] = rb
                        moved = True
            if not moved:
                break

        self._positions = pos
        self._label_boxes = boxes

    def _edge_hits_any_label(self, x1, y1, x2, y2, exclude_a=None, exclude_b=None) -> bool:
        for rect, idx in self._label_boxes:
            if idx == exclude_a or idx == exclude_b:
                continue
            if segment_intersects_rect(x1, y1, x2, y2, rect):
                return True
        return False

    def _route_segment(self, x1, y1, x2, y2, src_idx=None, dst_idx=None):
        """Return a list of points representing a routed polyline avoiding labels."""
        # If straight is clear, use it
        if not self._edge_hits_any_label(x1, y1, x2, y2, src_idx, dst_idx):
            return [(x1,y1), (x2,y2)]
        # Else, try a single-bend route via a perpendicular offset at the midpoint
        mx, my = (x1 + x2)/2.0, (y1 + y2)/2.0
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy) or 1.0
        nx, ny = -dy/length, dx/length  # perpendicular
        # Try a series of offsets outward
        for mag in (30, 60, 90, 120, 160):
            for sign in (1, -1):
                vx, vy = mx + sign*mag*nx, my + sign*mag*ny
                if (not self._edge_hits_any_label(x1, y1, vx, vy, src_idx, dst_idx) and
                    not self._edge_hits_any_label(vx, vy, x2, y2, src_idx, dst_idx)):
                    return [(x1,y1), (vx,vy), (x2,y2)]
        # Give up and return straight (it will be clipped visually by labels)
        return [(x1,y1), (x2,y2)]

    def paintEvent(self, ev: QtGui.QPaintEvent):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        p.fillRect(self.rect(), QtGui.QColor(DARK_BG))

        w, h = self.width(), self.height()
        if not self._positions or self._recalc_needed:
            self._compute_layout(w, h)
            self._recalc_needed = False

        # world transform
        p.translate(self._offset)
        p.scale(self._zoom, self._zoom)

        # draw edges (green), with trimming and routing
        pen_edge = QtGui.QPen(EDGE_QCOLOR, 2.2)
        p.setPen(pen_edge)
        for (src, dst) in self.graph.edges:
            x1, y1 = self._positions.get(src, (w/2, h/2))
            x2, y2 = self._positions.get(dst, (w/2, h/2))
            # trim at triangles
            tx1, ty1, tx2, ty2 = trim_segment(x1, y1, x2, y2, TRI_RADIUS, TRI_RADIUS, margin=8.0)
            # route if would cross labels
            pts = self._route_segment(tx1, ty1, tx2, ty2, src_idx=src, dst_idx=dst)
            # draw polyline
            for i in range(len(pts)-1):
                a = pts[i]; b = pts[i+1]
                p.drawLine(QtCore.QLineF(a[0], a[1], b[0], b[1]))

        # draw triangle nodes (same size; thicker borders)
        pen_center = QtGui.QPen(C_CYAN,   3.0)
        pen_parent = QtGui.QPen(C_RED,    3.0)
        pen_child  = QtGui.QPen(C_ORANGE, 3.0)

        for i, node in enumerate(self.graph.nodes):
            x, y = self._positions.get(i, (w/2, h/2))
            role = node["role"]
            if role == "center":
                pen = pen_center
            elif role == "parent":
                pen = pen_parent
            else:
                pen = pen_child
            pts = equilateral_triangle(x, y, TRI_RADIUS, rotation=-math.pi/2)
            p.setBrush(QtCore.Qt.NoBrush); p.setPen(pen)
            p.drawPolygon(QtGui.QPolygonF(pts))

        # labels centered under triangles (drawn last)
        p.setFont(self._font)
        p.setPen(QtGui.QPen(QtGui.QColor(FG_TEXT)))
        for rect, idx in self._label_boxes:
            text = self.graph.nodes[idx]["label"]
            p.drawText(rect, QtCore.Qt.AlignHCenter | QtCore.Qt.AlignVCenter, text)

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, json_path: str, refresh_s: int):
        super().__init__()
        self.json_path = json_path
        self.refresh_s = max(60, refresh_s)
        self.setWindowTitle("Linkmap Viewer")
        self.setMinimumSize(1400, 920)

        self.graph = LinkGraph(self.json_path)
        self.view  = GraphView(self.graph)
        self.setCentralWidget(self.view)

        pal = self.palette()
        pal.setColor(QtGui.QPalette.Window, QtGui.QColor(DARK_BG))
        pal.setColor(QtGui.QPalette.Base, QtGui.QColor(DARK_BG))
        pal.setColor(QtGui.QPalette.Text, QtGui.QColor("#cdeccd"))
        pal.setColor(QtGui.QPalette.Button, QtGui.QColor(PANEL_BG))
        pal.setColor(QtGui.QPalette.ButtonText, QtGui.QColor("#cdeccd"))
        self.setPalette(pal)

        self._build_menu()

        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(self.refresh_s * 1000)
        self.timer.timeout.connect(self.reload_graph)
        self.timer.start()

        self._status(f"Loaded {self.json_path}  |  Refresh every {self.refresh_s}s")

    def _build_menu(self):
        bar = self.menuBar()
        bar.setStyleSheet("background-color: #0f1621; color: #e2e8f0;")
        mfile = bar.addMenu("&File")
        act_reload = mfile.addAction("Reload"); act_reload.triggered.connect(self.reload_graph)
        mfile.addSeparator()
        act_html = mfile.addAction("Export HTML…"); act_html.triggered.connect(self.export_html)
        act_png  = mfile.addAction("Export PNG…");  act_png.triggered.connect(self.export_png)
        mfile.addSeparator()
        act_exit = mfile.addAction("Exit"); act_exit.triggered.connect(self.close)

        mview = bar.addMenu("&View")
        act_reset = mview.addAction("Reset View (R)"); act_reset.triggered.connect(self.view.resetView)

    def keyPressEvent(self, ev: QtGui.QKeyEvent):
        if ev.key() == QtCore.Qt.Key_R:
            self.view.resetView()

    def _status(self, msg):
        self.statusBar().setStyleSheet("background:#0f1621; color:#e2e8f0;")
        self.statusBar().showMessage(msg, 6000)

    def reload_graph(self):
        self.graph.load()
        self.view._recalc_needed = True
        self.view.update()
        self._status("Graph reloaded.")

    def export_html(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save HTML", "Linkmap.html", "HTML Files (*.html)")
        if not path: return
        try:
            html = build_html(self.graph)
            with open(path, "w", encoding="utf-8") as f: f.write(html)
            self._status(f"Saved {os.path.basename(path)}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", str(e))

    def export_png(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save PNG", "Linkmap.png", "PNG Files (*.png)")
        if not path: return
        img = QtGui.QImage(self.view.size(), QtGui.QImage.Format_ARGB32)
        img.fill(QtGui.QColor(DARK_BG))
        painter = QtGui.QPainter(img); self.view.render(painter); painter.end()
        img.save(path)
        self._status(f"Saved {os.path.basename(path)}")

# For brevity, HTML export reuses straight layout + trimming but does not route around labels.
def build_html(graph: LinkGraph) -> str:
    width, height = 1600, 1000
    cx, cy = width/2, height/2
    positions = {0: (cx, cy)}
    parents = [i for i,n in enumerate(graph.nodes) if n["role"]=="parent"]
    pcount = max(1, len(parents))
    r1 = max(260, min(width, height) * 0.36)
    for k, i in enumerate(parents):
        ang = (k / pcount) * (2*math.pi) - math.pi/2
        positions[i] = (cx + r1*math.cos(ang), cy + r1*math.sin(ang))
    children_by_parent = {i: [] for i in parents}
    edges = []
    for (src, dst) in graph.edges:
        if graph.nodes[src]["role"] == "parent" and graph.nodes[dst]["role"] == "child":
            children_by_parent[src].append(dst)
        edges.append((src,dst))
    for pi, kids in children_by_parent.items():
        pcx, pcy = positions[pi]
        pang = math.atan2(pcy - cy, pcx - cx)
        count = max(1, len(kids))
        r2 = r1 + 140 + min(100, count*6)
        arc = max(math.radians(30), min(math.radians(120), count*math.radians(10)))
        start = pang - arc/2.0
        for j, ci in enumerate(kids):
            t = j/(count-1) if count>1 else 0.5
            ang = start + t*arc
            positions[ci] = (cx + r2*math.cos(ang), cy + r2*math.sin(ang))

    def tri_points(x, y, r):
        pts = []
        for k in range(3):
            ang = -math.pi/2 + k * (2*math.pi/3)
            px = x + r * math.cos(ang)
            py = y + r * math.sin(ang)
            pts.append(f"{px},{py}")
        return " ".join(pts)

    def color(role):
        return "#00FFFF" if role=="center" else ("#FF3B30" if role=="parent" else "#FFA500")

    edge_lines = []
    for (src, dst) in edges:
        x1,y1 = positions.get(src, (cx,cy))
        x2,y2 = positions.get(dst, (cx,cy))
        tx1, ty1, tx2, ty2 = trim_segment(x1, y1, x2, y2, TRI_RADIUS, TRI_RADIUS, margin=8.0)
        edge_lines.append(f'<line x1="{tx1}" y1="{ty1}" x2="{tx2}" y2="{ty2}" stroke="rgb(0,200,0)" stroke-opacity="0.9" stroke-width="2.2" />')

    tri_nodes = []
    labels = []
    for i, n in enumerate(graph.nodes):
        x,y = positions.get(i, (cx,cy))
        tri_nodes.append(f'<polygon points="{tri_points(x,y,TRI_RADIUS)}" fill="none" stroke="{color(n["role"])}" stroke-width="3.0" />')
        t = n["label"].replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
        labels.append(f'<text x="{x}" y="{y + TRI_RADIUS + 20}" fill="{FG_TEXT}" font-size="20px" font-family="VT323, Consolas, monospace" text-anchor="middle" dominant-baseline="middle">{t}</text>')

    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Linkmap</title>
<style>html,body{{height:100%;margin:0;background:{DARK_BG};color:{FG_TEXT};}}</style></head>
<body>
<svg width="{width}" height="{height}">
  {"".join(edge_lines)}
  {"".join(tri_nodes)}
  {"".join(labels)}
</svg>
</body></html>
"""
    return html

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=os.path.join(".", "store", "link_graph.json"), help="Path to link_graph.json")
    ap.add_argument("--refresh", type=int, default=1800, help="Auto-refresh seconds (min 60)")
    args = ap.parse_args()

    app = QtWidgets.QApplication(sys.argv); app.setStyle("Fusion")
    win = MainWindow(args.json, max(60, args.refresh)); win.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
