"""Gráfico PNG de la ruta PADOMI.
Uso: python3 grafico_ruta.py ruta.json etiquetas.json salida.png
  ruta.json      -> salida de ruta_padomi.py
  etiquetas.json -> {"titulo": "...", "subtitulo": "...",
                     "direcciones": ["dirección corta parada 1", ...],
                     "direcciones_visitadas": ["...", ...],    (en plena ruta: paradas ya atendidas)
                     "zonas": [["SALAMANCA", lat, lng], ...]}   (zonas es opcional)
En plena ruta muestra también las paradas ya atendidas, en gris y tachadas, y las paradas
que se hacen a pie (sin mover la unidad) con línea de puntos.
"""
import json, math, sys, textwrap
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, Circle

PADOMI = (-12.0782458, -77.0368112)
ARENALES = (-12.069933, -77.037982)

ruta = json.load(open(sys.argv[1], encoding="utf-8"))
et = json.load(open(sys.argv[2], encoding="utf-8"))
OUT = sys.argv[3]
P = ruta["paradas"]
T = ruta["tramos"]
dirs = et["direcciones"]
assert len(dirs) == len(P), f"{len(dirs)} direcciones para {len(P)} paradas"
pen = ruta.get("penultima_parada")
INI = ruta.get("inicio", {"tipo": "padomi"})
N0 = INI["n"] if INI.get("tipo") == "parada" else 0     # en plena ruta la numeración sigue desde N0+1
V = ruta.get("visitadas", [])                            # paradas ya atendidas: van en gris y tachadas
vdirs = et.get("direcciones_visitadas", [""] * len(V))
GRIS = "#9CA3AF"

COLS = ["#0F766E", "#6D28D9", "#C2410C", "#1D4ED8", "#BE185D", "#4D7C0F"]
TR = {n: t["tramo"] for t in T for n in t["paradas"]}   # parada -> tramo (tramos de 5 paradas, del script)
def tramo_de(n):
    return TR.get(n, T[-1]["tramo"] if T else 1)
def col(k):
    return COLS[(k - 1) % len(COLS)]
INK, MUTED, BG = "#1F2328", "#6B7280", "#FFFFFF"

PART = {"DE", "DEL", "LA", "LAS", "LOS", "SAN", "SANTA", "DA", "DI", "VAN", "VON", "MC", "MAC"}
def primer_apellido(nombre):
    t = nombre.split()
    out, i = [], 0
    while i < len(t) - 1 and t[i] in PART:
        out.append(t[i]); i += 1
    out.append(t[i])
    return " ".join(w.capitalize() if k == 0 or w not in PART else w.lower() for k, w in enumerate(out))

def fmt(m):
    if m < 60:
        return f"{m} min"
    return f"{m // 60} h" if m % 60 == 0 else f"{m // 60} h {m % 60:02d} min"
def r5(m):
    return int(5 * round(m / 5.0))

# ---------- proyección a km ----------
KX = 111.32 * math.cos(math.radians(12.05)); KY = 110.57
def xy(la, lo):
    return (lo * KX, la * KY)

pts = [xy(p["lat"], p["lng"]) for p in P]
vpts = [xy(p["lat"], p["lng"]) for p in V]
pad, are = xy(*PADOMI), xy(*ARENALES)
HAY_INI = INI.get("tipo") in ("parada", "gps")          # se parte de donde está el usuario
ini = xy(INI["lat"], INI["lng"]) if HAY_INI else None
xs = [p[0] for p in pts + vpts] + ([ini[0]] if ini else [])
ys = [p[1] for p in pts + vpts] + ([ini[1]] if ini else [])
M = max(0.7, 0.035 * max(max(xs) - min(xs), max(ys) - min(ys)))
x0, x1, y0, y1 = min(xs) - M, max(xs) + M, min(ys) - M, max(ys) + M
padomi_dentro = (x0 - 1.5 <= pad[0] <= x1 + 1.5) and (y0 - 1.5 <= pad[1] <= y1 + 1.5)
if padomi_dentro:
    x0, x1 = min(x0, pad[0] - 0.5, are[0] - 0.5), max(x1, pad[0] + 0.5, are[0] + 0.5)
    y0, y1 = min(y0, pad[1] - 0.5, are[1] - 0.5), max(y1, pad[1] + 0.5, are[1] + 0.5)
