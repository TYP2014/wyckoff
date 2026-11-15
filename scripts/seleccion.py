#!/usr/bin/env python3
"""Selección de los mejores escenarios: todo lo de los cursos integrado.

Cinco pasos de Schroeder (curso Wyckoff de Precio & Volumen):
  1. ¿A favor de la línea de menor resistencia?  -> tendencia mensual, semanal y diaria.
  2. ¿Fuerza o debilidad del activo?             -> fuerza relativa frente a su índice (3 y 6 meses).
  3. ¿Hay causa evidente y significativa?         -> rango / acumulación (SC, ST, spring, test) o
                                                     trinchera de soporte defendida muchas veces.
  4. ¿Está en el sitio adecuado?                  -> en una trinchera de soporte fuerte, en el back de una
                                                     resistencia rota o justo debajo de la resistencia que
                                                     hay que romper (para la orden de compra).
  5. ¿Cumple el timing de entrada?                -> spring en soporte fuerte (agresiva), rotura con
                                                     intención (conservadora), corrección sin volumen,
                                                     patrones de Paco Gómez.

TRINCHERAS (soportes y resistencias como ZONA, no como precio exacto): giros del diario de los últimos
~2 años agrupados a menos de 1 ATR. De cada zona: toques, defensas (giros que después se alejaron 2 ATR o más
en 10 sesiones: alguien la defendió) y volumen en los toques frente a su media de 50 sesiones.

Las probabilidades de perder existen siempre: esto ordena escenarios, no adivina. Apoyo a la decisión,
no ejecuta órdenes ni es asesoramiento financiero.
"""
import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"


def fm(x, d=2):
    return f"{x:.{d}f}".replace(".", ",")


def fe(t):
    return f"{t[8:10]}/{t[5:7]}"


def _vm(v, i, n=50):
    s = v[max(0, i - n):i]
    return sum(s) / len(s) if s else 0


# ------------------------------------------------------------------ trincheras
def trincheras(d, a, ventana=500, k=4, tol=0.6):
    import scan as S
    n, h, l, c, v = d["n"], d["h"], d["l"], d["c"], d["v"]
    if n < 60:
        return []
    A = a[-1]
    G = sorted(S.giros(d, max(k, n - ventana), n, k), key=lambda q: q["p"])
    grupos, g = [], []
    for q in G:
        if g and q["p"] - g[0]["p"] > tol * A:
            grupos.append(g); g = []
        g.append(q)
    if g:
        grupos.append(g)
    out = []
    for x in grupos:
        if len(x) < 2:
            continue
        lo, hi = min(q["p"] for q in x), max(q["p"] for q in x)
        defensas, vols = 0, []
        for q in x:
            i = q["i"]
            fut = range(i + 1, min(n, i + 11))
            if fut:
                if q["t"] == "L" and max(h[j] for j in fut) - l[i] >= 2 * a[i]:
                    defensas += 1
                if q["t"] == "H" and h[i] - min(l[j] for j in fut) >= 2 * a[i]:
                    defensas += 1
            vm = _vm(v, i)
            if vm:
                vols.append(max(v[max(0, i - 1):i + 2]) / vm)
        vol = sum(vols) / len(vols) if vols else 0
        ult = max(q["i"] for q in x)
        fuerza = len(x) + 0.5 * defensas + (1 if vol >= 1.5 else 0) + (0.5 if n - ult < 120 else 0)
        out.append({"lo": round(lo, 2), "hi": round(hi, 2), "toques": len(x), "defensas": defensas,
                    "vol": round(vol, 2), "fuerza": round(fuerza, 1), "ult": d["t"][ult] if isinstance(d["t"][ult], str) else int(d["t"][ult]),
                    "fuertes": len(x) >= 4 or (len(x) >= 3 and defensas >= 2)})
    return out


def texto_zona(z):
    return (f"{fm(z['lo'])}-{fm(z['hi'])} ({z['toques']} toques, defendida {z['defensas']} "
            f"{'vez' if z['defensas'] == 1 else 'veces'}, volumen {fm(z['vol'], 1)}× en los toques)")


