#!/usr/bin/env python3
"""Prueba histórica de las entradas nuevas de seleccion.py (diario, 79 valores).

  agresiva:     spring en una trinchera de soporte fuerte (perfora y recupera en <= 3 sesiones); entrada al cierre
                del día en que se detecta, stop 0,3 ATR bajo el mínimo del spring.
  conservadora: rotura con intención de una trinchera fuerte (cierre encima, rango >= 1 ATR, cierre en el tercio alto,
                volumen >= 1,3x); entrada al cierre de la rotura, stop 0,5 ATR bajo la zona.
Filtro: semanal y mensual alcistas (Schroeder paso 1), calculados solo con datos hasta ese día.
Salida: objetivo (siguiente trinchera de 3 toques o más; si no hay, 3R), stop (con huecos de apertura) o 60 sesiones.
Uso: python scripts/prueba_seleccion.py [años]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scan as S  # noqa: E402
import seleccion as SE  # noqa: E402


def agrupar(d, k):
    out = {x: [] for x in "tohlcv"}
    for s in range(d["n"] % k, d["n"], k):
        e = s + k
        out["t"].append(d["t"][s]); out["o"].append(d["o"][s]); out["h"].append(max(d["h"][s:e]))
        out["l"].append(min(d["l"][s:e])); out["c"].append(d["c"][e - 1]); out["v"].append(sum(d["v"][s:e]))
    out["n"] = len(out["c"])
    return out


def corte(d, i, desde=0):
    x = {k: d[k][desde:i + 1] for k in "tohlcv"}
    x["n"] = len(x["c"])
    return x


def simular(d, i, entrada, stop, obj, maxd=60):
    for j in range(i + 1, min(d["n"], i + 1 + maxd)):
        if d["o"][j] <= stop:
            return (d["o"][j] - entrada) / (entrada - stop), j - i
        if d["l"][j] <= stop:
            return -1.0, j - i
        if d["o"][j] >= obj:
            return (d["o"][j] - entrada) / (entrada - stop), j - i
        if d["h"][j] >= obj:
            return (obj - entrada) / (entrada - stop), j - i
    j = min(d["n"] - 1, i + maxd)
    return (d["c"][j] - entrada) / (entrada - stop), j - i


def main():
    anos = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    lista = json.loads(S.CONFIG.read_text())
    res = {"agresiva": [], "conservadora": []}
    for info in lista:
        d = S.cargar(info["symbol"], "1d")
        if not d or d["n"] < 800:
            continue
        ini = max(700, d["n"] - 252 * anos)
        ult = {"agresiva": -99, "conservadora": -99}
        Z, tend, a = None, False, S.atr(d)
        for i in range(ini, d["n"] - 1):
            if (i - ini) % 5 == 0:
                x = corte(d, i, max(0, i - 2600))
                tend = S.tendencia(agrupar(x, 5)) == "alcista" and S.tendencia(agrupar(x, 21)) == "alcista"
                Z = SE.trincheras(corte(d, i, i - 700), a[i - 700:i + 1]) if tend else []
            if not tend or not Z:
                continue
            x = corte(d, i, i - 60)
            ax = a[i - 60:i + 1]
            A, cierre = a[i], d["c"][i]
            fuertes = [z for z in Z if z["fuertes"]]
            obj_de = lambda e, st: min([z["lo"] for z in Z if z["lo"] > e + 0.5 * A and z["toques"] >= 3], default=e + 3 * (e - st))
            # agresiva
            sop = [z for z in fuertes if z["lo"] - 0.3 * A <= cierre and z["hi"] < cierre + 2 * A]
            if sop and i - ult["agresiva"] > 10:
                z = max(sop, key=lambda z: z["hi"])
                sp = SE.spring_en_zona(x, ax, z, dias=3)
                if sp and sp["i"] >= x["n"] - 3:
                    st = sp["min"] - 0.3 * A
                    if st < cierre:
                        ob = obj_de(cierre, st)
                        r, dur = simular(d, i, cierre, st, ob)
                        rg = d["h"][i] - d["l"][i]
                        res["agresiva"].append((info["symbol"], d["t"][i], round(r, 2), dur, (ob - cierre) / (cierre - st),
                                                z["toques"], z["defensas"], sp["vol"], (cierre - d["l"][i]) / rg if rg else 0.5,
                                                d["v"][i] / (SE._vm(d["v"], i) or 1), (cierre - st) / A))
                        ult["agresiva"] = i
            # conservadora
            if i - ult["conservadora"] > 10:
                for z in fuertes:
                    if z["hi"] < cierre < z["hi"] + 2 * A:
                        rt = SE.rotura(x, ax, z, dias=1)
                        if rt and rt["i"] == x["n"] - 1:
                            st = z["lo"] - 0.5 * A
                            ob = obj_de(cierre, st)
                            r, dur = simular(d, i, cierre, st, ob)
                            res["conservadora"].append((info["symbol"], d["t"][i], round(r, 2), dur, (ob - cierre) / (cierre - st),
                                                           z["toques"], z["defensas"], rt["vol"], 1, 1, (cierre - st) / A))
                            ult["conservadora"] = i
                            break
    for tipo, L in res.items():
        for nombre, F in (("todas", L), ("B/R >= 1,5", [x for x in L if x[4] >= 1.5])):
            if not F:
                continue
            R = [x[2] for x in F]
            g = [r for r in R if r > 0]; p = [r for r in R if r <= 0]
            pf = sum(g) / -sum(p) if p and sum(p) else 0
            print(f"{tipo:13} {nombre:11} n={len(R):4}  gana {len(g) / len(R) * 100:4.0f} %  media {sum(R) / len(R):+.2f}R"
                  f"  factor {pf:.2f}  duración {sum(x[3] for x in F) / len(F):.0f} ses.")
    Path("/tmp/prueba_seleccion.json").write_text(json.dumps(res))


if __name__ == "__main__":
    main()