if not padomi_dentro:
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    ddx, ddy = pad[0] - cx, pad[1] - cy
    if abs(ddx) >= 0.4 * abs(ddy):          # PADOMI hacia el oeste/este
        ex = max(2.2, 0.2 * (x1 - x0))
        if ddx < 0: x0 -= ex
        else: x1 += ex
    if abs(ddy) >= 0.4 * abs(ddx):          # PADOMI hacia el norte/sur
        ey = max(1.2, 0.25 * (y1 - y0))
        if ddy < 0: y0 -= ey
        else: y1 += ey
xspan, yspan = x1 - x0, y1 - y0
ratio = yspan / xspan

FW = 7.2
mw = 6.77; mh = mw * ratio
if mh > 7.6:
    mh = 7.6; mw = mh / ratio

# ---------- leyenda: filas ----------
rows = []  # (tipo, datos, alto en filas)
for t in T:
    man = r5(t["manejo_min"]); tot = man + t["atencion_min"]
    ps = t["paradas"]
    rango = f"paradas {ps[0]} a {ps[-1]}" if len(ps) > 1 else (f"parada {ps[0]}" if ps else "retorno")
    extra = " + retorno" if t is T[-1] else ""
    txt = (f"Tramo {t['tramo']} ({rango}{extra}): manejo ~{fmt(man)} + atención "
           f"{fmt(t['atencion_min'])} ({t['pacientes']} pac.) = {fmt(tot)}")
    rows.append(("tramo", (t["tramo"], txt), 1))
total = sum(r5(t["manejo_min"]) + t["atencion_min"] for t in T)
npac = sum(len(p["pacientes"]) for p in P)
rows.append(("total", (f"Tiempo restante estimado: {fmt(total)}  ({npac} pacientes por atender × 6 min + manejo)" if HAY_INI
                       else f"Tiempo total estimado: {fmt(total)}  ({npac} pacientes × 6 min + manejo)"), 1.2))
rows.append(("gap", None, 0.4))
if V:
    rows.append(("titulo_v", f"Ya visitados (paradas 1 a {V[-1]['n']})", 1))
    for p, d in zip(V, vdirs):
        aps = [primer_apellido(x["paciente"]) for x in p["pacientes"]]
        k = len(aps)
        txt = f"{d} ({aps[0]})" if k == 1 else f"{d} x{k} ({' / '.join(aps)})"
        rows.append(("visitada", (p["n"], txt), 1))
    rows.append(("titulo_v", "Por visitar", 1))
for p, d in zip(P, dirs):
    aps = [primer_apellido(x["paciente"]) for x in p["pacientes"]]
    k = len(aps)
    txt = f"{d} ({aps[0]})" if k == 1 else f"{d} x{k} ({' / '.join(aps)})"
    if any(x.get("nuevo") for x in p["pacientes"]):
        txt += " · NUEVO"
    if p.get("a_pie_desde") is not None:
        txt += " · A PIE"
    if p["n"] == pen:
        txt += " · COMBUSTIBLE"
    lines = textwrap.wrap(txt, 64, subsequent_indent="   ")
    bold = k > 1 or p["n"] == pen or any(x.get("nuevo") for x in p["pacientes"])
    rows.append(("parada", (p["n"], "\n".join(lines), bold), max(1, len(lines) * 0.85)))
nota_manejo = ("Manejo: tiempos por calle (OpenStreetMap) con tráfico según la hora y el sentido (data/trafico.json)."
               if ruta.get("tiempos") == "calles" else
               "Manejo estimado: distancia en línea recta × 1.35 a 20 km/h promedio.")
rows.append(("nota", nota_manejo + " Atención: 6 min por paciente.\n"
                     "Las líneas rectas muestran el orden de visita, no el camino exacto. Para manejar usa Google Maps.\n"
                     "Línea de puntos = a pie, sin mover la unidad. Gris y tachado = ya atendido.\n"
                     "Mapa base: vías principales © colaboradores de OpenStreetMap; distritos: IGN.", 2.4))
RH = 0.30
leg_h = sum(r[2] for r in rows) * RH
H = 0.95 + mh + 0.35 + leg_h + 0.25

fig = plt.figure(figsize=(FW, H), dpi=150, facecolor=BG)
fig.text(0.05, 1 - 0.28 / H, et["titulo"], fontsize=14, fontweight="bold", color=INK, va="top")
fig.text(0.05, 1 - 0.62 / H, et.get("subtitulo", ""), fontsize=10.5, color=MUTED, va="top")

