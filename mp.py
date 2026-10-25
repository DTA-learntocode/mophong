# -*- coding: utf-8 -*-
"""
MÔ PHỎNG TRỰC THĂNG THẢ HÀNG (Oxyz)
Cài thư viện:  pip install matplotlib numpy
Chạy:          python mo_phong_truc_thang.py

- Nhập tọa độ nhà (x, y, z) -> hiện nhà
- Nhập tọa độ trực thăng (x, y, z) -> hiện trực thăng
- Nút "Thả thẳng": bay tới ngay trên nhà (giữ nguyên z), thả hàng rơi thẳng, rồi bay về điểm đầu
- Nút "Thả khi đang bay": trực thăng bay ngang với vận tốc V, thả hàng sớm hơn một đoạn
  (s = v * sqrt(2h/g)) để hàng rơi trúng nhà, rồi bay về điểm đầu
Đơn vị tọa độ: km.
"""
import math
import time
import tkinter as tk
from tkinter import ttk

import numpy as np
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

# ----------------------------- HẰNG SỐ -----------------------------
G = 9.8              # m/s^2
V_NGANG = 5.0        # m/s - vận tốc bay ngang khi thả
FPS_MS = 30          # ms mỗi khung hình
T_BAY = 3.0          # giây (thời gian hoạt ảnh) bay đi / bay về
T_ROI = 3.0          # giây hoạt ảnh cho đoạn hàng rơi
T_NGHI = 0.6         # giây dừng ngắn

# ----------------------------- HÌNH HỌC -----------------------------
def cube_faces(c, sx, sy, sz):
    x, y, z = c
    hx, hy, hz = sx / 2, sy / 2, sz / 2
    v = np.array([[x + a * hx, y + b * hy, z + d * hz]
                  for a in (-1, 1) for b in (-1, 1) for d in (-1, 1)])
    idx = [(0, 1, 3, 2), (4, 5, 7, 6), (0, 1, 5, 4),
           (2, 3, 7, 6), (0, 2, 6, 4), (1, 3, 7, 5)]
    return [v[list(i)] for i in idx]


def house_faces(base, s):
    """Nhà: thân hộp + mái chóp. base = tọa độ chân nhà (z là mặt đất của nhà)."""
    x, y, z = base
    wall_h = s * 0.8
    body = cube_faces((x, y, z + wall_h / 2), s, s, wall_h)
    h = s / 2
    zt = z + wall_h
    a = (x - h, y - h, zt); b = (x + h, y - h, zt)
    c = (x + h, y + h, zt); d = (x - h, y + h, zt)
    top = (x, y, zt + s * 0.6)
    roof = [[a, b, top], [b, c, top], [c, d, top], [d, a, top]]
    return body, roof


