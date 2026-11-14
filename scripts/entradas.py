#!/usr/bin/env python3
"""Entradas tras corrección a favor de la tendencia (diario).

Criterio extraído de los cursos del usuario (FHI básico «entrada N2», Paco Gómez «se queda sin
presión bajista», Valdecantos «test con poco volumen»):
  1. Tendencia a favor: semanal alcista y diario alcista (máximos y mínimos crecientes).
  2. Impulso previo CON volumen: último tramo alcista del diario (zigzag 3 ATR).
  3. Corrección SIN volumen: retrocede entre el 38,2 % y el 70 % del impulso, sin perder su origen,
     y su volumen medio es menor que el del impulso y que la media de 50 sesiones.
  4. Sin presión bajista: desde el mínimo de la corrección hay al menos 3 velas sin nuevo mínimo
     (barras de fallo) y como mucho 12.
  5. Activación: la vela de hoy cierra alcista y por encima del máximo de ayer (intención).
  6. Stop 0,5 ATR bajo el mínimo de la corrección; objetivo 1 = máximo del impulso; objetivo 2 =
     proyección del 61,8 % del impulso. Se exige beneficio/riesgo >= 2 hasta el objetivo 2.
Herramienta de apoyo a la decisión: no ejecuta órdenes ni es asesoramiento financiero.
"""

P = {"mult": 3.0, "rmin": 0.382, "rmax": 0.70, "fmin": 1, "fmax": 5, "act": "none", "vol": True, "rr": 2.0, "sem": True, "sa": 0.5}


def _atr(h, l, c, n=14):
    out, prev, s = [], None, 0.0
    for i in range(len(c)):
        tr = h[i] - l[i] if i == 0 else max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
        if i < n:
            s += tr; prev = s / (i + 1)
        else:
            prev = (prev * (n - 1) + tr) / n
        out.append(prev)
    return out


def _zigzag(h, l, a, mult):
    n = len(h)
    if n < 3:
        return []
    piv, d, ext, imax, imin = [], 0, 0, 0, 0
    for i in range(1, n):
        th = mult * a[i]
        if d == 0:
            if h[i] > h[imax]: imax = i
            if l[i] < l[imin]: imin = i
            if h[i] - l[imin] >= th and imin < i:
                piv.append((imin, l[imin], "L")); d, ext = 1, i
            elif h[imax] - l[i] >= th and imax < i:
                piv.append((imax, h[imax], "H")); d, ext = -1, i
        elif d == 1:
            if h[i] >= h[ext]: ext = i
            elif h[ext] - l[i] >= th:
                piv.append((ext, h[ext], "H")); d, ext = -1, i
        else:
            if l[i] <= l[ext]: ext = i
            elif h[i] - l[ext] >= th:
                piv.append((ext, l[ext], "L")); d, ext = 1, i
    return piv


def tendencia_simple(h, l, c):
    """'alcista' / 'bajista' / 'rango' / None con la misma lógica que el graficador."""
    if len(c) < 10:
        return None
    a = _atr(h, l, c)
    for mult in (5, 3, 2):
        piv = _zigzag(h, l, a, mult)
        H = [p for p in piv if p[2] == "H"]; L = [p for p in piv if p[2] == "L"]
        # se añade el extremo provisional para no ir con retraso
        if len(H) >= 2 and len(L) >= 2:
            hh, hl = H[-1][1] > H[-2][1], L[-1][1] > L[-2][1]
            return "alcista" if hh and hl else ("bajista" if not hh and not hl else "rango")
    return None


def _estructura(h, l, c, v, p):
    """Último impulso alcista del diario (L0 -> H1) y corrección en curso. None si el diario no es alcista."""
    n = len(c)
    a = _atr(h, l, c)
    piv = _zigzag(h, l, a, p["mult"])
    k = len(piv) - 1
    while k >= 0 and piv[k][2] != "H":
        k -= 1
    if k < 3:
        return None
    iH, pH, _ = piv[k]
    iL0, pL0, _ = piv[k - 1]
    pH_prev, pL_prev = piv[k - 2][1], piv[k - 3][1]
    if piv[k - 2][2] != "H":
        pH_prev, pL_prev = piv[k - 3][1], piv[k - 2][1]
    if not (pH > pH_prev and pL0 > pL_prev):          # diario alcista: máximo y mínimo crecientes
        return None
    if iH >= n - 1:
        return None
    if max(h[iH + 1:]) > pH:                          # ya superó el techo: la corrección terminó
        return None
    j = min(range(iH + 1, n), key=lambda i: l[i])     # mínimo de la corrección
    imp = pH - pL0
    if imp <= 0:
        return None
    vimp = sum(v[iL0:iH + 1]) / max(1, iH + 1 - iL0)
    vcor = sum(v[iH + 1:n - 1]) / max(1, n - 1 - (iH + 1)) if n - 1 > iH + 1 else v[-1]
    base = v[max(0, iL0 - 50):iL0]
    vmed = sum(base) / len(base) if base else 0
    return {"a": a, "iH": iH, "pH": pH, "iL0": iL0, "pL0": pL0, "j": j, "pLc": l[j], "imp": imp,
            "retr": (pH - l[j]) / imp, "fallo": n - 1 - j, "vimp": vimp, "vcor": vcor, "vmed": vmed}


