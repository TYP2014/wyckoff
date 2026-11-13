# Buscador Wyckoff – versión 1 (datos + graficador de 1 acción)

Herramienta personal de apoyo a la decisión. No ejecuta órdenes ni es asesoramiento financiero.

## Qué hay
- `scripts/update_data.py` – descarga velas OHLC + volumen (yfinance) y las guarda en `data/<SÍMBOLO>/`:
  `1d`, `1wk`, `1mo` (todo el histórico; semanal y mensual se calculan desde el diario) y `60m` (~2 años, se va acumulando).
- `.github/workflows/actualizar-datos.yml` – actualización automática de lunes a viernes a las 22:30 UTC, y manual.
- `index.html` – graficador (Lightweight Charts 5.3, copia local en `lib/`): velas + volumen con media de 20,
  60m / D / S / M, tendencia por temporalidad, Fibonacci automático y manual, soportes y resistencias.
- `config/tickers.json` – valor a seguir (ahora AAPL). Para España usar el sufijo de Yahoo, p. ej. `ITX.MC`.

## Puesta en marcha
1. Subir todo a un repositorio de GitHub (público, necesario para GitHub Pages gratis).
2. Settings → Actions → General → Workflow permissions → **Read and write**.
3. Actions → «Actualizar datos» → **Run workflow** (primera descarga).
4. Settings → Pages → Deploy from a branch → `main` / root.

## Criterios de cálculo
- **Giros (zigzag):** un giro se confirma cuando el precio retrocede más de N × ATR(14) desde el extremo
  (Finos 3, Medios 5, Amplios 8). El último punto es provisional.
- **Tendencia:** máximos y mínimos crecientes = alcista; decrecientes = bajista; mixto = rango.
- **Fibonacci automático:** último tramo del zigzag (A = giro anterior, B = extremo en curso). Zona 38,2–61,8 % resaltada.
- **Precios:** ajustados por splits, no por dividendos (como en el bróker).
- Soportes/resistencias y Fibonacci manual se guardan en el navegador (no se sincronizan entre dispositivos).
