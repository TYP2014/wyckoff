#!/usr/bin/env python3
"""Descarga velas OHLC + volumen y las guarda en data/<SIMBOLO>/<temporalidad>.json

Temporalidades: 60m (historico gratuito ~2 anos, se va acumulando), 1d, 1wk, 1mo.
Semanal y mensual se calculan a partir del diario para que todo cuadre.

Uso:  python scripts/update_data.py            (todos los valores de config/tickers.json)
      python scripts/update_data.py AAPL ITX.MC
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CONFIG = ROOT / "config" / "tickers.json"

# ---------------------------------------------------------------- proveedores
# Para cambiar a un proveedor de pago: escribir otra funcion con la misma firma
# (devuelve DataFrame con indice de fechas y columnas Open/High/Low/Close/Volume)
# y apuntar PROVEEDOR a ella.


def proveedor_yfinance(symbol: str, interval: str) -> pd.DataFrame:
    import yfinance as yf

    # 60m: Yahoo da como mucho ~730 dias; en valores recientes hay que pedir menos
    periodos = ["730d", "1y", "6mo", "3mo", "1mo"] if interval == "60m" else ["max"]
    ultimo = None
    for intento in range(3):  # Yahoo a veces corta: reintentos con espera
        for period in periodos:
            try:
                df = yf.Ticker(symbol).history(
                    period=period, interval=interval, auto_adjust=False, actions=False
                )
                if len(df):
                    return df[["Open", "High", "Low", "Close", "Volume"]]
                ultimo = RuntimeError("sin datos")
            except Exception as e:
                ultimo = e
        time.sleep(3 * (intento + 1))
    raise RuntimeError(f"{symbol} {interval}: {ultimo}")


PROVEEDOR = proveedor_yfinance

# -------------------------------------------------------------------- utiles


def limpiar(df: pd.DataFrame) -> pd.DataFrame:
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    df = df[(df["High"] >= df["Low"]) & (df["Close"] > 0)]
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df


def sin_zona(df: pd.DataFrame) -> pd.DataFrame:
    """Quita la zona horaria conservando la hora local del mercado."""
    if df.index.tz is not None:
        df = df.copy()
        df.index = df.index.tz_localize(None)
    return df


def agrupar(diario: pd.DataFrame, regla: str) -> pd.DataFrame:
    agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    g = diario.resample(regla, label="left", closed="left").agg(agg)
    return g.dropna(subset=["Open"])


def a_barras(df: pd.DataFrame, intradia: bool) -> list:
    barras = []
    for ts, r in df.iterrows():
        if intradia:
            # hora local del mercado guardada como si fuera UTC (asi la muestra el grafico)
            t = int(ts.replace(tzinfo=timezone.utc).timestamp())
        else:
            t = ts.strftime("%Y-%m-%d")
        barras.append(
            [t, round(float(r.Open), 4), round(float(r.High), 4),
             round(float(r.Low), 4), round(float(r.Close), 4), int(r.Volume or 0)]
        )
    return barras


def guardar(symbol: str, tf: str, barras: list) -> None:
    carpeta = DATA / symbol
    carpeta.mkdir(parents=True, exist_ok=True)
    doc = {
        "symbol": symbol,
        "tf": tf,
        "actualizado": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "columnas": ["t", "o", "h", "l", "c", "v"],
        "barras": barras,
    }
    (carpeta / f"{tf}.json").write_text(json.dumps(doc, separators=(",", ":")))


def fusionar_60m(symbol: str, nuevas: list) -> list:
    """Une las barras nuevas con las ya guardadas: el historico de 60m crece con el tiempo."""
    f = DATA / symbol / "60m.json"
    por_t = {}
    if f.exists():
        try:
            por_t = {b[0]: b for b in json.loads(f.read_text())["barras"]}
        except Exception:
            por_t = {}
    for b in nuevas:
        por_t[b[0]] = b
    return [por_t[t] for t in sorted(por_t)]


def actualizar(symbol: str) -> None:
    diario = limpiar(sin_zona(PROVEEDOR(symbol, "1d")))
    if len(diario) < 50:
        raise RuntimeError(f"{symbol}: datos diarios insuficientes ({len(diario)} barras)")
    diario.index = diario.index.normalize()

    try:
        h60 = limpiar(sin_zona(PROVEEDOR(symbol, "60m")))
    except Exception as e:  # sin 60m no se pierde el resto
        print(f"AVISO {symbol}: 60m no disponible ({e})", file=sys.stderr)
        h60 = None
    # Sin inventar datos: si Yahoo aún no ha publicado la vela diaria de la última sesión (pasa con Madrid),
    # se avisa y se espera a la siguiente actualización (hay una segunda pasada por la mañana).
    if h60 is not None and len(h60) and h60.index.normalize().max() > diario.index[-1]:
        print(f"AVISO {symbol}: falta la vela diaria del {h60.index.normalize().max().date()} (Yahoo aún no la ha publicado)",
              file=sys.stderr)

    guardar(symbol, "1d", a_barras(diario, False))
    guardar(symbol, "1wk", a_barras(agrupar(diario, "W-MON"), False))
    guardar(symbol, "1mo", a_barras(agrupar(diario, "MS"), False))

    nuevas_60 = a_barras(h60, True) if h60 is not None else []
    barras_60 = fusionar_60m(symbol, nuevas_60)
    if barras_60:
        guardar(symbol, "60m", barras_60)

    print(f"OK {symbol}: diario {len(diario)} barras "
          f"({diario.index[0].date()} -> {diario.index[-1].date()}), 60m {len(barras_60)} barras")


def main() -> int:
    simbolos = sys.argv[1:] or [t["symbol"] for t in json.loads(CONFIG.read_text())]
    errores = 0
    for s in simbolos:
        try:
            actualizar(s)
        except Exception as e:  # un valor que falla no para al resto
            errores += 1
            print(f"ERROR {s}: {e}", file=sys.stderr)
        time.sleep(0.5)
    print(f"Terminado: {len(simbolos) - errores} correctos, {errores} con error")
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
