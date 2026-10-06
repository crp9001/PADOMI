#!/usr/bin/env python3
"""Ruta PADOMI v2: orden de visitas según el sentido de las calles, lista para el chat, mapa y gráfico.

Se corre siempre desde la carpeta de trabajo; los archivos del día llevan la fecha (AAAAMMDD).

  1) python3 ruta_padomi.py preparar <archivo con el texto "RUTA PADOMI {...}">
       Guarda citas_<fec>.json y muestra: fecha, cuenta de Geoprog, pacientes, si la lista cambió,
       las direcciones a ubicar con places_search (sin repetir) y, si es ruta nueva,
       las URLs de tiempos por calle para WebFetch (osrm_plan_<fec>.json).
  2) (solo en plena ruta) python3 ruta_padomi.py plan <fec> --voy N
       Recalcula desde el paciente N: escribe osrm_plan_<fec>.json con las URLs para WebFetch.
  3) python3 ruta_padomi.py ruta <fec> [--voy N] [--especialista "Nombre Apellido"]
       Usa lugares_<fec>.json (resultados de places_search) y osrm_<fec>_k.json (respuestas de WebFetch).
       Escribe ruta_<fec>.json, lista_<fec>.md (texto para el chat), mapa_<fec>.json (para el mapa)
       y etiquetas_<fec>.json, y genera el gráfico ruta_padomi_<ddmm>.png.

lugares_<fec>.json = lista de lugares tal como los da places_search
  [{"address": .., "latitude": .., "longitude": .., "types": [..], "place_id": ..}, ...]
  (también sirve {"places": [...]}). No hace falta ordenarlos: cada paciente toma el lugar con su
  mismo número y calle más cercano a su pin.
"""
import json, math, sys, html, re, argparse, os, itertools, random, shutil, subprocess, datetime
from collections import Counter
from urllib.parse import quote

PADOMI = (-12.0782458, -77.0368112)    # Av. Arenales 1302, Jesús María
PADOMI_PID = "ChIJxaPv7bbJBZERIZPpt74sv7E"
ARENALES = (-12.069933, -77.037982)    # Av. Arenales cdra 5: obliga a volver por Arenales
MIN_POR_PACIENTE = 6                   # atención aproximada por paciente
FACTOR_CALLES = 1.35                   # línea recta -> recorrido por calles
VEL_LIBRE_KMH = 30                     # sin tiempos por calle: línea recta x1.35 a 30 km/h sin tráfico
FACTOR_TRAFICO = 1.5                   # los tiempos por calle son sin tráfico; en Lima x1.5 (= 20 km/h promedio)
GRUPO_SEG = 150                        # pequeño grupo: paradas a 2.5 min o menos entre sí por calle (sin tráfico)
MAX_GRUPO = 6                          # paradas como máximo por grupo
PENAL_GRUPO = 240                      # volver a un grupo ya empezado cuesta +4 min en la búsqueda del orden
OSRM = "https://router.project-osrm.org"   # OpenStreetMap: conoce el sentido de cada vía
MAX_URL = 230                          # largo máximo de URL que acepta WebFetch (216 funciona, 330 no)
PROMPT_OSRM = ('Return the "code" field and the "durations" matrix exactly as given (JSON array of arrays, '
               'every number unchanged, verbatim, all rows). Output only JSON: {"code":..., "durations":[...]}')
PARADAS_POR_TRAMO = 5                  # tramos de 5 paradas: enlace de tramo, tiempos y colores del gráfico
MAX_AJUSTE_KM = 0.30                   # cruce pin-dirección: se acepta si están a 300 m o menos
A_PIE_KM = 0.04                        # a 40 m o menos (cruzar la calle): la unidad no se mueve, el especialista va a pie
VEL_PIE_MS = 1.0                       # a pie con el maletín (m/s), cruzando la calle
FACTOR_PIE = 1.3                       # línea recta -> camino a pie
# avenidas anchas o de mucho tránsito: no se cruzan a pie (ahí sí se mueve la unidad). Se suman más con --ancha
AVENIDAS_ANCHAS = ["JAVIER PRADO", "AVIACION", "ANGAMOS", "AREQUIPA", "PASEO DE LA REPUBLICA", "VIA EXPRESA",
                   "PANAMERICANA", "TOMAS MARSANO", "BENAVIDES", "REPUBLICA DE PANAMA", "PRIMAVERA", "LA MARINA",
                   "BRASIL", "SALAVERRY", "CANADA", "CIRCUNVALACION", "UNIVERSITARIA", "COLONIAL", "VENEZUELA",
                   "FAUCETT", "TUPAC AMARU", "PROCERES", "SEPARADORA INDUSTRIAL", "CARRETERA CENTRAL",
                   "NICOLAS AYLLON", "JOSE LARCO", "PETIT THOUARS", "28 DE JULIO", "ALFONSO UGARTE", "ABANCAY",
                   "NICOLAS ARRIOLA", "DEFENSORES DEL MORRO", "PACHACUTEC", "RAUL FERRERO", "LA FONTANA",
                   "EVITAMIENTO", "RAMIRO PRIALE", "ARGENTINA", "MORALES DUAREZ", "NARANJAL", "CARLOS IZAGUIRRE",
                   "SAN LUIS", "LA MOLINA", "EL DERBY", "CAMINOS DEL INCA", "SANTA ROSA", "GRAU"]
NAV = "https://www.google.com/maps/dir/?api=1&travelmode=driving&dir_action=navigate"
AQUI = os.path.dirname(os.path.abspath(__file__))
DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]


# ---------------------------------------------------------------- utilidades
def hav(a, b):
    R = 6371.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))

def sin_tildes(t):
    for a, b in zip("ÁÉÍÓÚÜáéíóúü", "AEIOUUaeiouu"):
        t = t.replace(a, b)
    return t.upper()

def hora_lima():
    return datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=5)   # Perú: UTC-5 todo el año

def dia_corto(fec):
    d = datetime.date(int(fec[:4]), int(fec[4:6]), int(fec[6:8]))
    return f"{DIAS[d.weekday()]} {d.day:02d}/{d.month:02d}"

def guardar(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, default=list)

