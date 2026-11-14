"""Aviso de distribución en zona clavicular (Paco Gómez, tutoría 20/05/2014).

Lo que dice el audio, unido a los gráficos:
  - DÓNDE LLEGA: a una resistencia de varios toques («zona muy difícil de romper»).
  - CÓMO LLEGA: se queda en un lateral estrecho debajo de la resistencia; ahí sale
    mucho volumen y el precio no se desplaza («estos son ventas»); doble techo / fallo.
    La parte baja del lateral es la zona clavicular.
  - ROTURA CON INTENCIÓN: cierra por debajo de la clavicular con vela amplia, cierre
    abajo y volumen; «a partir de ahí cuidado con los largos». Objetivo mínimo:
    deshacer todo el movimiento previo.
Uso aquí: aviso de salida para posiciones abiertas y descarte en el buscador.
Solo velas diarias oficiales; no estima nada.
"""
import patrones


def detectar(o, h, l, c, v, hoy=None, P=None):
    P = P or {}
    lat_min = P.get("lat_min", 6)        # velas mínimas del lateral
    lat_max = P.get("lat_max", 30)
    ancho = P.get("ancho", 3.0)          # alto máximo del lateral en ATR
    tol_res = P.get("tol_res", 0.8)      # techo del lateral a menos de x ATR de la resistencia
    vabs = P.get("vabs", 1.5)            # volumen alto sin desplazamiento
    rango = P.get("rango", 1.0)          # vela de rotura >= x ATR
    q = len(c) - 1 if hoy is None else hoy
    if q < 120:
        return None
    a = patrones._atr(h[:q + 1], l[:q + 1], c[:q + 1])
    A = a[q - 1]
    vm = patrones._vm(v, q) or 1
    for L in range(lat_min, lat_max + 1):
        ini = q - L
        techo = max(h[ini:q]); suelo = min(l[ini:q])
        if techo - suelo > ancho * A:
            break                         # más atrás el lateral ya no es estrecho
        if L < lat_min:
            continue
        # la vela de hoy rompe el suelo con intención y ninguna anterior del lateral cerró debajo
        if not (c[q] < suelo and h[q] - l[q] >= rango * A
                and (c[q] - l[q]) <= 0.35 * (h[q] - l[q]) and v[q] >= vm):
            continue
        # se llegó subiendo: antes del lateral el precio estaba claramente más abajo
        if min(l[max(0, ini - 40):ini]) > suelo - 1.5 * A:
            continue
        # dónde llega: resistencia previa (niveles de varios toques antes del lateral)
        nv = patrones.niveles(h, l, ini, a)
        res = [p for p, t in nv if abs(p - techo) <= tol_res * A]
        if not res:
            continue
        # cómo llega: volumen alto sin desplazamiento dentro del lateral
        absor = [i for i in range(ini, q) if v[i] >= vabs * vm and h[i] - l[i] <= 1.2 * a[i]]
        if not absor:
            continue
        return {"resistencia": round(res[0], 2), "techo": round(techo, 2), "clavicular": round(suelo, 2),
                "lateral": L, "vol_abs": round(max(v[i] for i in absor) / vm, 2),
                "vol_rotura": round(v[q] / vm, 2), "objetivo_min": round(min(l[max(0, ini - 40):ini]), 2)}
    return None
