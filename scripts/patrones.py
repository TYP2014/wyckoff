#!/usr/bin/env python3
"""Patrones de las tutorías de Paco Gómez sobre soportes y resistencias (velas diarias).

1. BACK A LA ZONA SUPERADA (abc sin volumen): el precio cierra por encima de una resistencia de varios toques con
   volumen por encima de la media; vuelve al nivel roto en una corrección (abc) con menos volumen, sin reentrar;
   entrada cuando hoy supera el máximo de esa vuelta. Prueba 2016-2026: 201 señales, gana el 48 %, media +0,22 R
   (PF 1,4), estable en los dos periodos. (Con vela de rotura amplia y volumen ≥ 1,5x no daba ventaja.) el precio rompe una resistencia de varios toques con
   una vela amplia y volumen alto; después vuelve al nivel roto con poco volumen (sin oferta), no reentra
   y se gira al alza. Entrada al girar; stop bajo el nivel.
2. ENGAÑO EN SOPORTE Y TEST (spring): el precio perfora un soporte de varios toques con volumen alto y lo
   recupera enseguida («trampa, engaño»); después vuelve a la zona con menos volumen, sin hacer nuevo
   mínimo, y se gira al alza. Entrada al girar; stop bajo el mínimo del engaño.
Prueba 2016-2026 (79 valores, salida con el plan de gestión y huecos incluidos) del patrón 2: 173 señales,
gana el 51 %, media +0,53 R por operación (+0,35 R sin las 3 mejores), positivo en 2016-2020 y en 2021-2026.
Solo con tendencia semanal alcista (a favor de la tendencia). Herramienta de apoyo: no es asesoramiento.
"""


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


def niveles(h, l, fin, a, k=4, ventana=300, minimo=3):
    """Niveles con varios giros (máximos/mínimos locales de ±k velas) en las `ventana` velas antes de `fin`."""
    ini = max(k, fin - ventana)
    pts = []
    for i in range(ini, fin - k):
        if h[i] == max(h[i - k:i + k + 1]):
            pts.append(h[i])
        if l[i] == min(l[i - k:i + k + 1]):
            pts.append(l[i])
    pts.sort()
    tol = 1.2 * a[fin - 1]
    out, g = [], []
    for p in pts:
        if g and p - g[0] > tol:
            if len(g) >= minimo:
                out.append((sum(g) / len(g), len(g)))
            g = []
        g.append(p)
    if len(g) >= minimo:
        out.append((sum(g) / len(g), len(g)))
    return out


def _vm(v, i, n=50):
    s = v[max(0, i - n):i]
    return sum(s) / len(s) if s else 0


def detectar(o, h, l, c, v, tend_semanal, max_dias=25, incluir_rotura=True, solo_rotura=False, vrot=1.0, ancha=False, gatillo="abc"):
    """Evalúa la última vela. Devuelve una lista de señales (normalmente 0 o 1)."""
    n = len(c)
    if n < 330 or tend_semanal != "alcista":
        return []
    a = _atr(h, l, c)
    A = a[-1]
    hoy = n - 1
    # activación de hoy: vela alcista que cierra por encima del máximo de ayer (giro)
    vela_giro = c[hoy] > o[hoy] and c[hoy] > h[hoy - 1]     # giro de hoy (para el engaño)
    out = []
    lv = niveles(h, l, n - max_dias, a)            # niveles que ya existían antes de la ventana
    for i in range(n - max_dias, n - 2):          # día del suceso (rotura o engaño)
        vmi = _vm(v, i)
        if not vmi or v[i] < min(1.5, vrot) * vmi:
            continue
        for p, toques in lv:
            # 1) rotura con intención de una resistencia y vuelta sin oferta
            if (incluir_rotura or solo_rotura) and v[i] >= vrot * vmi and c[i - 1] <= p < c[i] and c[i] > p + 0.3 * a[i] \
                    and (not ancha or ((h[i] - l[i]) >= 1.2 * a[i] and (c[i] - l[i]) >= 0.65 * (h[i] - l[i]))):
                vuelta = range(i + 1, hoy)
                if not vuelta or min(c[k] for k in vuelta) < p - 0.3 * a[i]:
                    continue                       # reentró en el rango: falla
                kmin = min(vuelta, key=lambda k: l[k])
                if l[kmin] > p + 0.6 * a[i]:
                    continue                       # no ha vuelto al nivel
                vcor = sum(v[k] for k in vuelta) / len(vuelta)
                if vcor >= vmi or vcor >= v[i] * 0.6:
                    continue                       # la vuelta no es «sin oferta»
                if not vela_giro and gatillo != "abc":
                    continue
                if hoy - kmin > (8 if gatillo == "abc" else 3):
                    continue                       # el giro tiene que ser reciente
                if gatillo == "abc":               # rompe el máximo de la vuelta (fin del abc) hoy
                    techo_b = max(h[k] for k in range(kmin, hoy)) if kmin < hoy else h[hoy - 1]
                    if not (c[hoy] > techo_b and c[hoy - 1] <= techo_b):
                        continue
                stop = min(l[kmin], p) - 0.5 * A
                out.append({"tipo": "Back a la zona superada", "nivel": round(p, 2), "toques": toques,
                            "i_suceso": i, "vol_suceso": round(v[i] / vmi, 2), "vol_vuelta": round(vcor / vmi, 2),
                            "minimo": round(l[kmin], 2), "stop": round(stop, 2), "entrada": round(c[hoy], 2),
                            "obj1": round(max(h[i:hoy + 1]), 2)})
            # 2) engaño bajo un soporte (spring) y test con menos volumen
            elif not solo_rotura and vela_giro and v[i] >= 1.5 * vmi and l[i] < p - 0.2 * a[i] and c[i - 1] >= p and any(c[k] > p for k in range(i, min(i + 3, hoy))):
                tras = range(i + 1, hoy)
                if not tras or min(l[k] for k in tras) < l[i]:
                    continue                       # nuevo mínimo: el engaño ha fallado
                if min(c[k] for k in tras) < p - 0.5 * a[i]:
                    continue
                cerca = [k for k in tras if l[k] <= p + 0.6 * a[i]]
                if not cerca:
                    continue                       # todavía no ha hecho el test
                kt = max(cerca)
                if hoy - kt > 3 or v[kt] >= v[i] * 0.7 or v[kt] >= vmi:
                    continue                       # test reciente y con menos volumen
                stop = l[i] - 0.5 * A
                out.append({"tipo": "Engaño en soporte y test", "nivel": round(p, 2), "toques": toques,
                            "i_suceso": i, "vol_suceso": round(v[i] / vmi, 2), "vol_vuelta": round(v[kt] / vmi, 2),
                            "minimo": round(l[i], 2), "stop": round(stop, 2), "entrada": round(c[hoy], 2),
                            "obj1": round(max(h[max(0, i - 30):hoy + 1]), 2)})
        if out:
            break
    for s in out:
        r = s["entrada"] - s["stop"]
        s["riesgo_pct"] = round(r / s["entrada"] * 100, 2) if r > 0 else None
        s["rr1"] = round((s["obj1"] - s["entrada"]) / r, 2) if r > 0 else None
    # la entrada tiene que estar cerca del nivel (no perseguir el precio): como mucho 1,5 ATR por encima
    return [s for s in out if s["riesgo_pct"] and s["entrada"] - s["nivel"] <= 1.5 * A]