ax = fig.add_axes([(FW - mw) / 2 / FW, 1 - (0.95 + mh) / H, mw / FW, mh / H])
ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_aspect("equal")
ax.set_xticks([]); ax.set_yticks([]); ax.set_facecolor("#F4F5F2")
for s in ax.spines.values():
    s.set_color("#B8BEC6"); s.set_linewidth(0.8)

# ---------- mapa base (tenue, debajo de la ruta): límites de distritos y vías principales ----------
import os
import matplotlib.patheffects as pe
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
def _cargar(nombre):
    try:
        return json.load(open(os.path.join(DATA, nombre), encoding="utf-8"))
    except Exception:
        return None
def _visible(pp, m=0.0):
    return any(x0 - m <= x <= x1 + m and y0 - m <= y <= y1 + m for x, y in pp)
MAPA_BASE = False
dist = _cargar("distritos_lima.json")
if dist:
    nombres = {}
    for d in dist["distritos"]:
        pp = [xy(la, lo) for lo, la in d["l"]]
        if not _visible(pp, 0.5):
            continue
        MAPA_BASE = True
        ax.fill([p[0] for p in pp], [p[1] for p in pp], color="#FFFFFF", alpha=0.35, lw=0, zorder=0.5)
        ax.plot([p[0] for p in pp], [p[1] for p in pp], color="#B9C0C8", lw=0.8, ls=(0, (5, 3)), zorder=0.6)
        cx, cy = sum(p[0] for p in pp) / len(pp), sum(p[1] for p in pp) / len(pp)
        if len(pp) > len(nombres.get(d["n"], ((0, 0), []))[1]):
            nombres[d["n"]] = ((cx, cy), pp)
    for n, ((cx, cy), _) in nombres.items():                      # nombre del distrito en su centro, si se ve
        if x0 + 0.3 < cx < x1 - 0.3 and y0 + 0.3 < cy < y1 - 0.3:
            ax.text(cx, cy, n.upper(), fontsize=8, color="#A3AAB3", ha="center", va="center", zorder=0.7,
                    fontweight="bold", alpha=0.85)
vias = _cargar("vias_lima.json")
mb, rr = 0.09 * max(xspan, yspan), 0.06 * max(xspan, yspan)     # margen del borde y distancia a las paradas
if vias:
    rotulos = {}
    for v in vias["vias"]:
        pp = [xy(la, lo) for lo, la in v["l"]]
        if not _visible(pp):
            continue
        MAPA_BASE = True
        ancho = 3.4 if v["c"] == "e" else 2.4
        ax.plot([p[0] for p in pp], [p[1] for p in pp], color="#FFFFFF", lw=ancho + 1.6, alpha=0.9, zorder=0.8,
                solid_capstyle="round", solid_joinstyle="round")
        ax.plot([p[0] for p in pp], [p[1] for p in pp], color="#E9B44C" if v["c"] == "e" else "#EFCB86",
                lw=ancho, alpha=0.75, zorder=0.9, solid_capstyle="round", solid_joinstyle="round")
        # tramo visible más largo, lejos del borde y de las paradas, para poner el nombre una sola vez
        for a, b in zip(pp, pp[1:]):
            mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            if (x0 + mb < mx < x1 - mb and y0 + mb < my < y1 - mb
                    and all(math.hypot(mx - q[0], my - q[1]) > rr for q in pts + vpts)):
                largo = math.hypot(b[0] - a[0], b[1] - a[1])
                if largo > rotulos.get(v["n"], (0,))[0]:
                    rotulos[v["n"]] = (largo, mx, my, math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])))
    for n, (largo, mx, my, ang) in rotulos.items():
        if largo < 0.25 * max(xspan, yspan) / 6:
            continue
        ang = ang + 180 if ang > 90 else (ang - 180 if ang < -90 else ang)
        ax.text(mx, my, n, fontsize=7.2, color="#8A6414", ha="center", va="center", rotation=ang,
                rotation_mode="anchor", zorder=1.0, alpha=0.95, clip_on=True,
                path_effects=[pe.withStroke(linewidth=2.2, foreground="white")])

if not MAPA_BASE:
    for z in et.get("zonas", []):
        zx, zy = xy(z[1], z[2])
        ax.text(zx, zy, z[0], fontsize=8.5, color="#9AA0A6", style="italic", ha="center", va="center", zorder=2)