def leer(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

GENERIC = {"CALLE", "AVENIDA", "JIRON", "PASAJE", "DPTO", "DPT", "PISO", "INT", "BLOCK", "URB", "LOTE",
           "ETAPA", "SECTOR", "CASA", "REPOSO", "ASOC", "SAN", "SANTA", "LOS", "LAS", "DEL", "LIMA"}
def addr_key(via):
    t = re.sub(r"[^A-Z0-9Ñ ]", " ", sin_tildes(via))
    nums = {w for w in t.split() if w.isdigit() and len(w) >= 2}
    words = {w for w in t.split() if w.isalpha() and len(w) >= 4 and w not in GENERIC}
    return nums, words

TIPO_VIA = {"CA", "CALLE", "AV", "AVENIDA", "JR", "JIRON", "PS", "PSJ", "PASAJE", "PROLONG", "PROLONGACION", "OV", "AL"}
def calle_y_numero(via):
    """'AV DEL PARQUE NORTE 470 URB CORPAC' -> ('DEL PARQUE NORTE', 470); sin número -> (calle, None)"""
    t = re.sub(r"[^A-Z0-9Ñ ]", " ", sin_tildes(html.unescape(str(via or "")))).split()
    while t and t[0] in ("CR", "OT"):
        t = t[1:]
    if t and t[0] in TIPO_VIA:
        t = t[1:]
    nombre, num = [], None
    for w in t:
        if w.isdigit() and nombre:                       # '28 DE JULIO 1234': el 28 es parte del nombre
            num = int(w); break
        if w in ("NRO", "NO", "N"):                      # 'Nº 421'
            continue
        if w in ("MZ", "LT", "DPTO", "DPT", "URB", "INT", "BLOCK"):
            break
        nombre.append(w)
    return " ".join(nombre), num

def es_ancha(via, anchas):
    c = f" {calle_y_numero(via)[0]} "
    return any(f" {a} " in c for a in anchas)

def pie_ok(via_a, via_b, anchas):
    """¿puede ir a pie el especialista de una dirección a la otra? Sí, salvo que haya que cruzar una
    avenida ancha. En la misma avenida ancha, solo por la misma vereda (los dos números pares o impares)."""
    aa = bool(via_a) and es_ancha(via_a, anchas)
    ab = bool(via_b) and es_ancha(via_b, anchas)
    if not (aa or ab):
        return True
    (ca, na), (cb, nb) = calle_y_numero(via_a), calle_y_numero(via_b)
    return aa and ab and ca == cb and na is not None and nb is not None and na % 2 == nb % 2

# ---------------------------------------------------------------- consultas para places_search
TIPOS = {"CA": "Calle", "CALLE": "Calle", "AV": "Avenida", "AVENIDA": "Avenida", "JR": "Jirón",
         "JIRON": "Jirón", "PS": "Pasaje", "PSJ": "Pasaje", "PASAJE": "Pasaje", "PROLONG": "Prolongación"}
DISTRITOS = {"LIMA CERCADO": "Cercado de Lima", "S. M. DE PORRES": "San Martín de Porres",
             "ATE VITARTE": "Ate", "S. J. DE LURIGANCHO": "San Juan de Lurigancho",
             "S. J. DE MIRAFLORES": "San Juan de Miraflores", "V. M. DEL TRIUNFO": "Villa María del Triunfo"}

def distrito(dst):
    dst = html.unescape(str(dst)).strip()
    return DISTRITOS.get(dst.upper(), titulo(dst))

def consulta(via, dst):
    """'CR CALLE SISLEY 192 "X"' -> 'Calle Sisley 192, San Borja'. None si no hay calle con número."""
    t = sin_tildes(html.unescape(via)).replace('"', " ").replace("_", " ").replace("#", " ")
    t = re.sub(r"\.(?=\S)", ". ", t)                       # "AV.DE" -> "AV. DE"
    t = re.sub(r"\b(?:N[º°]|NRO|NO)\.?\s*(?=\d)", " ", t)   # "Nº 135", "NO 12" (no toca "NORTE")
    toks = [x.strip(".,") for x in t.split()]
    toks = [x for x in toks if x]
    while toks and toks[0] in ("CR", "OT", "C.R", "C.R."):
        toks = toks[1:]
    if not toks or toks[0] in ("AH", "AAHH", "UV", "UR", "PQ", "MZ", "MZ.", "ASOC", "URB"):
        return None
    tipo = TIPOS.get(toks[0])
    rest = toks[1:] if tipo else toks
    nombre, numero = [], None
    for w in rest:
        m = re.match(r"^(\d{2,5})", w)
        if m:
            numero = m.group(1); break
        if w.startswith("MZ") or w in ("LT", "LOTE", "BLOCK"):
            return None
        nombre.append(w)
    if not numero or not nombre:
        return None
    calle = " ".join(w.capitalize() for w in nombre)
    return f"{(tipo + ' ') if tipo else ''}{calle} {numero}, {distrito(dst)}"

def clave_consulta(q):
    """'Avenida Florida 339, Chaclacayo' y 'Florida 339, Chaclacayo' son la misma búsqueda"""
    t = re.sub(r"[^A-Z0-9Ñ ]", " ", sin_tildes(q)).split()
    return " ".join(w for w in t if w not in ("CALLE", "AVENIDA", "JIRON", "PASAJE", "PROLONGACION"))

def cargar_lugares(fec):
    path = f"lugares_{fec}.json"
    if not os.path.exists(path):
        return []
    d = leer(path)
    if isinstance(d, dict):
        d = d.get("places", list(d.values()))
    out = []
    for L in d:
        try:
            out.append({"lat": float(L.get("latitude", L.get("lat"))), "lng": float(L.get("longitude", L.get("lng"))),
                        "direccion": L.get("address", L.get("direccion", "")) or "",
                        "place_id": L.get("place_id"), "tipos": L.get("types", L.get("tipos", ["street_address"]))})
        except (TypeError, ValueError):
            continue
    return out

def lugar_para(nom_via, lat, lng, lugares):
    """el lugar con el mismo número y la misma calle, el más cercano al pin de Geoprog"""
    nums, words = addr_key(nom_via)
    best = None
    for L in lugares:
        n2, w2 = addr_key(L["direccion"])
        if (nums & n2) and (words & w2):
            d = hav((lat, lng), (L["lat"], L["lng"]))
            if best is None or d < best[0]:
                best = (d, L)
    return best

# ---------------------------------------------------------------- textos para el chat
PARTICULAS = {"DE", "DEL", "LA", "LAS", "LOS", "Y", "E", "EN", "CON"}
ROMANOS = {"II", "III", "IV", "VI", "VII", "VIII", "IX", "XI", "XII"}
def _palabra(w, inicio, tras_mz):
    u = w.upper()
    if tras_mz:                                  # "MZ Y LT 13": la letra de la manzana va en mayúscula
        return u
    if not inicio and u in PARTICULAS:
        return w.lower()
    if u == "VDA":
        return "vda."
    if u in ROMANOS or (any(c.isdigit() for c in w) and len(w) <= 4):
        return u
    return re.sub(r"[^\W\d_]+", lambda m: m.group(0).capitalize(), w)   # "SQ.MORON" -> "Sq.Moron"

def titulo(t, fijas=()):
    """MAYÚSCULAS de Geoprog -> Tipo Título, con 'de', 'la', 'del' en minúscula; 'fijas' se dejan tal cual"""
    out = []
    for w in html.unescape(str(t)).split():
        if w in fijas:
            out.append(w)
            continue
        prev = out[-1] if out else ""
        out.append(_palabra(w, not out or prev in fijas or prev.endswith("."), prev in ("Mz", "Lt", "MZ", "LT")))
    return " ".join(out)

ABREV = {"CA": "Calle", "AV": "Av.", "AV.": "Av.", "JR": "Jr.", "JR.": "Jr.", "PS": "Psje.", "PSJ": "Psje.",
         "UR": "Urb.", "URB": "Urb.", "URB.": "Urb.", "UR.": "Urb.", "ASOC": "Asoc.", "ASOC.": "Asoc.",
         "AH": "A.H.", "AAHH": "A.H.", "UV": "U.V.", "MZ": "Mz", "MZ.": "Mz", "LT": "Lt", "LT.": "Lt",
         "PROLONG": "Prolong.", "CDRA": "cdra", "CDRA.": "cdra"}

ERRATAS = {"PARUQE": "PARQUE", "CALERADE": "CALERA DE", "NEOPLASTICA": "NEOPLASICAS", "NEOPLASICA": "NEOPLASICAS",
           "CINCURVALACION": "CIRCUNVALACION", "AVIACON": "AVIACION", "REPUBLCA": "REPUBLICA"}
def limpiar(t, dst=""):
    """arregla lo que Geoprog trae mal escrito: 'URB.LOS' -> 'URB. LOS', 'NRO.164' -> '164',
    errores comunes y el distrito repetido al final de la dirección"""
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\b(URB|DPTO|DPT|PSJE|AV|CA|JR|ALT|CDRA|CDR|ESQ|STA)\.(?=[A-Z0-9])", r"\1. ", t, flags=re.I)
    t = re.sub(r"\b(?:NRO|N[°º])\.?\s*(?=\d)", "", t, flags=re.I)
    for a, b in ERRATAS.items():
        t = re.sub(rf"\b{a}\b", b, t, flags=re.I)
    if dst and len(t) > len(dst) + 8 and t.upper().endswith(" " + dst.upper()):
        t = t[:-len(dst) - 1].rstrip(" ,")
    return t

def partes_dir(nom_via):
    """'CR FLORIDA 339 C.R. ANCIANOS DESAMPARADOS' -> ('Florida 339', 'C.R. Ancianos Desamparados')"""
    t = re.sub(r"\s+", " ", html.unescape(str(nom_via)).replace("_", " ")).strip()
    t = re.sub(r"^(CR|OT)\s+", "", t, flags=re.I)
    casa = ""
    m = re.search(r'\s*(?:"|\bC\.\s?R\.?\s*)(.*)$', t)
    if m:
        casa = titulo(m.group(1).replace('"', "").strip())
        casa = ("C.R. " + casa) if casa else ""
        t = t[:m.start()].strip()
    t = re.sub(r"\b(MZ|LT)\.?(?=[A-Z0-9])", r"\1 ", t, flags=re.I)   # "LT.8" -> "LT 8"
    toks = [ABREV.get(w.upper(), w) for w in t.split()]
    principal = titulo(" ".join(toks), fijas=set(ABREV.values()))
    return principal, casa

def dir_larga(p):
    principal, casa = partes_dir(p["nom_via"])
    s = f"{principal}, {distrito(p['nom_dst'])}"
    return f"{s} · {casa}" if casa else s

def dir_corta(p, max_c=44):
    """dirección corta para el gráfico y el mapa: calle y número, o urbanización/asociación + Mz/Lt"""
    principal, _ = partes_dir(p["nom_via"])
    toks = principal.split()
    dst = distrito(p["nom_dst"])
    if "Mz" in toks or "Lt" in toks:
        val = lambda k: toks[toks.index(k) + 1] if k in toks and toks.index(k) + 1 < len(toks) else ""
        mzlt = " ".join(x for x in (f"Mz {val('Mz')}" if val("Mz") else "", f"Lt {val('Lt')}" if val("Lt") else "") if x)
        zona = [i for i, w in enumerate(toks) if w in ("Urb.", "Asoc.", "A.H.", "U.V.")]
        if zona:
            i = zona[0] + 1
            j = next((k for k in range(i, len(toks)) if toks[k] in ("Mz", "Lt")), len(toks))
            nombre = toks[i:j]
        else:
            nombre = toks[:min(toks.index(k) for k in ("Mz", "Lt") if k in toks)]
        base = f"{' '.join(nombre)} {mzlt}".strip()
    else:
        # 'Nro.164' -> '164'; el número también puede ser 'M-8'
        toks = [re.sub(r"^(?:Nro|N[º°]|No)\.?(?=\d)", "", w, flags=re.I) for w in toks]
        k = next((i for i, w in enumerate(toks)
                  if i and ((w.isdigit() and len(w) >= 2) or re.fullmatch(r"[A-Za-z]-?\d{1,3}", w))), None)
        base = " ".join(toks[:k + 1] if k is not None else toks)
    base = base[:1].upper() + base[1:]
    if len(base) > max_c:
        base = base[:max_c - 1].rsplit(" ", 1)[0] + "…"
    s = f"{base}, {dst}"
    return s if len(s) <= max_c else base

def es_casa_reposo(p):
    t = sin_tildes(p["nom_via"] + " " + p["ref_dom"])
    return bool(re.search(r"\bC\.\s?R\.|CASA DE REPOSO|ASILO|ALBERGUE|HERMANITA", t))

def es_mz_lt(p):
    t = sin_tildes(p["nom_via"])
    return bool(re.search(r"\bMZ\b|\bMZ\.|\bLT\b|\bLT\.|\bAAHH\b|\bA\.\s?H\.|\bASOC|\bAH\b|\bUV\b", t))

def telefonos(t):
    out = []
    for w in re.split(r"[\s/,;]+", str(t)):
        w = w.strip("-.")
        if sum(c.isdigit() for c in w) >= 6 and w not in out:
            out.append(w)
    return out

def primer_apellido(nombre):
    t = nombre.split()
    out, i = [], 0
    while i < len(t) - 1 and t[i].upper() in PARTICULAS | {"SAN", "SANTA"}:
        out.append(t[i]); i += 1
    out.append(t[i])
    return titulo(" ".join(out))

def fmt(m):
    if m < 60:
        return f"{m} min"
    return f"{m // 60} h" if m % 60 == 0 else f"{m // 60} h {m % 60:02d} min"

def r5(m):
    return int(5 * round(m / 5.0))

def base_pac(p):
    """el paciente con la forma más repetida de la dirección de la parada (para mostrarla)"""
    pcs = p["pacientes"]
    norm = lambda x: re.sub(r"\s+", " ", x["nom_via"]).strip()
    c = Counter(norm(x) for x in pcs)
    return max(pcs, key=lambda x: c[norm(x)])

def moda(xs):
    xs = [re.sub(r"\s+", " ", x).strip() for x in xs if x]
    return Counter(xs).most_common(1)[0][0] if xs else ""


# ---------------------------------------------------------------- paradas
def construir(fec, voy, usar_lugares, gps=None, quitar=None):
    data = leer(f"citas_{fec}.json")
    rows = data["rows"] if isinstance(data, dict) else data
    lugares = cargar_lugares(fec) if usar_lugares else []
    visitadas, inicio, cods_previos, prev = [], {"tipo": "padomi"}, set(), None
    if voy is not None:
        base = f"ruta_{fec}_previa.json"
        if not os.path.exists(base):
            sys.exit(f"Falta {base}: corre primero 'plan {fec} --voy {voy}'")
        prev = leer(base)
        todas = prev.get("visitadas", []) + prev["paradas"]
        for p in todas:
            cods_previos |= {x["cod_pac"] for x in p["pacientes"]}
        visitadas = [p for p in todas if p["n"] <= voy]
        actual = next((p for p in todas if p["n"] == voy), None)
        if actual is None:
            sys.exit(f"No existe la parada {voy} en la ruta anterior")
        inicio = {"tipo": "parada", "n": voy, "lat": actual["lat"], "lng": actual["lng"],
                  "pacientes": [x["paciente"] for x in actual["pacientes"]],
                  "cods": [x["cod_pac"] for x in actual["pacientes"]],
                  "nom_via": actual["pacientes"][0]["nom_via"]}
    elif gps:
        inicio = {"tipo": "gps", "lat": gps[0], "lng": gps[1]}
    cods_visitados = {x["cod_pac"] for p in visitadas for x in p["pacientes"]}
    quitar = [sin_tildes(q.strip()) for q in (quitar or "").split(",") if q.strip()]
    if quitar:   # pacientes ya atendidos que dijo el usuario (por apellido o código)
        for r in rows:
            nombre = sin_tildes(html.unescape(str(r.get("paciente", ""))))
            if any(q in nombre or q == str(r.get("cod_pac", "")).upper() for q in quitar):
                cods_visitados.add(r.get("cod_pac"))

    stops, avisos = [], []
    for r in rows:
        if r.get("cod_pac") in cods_visitados:
            continue
        try:
            lat, lng = float(r["coordy"]), float(r["coordx"])
        except (KeyError, TypeError, ValueError):
            avisos.append(f"SIN COORDENADAS: {html.unescape(str(r.get('paciente','')))}")
            continue
        if not (-12.6 < lat < -11.6 and -77.3 < lng < -76.6):
            avisos.append(f"COORDENADAS FUERA DE LIMA/CALLAO: {html.unescape(str(r.get('paciente','')))} ({lat},{lng})")
            continue
        pac = {k: html.unescape(str(r.get(k, ""))).strip()
               for k in ("cod_pac", "paciente", "nom_via", "ref_dom", "nom_dst", "telfs", "edad")}
        pac["nom_via"], pac["ref_dom"] = limpiar(pac["nom_via"], pac["nom_dst"]), limpiar(pac["ref_dom"])
        pac["nuevo"] = voy is not None and pac["cod_pac"] not in cods_previos
        # cruce pin de Geoprog <-> dirección escrita
        destino = None
        if lugares and consulta(pac["nom_via"], pac["nom_dst"]):
            hit = lugar_para(pac["nom_via"], lat, lng, lugares)
            if hit:
                d_aj, g = hit
                tipos_ok = any(t in ("street_address", "premise", "subpremise") for t in g["tipos"])
                if tipos_ok and d_aj <= MAX_AJUSTE_KM:
                    destino = {"lat": g["lat"], "lng": g["lng"], "direccion": g["direccion"],
                               "place_id": g["place_id"], "ajuste_m": int(round(d_aj * 1000))}
                    lat, lng = g["lat"], g["lng"]
                elif tipos_ok:
                    avisos.append(f"REVISAR: el pin de Geoprog y la dirección de {pac['paciente']} están a "
                                  f"{d_aj*1000:.0f} m; se usa el pin de Geoprog")
        pac["destino"] = destino
        nums, words = addr_key(pac["nom_via"])
        s = None
        for x in stops:
            dkm = hav((x["lat"], x["lng"]), (lat, lng))
            # misma parada: a 25 m o menos, o a 100 m o menos con el mismo número y la misma calle
            if dkm <= 0.025 or (dkm <= 0.100 and (nums & x["nums"]) and (words & x["words"])):
                s = x
                break
        if s is None:
            s = {"lat": lat, "lng": lng, "pacientes": [], "nums": nums, "words": words, "destino": destino}
            stops.append(s)
        s["pacientes"].append(pac)

    if prev is not None:
        nuevos_cods = {r.get("cod_pac") for r in rows}
        for p in prev["paradas"]:
            if p["n"] > voy:
                for x in p["pacientes"]:
                    if x["cod_pac"] not in nuevos_cods:
                        avisos.append(f"YA NO FIGURA EN LA LISTA (¿cancelado?): {titulo(x['paciente'])}")
    start = (inicio["lat"], inicio["lng"]) if inicio["tipo"] in ("parada", "gps") else PADOMI
    return {"data": data, "rows": rows, "stops": stops, "avisos": avisos, "inicio": inicio,
            "visitadas": visitadas, "start": start}


# ---------------------------------------------------------------- tiempos por calle (OSRM)
def _cod(v):
    v = ~(v << 1) if v < 0 else (v << 1)
    s = ""
    while v >= 0x20:
        s += chr((0x20 | (v & 0x1F)) + 63); v >>= 5
    return s + chr(v + 63)

def _delta_ok(d):
    """un delta 0 se codifica como '?', que rompe la URL (OSRM responde 400): se corre 1e-5 grados (~1 m)"""
    d = d or 1
    return d, _cod(d)

def polyline(coords):
    out, pl, pg = "", 0, 0
    for la, lo in coords:
        da, ca = _delta_ok(int(round(la * 1e5)) - pl)
        db, cb = _delta_ok(int(round(lo * 1e5)) - pg)
        out += ca + cb
        pl, pg = pl + da, pg + db
    return out

# caché de tiempos por calle del día (tiempos_<fec>.json): {"nodo_de": {cod_pac: nodo}, "t": {"A|B": seg}}
# En plena ruta solo se consultan los pares que faltan: sin pacientes nuevos, ninguna consulta.
def cargar_cache(fec):
    path = f"tiempos_{fec}.json"
    c = leer(path) if os.path.exists(path) else {}
    c.setdefault("nodo_de", {})
    c.setdefault("t", {})
    return c

def ids_nodos(B, nodo_de, registrar=False):
    """identificador estable de cada punto (inicio, paradas, PADOMI) para el caché de tiempos"""
    ini = B["inicio"]
    if ini["tipo"] == "parada":
        i0 = nodo_de.get(ini["cods"][0], "INI:" + ini["cods"][0])
    elif ini["tipo"] == "gps":
        i0 = f"GPS:{ini['lat']:.4f},{ini['lng']:.4f}"
    else:
        i0 = "PADOMI"
    ids = [i0]
    for s in B["stops"]:
        cods = [x["cod_pac"] for x in s["pacientes"]]
        i = next((nodo_de[c] for c in cods if c in nodo_de), None) or min(cods)
        if registrar:
            for c in cods:
                nodo_de.setdefault(c, i)
        ids.append(i)
    return ids + ["PADOMI"]

def hacer_plan(fec, voy, gps=None, quitar=None):
    """URLs de tiempos por calle (con los pines de Geoprog: no hace falta esperar a places_search),
    solo para los pares de puntos que todavía no están en el caché del día"""
    B = construir(fec, voy, usar_lugares=False, gps=gps, quitar=quitar)
    cache = cargar_cache(fec)
    ids = ids_nodos(B, cache["nodo_de"], registrar=True)
    uniq = {}
    for i, pt in zip(ids, [B["start"]] + [(s["lat"], s["lng"]) for s in B["stops"]] + [PADOMI]):
        uniq.setdefault(i, pt)
    keys, t = list(uniq), cache["t"]
    falta = lambda a, b: a != b and f"{a}|{b}" not in t
    conocidos = {k.split("|")[0] for k in t}
    nuevos = [k for k in keys if k not in conocidos]   # puntos sin ningún tiempo guardado
    for a in keys:                                      # y los conocidos a los que les falta algún par
        if a not in nuevos and any(falta(a, b) or falta(b, a) for b in keys if b not in nuevos):
            nuevos.append(a)
    def url(ks):
        return (f"{OSRM}/table/v1/driving/polyline({quote(polyline([uniq[k] for k in ks]), safe='')})"
                "?annotations=duration")
    def en_orden(ks):                                     # vecino más cercano: deltas cortos = URL corta
        ks = list(ks)
        out = ks[:1]
        resto = ks[1:]
        while resto:
            nx = min(resto, key=lambda k: hav(uniq[out[-1]], uniq[k]))
            out.append(nx); resto.remove(nx)
        return out
    def partir(base, extra, margen=0):
        """grupos base+pedazo de 'extra' cuyas URLs entran; si base está vacío, todos contra todos"""
        orden, g = en_orden(extra), 1
        while True:
            tam = max(1, math.ceil(len(orden) / g))
            partes = [orden[k:k + tam] for k in range(0, len(orden), tam)]
            if base:
                grupos = [base + x for x in partes]
            else:
                grupos = [partes[0]] if len(partes) == 1 else [x + y for x, y in itertools.combinations(partes, 2)]
            if all(len(url(en_orden(x))) + margen <= MAX_URL for x in grupos) or tam == 1:
                return grupos
            g += 1
    consultas = []
    if nuevos:
        viejos = [k for k in keys if k not in nuevos]
        solo_nuevos = bool(viejos) and len(url(en_orden(nuevos))) <= MAX_URL * 0.6
        if solo_nuevos:
            grupos = partir(nuevos, viejos, 25)         # pocos nuevos: nuevos + un pedazo de los conocidos
        else:
            grupos = partir([], keys)                   # día nuevo o muchos nuevos: todos contra todos
        for k, x in enumerate(grupos, 1):
            x = en_orden(x)
            if not solo_nuevos:
                partes = [("", x, x)]                   # todos contra todos
            else:                                       # solo filas y columnas de los nuevos: respuesta chica
                ix = "%3B".join(str(x.index(q)) for q in x if q in nuevos)   # ';' sin codificar no llega a OSRM
                sel = [q for q in x if q in nuevos]
                partes = [(f"&sources={ix}", sel, x), (f"&destinations={ix}", x, sel)]
            for suf, (extra, fu, de) in zip("ab", partes):
                arch = f"osrm_{fec}_{k}{suf if len(partes) > 1 else ''}.json"
                if os.path.exists(arch):
                    os.remove(arch)                     # que no se use una respuesta vieja
                consultas.append({"archivo": arch, "url": url(x) + extra, "fuentes": fu, "destinos": de})
    guardar(f"tiempos_{fec}.json", cache)
    plan = {"fec": fec, "prompt": PROMPT_OSRM, "consultas": consultas}
    guardar(f"osrm_plan_{fec}.json", plan)
    return plan

def ingerir_tiempos(fec, cache, avisos):
    """pasa al caché las respuestas de WebFetch del último plan y borra esos archivos"""
    path = f"osrm_plan_{fec}.json"
    if not os.path.exists(path):
        return
    for c in leer(path).get("consultas", []):
        a = c["archivo"]
        if not os.path.exists(a):
            continue
        try:
            r = leer(a)
            mat, fu, de = r["durations"], c["fuentes"], c["destinos"]
            assert r.get("code", "Ok") == "Ok" and len(mat) == len(fu) and all(len(f) == len(de) for f in mat)
        except Exception as e:
            avisos.append(f"TIEMPOS POR CALLE: no pude usar {a} ({e.__class__.__name__}); esas paradas van por línea recta")
            continue
        for fila, ka in zip(mat, fu):
            for v, kb in zip(fila, de):
                if ka != kb and isinstance(v, (int, float)):
                    cache["t"][f"{ka}|{kb}"] = float(v)
        os.remove(a)
    guardar(f"tiempos_{fec}.json", cache)


# ---------------------------------------------------------------- orden de visita
def calcular(fec, voy, gps=None, quitar=None, anchas=()):
    anchas = AVENIDAS_ANCHAS + [sin_tildes(a.strip()) for a in anchas if a.strip()]
    B = construir(fec, voy, usar_lugares=True, gps=gps, quitar=quitar)
    S, avisos, inicio = B["stops"], B["avisos"], B["inicio"]
    n = len(S)
    if n == 0:
        return B, None
    pts = [B["start"]] + [(s["lat"], s["lng"]) for s in S] + [PADOMI]
    E, N = n + 1, n + 2
    D = [[hav(pts[i], pts[j]) for j in range(N)] for i in range(N)]
    def t_estimado(i, j):
        return D[i][j] * FACTOR_CALLES / VEL_LIBRE_KMH * 3600

    cache = cargar_cache(fec)
    ingerir_tiempos(fec, cache, avisos)
    ids, tc = ids_nodos(B, cache["nodo_de"]), cache["t"]
    T = [[0.0] * N for _ in range(N)]
    malos = hay = 0
    for i in range(N):
        for j in range(N):
            if i == j:
                continue
            est = t_estimado(i, j)
            v = tc.get(f"{ids[i]}|{ids[j]}") if ids[i] != ids[j] else None
            if v is not None and D[i][j] / 110 * 3600 * 0.9 <= v <= max(900, 6 * est):   # creíble
                T[i][j] = v
                hay += 1
            else:
                T[i][j] = est
                malos += ids[i] != ids[j]
    if not hay:
        avisos.append("TIEMPOS POR CALLE: no hay; el orden sale por línea recta")
    elif malos:
        avisos.append(f"TIEMPOS POR CALLE: {malos} de {N * (N - 1)} tiempos faltaban o no eran creíbles; ahí se usó línea recta")
    tiempos = "calles" if hay else "linea_recta"

    # a pie: a 150 m o menos y sin cruzar una avenida ancha, la unidad no se mueve y el especialista cruza
    # caminando. Así se atiende primero a los que están al frente o a la vuelta, aunque en carro haya que
    # dar la vuelta a la manzana por el sentido de las calles.
    vias = [inicio.get("nom_via")] + [s["pacientes"][0]["nom_via"] for s in S] + [None]
    pie, cerca_avenida = set(), set()
    desde = range(0, n + 1) if inicio["tipo"] in ("parada", "gps") else range(1, n + 1)
    for i in desde:
        for j in range(1, n + 1):
            if i == j or D[i][j] > A_PIE_KM:
                continue
            if pie_ok(vias[i], vias[j], anchas):
                pie.add((i, j))
                t_pie = D[i][j] * 1000 * FACTOR_PIE / VEL_PIE_MS / FACTOR_TRAFICO   # luego se multiplica x1.5
                T[i][j] = min(T[i][j], t_pie)
            else:
                cerca_avenida.add((i, j))

    # pequeños grupos: terminar un grupo antes de pasar al siguiente
    G = [{i} for i in range(1, n + 1)]
    while True:
        best = None
        for a, b in itertools.combinations(range(len(G)), 2):
            if len(G[a]) + len(G[b]) > MAX_GRUPO:
                continue
            dm = max(max(T[i][j], T[j][i]) for i in G[a] for j in G[b])
            if dm <= GRUPO_SEG and (best is None or dm < best[0]):
                best = (dm, a, b)
        if best is None:
            break
        _, a, b = best
        G[a] |= G[b]
        del G[b]
    gid = {i: k for k, grp in enumerate(G) for i in grp}
    gmask = [sum(1 << (i - 1) for i in grp) for grp in G]

    def costo(order):
        seq = [0] + order + [E]
        c = sum(T[a][b] for a, b in zip(seq, seq[1:]))
        vistos, prev = set(), None
        for i in order:
            if gid[i] != prev:
                if gid[i] in vistos:
                    c += PENAL_GRUPO
                vistos.add(gid[i]); prev = gid[i]
        return c

    if n <= 13:                                               # exacto
        INF = float("inf")
        full = (1 << n) - 1
        dp = [[INF] * n for _ in range(1 << n)]
        par = [[-1] * n for _ in range(1 << n)]
        for i in range(n):
            dp[1 << i][i] = T[0][i + 1]
        for mask in range(1, 1 << n):
            row = dp[mask]
            for j in range(n):
                c = row[j]
                if c == INF:
                    continue
                gj = gid[j + 1]
                sale = PENAL_GRUPO if (mask & gmask[gj]) != gmask[gj] else 0   # deja su grupo a medias
                for k in range(n):
                    if mask & (1 << k):
                        continue
                    nc = c + T[j + 1][k + 1] + (sale if gid[k + 1] != gj else 0)
                    nm = mask | (1 << k)
                    if nc < dp[nm][k]:
                        dp[nm][k] = nc
                        par[nm][k] = j
        last = min(range(n), key=lambda j: dp[full][j] + T[j + 1][E])
        order, mask, j = [], full, last
        while j != -1:
            order.append(j + 1)
            pj = par[mask][j]
            mask ^= 1 << j
            j = pj
        order.reverse()
    else:                                                     # aproximado: varios arranques + mejoras locales
        rnd = random.Random(7)
        order, mejor = None, None
        for it in range(40 if n <= 20 else 12):
            left, seq, cur = set(range(1, n + 1)), [], 0
            while left:
                cand = sorted(left, key=lambda k: T[cur][k])[:1 if it == 0 else 2]
                cur = rnd.choice(cand); seq.append(cur); left.remove(cur)
            c = costo(seq)
            mejoro = True
            while mejoro:
                mejoro = False
                for L in (1, 2, 3):                           # mover 1 a 3 paradas seguidas a otra posición
                    for i in range(len(seq) - L + 1):
                        seg, resto = seq[i:i + L], seq[:i] + seq[i + L:]
                        for j in range(len(resto) + 1):
                            for sg in (seg, seg[::-1]):
                                cand = resto[:j] + sg + resto[j:]
                                cc = costo(cand)
                                if cc < c - 1e-9:
                                    seq, c, mejoro = cand, cc, True
                for i in range(len(seq) - 1):                 # invertir un pedazo
                    for k in range(i + 1, len(seq)):
                        cand = seq[:i] + seq[i:k + 1][::-1] + seq[k + 1:]
                        cc = costo(cand)
                        if cc < c - 1e-9:
                            seq, c, mejoro = cand, cc, True
            if mejor is None or c < mejor:
                order, mejor = seq, c

    # sin tiempos por calle el circuito al revés cuesta igual: terminar en la parada más cercana a PADOMI
    if tiempos == "linea_recta" and inicio["tipo"] == "padomi" and D[order[-1]][E] > D[order[0]][E] \
            and abs(costo(order[::-1]) - costo(order)) < 1:
        order.reverse()

    n0 = voy if inicio["tipo"] == "parada" else 0
    paradas, prev_i, prev_num = [], 0, n0
    for num, idx in enumerate(order, n0 + 1):
        s = S[idx - 1]
        d = s["destino"] or {}
        pid = d.get("place_id") if str(d.get("place_id") or "").startswith("ChIJ") else None
        la, lo = round(s["lat"], 6), round(s["lng"], 6)
        nav = f"{NAV}&destination={la:.6f},{lo:.6f}"
        if pid:                                           # dirección exacta: Google entra por la calle de esa dirección
            nav += f"&destination_place_id={pid}"
        paradas.append({"n": num, "lat": round(s["lat"], 6), "lng": round(s["lng"], 6),
                        "km_desde_anterior": round(D[prev_i][idx], 2),
                        "min_desde_anterior": round(T[prev_i][idx] * FACTOR_TRAFICO / 60, 1),
                        "pacientes": s["pacientes"], "destino": s["destino"], "place_id": pid,
                        "gps": f"{la:.5f}, {lo:.5f}", "nav": nav,
                        # a pie desde la parada anterior (0 = desde donde estás): la unidad no se mueve
                        "a_pie_desde": prev_num if (prev_i, idx) in pie else None,
                        "a_pie_m": int(round(D[prev_i][idx] * 100)) * 10 if (prev_i, idx) in pie else None,
                        "cerca_avenida_desde": prev_num if (prev_i, idx) in cerca_avenida else None})
        prev_i, prev_num = idx, num
    num_de = {idx: n0 + k for k, idx in enumerate(order, 1)}
    grupos = sorted([sorted(num_de[i] for i in grp) for grp in G if len(grp) > 1])
    nav_retorno = (f"{NAV}&destination={PADOMI[0]:.6f},{PADOMI[1]:.6f}&destination_place_id={PADOMI_PID}"
                   f"&waypoints={ARENALES[0]:.6f},{ARENALES[1]:.6f}")

    seq_nodes = [0] + order + [E]
    n_par = len(paradas)
    tramos = []
    for k in range(1, max(1, math.ceil(n_par / PARADAS_POR_TRAMO)) + 1):
        stops_k = paradas[(k - 1) * PARADAS_POR_TRAMO: k * PARADAS_POR_TRAMO]
        legs = [j for j in range(1, n_par + 1) if (j - 1) // PARADAS_POR_TRAMO + 1 == k]
        if k * PARADAS_POR_TRAMO >= n_par:
            legs.append(n_par + 1)
        # en el enlace van solo las paradas a las que se mueve la unidad (las de a pie no)
        manejo_k = [p for p in stops_k if p.get("a_pie_desde") is None] or stops_k[-1:]
        c = [f"{p['lat']:.5f},{p['lng']:.5f}" for p in manejo_k]   # enlace corto: solo coordenadas, separador %7C
        enlace = f"{NAV}&destination={c[-1]}" + (("&waypoints=" + "%7C".join(c[:-1])) if len(c) > 1 else "")
        km = sum(D[seq_nodes[j - 1]][seq_nodes[j]] for j in legs) * FACTOR_CALLES
        manejo = sum(T[seq_nodes[j - 1]][seq_nodes[j]] for j in legs) * FACTOR_TRAFICO / 60
        npac = sum(len(p["pacientes"]) for p in stops_k)
        tramos.append({"tramo": k, "paradas": [p["n"] for p in stops_k], "pacientes": npac, "enlace": enlace,
                       "km_calles_est": round(km, 1), "manejo_min": int(round(manejo)),
                       "atencion_min": npac * MIN_POR_PACIENTE,
                       "total_min": int(round(manejo)) + npac * MIN_POR_PACIENTE})
    ruta = {
        "fec": fec, "inicio": inicio, "visitadas": B["visitadas"], "paradas": paradas,
        "penultima_parada": paradas[-2]["n"] if len(paradas) >= 2 else None,
        "km_linea_recta_total": round(sum(D[a][b] for a, b in zip(seq_nodes, seq_nodes[1:])), 1),
        "nav_retorno": nav_retorno, "tiempos": tiempos, "grupos": grupos, "tramos": tramos,
        "total_min": sum(r5(t["manejo_min"]) + t["atencion_min"] for t in tramos),
        "paradas_ajustadas_a_direccion": [{"n": p["n"], "direccion": p["destino"]["direccion"],
                                           "ajuste_m": p["destino"]["ajuste_m"]} for p in paradas if p.get("destino")],
        "nuevos": [x["paciente"] for p in paradas for x in p["pacientes"] if x.get("nuevo")],
        "avisos": avisos,
    }
    return B, ruta


# ---------------------------------------------------------------- salidas
def lista_md(ruta, ahora):
    P, pen = ruta["paradas"], ruta["penultima_parada"]
    L = []
    for p in P:
        pcs = p["pacientes"]
        dl = dir_larga(base_pac(p))
        ref = titulo(moda([x["ref_dom"] for x in pcs]))
        nuevo = lambda x: "🆕 " if x.get("nuevo") else ""
        if len(pcs) == 1:
            x = pcs[0]
            tel = " / ".join(telefonos(x["telfs"])) or "sin teléfono"
            L.append(f"**{p['n']}. {dl}**")
            L.append(f"{nuevo(x)}{titulo(x['paciente'])} ({x['edad']}) · {ref} · ☎ {tel}")
        else:
            cnt = Counter(t for x in pcs for t in set(telefonos(x["telfs"])))
            comunes = [t for t, c in cnt.most_common() if c >= max(2, len(pcs) / 2)]
            extras = []
            for x in pcs:
                otros = [t for t in telefonos(x["telfs"]) if t not in comunes]
                if otros:
                    extras.append(f"{primer_apellido(x['paciente'])}: {' / '.join(otros)}")
            tel = " / ".join(comunes) + (f" ({' · '.join(extras)})" if extras else "")
            L.append(f"**{p['n']}. {dl} ({len(pcs)} pacientes)**")
            L.append(f"{ref} · ☎ {tel.strip()}")
            L.append("Pacientes: " + ", ".join(f"{nuevo(x)}{titulo(x['paciente'])} ({x['edad']})" for x in pcs))
        k = p.get("a_pie_desde")
        if k is not None:
            de = f"la {k}" if k else "donde estás"
            L.append(f"🚶 **A pie desde {de}** (~{p['a_pie_m']} m), sin mover la unidad.")
        elif p.get("cerca_avenida_desde") is not None:
            L.append(f"🚗 Cerca de la {p['cerca_avenida_desde']}, pero cruzando una avenida ancha: mueve la unidad.")
        L.append(f"[🧭 Ir]({p['nav']}) · GPS `{p['gps']}`")
        if p["n"] == pen:
            L.append("⛽ Aquí te pregunto por el combustible.")
        L.append("")
    # tramos y tiempos
    L.append("**Tramos**")
    for t in ruta["tramos"]:
        ps = t["paradas"]
        rango = f"paradas {ps[0]} a {ps[-1]}" if len(ps) > 1 else f"parada {ps[0]}"
        man = r5(t["manejo_min"])
        L.append(f"[🗺️ Tramo {t['tramo']}: {rango}]({t['enlace']}) · manejo ~{fmt(man)} + atención "
                 f"{fmt(t['atencion_min'])} ({t['pacientes']} pac.) = {fmt(man + t['atencion_min'])}")
    total = ruta["total_min"]
    llegada = (ahora + datetime.timedelta(minutes=total)).strftime("%H:%M")
    if ruta["inicio"]["tipo"] != "padomi":
        L.append(f"**Tiempo restante: {fmt(total)}** · llegada a PADOMI hacia las {llegada}")
    else:
        L.append(f"**Tiempo total estimado: {fmt(total)}** · si sales ahora ({ahora.strftime('%H:%M')}), llegas a PADOMI hacia las {llegada}")
    L.append(f"Regreso a PADOMI por Arenales: [🧭 Ir]({ruta['nav_retorno']})")
    L.append("")
    # notas de acceso
    N = []
    pares_pie = [[p["a_pie_desde"], p["n"]] for p in P if p.get("a_pie_desde") is not None]
    grupos = [g for g in ruta["grupos"] if g not in pares_pie]
    if grupos:
        N.append("Pequeños grupos que se hacen seguidos: " + "; ".join(" y ".join(map(str, g)) for g in grupos) + ".")
    a_pie = [f"{a or 'donde estás'} → {b}" for a, b in pares_pie]
    if a_pie:
        N.append("A pie, sin mover la unidad (el especialista cruza): " + "; ".join(a_pie)
                 + ". El 🗺️ del tramo no pasa por esas paradas.")
    llamar = [str(p["n"]) for p in P if any(es_mz_lt(x) for x in p["pacientes"])]
    if llamar:
        N.append("Llama antes de llegar (dirección con Mz/Lt o asociación): " + ", ".join(llamar) + ".")
    casas = [str(p["n"]) for p in P if any(es_casa_reposo(x) for x in p["pacientes"])]
    if casas:
        N.append("Casa de reposo o asilo, avisa antes de llegar: " + ", ".join(casas) + ".")
    for a in ruta["avisos"]:
        N.append(a)
    if ruta["tiempos"] != "calles":
        N.append("Orden sin tiempos por calle (línea recta).")
    if N:
        L.append("**Notas de acceso**")
        L += [f"- {x}" for x in N]
    return "\n".join(L).strip() + "\n"

def mapa_json(ruta):
    locs = []
    ini = ruta["inicio"]
    if ini["tipo"] in ("parada", "gps"):
        locs.append({"name": f"Estás aquí (paciente {ini['n']})" if ini["tipo"] == "parada" else "Estás aquí", "latitude": ini["lat"], "longitude": ini["lng"]})
    else:
        locs.append({"name": "PADOMI (salida)", "latitude": PADOMI[0], "longitude": PADOMI[1],
                     "place_id": PADOMI_PID, "notes": "Av. Arenales 1302, Jesús María"})
    for p in ruta["paradas"]:
        x = base_pac(p)
        k = len(p["pacientes"])
        loc = {"name": f"{p['n']} · {dir_corta(x, 60)}" + (f" ({k} pac.)" if k > 1 else ""),
               "latitude": p["lat"], "longitude": p["lng"], "notes": titulo(moda([y["ref_dom"] for y in p["pacientes"]]))}
        if p.get("place_id"):
            loc["place_id"] = p["place_id"]
        if p.get("a_pie_desde") is not None:
            loc["notes"] += f" · a pie desde la {p['a_pie_desde']}" if p["a_pie_desde"] else " · a pie desde donde estás"
        if p["n"] == ruta["penultima_parada"]:
            loc["notes"] += " · combustible"
        locs.append(loc)
    locs.append({"name": "Retorno por Av. Arenales", "latitude": ARENALES[0], "longitude": ARENALES[1],
                 "notes": "Punto de paso, cdra 5"})
    locs.append({"name": "PADOMI (llegada)", "latitude": PADOMI[0], "longitude": PADOMI[1],
                 "place_id": PADOMI_PID, "notes": "Av. Arenales cdra 13"})
    dias = [{"day_number": 1, "title": " → ".join(distritos_ruta(ruta, 4)), "locations": locs}]
    V = ruta.get("visitadas", [])
    if V:   # en plena ruta: día 1 = ya atendidos (tachados), día 2 = lo que falta
        tachar = lambda t: "".join(c + "\u0336" for c in t)
        hechos = [{"name": "PADOMI (salida)", "latitude": PADOMI[0], "longitude": PADOMI[1]}] + \
                 [{"name": "✓ " + tachar(f"{p['n']} · {dir_corta(base_pac(p))}"), "latitude": p["lat"],
                   "longitude": p["lng"], "notes": "Ya atendido"} for p in V]
        dias = [{"day_number": 1, "title": f"Ya visitados (1 a {V[-1]['n']})", "locations": hechos},
                {"day_number": 2, "title": f"Lo que falta: {ruta['paradas'][0]['n']} a {ruta['paradas'][-1]['n']} y retorno",
                 "locations": locs}]
    return {"title": f"Ruta PADOMI · {dia_corto(ruta['fec'])}", "travel_mode": "driving", "days": dias}

def distritos_ruta(ruta, k):
    out = []
    for p in ruta["paradas"]:
        d = distrito(p["pacientes"][0]["nom_dst"])
        if d not in out:
            out.append(d)
    return out[:k]

def etiquetas_json(ruta, especialista, ahora):
    P = ruta["paradas"]
    npac = sum(len(p["pacientes"]) for p in P)
    tit = f"Ruta PADOMI · {dia_corto(ruta['fec'])} · {', '.join(distritos_ruta(ruta, 3))}"
    if ruta["inicio"]["tipo"] == "parada":
        hechos = sum(len(p["pacientes"]) for p in ruta.get("visitadas", []))
        sub = (f"Act. {ahora.strftime('%H:%M')} · vas en el {ruta['inicio']['n']} · {hechos} atendidos, {npac} por atender"
               + (f" · con {especialista}" if especialista else ""))
    elif ruta["inicio"]["tipo"] == "gps":
        sub = f"Actualizada {ahora.strftime('%H:%M')} · desde tu ubicación · {len(P)} paradas pendientes"
    else:
        sub = f"{len(P)} paradas · {npac} pacientes" + (f" · con {especialista}" if especialista else "")
    # zonas: nombre del distrito al sur de sus paradas, solo si tiene 2 o más paradas juntas
    lats, lngs = [p["lat"] for p in P], [p["lng"] for p in P]
    span = max(max(lats) - min(lats), (max(lngs) - min(lngs)) * 0.98, 0.01)
    zonas, porD = [], {}
    for p in P:
        porD.setdefault(distrito(p["pacientes"][0]["nom_dst"]), []).append(p)
    for d, ps in porD.items():
        cy = sum(p["lat"] for p in ps) / len(ps); cx = sum(p["lng"] for p in ps) / len(ps)
        if len(ps) >= 2 and max(hav((cy, cx), (p["lat"], p["lng"])) for p in ps) <= 0.15 * span * 111:
            zonas.append([d.upper(), round(cy - max(0.003, 0.06 * span), 5), round(cx, 5)])
    return {"titulo": tit, "subtitulo": sub,
            "direcciones": [dir_corta(base_pac(p)) for p in P],
            # paradas ya atendidas: el gráfico las muestra en gris y tachadas
            "direcciones_visitadas": [dir_corta(base_pac(p)) for p in ruta.get("visitadas", [])],
            "zonas": zonas[:4]}


# ---------------------------------------------------------------- comandos
def gps_arg(t):
    if not t:
        return None
    la, lo = (float(x) for x in t.replace(" ", "").split(","))
    return (la, lo)

def cmd_preparar(a):
    txt = sys.stdin.read() if a.archivo == "-" else open(a.archivo, encoding="utf-8-sig").read()
    try:
        data = json.loads(txt[txt.index("{"):txt.rindex("}") + 1])
    except ValueError as e:
        sys.exit(f"No encontré el texto RUTA PADOMI {{...}} en {a.archivo} ({e})")
    rows = data["rows"] if isinstance(data, dict) else data
    if not isinstance(data, dict):
        data = {"fec": a.fec, "prof": "", "rows": rows}
    fec = str(data.get("fec") or a.fec or "").strip()
    if not re.fullmatch(r"\d{8}", fec):
        sys.exit("El texto no trae la fecha (fec). Pásala con --fec AAAAMMDD")
    path = f"citas_{fec}.json"
    canon = lambda rs: sorted(json.dumps(r, sort_keys=True, ensure_ascii=False) for r in rs)
    igual, cambios = False, None
    if os.path.exists(path):
        prev_rows = leer(path)["rows"]
        igual = canon(prev_rows) == canon(rows)
        if not igual:
            pc, nc = {r.get("cod_pac") for r in prev_rows}, {r.get("cod_pac") for r in rows}
            cambios = {"nuevos": [titulo(r.get("paciente", "")) for r in rows if r.get("cod_pac") not in pc],
                       "ya_no_figuran": [titulo(r.get("paciente", "")) for r in prev_rows if r.get("cod_pac") not in nc]}
    if not igual:
        guardar(path, data)
    hay_ruta = os.path.exists(f"ruta_{fec}.json")
    prof = html.unescape(str(data.get("prof", ""))).replace("¥", "Ñ").strip()
    m = re.search(r"TECNICO\s+APOYO\s+0*(\d+)", sin_tildes(prof))
    ahora = hora_lima()
    # direcciones a ubicar: una consulta por dirección; con lugares ya guardados, solo las que faltan
    lugares = cargar_lugares(fec)
    ya = f"consultadas_{fec}.json"
    previas = set(leer(ya)) if os.path.exists(ya) else set()
    consultas, vistas = [], set(previas)
    for r in rows:
        q = consulta(str(r.get("nom_via", "")), str(r.get("nom_dst", "")))
        if not q or clave_consulta(q) in vistas:
            continue
        vistas.add(clave_consulta(q))
        try:
            lat, lng = float(r["coordy"]), float(r["coordx"])
        except (KeyError, TypeError, ValueError):
            continue
        if lugares and lugar_para(html.unescape(str(r.get("nom_via", ""))), lat, lng, lugares):
            continue
        consultas.append(q)
    guardar(ya, sorted(previas | {clave_consulta(q) for q in consultas}))   # no volver a buscarlas
    out = {"fec": fec, "dia": dia_corto(fec), "prof": prof,
           "tecnico_apoyo": f"{int(m.group(1)):02d}" if m else None,
           "pacientes": len(rows), "hoy": ahora.strftime("%Y%m%d"), "hora_lima": ahora.strftime("%H:%M"),
           "fecha_distinta_a_hoy": fec != ahora.strftime("%Y%m%d"), "despues_de_6pm": ahora.hour >= 18,
           "igual_a_la_anterior": igual, "cambios": cambios, "ya_hay_ruta_de_ese_dia": hay_ruta,
           "places_search": consultas}
    if not hay_ruta:
        plan = hacer_plan(fec, None)
        out["webfetch"] = {"prompt": plan["prompt"],
                           "consultas": [{"url": c["url"], "guardar_en": c["archivo"]} for c in plan["consultas"]]}
    print(json.dumps(out, ensure_ascii=False, indent=1))

def cmd_plan(a):
    fec = a.fec
    if a.voy is not None:
        if not os.path.exists(f"ruta_{fec}.json"):
            sys.exit(f"No hay ruta_{fec}.json para recalcular desde el paciente {a.voy}")
        shutil.copyfile(f"ruta_{fec}.json", f"ruta_{fec}_previa.json")
    plan = hacer_plan(fec, a.voy, gps_arg(a.gps), a.quitar)
    if not plan["consultas"]:
        print(json.dumps({"consultas": [], "nota": "Los tiempos por calle ya están guardados: corre 'ruta' directo, sin WebFetch."},
                         ensure_ascii=False))
        return
    print(json.dumps({"prompt": plan["prompt"],
                      "consultas": [{"url": c["url"], "guardar_en": c["archivo"]} for c in plan["consultas"]]},
                     ensure_ascii=False, indent=1))

def cmd_ruta(a):
    fec = a.fec
    B, ruta = calcular(fec, a.voy, gps_arg(a.gps), a.quitar, (a.ancha or "").split(","))
    if ruta is None:
        print(json.dumps({"paradas": 0, "avisos": B["avisos"] or ["Sin pacientes pendientes"]}, ensure_ascii=False))
        return
    ahora = hora_lima()
    ruta["prof"] = B["data"].get("prof", "") if isinstance(B["data"], dict) else ""
    ruta["especialista"] = a.especialista
    guardar(f"ruta_{fec}.json", ruta)
    with open(f"lista_{fec}.md", "w", encoding="utf-8") as f:
        f.write(lista_md(ruta, ahora))
    guardar(f"mapa_{fec}.json", mapa_json(ruta))
    guardar(f"etiquetas_{fec}.json", etiquetas_json(ruta, a.especialista, ahora))
    png = f"ruta_padomi_{fec[6:8]}{fec[4:6]}" + (f"_desde{a.voy}" if a.voy else ("_aqui" if a.gps else "")) + ".png"
    graf = os.path.join(AQUI, "grafico_ruta.py")
    revisar = False
    if a.sin_grafico:
        g = "omitido"
    else:
        r = subprocess.run([sys.executable, graf, f"ruta_{fec}.json", f"etiquetas_{fec}.json", png],
                           capture_output=True, text=True)
        g = png if r.returncode == 0 else f"ERROR: {(r.stderr or r.stdout).strip()[-300:]}"
        revisar = next((x[8:] for x in r.stdout.splitlines() if x.startswith("REVISAR")), False) or r.returncode != 0
    P = ruta["paradas"]
    print(json.dumps({
        "paradas": len(P), "pacientes": sum(len(p["pacientes"]) for p in P),
        "penultima_parada": ruta["penultima_parada"], "tiempos": ruta["tiempos"], "grupos": ruta["grupos"],
        "total_min": ruta["total_min"], "nuevos": ruta["nuevos"], "avisos": ruta["avisos"],
        "grafico": g, "revisar_grafico": revisar, "etiquetas": f"etiquetas_{fec}.json",
    }, ensure_ascii=False, indent=1))
    # primero lo urgente: a dónde ir ahora (se manda apenas sale, antes de la lista, el mapa y el gráfico)
    p = P[0]
    gente = ", ".join(f"{titulo(y['paciente'])} ({y['edad']})" for y in p["pacientes"])
    tels = " / ".join(dict.fromkeys(t for y in p["pacientes"] for t in telefonos(y["telfs"]))) or "sin teléfono"
    ref = titulo(moda([y["ref_dom"] for y in p["pacientes"]]))
    cab = "Ve a la" if ruta["inicio"]["tipo"] == "padomi" else "Siguiente:"
    print("\n===== PRIMER MENSAJE (mándalo ya) =====")
    print(f"**{cab} {p['n']}. {dir_larga(base_pac(p))}**\n{gente} · {ref} · ☎ {tels}\n[🧭 Ir]({p['nav']})")
    # todo lo que va al chat, para no tener que abrir más archivos
    print("\n===== LISTA PARA EL CHAT (lista_%s.md) =====" % fec)
    print(open(f"lista_{fec}.md", encoding="utf-8").read())
    print("===== MAPA: argumentos para places_map_display_v0 (mapa_%s.json) =====" % fec)
    print(json.dumps(mapa_json(ruta), ensure_ascii=False))

ap = argparse.ArgumentParser(description="Ruta PADOMI v3")
sub = ap.add_subparsers(dest="cmd", required=True)
p1 = sub.add_parser("preparar"); p1.add_argument("archivo"); p1.add_argument("--fec")
p2 = sub.add_parser("plan"); p3 = sub.add_parser("ruta")
for p_ in (p2, p3):
    p_.add_argument("fec"); p_.add_argument("--voy", type=int)
    p_.add_argument("--gps", help="--gps=LAT,LNG (con =, porque empieza con signo menos): donde está el usuario")
    p_.add_argument("--quitar", help="apellidos o códigos de pacientes ya atendidos, separados por comas")
p3.add_argument("--especialista"); p3.add_argument("--sin-grafico", action="store_true")
p3.add_argument("--ancha", help="calles que el usuario dice que son anchas o peligrosas de cruzar a pie, separadas por comas")
A = ap.parse_args()
{"preparar": cmd_preparar, "plan": cmd_plan, "ruta": cmd_ruta}[A.cmd](A)
