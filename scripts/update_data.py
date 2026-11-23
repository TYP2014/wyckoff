#!/usr/bin/env python3
"""Descarga velas OHLC + volumen y las guarda en data/<SIMBOLO>/<temporalidad>.json

Temporalidades: 60m (historico gratuito ~2 anos, se va acumulando), 1d, 1wk, 1mo;
5m (Yahoo solo da ~60 dias; se va acumulando) y 15m / 30m agrupados desde el 5m.
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
    periodos = (["730d", "1y", "6mo", "3mo", "1mo"] if interval == "60m"
                else ["60d", "30d", "5d"] if interval == "5m" else ["max"])
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


def proveedor_tiingo(symbol: str) -> pd.DataFrame:
    """Velas diarias de Tiingo (solo EE. UU.; plan gratuito con registro). Clave en la variable TIINGO_TOKEN.

    Tiingo da el precio bruto y el factor de split de cada día; aquí se ajusta solo por splits
    (como Yahoo con auto_adjust=False) para que el histórico cuadre. El volumen se ajusta igual.
    """
    import os
    import requests

    token = os.environ.get("TIINGO_TOKEN", "").strip()
    if not token:
        raise RuntimeError("sin TIINGO_TOKEN")
    url = f"https://api.tiingo.com/tiingo/daily/{symbol.lower()}/prices"
    ultimo = None
    for intento in range(3):
        try:
            r = requests.get(url, params={"startDate": "1980-01-01", "token": token}, timeout=60)
            if r.status_code == 200:
                filas = r.json()
                if filas:
                    break
                ultimo = RuntimeError("sin datos")
            else:
                ultimo = RuntimeError(f"HTTP {r.status_code}: {r.text[:120]}")
        except Exception as e:
            ultimo = e
        time.sleep(5 * (intento + 1))
    else:
        raise RuntimeError(f"Tiingo {symbol}: {ultimo}")
    df = pd.DataFrame(filas)
    df.index = pd.DatetimeIndex(pd.to_datetime(df["date"]).dt.tz_localize(None).dt.normalize().values)
    # factor acumulado de los splits posteriores a cada día
    sf = df["splitFactor"].astype(float).fillna(1.0)
    fut = sf[::-1].cumprod()[::-1].shift(-1).fillna(1.0)
    out = pd.DataFrame({
        "Open": df["open"] / fut, "High": df["high"] / fut, "Low": df["low"] / fut,
        "Close": df["close"] / fut, "Volume": (df["volume"] * fut).round(),
    }, index=df.index)
    return out


def es_usa(symbol: str) -> bool:
    return "." not in symbol and "=" not in symbol and not symbol.startswith("^")


def diario_usa(symbol: str) -> pd.DataFrame:
    """EE. UU.: Tiingo si hay clave (más fiable); Yahoo si no hay clave, si falla o si va más atrasado."""
    yh = None
    try:
        yh = limpiar(sin_zona(proveedor_yfinance(symbol, "1d")))
        yh.index = yh.index.normalize()
    except Exception as e:
        print(f"AVISO {symbol}: Yahoo diario no disponible ({e})", file=sys.stderr)
    try:
        ti = limpiar(proveedor_tiingo(symbol))
    except Exception as e:
        if "sin TIINGO_TOKEN" not in str(e):
            print(f"AVISO {symbol}: Tiingo no disponible, se usa Yahoo ({e})", file=sys.stderr)
        if yh is None:
            raise
        return yh
    if yh is not None and len(yh):
        # comparación con Yahoo en las últimas 250 sesiones comunes (para validar la fuente)
        com = ti.index.intersection(yh.index)[-250:]
        if len(com):
            dc = ((ti.loc[com, "Close"] / yh.loc[com, "Close"] - 1).abs() * 100)
            rv = (ti.loc[com, "Volume"] / yh.loc[com, "Volume"].replace(0, float("nan")))
            print(f"CMP {symbol}: {len(com)} sesiones; cierre dif. media {dc.mean():.3f} % (máx {dc.max():.2f} %); "
                  f"volumen Tiingo/Yahoo mediana {rv.median():.3f} (p10 {rv.quantile(.1):.3f}, p90 {rv.quantile(.9):.3f})")
        if yh.index[-1] > ti.index[-1]:
            print(f"AVISO {symbol}: Tiingo llega hasta {ti.index[-1].date()} y Yahoo hasta {yh.index[-1].date()}; se usa Yahoo",
                  file=sys.stderr)
            return yh
    return ti

# -------------------------------------------------------------------- utiles


def limpiar(df: pd.DataFrame) -> pd.DataFrame:
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    if "Volume" in df:                       # los índices a veces no traen volumen
        df = df.assign(Volume=df["Volume"].fillna(0))
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


# Maximo de barras guardadas por temporalidad intradia (para no llenar el repositorio)
TOPE = {"60m": 100000, "30m": 6000, "15m": 8000, "5m": 12000}


def fusionar_60m(symbol: str, nuevas: list, tf: str = "60m") -> list:
    """Une las barras nuevas con las ya guardadas: el historico intradia crece con el tiempo."""
    f = DATA / symbol / f"{tf}.json"
    por_t = {}
    if f.exists():
        try:
            por_t = {b[0]: b for b in json.loads(f.read_text())["barras"]}
        except Exception:
            por_t = {}
    for b in nuevas:
        por_t[b[0]] = b
    return [por_t[t] for t in sorted(por_t)][-TOPE[tf]:]


def agrupar_intradia(df: pd.DataFrame, minutos: int) -> pd.DataFrame:
    agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    g = df.resample(f"{minutos}min", label="left", closed="left", origin="start_day").agg(agg)
    return g.dropna(subset=["Open"])


def actualizar(symbol: str, yahoo: str = None) -> None:
    """symbol = carpeta en data/ (y nombre en el graficador); yahoo = ticker real si es distinto
    (índices y futuros: IBEX35 -> ^IBEX, ES -> ES=F)."""
    ys = yahoo or symbol
    if es_usa(ys):
        diario = diario_usa(ys)
    else:
        diario = limpiar(sin_zona(PROVEEDOR(ys, "1d")))
    if len(diario) < 50:
        raise RuntimeError(f"{symbol}: datos diarios insuficientes ({len(diario)} barras)")
    diario.index = diario.index.normalize()

    try:
        h60 = limpiar(sin_zona(PROVEEDOR(ys, "60m")))
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

    # 5 / 15 / 30 min: una sola descarga de 5 min y se agrupa (asi las tres cuadran)
    cortos = {}
    try:
        h5 = limpiar(sin_zona(PROVEEDOR(ys, "5m")))
        for tf, df in (("5m", h5), ("15m", agrupar_intradia(h5, 15)), ("30m", agrupar_intradia(h5, 30))):
            cortos[tf] = fusionar_60m(symbol, a_barras(df, True), tf)
            guardar(symbol, tf, cortos[tf])
    except Exception as e:
        print(f"AVISO {symbol}: 5m no disponible ({e})", file=sys.stderr)

    print(f"OK {symbol}: diario {len(diario)} barras "
          f"({diario.index[0].date()} -> {diario.index[-1].date()}), 60m {len(barras_60)} barras, "
          f"5m {len(cortos.get('5m', []))}, 15m {len(cortos.get('15m', []))}, 30m {len(cortos.get('30m', []))}")


INDICES = {"GSPC": "^GSPC", "IBEX": "^IBEX"}   # referencias para la fuerza relativa


def actualizar_indices() -> None:
    for nombre, ticker in INDICES.items():
        try:
            diario = limpiar(sin_zona(PROVEEDOR(ticker, "1d")))
            diario.index = diario.index.normalize()
            guardar("_indices/" + nombre, "1d", a_barras(diario, False))
            print(f"OK índice {nombre}: {len(diario)} barras")
        except Exception as e:
            print(f"AVISO índice {nombre}: {e}", file=sys.stderr)


def main() -> int:
    if not sys.argv[1:]:
        actualizar_indices()
    lista = json.loads(CONFIG.read_text())
    yahoo = {t["symbol"]: t.get("yahoo") for t in lista}
    simbolos = sys.argv[1:] or [t["symbol"] for t in lista]
    errores = 0
    for s in simbolos:
        try:
            actualizar(s, yahoo.get(s))
        except Exception as e:  # un valor que falla no para al resto
            errores += 1
            print(f"ERROR {s}: {e}", file=sys.stderr)
        time.sleep(0.5)
    print(f"Terminado: {len(simbolos) - errores} correctos, {errores} con error")
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