def vigilar(o, h, l, c, v, tend_semanal, p=None):
    """Valor en tendencia (semanal y diario alcistas) que está corrigiendo: candidato a vigilar."""
    p = {**P, **(p or {})}
    if len(c) < 120 or tend_semanal != "alcista":
        return None
    e = _estructura(h, l, c, v, p)
    if not e or e["pLc"] <= e["pL0"] or not (0.30 <= e["retr"] <= 0.75):
        return None
    return {"techo": round(e["pH"], 2), "origen": round(e["pL0"], 2), "minimo": round(e["pLc"], 2),
            "retr": round(e["retr"] * 100, 1), "fallo": e["fallo"],
            "vol_cor": round(e["vcor"] / e["vmed"], 2) if e["vmed"] else None,
            "vol_imp": round(e["vimp"] / e["vmed"], 2) if e["vmed"] else None,
            "seca": bool(e["vmed"] and e["vcor"] < e["vimp"] and e["vcor"] < e["vmed"]),
            "z382": round(e["pH"] - 0.382 * e["imp"], 2), "z618": round(e["pH"] - 0.618 * e["imp"], 2)}


def senal(o, h, l, c, v, tend_semanal, p=None):
    """Evalúa la última vela de las series. Devuelve dict con la señal o None."""
    p = {**P, **(p or {})}
    n = len(c)
    if n < 120 or (p["sem"] and tend_semanal != "alcista"):
        return None
    e = _estructura(h, l, c, v, p)
    if not e:
        return None
    A = e["a"][-1]
    iL0, iH, j, pH, pL0, pLc, imp = e["iL0"], e["iH"], e["j"], e["pH"], e["pL0"], e["pLc"], e["imp"]
    retr, fallo, vimp, vcor, vmed = e["retr"], e["fallo"], e["vimp"], e["vcor"], e["vmed"]
    if iH >= n - 2:
        return None
    if not (p["rmin"] <= retr <= p["rmax"]) or pLc <= pL0:
        return None
    if not (p["fmin"] <= fallo <= p["fmax"]):          # velas sin nuevo mínimo desde el mínimo de la corrección
        return None
    if not vmed or (p["vol"] and (vcor >= vimp or vcor >= vmed)):   # impulso con volumen, corrección sin volumen
        return None
    if p["act"] == "vela" and not (c[-1] > o[-1] and c[-1] > h[-2]):
        return None
    if p["act"] == "rompe" and not (c[-1] > max(h[j:n - 1])):
        return None
    entrada = c[-1]
    stop = pLc - p["sa"] * A
    riesgo = entrada - stop
    if riesgo <= 0:
        return None
    obj1 = pH
    obj2 = pH + 0.618 * imp
    rr1, rr2 = (obj1 - entrada) / riesgo, (obj2 - entrada) / riesgo
    if rr2 < p["rr"]:
        return None
    pts = 0
    pts += 2 if 0.5 <= retr <= 0.618 else 1                     # zona Fibonacci clásica
    pts += 2 if vcor < 0.7 * vimp else 1                         # sequía de volumen
    pts += 1 if v[-1] > sum(v[-4:-1]) / 3 else 0                 # el volumen empieza a subir
    pts += 1 if rr2 >= 3 else 0
    return {
        "origen": round(pL0, 2), "techo": round(pH, 2), "minimo": round(pLc, 2),
        "retr": round(retr * 100, 1), "fallo": fallo,
        "vol_imp": round(vimp / vmed, 2), "vol_cor": round(vcor / vmed, 2),
        "entrada": round(entrada, 2), "stop": round(stop, 2),
        "obj1": round(obj1, 2), "obj2": round(obj2, 2),
        "rr1": round(rr1, 2), "rr2": round(rr2, 2),
        "riesgo_pct": round(riesgo / entrada * 100, 2), "calidad": pts,
    }