def seg(a, b, color, dashed=False):
    ax.plot([a[0], b[0]], [a[1], b[1]], color=color, lw=2.4, ls=(0, (4, 2)) if dashed else "-",
            zorder=3, solid_capstyle="round")
    if math.hypot(b[0] - a[0], b[1] - a[1]) > 0.45:
        s0 = (a[0] + (b[0] - a[0]) * 0.50, a[1] + (b[1] - a[1]) * 0.50)
        s1 = (a[0] + (b[0] - a[0]) * 0.58, a[1] + (b[1] - a[1]) * 0.58)
        ax.add_patch(FancyArrowPatch(s0, s1, arrowstyle="-|>", mutation_scale=13, color=color, lw=0, zorder=4))

def borde(p, q, m=0.08):
    """punto donde el rayo p->q sale del recuadro del mapa"""
    dx, dy = q[0] - p[0], q[1] - p[1]
    ts = []
    for lim, d, c in ((x0 + m, dx, p[0]), (x1 - m, dx, p[0]), (y0 + m, dy, p[1]), (y1 - m, dy, p[1])):
        if abs(d) > 1e-9:
            t = (lim - c) / d
            if t > 0:
                ts.append(t)
    t = min(ts + [1.0])
    return (p[0] + dx * t, p[1] + dy * t)

last_col = col(tramo_de(P[-1]["n"]))
def segv(a, b):
    """tramo ya recorrido: gris, delgado y punteado"""
    ax.plot([a[0], b[0]], [a[1], b[1]], color=GRIS, lw=1.6, ls=(0, (2, 2)), zorder=3)
for i in range(len(vpts) - 1):
    segv(vpts[i], vpts[i + 1])
if vpts:
    segv(pad if padomi_dentro else borde(vpts[0], pad), vpts[0])
def segp(a, b, color):
    """a pie (la unidad no se mueve): línea de puntos delgada"""
    ax.plot([a[0], b[0]], [a[1], b[1]], color=color, lw=1.6, ls=(0, (1, 1.6)), zorder=3)
apie = lambda st: st.get("a_pie_desde") is not None
for i in range(len(pts) - 1):
    (segp if apie(P[i + 1]) else seg)(pts[i], pts[i + 1], col(tramo_de(P[i + 1]["n"])))
if ini:
    (segp if apie(P[0]) else seg)(ini, pts[0], col(1))
    if not V:
        ax.plot(*ini, marker="*", ms=22, color="#F59E0B", markeredgecolor=INK, zorder=11)
if padomi_dentro:
    if not ini:
        seg(pad, pts[0], col(1))
    seg(pts[-1], are, last_col, dashed=True); seg(are, pad, last_col, dashed=True)
    ax.plot(*pad, marker="s", ms=13, color=INK, zorder=9)
    ax.text(pad[0], pad[1], "P", color="white", fontsize=8, fontweight="bold", ha="center", va="center", zorder=10)
    lado = -1 if pad[0] > (x0 + x1) / 2 else 1   # el texto hacia el centro del mapa
    ax.text(pad[0] + 0.25 * lado, pad[1] - 0.25, "PADOMI", fontsize=8.5, color=INK, fontweight="bold", va="top",
            ha="left" if lado > 0 else "right", zorder=10)
else:
    e_in = borde(pts[0], pad); e_out = borde(pts[-1], are)
    if not ini:
        seg(e_in, pts[0], col(1), dashed=True)
    seg(pts[-1], e_out, last_col, dashed=True)
    km_pad = math.hypot(pad[0] - pts[0][0], pad[1] - pts[0][1])
    etiquetas_borde = ([] if ini else [(e_in, f"Desde PADOMI\n(Av. Arenales, ~{km_pad:.0f} km)", col(1))]) + \
                      [(e_out, "Retorno a PADOMI\npor Av. Arenales", last_col)]
    if not ini and math.hypot(e_in[0] - e_out[0], e_in[1] - e_out[1]) < 0.12 * max(xspan, yspan):
        # ida y retorno salen por el mismo lado: una sola etiqueta para que no se monten
        etiquetas_borde = [(e_in, f"PADOMI: ida y retorno\npor Av. Arenales (~{km_pad:.0f} km)", INK)]
    for k_, (ep, txt, c) in enumerate(etiquetas_borde, 0 if not ini else 1):
        dist_edges = {"left": ep[0] - x0, "right": x1 - ep[0], "bottom": ep[1] - y0, "top": y1 - ep[1]}
        edge = min(dist_edges, key=dist_edges.get)
        entrada = k_ == 0
        if edge in ("left", "right"):
            ha = "left" if edge == "left" else "right"
            tx = ep[0] + (0.1 if edge == "left" else -0.1)
            th = 0.34 * yspan / mh + 0.1   # alto del texto (2 líneas) en km
            arriba = entrada
            if len(etiquetas_borde) == 2:
                otro = etiquetas_borde[1 - k_][0]
                arriba = ep[1] >= otro[1]
            if ep[1] - y0 < th + 0.3:
                arriba = True
            elif y1 - ep[1] < th + 0.3:
                arriba = False
            va = "bottom" if arriba else "top"
            ty = ep[1] + (0.55 if arriba else -0.55)
        else:
            ha = "right" if ep[0] > (x0 + x1) / 2 else "left"
            tx = ep[0] + (-0.15 if ha == "right" else 0.15)
            if edge == "bottom":
                ty, va = ep[1] + (0.9 if entrada else 0.25), "bottom"
            else:
                ty, va = ep[1] - (0.25 if entrada else 0.9), "top"
        ax.text(tx, ty, txt, fontsize=8.5, color=c, ha=ha, va=va, fontweight="bold", zorder=6,
                bbox=dict(facecolor="#F4F5F2", edgecolor="none", alpha=0.9, pad=1.5))

