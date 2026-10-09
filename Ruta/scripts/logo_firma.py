"""Firma "by / CRISTHIAN RAMIREZ" sin fondo (PNG transparente) para el gráfico de la ruta PADOMI.
Uso (desde Ruta/scripts): python3 logo_firma.py ../data/firma.png [ICONO] [ESTILO] [fuente_nombre.ttf] [fuente_by.ttf]
  ICONO:  uno o varios unidos con "+", p. ej. ruta+gps. ruta (anillo -> quiebre -> punto) | pin (marcador de ubicación) |
          trayecto (anillo y punto unidos por un camino de puntitos) | gps (punto con anillo, "estás aquí")
  ESTILO: solido (gris claro sin contorno) | contorno (borde fino) | sombra
"""
import math
import sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops

S = 8                                   # resolución: píxeles por unidad de diseño
GRIS_CLARO = (180, 186, 195, 255)       # #B4BAC3  letra y punto de llegada (gris claro, un tono más oscuro)
GRIS_MEDIO = (147, 154, 166, 255)       # #939AA6  trazos del ícono
OSCURO = (75, 85, 99)                   # #4B5563  contorno / sombra
TRANSP = (0, 0, 0, 0)


def ancho(txt, f, trk):
    return sum(f.getlength(c) for c in txt) + trk * (len(txt) - 1)


def escribir(d, x, y, txt, f, trk, color):
    for c in txt:
        d.text((x, y), c, font=f, fill=color, anchor="ls")
        x += f.getlength(c) + trk
    return x


def circulo(d, cx, cy, r, **kw):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], **kw)


def icono(d, tipo, x0, y0, y1):
    """Dibuja el ícono en la columna izquierda: x desde x0, alto de y0 (arriba) a y1 (línea base)."""
    lw = int(1.5 * S)
    ra, rb = 3.0 * S, 2.8 * S
    if tipo == "ruta":                                   # anillo de salida -> quiebre a 45° -> punto de llegada
        ax_, ay_ = x0 + ra, y0 + ra
        bx_, by_ = x0 + 8.5 * S, y1 - rb
        circulo(d, ax_, ay_, ra, outline=GRIS_MEDIO, width=lw)
        codo = by_ - (bx_ - ax_)
        d.line([(ax_, ay_ + ra), (ax_, max(codo, ay_ + ra)), (bx_, by_ - rb * 0.2)],
               fill=GRIS_MEDIO, width=lw, joint="curve")
        circulo(d, bx_, by_, rb, fill=GRIS_CLARO)
    elif tipo == "pin":                                  # marcador de ubicación con centro hueco
        R = 4.6 * S
        cx, tip = x0 + R, y1
        cy = tip - 14 * S + R
        circulo(d, cx, cy, R, fill=GRIS_MEDIO)
        a = math.radians(38)
        d.polygon([(cx - R * math.cos(a), cy + R * math.sin(a)), (cx + R * math.cos(a), cy + R * math.sin(a)),
                   (cx, tip)], fill=GRIS_MEDIO)
        circulo(d, cx, cy, 2.0 * S, fill=TRANSP)          # hueco
    elif tipo == "trayecto":                             # anillo abajo -> camino punteado en S -> punto arriba
        ax_, ay_ = x0 + ra, y1 - ra
        bx_, by_ = x0 + 8.0 * S, y0 + rb + 0.5 * S
        circulo(d, ax_, ay_, ra, outline=GRIS_MEDIO, width=lw)
        circulo(d, bx_, by_, rb, fill=GRIS_CLARO)
        p0, p3 = (ax_, ay_ - ra - 1.2 * S), (bx_, by_ + rb + 1.2 * S)
        ym = (p0[1] + p3[1]) / 2
        p1, p2 = (p0[0], ym), (p3[0], ym)
        pts = []
        for i in range(201):
            t = i / 200
            x = (1-t)**3*p0[0] + 3*(1-t)**2*t*p1[0] + 3*(1-t)*t**2*p2[0] + t**3*p3[0]
            y = (1-t)**3*p0[1] + 3*(1-t)**2*t*p1[1] + 3*(1-t)*t**2*p2[1] + t**3*p3[1]
            pts.append((x, y))
        largo = [0.0]                                    # 2 puntitos repartidos a lo largo del camino
        for a_, b_ in zip(pts, pts[1:]):
            largo.append(largo[-1] + math.hypot(b_[0] - a_[0], b_[1] - a_[1]))
        for k in (1, 2):
            objetivo = largo[-1] * k / 3
            j = min(range(len(largo)), key=lambda q: abs(largo[q] - objetivo))
            circulo(d, pts[j][0], pts[j][1], 1.0 * S, fill=GRIS_MEDIO)
    elif tipo == "gps":                                  # punto con anillo ("estás aquí"), centrado
        cx, cy = x0 + 5.2 * S, (y0 + y1) / 2
        circulo(d, cx, cy, 5.2 * S, outline=GRIS_MEDIO, width=int(1.4 * S))
        circulo(d, cx, cy, 2.4 * S, fill=GRIS_CLARO)
    else:
        raise ValueError(f"ícono desconocido: {tipo}")