# ------------------------------------------------------------------ gatillos
def spring_en_zona(d, a, z, dias=10):
    """Perfora la trinchera de soporte y vuelve dentro en 3 sesiones o menos; hoy sigue dentro o encima."""
    n, h, l, c, v = d["n"], d["h"], d["l"], d["c"], d["v"]
    if c[-1] < z["lo"]:
        return None
    for j in range(n - 1, max(0, n - 1 - dias), -1):
        if l[j] < z["lo"] - 0.1 * a[j] and any(c[m] >= z["lo"] for m in range(j, min(n, j + 4))) and min(l[j:]) >= l[j]:
            vm = _vm(v, j) or 1
            test = None
            for k in range(j + 2, n):          # test: vuelve a la zona sin perforar el spring, con menos volumen
                if l[j] < l[k] <= z["hi"] + 0.3 * a[k] and v[k] < v[j]:
                    test = k
            # recuperación con intención (prueba histórica: mejora el resultado): alguna vela entre el spring y 3 después
            # cierra dentro de la zona, en su tercio alto y con volumen >= su media
            intencion = any(c[k] >= z["lo"] and h[k] > l[k] and (c[k] - l[k]) >= 0.6 * (h[k] - l[k]) and v[k] >= (_vm(v, k) or 1)
                            for k in range(j, min(n, j + 4)))
            return {"i": j, "fecha": d["t"][j], "min": round(l[j], 2), "vol": round(v[j] / vm, 2), "intencion": intencion,
                    "test": d["t"][test] if test is not None else None,
                    "vol_test": round(v[test] / (_vm(v, test) or 1), 2) if test is not None else None}
    return None


def rotura(d, a, z, dias=5):
    """Cierre por encima de la trinchera de resistencia con intención: rango >= 1 ATR, cierre en el tercio
    alto y volumen >= 1,3 veces la media. Hoy no ha vuelto a meterse por debajo de la zona."""
    n, h, l, c, v = d["n"], d["h"], d["l"], d["c"], d["v"]
    for j in range(n - 1, max(0, n - 1 - dias), -1):
        r = h[j] - l[j]
        vm = _vm(v, j) or 1
        if c[j] > z["hi"] and c[j - 1] <= z["hi"] + 0.2 * a[j] and r >= a[j - 1] and (c[j] - l[j]) >= 0.65 * r and v[j] >= 1.3 * vm:
            if min(c[j:]) < z["lo"]:
                return None
            return {"i": j, "fecha": d["t"][j], "cierre": round(c[j], 2), "vol": round(v[j] / vm, 2)}
    return None


# ------------------------------------------------------------------ lectura del volumen en 60 min
def cargar60(sym):
    f = DATA / sym / "60m.json"
    if not f.exists():
        return None
    B = json.loads(f.read_text())["barras"]
    return {"t": [x[0] for x in B], "o": [x[1] for x in B], "h": [x[2] for x in B], "l": [x[3] for x in B],
            "c": [x[4] for x in B], "v": [x[5] for x in B], "n": len(B)}