# números con separación automática
R = max(0.21, 0.02 * max(xspan, yspan)) if max(xspan, yspan) > 6 else max(0.12, 0.035 * max(xspan, yspan))
lab = [list(p) for p in vpts + pts]
for _ in range(500):
    moved = False
    for i in range(len(lab)):
        for j in range(i + 1, len(lab)):
            dx, dy = lab[j][0] - lab[i][0], lab[j][1] - lab[i][1]
            dist = math.hypot(dx, dy); need = 2 * R + 0.05
            if dist < need:
                if dist < 1e-6:
                    dx, dy, dist = 1.0, 0.3, math.hypot(1.0, 0.3)
                push = (need - dist) / 2 + 0.004
                lab[i][0] -= dx / dist * push; lab[i][1] -= dy / dist * push
                lab[j][0] += dx / dist * push; lab[j][1] += dy / dist * push
                moved = True
    for l in lab:                                # que ningún círculo se salga del recuadro
        cx_ = min(max(l[0], x0 + R * 1.15), x1 - R * 1.15)
        cy_ = min(max(l[1], y0 + R * 1.15), y1 - R * 1.15)
        moved = moved or (cx_, cy_) != (l[0], l[1])
        l[0], l[1] = cx_, cy_
    if not moved:
        break
labv, labp = lab[:len(vpts)], lab[len(vpts):]
for p, l, st in zip(vpts, labv, V):
    nn = st["n"]
    ax.plot(p[0], p[1], "o", ms=3.2, color=GRIS, zorder=7)
    if math.hypot(l[0] - p[0], l[1] - p[1]) > R * 0.5:
        ax.plot([p[0], l[0]], [p[1], l[1]], color=GRIS, lw=0.8, zorder=7)
    aqui = (nn == N0)
    ax.add_patch(Circle(l, R, facecolor=GRIS, edgecolor="#F59E0B" if aqui else "white",
                        lw=2.6 if aqui else 1.4, zorder=8))
    ax.text(l[0], l[1], str(nn), color="white", fontsize=9 if nn < 10 else 8.2, fontweight="bold",
            ha="center", va="center", zorder=9)
    ax.plot([l[0] - R * 0.62, l[0] + R * 0.62], [l[1], l[1]], color="white", lw=1.3, zorder=10)   # tachado
    if aqui:
        ax.text(l[0], l[1] + R * 1.25, f"Estás aquí (paciente {N0})", fontsize=8.5, color=INK, fontweight="bold",
                ha="center", va="bottom", zorder=11, bbox=dict(facecolor="#FEF3C7", edgecolor="#F59E0B", lw=0.8, pad=1.8))
for p, l, st in zip(pts, labp, P):
    nn = st["n"]; c = col(tramo_de(nn))
    ax.plot(p[0], p[1], "o", ms=3.2, color=INK, zorder=7)
    if math.hypot(l[0] - p[0], l[1] - p[1]) > R * 0.5:
        ax.plot([p[0], l[0]], [p[1], l[1]], color=INK, lw=0.8, zorder=7)
    ax.add_patch(Circle(l, R, facecolor=c, edgecolor="#F59E0B" if nn == pen else "white",
                        lw=2.2 if nn == pen else 1.4, zorder=8))
    ax.text(l[0], l[1], str(nn), color="white", fontsize=9 if nn < 10 else 8.2, fontweight="bold",
            ha="center", va="center", zorder=9)

