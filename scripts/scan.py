#!/usr/bin/env python3
"""Buscador Wyckoff (scan diario). Lee data/<SIMBOLO>/ y escribe data/scan.json

Criterios (version inicial, estandar; se ajustan con las indicaciones del usuario):
 1. Tendencia mayor: alcista en mensual y semanal (estructura de maximos y minimos del zigzag).
 2. Rango de trading en diario: tramo lateral de 30 a 150 velas con al menos 2 toques arriba y 2 abajo.
 3. Eventos: SC, AR, ST, Spring, Test, SOS, LPS; y de distribucion para descartar: UT, SOW, LPSY.
 4. Fibonacci: precio en el retroceso 38,2-61,8 % del ultimo tramo alcista semanal.
 5. Soportes y resistencias por repeticion de toques (los mismos que dibuja el graficador) y avisos de llegada.
 6. Puntuacion y lista de candidatas con el motivo de cada aviso.

Herramienta de apoyo a la decision: no ejecuta ordenes ni es asesoramiento financiero.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CONFIG = ROOT / "config" / "tickers.json"


# ------------------------------------------------------------------ datos
def fm(x, d=2):
    """Numero con coma decimal."""
    return f"{x:.{d}f}".replace(".", ",")


def cargar(sym, tf):
    f = DATA / sym / f"{tf}.json"
    if not f.exists():
        return None
    B = json.loads(f.read_text())["barras"]
    return {"t": [x[0] for x in B], "o": [x[1] for x in B], "h": [x[2] for x in B],
            "l": [x[3] for x in B], "c": [x[4] for x in B], "v": [x[5] for x in B], "n": len(B)}


# --------------------------------------------- calculos comunes con el graficador
def atr(b, n=14):
    out, prev, suma = [], None, 0.0
    for i in range(b["n"]):
        tr = b["h"][i] - b["l"][i] if i == 0 else max(
            b["h"][i] - b["l"][i], abs(b["h"][i] - b["c"][i - 1]), abs(b["l"][i] - b["c"][i - 1]))
        if i < n:
            suma += tr
            prev = suma / (i + 1)
        else:
            prev = (prev * (n - 1) + tr) / n
        out.append(prev)
    return out


def zigzag(b, mult, a=None):
    if b["n"] < 3:
        return []
    a = a or atr(b)
    h, l = b["h"], b["l"]
    piv, d, ext, imax, imin = [], 0, 0, 0, 0
    for i in range(1, b["n"]):
        th = mult * a[i]
        if d == 0:
            if h[i] > h[imax]:
                imax = i
            if l[i] < l[imin]:
                imin = i
            if h[i] - l[imin] >= th and imin < i:
                piv.append({"i": imin, "p": l[imin], "t": "L"}); d, ext = 1, i
            elif h[imax] - l[i] >= th and imax < i:
                piv.append({"i": imax, "p": h[imax], "t": "H"}); d, ext = -1, i
        elif d == 1:
            if h[i] >= h[ext]:
                ext = i
            elif h[ext] - l[i] >= th:
                piv.append({"i": ext, "p": h[ext], "t": "H"}); d, ext = -1, i
        else:
            if l[i] <= l[ext]:
                ext = i
            elif h[i] - l[ext] >= th:
                piv.append({"i": ext, "p": l[ext], "t": "L"}); d, ext = 1, i
    if d != 0:
        piv.append({"i": ext, "p": h[ext] if d == 1 else l[ext], "t": "H" if d == 1 else "L", "prov": True})
    return piv


def tendencia(b):
    if not b or b["n"] < 10:
        return None
    a = atr(b)
    for mult in (5, 3, 2):
        piv = zigzag(b, mult, a)
        H = [p for p in piv if p["t"] == "H"]
        L = [p for p in piv if p["t"] == "L"]
        if len(H) >= 2 and len(L) >= 2:
            hh, hl = H[-1]["p"] > H[-2]["p"], L[-1]["p"] > L[-2]["p"]
            return "alcista" if hh and hl else ("bajista" if not hh and not hl else "rango")
    return None


def giros(b, ini, fin, k=4):
    """Maximos y minimos locales (extremo de +-k velas) entre ini y fin."""
    h, l, n, out = b["h"], b["l"], b["n"], []
    for i in range(max(ini, k), min(fin, n - 2)):
        esh = esl = True
        for j in range(i - k, min(n - 1, i + k) + 1):
            if j == i:
                continue
            if (h[j] >= h[i]) if j < i else (h[j] > h[i]):
                esh = False
            if (l[j] <= l[i]) if j < i else (l[j] < l[i]):
                esl = False
        if esh:
            out.append({"p": h[i], "i": i, "t": "H"})
        if esl:
            out.append({"p": l[i], "i": i, "t": "L"})
    return out


def niveles_auto(b, a):
    n = b["n"]
    if n < 30:
        return []
    tol = 1.2 * a[-1]
    pts = sorted(giros(b, n - 300, n), key=lambda q: q["p"])
    grupos, g = [], []
    for q in pts:
        if g and q["p"] - g[0]["p"] > tol:
            grupos.append(g); g = []
        g.append(q)
    if g:
        grupos.append(g)
    cierre, out = b["c"][-1], []
    for x in grupos:
        if len(x) < 2:
            continue
        nh = sum(1 for q in x if q["t"] == "H"); nl = len(x) - nh
        p = x[-1]["p"] if nh >= 0.7 * len(x) else (x[0]["p"] if nl >= 0.7 * len(x) else x[len(x) // 2]["p"])
        ult = max(q["i"] for q in x)
        out.append({"p": round(p, 2), "n": len(x), "sop": p <= cierre, "peso": len(x) + (0.5 if n - ult < 60 else 0)})
    out.sort(key=lambda z: -z["peso"])
    fin = []
    for z in out:
        if not any(abs(y["p"] - z["p"]) < tol * 0.6 for y in fin):
            fin.append(z)
    return sorted(fin[:8], key=lambda z: -z["p"])


# ---------------------------------------------------------------- Wyckoff
def media_vol(b, i, n=50):
    v = b["v"][max(0, i - n):i]
    return sum(v) / len(v) if v else 0


def buscar_rango(b, a):
    """Tramo lateral mas largo (30-150 velas) que termina hoy. Los ultimos 5 dias no definen los bordes."""
    n, h, l, c = b["n"], b["h"], b["l"], b["c"]
    for L in range(150, 29, -5):
        s, e = n - L, n - 5
        if s < 60:
            continue
        sup, inf = max(h[s:e]), min(l[s:e])
        alto, medio = sup - inf, (sup + inf) / 2
        if alto <= 0 or alto / medio > 0.25:
            continue
        m = (s + e) // 2
        c1, c2 = sum(c[s:m]) / (m - s), sum(c[m:e]) / (e - m)
        if abs(c1 - c2) > 0.3 * alto:
            continue
        G = giros(b, s, e, 3)
        arriba = sum(1 for q in G if q["t"] == "H" and q["p"] >= sup - 0.25 * alto)
        abajo = sum(1 for q in G if q["t"] == "L" and q["p"] <= inf + 0.25 * alto)
        if arriba < 2 or abajo < 2:
            continue
        antes_h, antes_l = max(h[s - 60:s]), min(l[s - 60:s])
        origen = "caida" if antes_h > sup + 0.5 * alto else ("subida" if antes_l < inf - 0.5 * alto else "lateral")
        return {"s": s, "sup": sup, "inf": inf, "alto": alto, "origen": origen, "dias": L}
    return None


def eventos_wyckoff(b, a, r):
    n, h, l, c, v, t = b["n"], b["h"], b["l"], b["c"], b["v"], b["t"]
    s, A, ev = r["s"], a[-1], {}

    def pon(tipo, i, precio, nota=""):
        ev[tipo] = {"tipo": tipo, "i": i, "fecha": t[i], "precio": round(precio, 2), "nota": nota, "hace": n - 1 - i}

    # --- acumulacion: climax de ventas, reaccion automatica y test secundario
    if r["origen"] == "caida":
        z0, z1 = max(0, s - 10), s + max(10, r["dias"] // 3)
        i = min(range(z0, z1), key=lambda k: l[k])
        vmax = max(v[max(0, i - 2):i + 3]); vm = media_vol(b, i)
        if vm and vmax >= 1.5 * vm:
            pon("SC", i, l[i], f"volumen {fm(vmax / vm, 1)}x la media")
            j = max(range(i + 1, min(n, i + 21)), key=lambda k: h[k]) if i + 1 < n else None
            if j:
                pon("AR", j, h[j])
                for k in range(j + 3, n - 1):
                    if l[k] <= l[i] + 0.25 * (h[j] - l[i]) and l[k] == min(l[k - 3:k + 4]) and v[k] < 0.8 * vmax:
                        pon("ST", k, l[k], "menor volumen que el climax"); break

    # --- spring: perfora el soporte del rango y vuelve dentro en 3 velas o menos
    for i in range(n - 1, max(s + 10, n - 26), -1):
        sop = min(l[s:i])
        if l[i] < sop - 0.1 * A and any(c[m] > sop for m in range(i, min(i + 4, n))) and min(c[i:]) >= l[i]:
            vm = media_vol(b, i)
            pon("Spring", i, l[i], f"volumen {fm(v[i] / vm, 1)}x la media" if vm else "")
            for k in range(n - 1, i + 2, -1):       # test: vuelve a la zona sin perforar y con menos volumen
                if l[i] < l[k] <= sop + 0.5 * A and v[k] < v[i] and l[k] <= min(l[max(i + 1, k - 2):k + 3]):
                    pon("Test", k, l[k], "menos volumen que el spring"); break
            break

    # --- senal de fortaleza: cierre por encima del rango con vela amplia y volumen
    for i in range(max(s + 10, n - 20), n):
        res = max(h[s:i]); vm = media_vol(b, i)
        if c[i] > res and (h[i] - l[i]) >= 1.2 * a[i] and vm and v[i] >= 1.3 * vm and c[-1] > res - 0.5 * A:
            pon("SOS", i, c[i], f"rompe {fm(res)} con volumen {fm(v[i] / vm, 1)}x")
            for k in range(n - 1, i + 1, -1):       # ultimo punto de apoyo: vuelta a la zona rota con poco volumen
                vk = media_vol(b, k)
                if l[k] <= res + 0.6 * A and c[k] >= res - 0.5 * A and vk and v[k] < vk:
                    pon("LPS", k, l[k], "apoyo sobre la resistencia rota, volumen bajo"); break
            break

    # --- distribucion (para descartar)
    for i in range(n - 1, max(s + 10, n - 26), -1):
        res = max(h[s:i])
        if h[i] > res + 0.1 * A and any(c[m] < res for m in range(i, min(i + 4, n))) and max(c[i:]) <= h[i] and c[-1] < res:
            pon("UT", i, h[i], f"supera {fm(res)} y vuelve dentro"); break
    for i in range(max(s + 10, n - 20), n):
        sop = min(l[s:i]); vm = media_vol(b, i)
        if c[i] < sop and (h[i] - l[i]) >= 1.2 * a[i] and vm and v[i] >= 1.3 * vm and c[-1] < sop:
            pon("SOW", i, c[i], f"pierde {fm(sop)} con volumen {fm(v[i] / vm, 1)}x")
            for k in range(n - 1, i + 1, -1):
                vk = media_vol(b, k)
                if h[k] >= sop - 0.6 * A and c[k] < sop and vk and v[k] < vk:
                    pon("LPSY", k, h[k], "rebote debil hasta el soporte perdido"); break
            break
    # una rotura que vuelve dentro del rango es upthrust, no senal de fortaleza
    if "UT" in ev and "SOS" in ev and ev["UT"]["i"] >= ev["SOS"]["i"]:
        ev.pop("SOS"); ev.pop("LPS", None)
    return ev


def fibo_semanal(w, cierre):
    """Ultimo tramo alcista del semanal y retroceso actual."""
    if not w or w["n"] < 30:
        return None
    piv = zigzag(w, 3)
    for k in range(len(piv) - 1, 0, -1):
        if piv[k]["t"] == "H" and piv[k - 1]["t"] == "L":
            A, B = piv[k - 1], piv[k]
            if B["p"] <= A["p"]:
                return None
            return {"a": round(A["p"], 2), "fa": w["t"][A["i"]], "b": round(B["p"], 2), "fb": w["t"][B["i"]],
                    "retr": round((B["p"] - cierre) / (B["p"] - A["p"]) * 100, 1)}
    return None


def avisos_niveles(b, a, niveles):
    c, h, l, A, out = b["c"], b["h"], b["l"], a[-1], []
    for z in niveles:
        p, n = z["p"], z["n"]
        if c[-2] < p and c[-1] > p + 0.4 * A:
            out.append({"tipo": "rompe_resistencia", "p": p, "n": n, "txt": f"Rompe la resistencia {fm(p)} (×{n})"})
        elif c[-2] > p and c[-1] < p - 0.4 * A:
            out.append({"tipo": "pierde_soporte", "p": p, "n": n, "txt": f"Pierde el soporte {fm(p)} (×{n})"})
        elif z["sop"] and l[-1] <= p + 0.4 * A and c[-1] >= p - 0.4 * A:
            out.append({"tipo": "en_soporte", "p": p, "n": n, "txt": f"Llega al soporte {fm(p)} (×{n})"})
        elif not z["sop"] and h[-1] >= p - 0.4 * A and c[-1] <= p + 0.4 * A:
            out.append({"tipo": "en_resistencia", "p": p, "n": n, "txt": f"Llega a la resistencia {fm(p)} (×{n})"})
    return out


PUNTOS = {"SC": 1, "AR": 0, "ST": 1, "Spring": 3, "Test": 2, "SOS": 3, "LPS": 2, "UT": -3, "SOW": -4, "LPSY": -3}
NOMBRE = {"SC": "Clímax de ventas (SC)", "AR": "Reacción automática (AR)", "ST": "Test secundario (ST)",
          "Spring": "Spring", "Test": "Test del spring", "SOS": "Señal de fortaleza (SOS)",
          "LPS": "Último punto de apoyo (LPS)", "UT": "Upthrust (UT)", "SOW": "Señal de debilidad (SOW)",
          "LPSY": "Último punto de oferta (LPSY)"}


def analizar(info):
    sym = info["symbol"]
    d, w, m = cargar(sym, "1d"), cargar(sym, "1wk"), cargar(sym, "1mo")
    if not d or d["n"] < 260:
        return None
    a = atr(d)
    cierre = d["c"][-1]
    r = {"symbol": sym, "nombre": info.get("nombre", ""), "mercado": info.get("mercado", ""),
         "fecha": d["t"][-1], "cierre": round(cierre, 2), "var": round((cierre / d["c"][-2] - 1) * 100, 2),
         "tendM": tendencia(m), "tendS": tendencia(w), "tendD": tendencia(d)}
    puntos, motivos = 0, []
    mayor = r["tendM"] == "alcista" and r["tendS"] == "alcista"
    if mayor:
        puntos += 3; motivos.append("Tendencia mayor alcista (mensual y semanal)")

    fib = fibo_semanal(w, cierre)
    en_fib = bool(fib and 38.2 <= fib["retr"] <= 61.8)
    if fib:
        r["fib"] = fib
        if en_fib:
            puntos += 2
            motivos.append(f"Retroceso del {fm(fib['retr'], 0)} % del tramo semanal {fm(fib['a'])} → {fm(fib['b'])} (zona 38,2-61,8 %)")

    niveles = niveles_auto(d, a)
    r["niveles"] = [{"p": z["p"], "n": z["n"], "sop": z["sop"]} for z in niveles]
    r["avisos"] = avisos_niveles(d, a, niveles)
    en_sop = any(x["tipo"] == "en_soporte" for x in r["avisos"])
    if en_sop:
        puntos += 1

    rango, ev = buscar_rango(d, a), {}
    if rango:
        puntos += 1
        r["rango"] = {"ini": d["t"][rango["s"]], "sup": round(rango["sup"], 2), "inf": round(rango["inf"], 2),
                      "dias": rango["dias"], "origen": rango["origen"]}
        de = {"caida": "tras una caída", "subida": "tras una subida", "lateral": ""}[rango["origen"]]
        motivos.append(f"Rango de {rango['dias']} sesiones entre {fm(rango['inf'])} y {fm(rango['sup'])} {de}".strip())
        ev = eventos_wyckoff(d, a, rango)
        for tipo in ("SC", "AR", "ST", "Spring", "Test", "SOS", "LPS", "UT", "SOW", "LPSY"):
            if tipo in ev:
                e = ev[tipo]; puntos += PUNTOS[tipo]
                if tipo != "AR":
                    motivos.append(f"{NOMBRE[tipo]} el {e['fecha'][8:10]}/{e['fecha'][5:7]} en {fm(e['precio'])}"
                                   + (f" ({e['nota']})" if e["nota"] else ""))
    r["eventos"] = [{k: e[k] for k in ("tipo", "fecha", "precio", "nota", "hace")} for e in sorted(ev.values(), key=lambda e: e["i"])]

    dist = [k for k in ("UT", "SOW", "LPSY") if k in ev]
    reciente = [k for k in ("Spring", "Test", "SOS", "LPS") if k in ev and ev[k]["hace"] <= 15]
    if not rango:
        r["fase"] = "Sin rango: " + ("corrección en zona Fibonacci" if en_fib else "tendencia")
    elif dist:
        r["fase"] = "Posible distribución"
    elif "SOS" in ev or "LPS" in ev:
        r["fase"] = "Fase D: salida del rango"
    elif "Spring" in ev or "Test" in ev:
        r["fase"] = "Fase C: spring / test"
    elif "SC" in ev:
        r["fase"] = "Fase B: construcción de la causa" if "ST" in ev else "Fase A: parada de la caída"
    else:
        r["fase"] = "Rango en desarrollo"

    r["puntos"], r["motivos"], r["descartada"] = puntos, motivos, bool(dist)
    r["candidata"] = bool(mayor and not dist and puntos >= 6 and (reciente or ((en_fib or rango) and en_sop)))
    return r


def main():
    lista = json.loads(CONFIG.read_text())
    out, errores = [], 0
    for info in lista:
        try:
            x = analizar(info)
            if x:
                out.append(x)
        except Exception as e:
            errores += 1
            print(f"ERROR scan {info['symbol']}: {e}", file=sys.stderr)
    out.sort(key=lambda x: (-x["candidata"], -x["puntos"], x["symbol"]))
    doc = {"generado": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "valores": out}
    (DATA / "scan.json").write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
    cand = [x["symbol"] for x in out if x["candidata"]]
    print(f"Scan: {len(out)} valores, {len(cand)} candidatas ({', '.join(cand)}), {errores} errores")
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