def lectura_60(sym, ses=2):
    """Flechas importantes de las últimas `ses` sesiones en 60 min (mismo criterio que el graficador:
    cada vela frente a las 20 anteriores de su misma hora)."""
    f = DATA / sym / "60m.json"
    if not f.exists():
        return None
    B = json.loads(f.read_text())["barras"]
    if len(B) < 200:
        return None
    hist, marcas = {}, []
    dias = sorted({b[0] // 86400 for b in B})[-ses:]
    for i, (t, o, h, l, c, v) in enumerate(B):
        r, key = h - l, t % 86400
        H = hist.setdefault(key, [])
        if len(H) >= 10 and i >= 2 and t // 86400 in dias:
            vm = sum(q[0] for q in H) / len(H); rm = sum(q[1] for q in H) / len(H)
            cp = (c - l) / r if r > 0 else 0.5
            sube, baja = c > B[i - 1][4], c < B[i - 1][4]
            seco = v < 0.8 * vm and v < B[i - 1][5] and v < B[i - 2][5]
            if v >= 2 * vm and r <= 0.8 * rm:
                marcas.append("absorción")
            elif sube and v >= 2 * vm and r >= 1.2 * rm and cp >= 0.65:
                marcas.append("compras")
            elif baja and v >= 2 * vm and r >= 1.2 * rm and cp <= 0.35:
                marcas.append("ventas")
            elif baja and r <= 0.8 * rm and seco:
                marcas.append("sin oferta")
            elif sube and r <= 0.8 * rm and seco:
                marcas.append("sin demanda")
        H.append((v, r))
        if len(H) > 20:
            H.pop(0)
    cuenta = {k: marcas.count(k) for k in ("compras", "absorción", "sin oferta", "ventas", "sin demanda") if marcas.count(k)}
    a_favor = cuenta.get("compras", 0) + cuenta.get("absorción", 0) + cuenta.get("sin oferta", 0)
    en_contra = cuenta.get("ventas", 0) + cuenta.get("sin demanda", 0)
    txt = ", ".join(f"{n} {k}" for k, n in cuenta.items()) or "sin flechas importantes"
    return {"cuenta": cuenta, "txt": txt, "tono": "favor" if a_favor > en_contra else "contra" if en_contra > a_favor else "neutro"}


# ------------------------------------------------------------------ fuerza relativa
def rendimiento(c, k):
    return c[-1] / c[-1 - k] - 1 if len(c) > k else None


# ------------------------------------------------------------------ evaluación completa
OK, MEDIO, NO = "si", "medio", "no"


def evaluar(d, a, r, ev, rango, bench, sym=None, intradia=True):
    """r: resultado del scan (tendencias, fib, entrada, patron). ev: eventos Wyckoff del rango.
    bench: (rend_3m, rend_6m) del índice de referencia."""
    n, h, l, c = d["n"], d["h"], d["l"], d["c"]
    A, cierre = a[-1], c[-1]
    pasos, escenario, entradas_ = [], [], []

    # 1. línea de menor resistencia
    tM, tS, tD = r["tendM"], r["tendS"], r["tendD"]
    if tM == "alcista" and tS == "alcista" and tD == "alcista":
        pasos.append((OK, "Mensual, semanal y diario alcistas: las tres a favor"))
    elif tM == "alcista" and tS == "alcista":
        pasos.append((MEDIO, f"Mensual y semanal alcistas; el diario está {tD or 'sin definir'} (corrigiendo dentro de la tendencia)"))
    elif tM == "alcista" and tS == "rango":
        pasos.append((MEDIO, "Mensual alcista, semanal lateral: esperar a que una parte abandone"))
    else:
        pasos.append((NO, f"Tendencia en contra (mensual {tM or '—'}, semanal {tS or '—'})"))

    # 2. fuerza relativa
    r3, r6 = rendimiento(c, 63), rendimiento(c, 126)
    if r3 is None or r6 is None or not bench or bench[0] is None:
        pasos.append((MEDIO, "Fuerza relativa sin datos suficientes"))
        fr = None
    else:
        f3, f6 = (r3 - bench[0]) * 100, (r6 - bench[1]) * 100
        fr = {"f3": round(f3, 1), "f6": round(f6, 1)}
        t = f"Frente a su índice: {'+' if f3 >= 0 else ''}{fm(f3, 1)} puntos en 3 meses y {'+' if f6 >= 0 else ''}{fm(f6, 1)} en 6 meses"
        pasos.append((OK if f3 > 0 and f6 > 0 else MEDIO if f3 > 0 or f6 > 0 else NO, t))

    # trincheras
    Z = trincheras(d, a)
    dentro = [z for z in Z if z["lo"] - 0.3 * A <= cierre <= z["hi"]]      # el precio está en la trinchera
    sop = [z for z in Z if z["hi"] < cierre] + dentro
    res = dentro + [z for z in Z if z["lo"] > cierre]
    sop_c = max(sop, key=lambda z: z["hi"]) if sop else None                       # soporte más cercano
    sop_f = max([z for z in sop if z["fuertes"]], key=lambda z: z["hi"], default=None)
    res_f = min([z for z in res if z["fuertes"]], key=lambda z: z["lo"], default=None)
    en_medio = bool(res_f and res_f in dentro)
    res_c = min(res, key=lambda z: z["lo"]) if res else None

    # 3. causa
    dist = [k for k in ("UT", "SOW", "LPSY") if k in ev]
    acum = [k for k in ("SC", "ST", "Spring", "Test", "SOS", "LPS") if k in ev]
    if dist:
        pasos.append((NO, "Señales de distribución: " + ", ".join(dist)))
    elif rango and rango["dias"] >= 30 and (acum or rango["origen"] == "caida"):
        pasos.append((OK, f"Rango de {rango['dias']} sesiones ({fm(rango['inf'])}-{fm(rango['sup'])})"
                      + (f" con {', '.join(acum)}" if acum else " tras una caída")))
    elif sop_f and sop_f["toques"] >= 4:
        pasos.append((OK if sop_f["defensas"] >= 3 else MEDIO, f"Trinchera {texto_zona(sop_f)}" + (" — el precio está dentro" if sop_f in dentro else "")))
    elif rango:
        pasos.append((MEDIO, f"Rango de {rango['dias']} sesiones sin eventos de acumulación claros"))
    else:
        pasos.append((NO, "Sin rango ni trinchera fuerte que construya causa"))

    # gatillos
    sp = spring_en_zona(d, a, sop_f) if sop_f else None
    rot = None
    for z in sorted([z for z in Z if z["fuertes"] and z["hi"] < cierre + 2 * A], key=lambda z: -z["hi"])[:2]:
        rot = rotura(d, a, z)
        if rot:
            rot["zona"] = z
            break
    stop_swing = min(l[-10:]) - 0.3 * A

    def objetivo(entrada):
        sig = [z for z in Z if z["lo"] > entrada + 0.5 * A and z["toques"] >= 3]
        if sig:
            z = min(sig, key=lambda z: z["lo"])
            return z["lo"], f"siguiente trinchera {fm(z['lo'])}-{fm(z['hi'])}"
        if rango:
            return entrada + rango["alto"], "altura del rango (causa → efecto)"
        return max(h[-260:]), "máximo de un año"

    def anotar(tipo, entrada, stop, nota, valida=True):
        if stop >= entrada:
            return
        obj, que = objetivo(entrada)
        br = (obj - entrada) / (entrada - stop)
        entradas_.append({"tipo": tipo, "entrada": round(entrada, 2), "stop": round(stop, 2), "obj": round(obj, 2),
                          "obj_txt": que, "br": round(br, 2), "riesgo_pct": round((entrada - stop) / entrada * 100, 1), "nota": nota,
                          "valida": bool(valida and br >= 1.5)})

    if sp:
        t = f"Spring el {fe(sp['fecha'])} en {fm(sp['min'])} (volumen {fm(sp['vol'], 1)}×) que recupera la trinchera"
        if sp["test"]:
            t += f"; test el {fe(sp['test'])} con menos volumen ({fm(sp['vol_test'], 1)}×)"
        t += "; recupera con intención (cierre arriba y volumen)" if sp["intencion"] else "; la recuperación aún no muestra intención"
        escenario.append(t)
        anotar("agresiva", cierre, sp["min"] - 0.3 * A, "Tras el spring: más riesgo, mejor precio", sp["intencion"])
    if rot:
        z = rot["zona"]
        escenario.append(f"Rompe la trinchera {fm(z['lo'])}-{fm(z['hi'])} el {fe(rot['fecha'])} con intención (volumen {fm(rot['vol'], 1)}×)")
        anotar("back", z["hi"], z["lo"] - 0.5 * A, "Compra en el back a la zona rota", z["toques"] >= 4 and z["defensas"] >= 3)
    elif res_f and cierre >= res_f["lo"] - 3 * A and pasos[0][0] != NO:
        entrada = res_f["hi"] + 0.1 * A
        escenario.append((f"Dentro de la trinchera {texto_zona(res_f)}: aquí se decide; si sale por arriba con intención, entrada"
                          if en_medio else f"Debajo de la trinchera de resistencia {texto_zona(res_f)}: si la rompe con intención, entrada"))
        anotar("conservadora", entrada, res_f["lo"] - 0.5 * A, f"Orden de compra si cierra por encima de {fm(entrada)} con volumen; stop si vuelve debajo de la zona",
               res_f["toques"] >= 4 and res_f["defensas"] >= 3)
    # afinar en 60 min: trinchera de 60 min más cercana por encima y por debajo (cerca del precio)
    z60 = None
    d60 = cargar60(sym) if intradia and sym else None
    if d60 and d60["n"] > 300 and pasos[0][0] != NO:
        import scan as S
        a60 = S.atr(d60)
        T = trincheras(d60, a60, ventana=600, k=4, tol=0.6)
        c60, A60 = d60["c"][-1], a60[-1]
        r60 = [z for z in T if z["lo"] >= c60 - 0.3 * A60 and z["hi"] > c60 and z["toques"] >= 3 and z["lo"] - c60 <= A]
        s60 = [z for z in T if z["hi"] <= c60 + 0.3 * A60 and z["toques"] >= 3 and c60 - z["hi"] <= A]
        z60 = {"res": min(r60, key=lambda z: z["lo"]) if r60 else None, "sop": max(s60, key=lambda z: z["hi"]) if s60 else None}
        if z60["res"]:
            zr = z60["res"]
            entrada = zr["hi"] + 0.1 * A60
            stop = (z60["sop"]["lo"] - 0.3 * A60) if z60["sop"] else entrada - A
            escenario.append(f"En 60 min: resistencia {fm(zr['lo'])}-{fm(zr['hi'])} ({zr['toques']} toques)"
                             + (f", soporte {fm(z60['sop']['lo'])}-{fm(z60['sop']['hi'])} ({z60['sop']['toques']} toques)" if z60["sop"] else ""))
            anotar("60 min", entrada, stop, f"Rotura de la resistencia de 60 min: compra si supera {fm(entrada)} con volumen en 60 min")
    if r.get("entrada"):
        e = r["entrada"]
        anotar("corrección", e["entrada"], e["stop"], f"Corrección del {fm(e['retr'])} % sin volumen")
    if r.get("patron"):
        e = r["patron"]
        anotar("patrón", e["entrada"], e["stop"], e["tipo"])

    # 4. sitio
    en_sop = sop_f and sop_f["lo"] - 0.5 * A <= cierre <= sop_f["hi"] + 1.5 * A
    fib = r.get("fib")
    if en_sop:
        pasos.append((OK, f"En la trinchera de soporte {fm(sop_f['lo'])}-{fm(sop_f['hi'])}"))
    elif rot:
        pasos.append((OK, f"En el back de la resistencia rota {fm(rot['zona']['lo'])}-{fm(rot['zona']['hi'])}"))
    elif res_f and res_f["lo"] - 1.5 * A <= cierre <= res_f["hi"]:
        pasos.append((MEDIO, f"Pegado a la resistencia {fm(res_f['lo'])}-{fm(res_f['hi'])}: sitio para la orden de rotura, no para comprar ya"))
    elif fib and 38.2 <= fib["retr"] <= 61.8:
        pasos.append((MEDIO, f"Retroceso del {fm(fib['retr'], 0)} % del tramo semanal (zona 38,2-61,8 %), sin trinchera cerca"))
    else:
        pasos.append((NO, "En tierra de nadie: lejos de soportes y resistencias importantes"))

    # 5. timing
    activos = [e for e in entradas_ if e["tipo"] in ("agresiva", "back", "corrección", "patrón")]
    buenos = [e for e in activos if e["valida"]]
    if buenos:
        pasos.append((OK, "Gatillo activo: " + ", ".join(f"{e['tipo']} (B/R {fm(e['br'], 1)})" for e in buenos)))
    elif activos:
        pasos.append((MEDIO, "Gatillo activo pero flojo: poco recorrido hasta la siguiente trinchera (B/R < 1,5) o recuperación sin intención"))
    elif any(e["tipo"] in ("conservadora", "60 min") for e in entradas_):
        pasos.append((MEDIO, "Pendiente: falta la rotura con intención"))
    else:
        pasos.append((NO, "Sin gatillo de entrada todavía"))

    # lectura 60 min (para afinar la entrada)
    l60 = lectura_60(sym) if intradia and sym else None
    nota = sum(2 if p[0] == OK else 1 if p[0] == MEDIO else 0 for p in pasos)
    mejor = max(entradas_, key=lambda e: (e["valida"], e["br"]), default=None)
    return {"pasos": [{"estado": p[0], "txt": p[1]} for p in pasos], "nota": nota, "fr": fr,
            "zonas": sorted(Z, key=lambda z: -z["hi"]),
            "soporte": sop_f or sop_c, "resistencia": res_f or res_c,
            "escenario": escenario, "entradas": entradas_, "mejor": mejor, "l60": l60, "z60": z60,
            "descartada": bool(dist) or pasos[0][0] == NO}