# ----------------------------- ỨNG DỤNG -----------------------------
class App:
    def __init__(self, root):
        self.root = root
        root.title("Mô phỏng Trực thăng thả hàng (Oxyz)")
        root.geometry("1200x720")

        self.vars = {}
        self.animating = False
        self.static_artists = []
        self.timeline = []
        self.t0 = 0.0

        self._build_ui()
        self._build_dynamic_artists()
        self.update_scene()

    # ---------------- Giao diện ----------------
    def _build_ui(self):
        left = ttk.Frame(self.root, padding=10)
        left.pack(side=tk.LEFT, fill=tk.Y)

        def group(title, defaults, key):
            lf = ttk.LabelFrame(left, text=title, padding=8)
            lf.pack(fill=tk.X, pady=6)
            for i, (name, val) in enumerate(zip("xyz", defaults)):
                ttk.Label(lf, text=f"{name} (km):").grid(row=i, column=0, sticky="w", pady=2)
                sv = tk.StringVar(value=str(val))
                sv.trace_add("write", lambda *a: self._on_input())
                ttk.Entry(lf, textvariable=sv, width=10).grid(row=i, column=1, padx=6)
                self.vars[f"{key}_{name}"] = sv

        group("Tọa độ NHÀ", (8, 1, 3), "nha")
        group("Tọa độ TRỰC THĂNG", (5, 0, 6), "tt")

        self.btn_thang = ttk.Button(left, text="⬇  Thả thẳng", command=self.run_drop_straight)
        self.btn_thang.pack(fill=tk.X, pady=(14, 4), ipady=6)
        self.btn_bay = ttk.Button(left, text="✈  Thả khi đang bay", command=self.run_drop_flying)
        self.btn_bay.pack(fill=tk.X, pady=4, ipady=6)
        self.btn_reset = ttk.Button(left, text="⟲  Đặt lại", command=self.reset)
        self.btn_reset.pack(fill=tk.X, pady=4, ipady=4)

        self.status = tk.StringVar(value="Nhập tọa độ để hiển thị nhà và trực thăng.")
        ttk.Label(left, textvariable=self.status, wraplength=200, foreground="#0a4").pack(pady=12)
        ttk.Label(left, text="Chuột trái: xoay | Chuột phải: dịch/zoom",
                  foreground="#666", wraplength=200).pack(side=tk.BOTTOM)

        self.fig = Figure(figsize=(8, 7), dpi=100)
        self.ax = self.fig.add_subplot(111, projection="3d")
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.root)
        self.canvas.get_tk_widget().pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

    def _build_dynamic_artists(self):
        ax = self.ax
        self.heli_body = Poly3DCollection([], facecolor="#3b82f6", edgecolor="k", linewidth=0.5)
        self.cargo = Poly3DCollection([], facecolor="#f97316", edgecolor="k", linewidth=0.5)
        ax.add_collection3d(self.heli_body)
        ax.add_collection3d(self.cargo)
        self.tail, = ax.plot([], [], [], color="#1e3a8a", lw=3)
        self.rotor1, = ax.plot([], [], [], color="k", lw=2)
        self.rotor2, = ax.plot([], [], [], color="k", lw=2)
        self.mast, = ax.plot([], [], [], color="k", lw=2)
        self.trail_h, = ax.plot([], [], [], color="#3b82f6", lw=1, ls="--", alpha=0.6)
        self.trail_c, = ax.plot([], [], [], color="#f97316", lw=1.5, ls="--", alpha=0.9)

    # ---------------- Đọc dữ liệu ----------------
    def _read(self, key):
        try:
            return np.array([float(self.vars[f"{key}_{n}"].get().replace(",", ".")) for n in "xyz"])
        except ValueError:
            return None

    def _on_input(self):
        if self.animating:
            return
        self.update_scene()

    # ---------------- Dựng cảnh tĩnh ----------------
    def update_scene(self):
        nha, tt = self._read("nha"), self._read("tt")
        if nha is None or tt is None:
            self.status.set("Tọa độ chưa hợp lệ (nhập số).")
            return
        self.nha, self.start = nha, tt
        self.status.set("Sẵn sàng.")

        # Giới hạn trục
        pts = [nha, tt, np.zeros(3)]
        rel = self._release_point()
        if rel is not None:
            pts.append(rel)
        P = np.array(pts)
        lo, hi = P.min(axis=0), P.max(axis=0)
        span = np.maximum(hi - lo, 1.0)
        lo, hi = lo - 0.2 * span, hi + 0.2 * span
        lo[2] = min(lo[2], 0) if lo[2] < 0 else 0
        self.lim = (lo, hi)
        self.S = 0.05 * float(np.max(hi - lo))

        ax = self.ax
        ax.set_xlim(lo[0], hi[0]); ax.set_ylim(lo[1], hi[1]); ax.set_zlim(lo[2], hi[2])
        ax.set_box_aspect(tuple(np.maximum(hi - lo, 1e-6)))
        ax.set_xlabel("x (km)"); ax.set_ylabel("y (km)"); ax.set_zlabel("z (km)")

        for a in self.static_artists:
            try:
                a.remove()
            except Exception:
                pass
        self.static_artists = []

        body, roof = house_faces(nha, self.S)
        pb = Poly3DCollection(body, facecolor="#e5e7eb", edgecolor="k", linewidth=0.6)
        pr = Poly3DCollection(roof, facecolor="#dc2626", edgecolor="k", linewidth=0.6)
        ax.add_collection3d(pb); ax.add_collection3d(pr)
        self.static_artists += [pb, pr]
        t1 = ax.text(nha[0], nha[1], nha[2] + 1.8 * self.S, "Nhà", color="#b91c1c", fontsize=10, ha="center")
        # đường chiếu xuống mặt đất (z=0) cho dễ nhìn
        l1, = ax.plot([nha[0]] * 2, [nha[1]] * 2, [0, nha[2]], color="gray", ls=":", lw=1)
        m1, = ax.plot([nha[0]], [nha[1]], [0], marker="x", color="gray")
        l2, = ax.plot([tt[0]] * 2, [tt[1]] * 2, [0, tt[2]], color="gray", ls=":", lw=1)
        m2, = ax.plot([tt[0]], [tt[1]], [0], marker="x", color="gray")
        t2 = ax.text(tt[0], tt[1], tt[2] + 2.2 * self.S, "Điểm đầu", color="#1d4ed8", fontsize=9, ha="center")
        self.static_artists += [t1, l1, m1, l2, m2, t2]

        self.trail_h.set_data_3d([], [], [])
        self.trail_c.set_data_3d([], [], [])
        self.trail_hx, self.trail_cx = [], []
        self.draw_state(self.start, ("attached", None), heading=self._heading(tt, nha))
        self.canvas.draw_idle()

    def _heading(self, a, b):
        d = np.array([b[0] - a[0], b[1] - a[1], 0.0])
        n = np.linalg.norm(d)
        return d / n if n > 1e-9 else np.array([1.0, 0.0, 0.0])

    def _release_point(self):
        """Điểm (x,y,z_trực thăng) cần thả khi đang bay."""
        try:
            nha, tt = self.nha, self.start
        except AttributeError:
            nha, tt = self._read("nha"), self._read("tt")
            if nha is None or tt is None:
                return None
        h_m = (tt[2] - nha[2]) * 1000.0
        if h_m <= 0:
            return None
        t = math.sqrt(2 * h_m / G)
        s_km = V_NGANG * t / 1000.0
        d = self._heading(tt, nha)
        r = np.array([nha[0], nha[1], tt[2]]) - d * s_km
        return r

    # ---------------- Vẽ trạng thái động ----------------
    def draw_state(self, hpos, cargo, heading=None):
        S = self.S
        if heading is None:
            heading = np.array([1.0, 0.0, 0.0])
        hp = np.array(hpos, dtype=float)
        self.heli_body.set_verts(cube_faces(hp, S * 0.9, S * 0.6, S * 0.5))
        tail_end = hp - heading * S * 1.5
        self.tail.set_data_3d([hp[0], tail_end[0]], [hp[1], tail_end[1]], [hp[2], tail_end[2]])
        top = hp + np.array([0, 0, S * 0.45])
        self.mast.set_data_3d([hp[0], top[0]], [hp[1], top[1]], [hp[2], top[2]])
        ang = (time.perf_counter() * 25) % (2 * math.pi)
        R = S * 1.1
        for line, off in ((self.rotor1, 0), (self.rotor2, math.pi / 2)):
            dx, dy = R * math.cos(ang + off), R * math.sin(ang + off)
            line.set_data_3d([top[0] - dx, top[0] + dx], [top[1] - dy, top[1] + dy], [top[2], top[2]])

        mode, cpos = cargo
        if mode == "attached":
            cpos = hp - np.array([0, 0, S * 0.55])
        if mode in ("attached", "free", "landed"):
            self.cargo.set_verts(cube_faces(cpos, S * 0.4, S * 0.4, S * 0.4))
        else:
            self.cargo.set_verts([])

    # ---------------- Hoạt ảnh ----------------
    def _lerp(self, a, b, u):
        u = 0.5 - 0.5 * math.cos(math.pi * u)   # ease in-out
        return np.array(a) + (np.array(b) - np.array(a)) * u

    def _start_timeline(self, timeline, msg):
        self.update_scene()
        if not hasattr(self, "nha"):
            return
        self.timeline = timeline
        self.total = sum(d for d, _ in timeline)
        self.t0 = time.perf_counter()
        self.animating = True
        self.landed_pos = None
        self.trail_hx, self.trail_cx = [], []
        for b in (self.btn_thang, self.btn_bay):
            b.state(["disabled"])
        self.status.set(msg)
        self._tick()

    def _tick(self):
        el = time.perf_counter() - self.t0
        if el >= self.total:
            self._finish()
            return
        acc = 0.0
        for dur, fn in self.timeline:
            if el < acc + dur:
                u = (el - acc) / dur if dur > 0 else 1.0
                hpos, cargo, head = fn(u)
                break
            acc += dur
        if cargo[0] == "landed":
            self.landed_pos = cargo[1]
        self.trail_hx.append(np.array(hpos))
        self.trail_cx_update(cargo)
        self.draw_state(hpos, cargo, head)
        H = np.array(self.trail_hx)
        self.trail_h.set_data_3d(H[:, 0], H[:, 1], H[:, 2])
        self.canvas.draw_idle()
        self.root.after(FPS_MS, self._tick)

    def trail_cx_update(self, cargo):
        if cargo[0] == "free":
            self.trail_cx.append(np.array(cargo[1]))
            C = np.array(self.trail_cx)
            self.trail_c.set_data_3d(C[:, 0], C[:, 1], C[:, 2])

    def _finish(self):
        self.animating = False
        for b in (self.btn_thang, self.btn_bay):
            b.state(["!disabled"])
        # Về điểm đầu: trực thăng đã quay lại, cảnh được dựng lại (hàng gắn lại vào trực thăng)
        self.status.set("Xong! Trực thăng đã quay về điểm đầu.")
        self.draw_state(self.start, ("attached", None), self._heading(self.start, self.nha))
        self.canvas.draw_idle()

    def reset(self):
        if self.animating:
            return
        self.update_scene()

    # ---------------- Kịch bản 1: thả thẳng ----------------
    def run_drop_straight(self):
        if self.animating:
            return
        nha, tt = self._read("nha"), self._read("tt")
        if nha is None or tt is None:
            self.status.set("Tọa độ chưa hợp lệ."); return
        if tt[2] <= nha[2]:
            self.status.set("Z trực thăng phải lớn hơn Z nhà."); return
        above = np.array([nha[0], nha[1], tt[2]])
        head = self._heading(tt, nha)
        land = np.array([nha[0], nha[1], nha[2] + self.S * 0.0])
        S_ = tt.copy()

        def fly_to(u): return self._lerp(S_, above, u), ("attached", None), head
        def hold(u): return above, ("attached", None), head
        def fall(u):
            z = tt[2] - (tt[2] - nha[2]) * u * u        # rơi tự do: z = z0 - 1/2 g t^2
            cpos = np.array([nha[0], nha[1], z - self.S * 0.55 * (1 - u)])
            if u >= 1:
                return above, ("landed", land + np.array([0, 0, self.S * 0.2])), head
            return above, ("free", cpos), head
        def landed(u): return above, ("landed", land + np.array([0, 0, self.S * 0.2])), head
        def back(u): return self._lerp(above, S_, u), ("landed", land + np.array([0, 0, self.S * 0.2])), -head

        tl = [(T_BAY, fly_to), (T_NGHI, hold), (T_ROI, fall), (T_NGHI, landed), (T_BAY, back)]
        self._start_timeline(tl, "Đang thả thẳng...")

    # ---------------- Kịch bản 2: thả khi đang bay ----------------
    def run_drop_flying(self):
        if self.animating:
            return
        nha, tt = self._read("nha"), self._read("tt")
        if nha is None or tt is None:
            self.status.set("Tọa độ chưa hợp lệ."); return
        if tt[2] <= nha[2]:
            self.status.set("Z trực thăng phải lớn hơn Z nhà."); return
        self.nha, self.start = nha, tt
        rel = self._release_point()
        head = self._heading(tt, nha)
        h_m = (tt[2] - nha[2]) * 1000.0
        s_km = V_NGANG * math.sqrt(2 * h_m / G) / 1000.0
        end = rel + head * s_km                      # vị trí trực thăng khi hàng chạm nhà
        land = np.array([nha[0], nha[1], nha[2] + self.S * 0.2])
        S_ = tt.copy()

        def fly_to(u): return self._lerp(S_, rel, u), ("attached", None), head
        def fall(u):
            # hàng chuyển động ném ngang: ngang đều, đứng rơi tự do (u = t / T_rơi)
            hx = rel + head * s_km * u
            if u >= 1:
                return end, ("landed", land), head
            cz = tt[2] - (tt[2] - nha[2]) * u * u
            cpos = np.array([hx[0], hx[1], cz - self.S * 0.55 * (1 - u)])
            return hx, ("free", cpos), head
        def back(u): return self._lerp(end, S_, u), ("landed", land), -head

        tl = [(T_BAY, fly_to), (T_ROI, fall), (T_BAY, back)]
        self._start_timeline(tl, "Đang thả khi bay...")


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