# escala y norte
sk = 1.0 if xspan > 4 else 0.5
sx = (x1 - 0.4 - sk) if pad[0] <= (x0 + x1) / 2 else (x0 + 0.4)   # lejos del lado de PADOMI
ax.plot([sx, sx + sk], [y0 + 0.3, y0 + 0.3], color=INK, lw=2)
ax.text(sx + sk / 2, y0 + 0.4, f"{sk:g} km", fontsize=8, color=INK, ha="center", va="bottom")
izq = min(math.hypot(l[0] - x0, l[1] - y1) for l in lab) > min(math.hypot(l[0] - x1, l[1] - y1) for l in lab)
ax.text((x0 + 0.15) if izq else (x1 - 0.15), y1 - 0.15, "N ↑", fontsize=10, color=INK,
        ha="left" if izq else "right", va="top", fontweight="bold")

# ---------- leyenda ----------
lg = fig.add_axes([0.05, 0.25 / H, 0.92, leg_h / H]); lg.axis("off")
tot_rows = sum(r[2] for r in rows)
lg.set_xlim(0, 1); lg.set_ylim(0, tot_rows)
y = tot_rows
tachar = []
for kind, dat, h in rows:
    yc = y - h / 2
    if kind == "titulo_v":
        lg.text(0.0, yc, dat, fontsize=9, color=MUTED, va="center", fontweight="bold")
    elif kind == "visitada":
        nn, txt = dat
        lg.scatter([0.022], [yc], s=230, color=GRIS, edgecolors="white", linewidths=1, zorder=3, clip_on=False)
        lg.text(0.022, yc, str(nn), color="white", fontsize=8, fontweight="bold", ha="center", va="center", zorder=4)
        tachar.append(lg.text(0.06, yc, txt, fontsize=9.6, color=GRIS, va="center"))
    elif kind == "tramo":
        k, txt = dat
        lg.plot([0.0, 0.045], [yc, yc], color=col(k), lw=3.2)
        lg.text(0.06, yc, txt, fontsize=8.6, color=INK, va="center")
    elif kind == "total":
        lg.text(0.0, yc, dat, fontsize=10, color=INK, va="center", fontweight="bold")
    elif kind == "parada":
        nn, txt, bold = dat
        top_line = y - 0.5
        lg.scatter([0.022], [top_line], s=230, color=col(tramo_de(nn)),
                   edgecolors="#F59E0B" if nn == pen else "white", linewidths=1.8 if nn == pen else 1,
                   zorder=3, clip_on=False)
        lg.text(0.022, top_line, str(nn), color="white", fontsize=8, fontweight="bold", ha="center", va="center", zorder=4)
        multi = "\n" in txt
        lg.text(0.06, top_line + 0.32 if multi else top_line, txt, fontsize=9.6, color=INK,
                va="top" if multi else "center", fontweight="bold" if bold else "normal", linespacing=1.25)
    elif kind == "nota":
        lg.text(0.0, yc, dat, fontsize=7.4, color=MUTED, va="center", linespacing=1.4)
    y -= h

if tachar:                                   # línea por el medio del texto de los ya visitados
    fig.canvas.draw()
    rend = fig.canvas.get_renderer(); inv = lg.transData.inverted()
    for t in tachar:
        bb = t.get_window_extent(rend)
        (ax0, ay0), (ax1, ay1) = inv.transform((bb.x0, bb.y0)), inv.transform((bb.x1, bb.y1))
        ym = (ay0 + ay1) / 2
        lg.plot([ax0 - 0.004, ax1 + 0.004], [ym, ym], color="#6B7280", lw=1.1, zorder=5, clip_on=False)
fig.savefig(OUT, dpi=150, facecolor=BG)
# aviso para revisar el PNG solo si hace falta: dirección cortada o números encimados
nums = [st["n"] for st in V + P]
encimados = [(nums[i], nums[j]) for i in range(len(lab)) for j in range(i + 1, len(lab))
             if math.hypot(lab[i][0] - lab[j][0], lab[i][1] - lab[j][1]) < 1.9 * R]
cortadas = [d for d in dirs + vdirs if d.endswith("…")]
print("ok", OUT)
if encimados or cortadas:
    print("REVISAR", {"numeros_encimados": encimados, "direcciones_cortadas": cortadas})
