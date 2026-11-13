/* Cartera ficticia: órdenes guardadas en el navegador y simuladas contra las velas diarias.
   No se guarda el estado de las posiciones: cada vez se recalcula todo desde las órdenes y los datos.

   Reglas de ejecución (velas diarias):
   - Solo cuentan las sesiones POSTERIORES a la fecha de la orden.
   - A mercado: se compra en la apertura de la siguiente sesión.
   - Limitada (comprar si baja a P): se ejecuta el primer día cuyo mínimo llega a P, al precio P
     (o a la apertura, si abre ya por debajo).
   - Stop de compra (comprar si sube a P): el primer día cuyo máximo llega a P, al precio P
     (o a la apertura, si abre ya por encima).
   - Stop loss y objetivo se vigilan desde la sesión siguiente a la compra. Si abre con hueco más allá
     del nivel, se sale a la apertura. Si el mismo día toca stop y objetivo, se toma el stop.
   - Vender a mercado: se vende en la apertura de la siguiente sesión.
   - Los cambios de stop u objetivo valen desde la sesión siguiente al cambio. */
window.Cartera = (() => {
  'use strict';
  const CLAVE = 'wyk:ordenes';
  const leer = () => { try { return JSON.parse(localStorage.getItem(CLAVE)) || []; } catch (e) { return []; } };
  const guardar = L => { try { localStorage.setItem(CLAVE, JSON.stringify(L)); return true; } catch (e) { return false; } };
  const hoy = () => { const d = new Date(); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); };

  // stop y objetivo en vigor para la sesión `fecha`
  function niveles(o, fecha) {
    let sl = o.sl || null, tp = o.tp || null;
    (o.cambios || []).forEach(c => { if (c.fecha < fecha) { sl = c.sl || null; tp = c.tp || null; } });
    return { sl, tp };
  }

  // barras: [{time:'AAAA-MM-DD', open, high, low, close}]
  function simular(o, barras) {
    const r = { estado: 'pendiente', entrada: null, salida: null, titulos: 0,
      ultimo: barras.length ? barras[barras.length - 1].close : null, fechaUltimo: barras.length ? barras[barras.length - 1].time : null };
    for (const b of barras) {
      if (b.time <= o.fecha) continue;
      if (!r.entrada) {
        if (o.cancelada && b.time > o.cancelada) { r.estado = 'cancelada'; break; }
        let px = null;
        if (o.tipo === 'mercado') px = b.open;
        else if (o.tipo === 'limite' && b.low <= o.precio) px = Math.min(b.open, o.precio);
        else if (o.tipo === 'stop' && b.high >= o.precio) px = Math.max(b.open, o.precio);
        if (px == null) continue;
        r.entrada = { fecha: b.time, precio: px };
        r.titulos = o.titulos || Math.floor(o.importe / px);
        r.estado = 'abierta';
        continue;                       // las salidas se vigilan desde la sesión siguiente
      }
      const n = niveles(o, b.time);
      if (o.venta && b.time > o.venta) r.salida = { fecha: b.time, precio: b.open, motivo: 'Venta a mercado' };
      else if (n.sl && b.low <= n.sl) r.salida = { fecha: b.time, precio: Math.min(b.open, n.sl), motivo: 'Stop loss' };
      else if (n.tp && b.high >= n.tp) r.salida = { fecha: b.time, precio: Math.max(b.open, n.tp), motivo: 'Objetivo' };
      if (r.salida) { r.estado = 'cerrada'; break; }
    }
    if (r.estado === 'pendiente' && o.cancelada) r.estado = 'cancelada';
    const vig = niveles(o, '9999-12-31'); r.sl = vig.sl; r.tp = vig.tp;
    if (r.entrada) {
      const fin = r.salida ? r.salida.precio : r.ultimo;
      r.pyg = (fin - r.entrada.precio) * r.titulos;
      r.pct = (fin / r.entrada.precio - 1) * 100;
      r.invertido = r.entrada.precio * r.titulos;
      r.riesgo = r.sl ? (r.entrada.precio - r.sl) * r.titulos : null;
    }
    return r;
  }

  return { leer, guardar, hoy, niveles, simular };
})();