def dibujo(tipo, f_nombre, f_by, margen):
    """Capa RGBA con la firma en gris, sin fondo."""
    fn = ImageFont.truetype(f_nombre, 15 * S)
    fb = ImageFont.truetype(f_by, 9.5 * S)
    t_n, t_b = 1.1 * S, 1.0 * S                       # espaciado entre letras
    nombre, by = "CRISTHIAN RAMIREZ", "by"
    h_by = -fb.getbbox("b", anchor="ls")[1]                # alto de la b (con su asta)
    h_n = -fn.getbbox("CR", anchor="ls")[1]
    tipos = tipo.split("+")
    paso = 13.5 * S                                        # separación entre íconos puestos lado a lado
    sep, m = 5.5 * S, margen
    ico = 15 * S + (len(tipos) - 1) * paso
    W = int(m + ico + ancho(nombre, fn, t_n) + m)
    H = int(m + h_by + sep + h_n + m)
    img = Image.new("RGBA", (W, H), TRANSP)
    d = ImageDraw.Draw(img)
    for k, t in enumerate(tipos):
        icono(d, t, m + k * paso, m + 0.3 * S, H - m)
    xt = m + ico
    escribir(d, xt, m + h_by, by, fb, t_b, GRIS_CLARO)       # un solo gris claro para toda la letra
    escribir(d, xt, H - m, nombre, fn, t_n, GRIS_CLARO)
    return img


def logo(salida, tipo="ruta+trayecto", estilo="solido", f_nombre="Orbitron-700.ttf", f_by="Orbitron-700.ttf"):
    capa = dibujo(tipo, f_nombre, f_by, margen=4 * S)
    alfa = capa.getchannel("A")
    out = Image.new("RGBA", capa.size, TRANSP)
    if estilo == "contorno":
        borde = alfa.filter(ImageFilter.MaxFilter(2 * int(0.5 * S) + 1))      # trazo engrosado
        out.paste(Image.new("RGBA", capa.size, OSCURO + (255,)), (0, 0), borde)
    elif estilo == "sombra":
        sm = ImageChops.offset(alfa, int(0.6 * S), int(0.8 * S)).filter(ImageFilter.GaussianBlur(0.7 * S))
        sm = sm.point(lambda v: int(v * 0.55))
        out.paste(Image.new("RGBA", capa.size, OSCURO + (255,)), (0, 0), sm)
    out.alpha_composite(capa)
    out = out.crop(out.getbbox())
    out.save(salida)
    return out


if __name__ == "__main__":
    a = sys.argv[1:]
    logo(a[0], a[1] if len(a) > 1 else "ruta+trayecto", a[2] if len(a) > 2 else "solido", *(a[3:5]))
    print("ok", a[0])
