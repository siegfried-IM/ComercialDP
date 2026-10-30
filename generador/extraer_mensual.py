# -*- coding: utf-8 -*-
"""Extractor MENSUAL: conteos de cada mes (SIE / 80-20 / Total Mercado) por producto y región,
para TODOS los meses de la app. Con ellos el tablero arma las ventanas como PROMEDIO DE MESES
(el DP% y el DF% de cada mes, promediados) además del acumulado de las medidas maestras
(farmacias que compraron al menos una vez en toda la ventana).

Es la consulta de extraer_ventanas.py con la ventana MEN (offset 0): misma medida maestra
parametrizada, mismas selecciones, check_selection y sello de reload por (mes, producto).

Salida: datos/mensual.json
  datos[mes][producto][region] = {"s":SIE, "p":80-20, "t":TotMdo}   (region incluye "TOTAL")
  sellos[mes][producto] = ReloadTime() con que se leyó

Los (mes, producto) que historico_win.json ya tiene con la ventana MEN se COPIAN con su sello
en vez de consultarse: es el mismo número. Si historico_win lo tiene con el reload vigente y
mensual.json con uno anterior, la copia se refresca. --sin-copiar los consulta igual (toda la
serie en el reload vigente). Va del mes más viejo al más nuevo: el próximo reload saca de la app
el más viejo, y mensual.json lo conserva.

Serial y resumible (guarda por producto). Uso:
  python extraer_mensual.py                       # todos los meses de la app que falten
  python extraer_mensual.py 24297 24298           # meses puntuales
  python extraer_mensual.py --productos "Acemuk,Trip D3"
  python extraer_mensual.py --sin-copiar
Con MENSUAL_STORE=<ruta> escribe en otro archivo (para probar sin tocar datos/).
"""
import os, sys, time
from collections import defaultdict
from qlik_client import connect_retry
import config as C
# El guardado indentado de historico.json: mensual.json también se commitea, porque conserva
# meses que la app pierde en cada reload (guarda 24).
from extraer import load_json, save_json, num

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "datos")
STORE = os.environ.get("MENSUAL_STORE") or os.path.join(DATA, "mensual.json")
WINSTORE = os.path.join(DATA, "historico_win.json")
MAPJS = os.path.join(DATA, "mapeo_mercados.json")
MEDIDAS = (C.MEAS["sie_act"], C.MEAS["p80_act"], C.MEAS["totmdo_act"])


def copiar_de_ventanas(store, meses, productos, sello_actual):
    """Copia la ventana MEN de historico_win.json a los (mes, producto) que falten, y a los
    que historico_win tiene con el reload vigente y mensual.json con uno anterior (la
    actualización mensual re-extrae P-1, P-3...): si no, acumulado y promedio mostrarían
    dos versiones del mismo mes."""
    win = load_json(WINSTORE, {})
    n = 0
    for P in meses:
        pk = str(P)
        for prod in productos:
            d = win.get("datos", {}).get(pk, {}).get(prod)
            sello = win.get("sellos", {}).get(pk, {}).get(prod)
            if not d or not d.get("_ok") or not sello:
                continue
            ya = store["datos"].get(pk, {}).get(prod, {}).get("_ok")
            viejo = store.get("sellos", {}).get(pk, {}).get(prod) != sello_actual
            if ya and not (sello == sello_actual and viejo):
                continue
            out = {reg: dict(w["MEN"]) for reg, w in d.items()
                   if reg != "_ok" and isinstance(w, dict) and "MEN" in w}
            if "TOTAL" not in out:
                continue
            out["_ok"] = True
            store["datos"].setdefault(pk, {})[prod] = out
            store.setdefault("sellos", {}).setdefault(pk, {})[prod] = sello
            n += 1
    return n


def main():
    args = sys.argv[1:]
    copiar = "--sin-copiar" not in args
    mapping = load_json(MAPJS, None)
    if "--productos" in args:
        pedidos_prod = [p.strip() for p in args[args.index("--productos") + 1].split(",")]
        faltan = [p for p in pedidos_prod if p not in mapping]
        if faltan:
            sys.exit(f"no están en mapeo_mercados.json: {faltan}")
        mapping = {p: mapping[p] for p in pedidos_prod}
    pedidos = [int(a) for a in args if a.isdigit()]

    q, doc = connect_retry(); q.clear_all(doc)

    def mdef(mid):
        h = q.rpc("GetMeasure", doc, [mid])["qReturn"]["qHandle"]
        return q.rpc("GetLayout", h, [])["qLayout"]["qMeasure"]["qDef"]
    # ventana MEN: el offset de la medida trimestral (-2) pasa a 0, como en extraer_ventanas.win()
    ms = [{"qDef": {"qDef": mdef(mid).replace("-2)", "-0)")}} for mid in MEDIDAS]

    min_p = int(round(float(str(q.evaluate(doc, "=Min([AñoMes_Num])")).replace(",", "."))))
    max_p = int(round(float(str(q.evaluate(doc, "=Max([AñoMes_Num])")).replace(",", "."))))
    sello = q.reload_time(doc)
    # El mes no se trunca en el borde de la app (el trimestre sí): entran todos, min incluido.
    meses = sorted(pedidos) if pedidos else list(range(min_p, max_p + 1))
    fuera = [P for P in meses if not min_p <= P <= max_p]
    if fuera:
        sys.exit(f"meses fuera de la app ({C.periodo_label(min_p)}..{C.periodo_label(max_p)}): {fuera}")

    store = load_json(STORE, {"meta": {}, "datos": {}, "sellos": {}})
    store["meta"] = {"schema": "mensual", "ventana": "MEN", "min_periodo": min_p, "max_periodo": max_p}
    if copiar:
        n = copiar_de_ventanas(store, meses, list(mapping), sello)
        save_json(STORE, store)
        print(f"copiados de historico_win.json: {n} (mes, producto)")

    pend = [(P, prod) for P in meses for prod in mapping
            if not store["datos"].get(str(P), {}).get(prod, {}).get("_ok")]
    print(f"App {C.periodo_label(min_p)}..{C.periodo_label(max_p)} · reload {sello} · "
          f"meses: {len(meses)} · a consultar: {len(pend)} (mes, producto)")
    t0 = time.time()
    for k, (P, prod) in enumerate(pend, 1):
        pk = str(P)
        done = store["datos"].setdefault(pk, {})
        sellos = store.setdefault("sellos", {}).setdefault(pk, {})
        t1 = time.time(); rows = None
        for attempt in range(3):
            try:
                q.clear_all(doc)
                q.select_text(doc, "TipoMercado", C.TIPO_MERCADO)
                q.select_num(doc, "AñoMes_Num", range(min_p, P + 1))
                q.select_text(doc, "DescripcionMercado", mapping[prod])
                q.check_selection(doc, "DescripcionMercado")
                obj = {"qInfo": {"qType": "v"}, "qHyperCubeDef": {
                    "qDimensions": [{"qLibraryId": C.DIM_REGIONCUP, "qNullSuppression": True}],
                    "qMeasures": ms,
                    "qInitialDataFetch": [{"qLeft": 0, "qTop": 0, "qWidth": 1 + len(ms), "qHeight": 60}]}}
                h = q.rpc("CreateSessionObject", doc, [obj])["qReturn"]["qHandle"]
                rows = q.rpc("GetLayout", h, [])["qLayout"]["qHyperCube"]["qDataPages"][0]["qMatrix"]
                break
            except Exception as e:
                print(f"  {prod} intento {attempt+1}: {e}")
                try: q.close()
                except Exception: pass
                q, doc = connect_retry(pausa_inicial=3)
        if rows is None:
            done[prod] = {"_ok": False}; sellos.pop(prod, None); save_json(STORE, store); continue
        ahora = q.reload_time(doc)
        if ahora != sello:
            save_json(STORE, store)
            sys.exit(f"LA APP RECARGO durante la extracción ({C.periodo_label(P)} / {prod}): "
                     f"{sello} -> {ahora}. Ese producto no se guarda; relanzar toma el reload nuevo.")
        agg = defaultdict(lambda: [0.0, 0.0, 0.0])   # region -> [s, p, t]
        for r in rows:
            region = C.REGIONCUP_TO_REGION.get(r[0]["qText"])
            if not region:
                continue
            for j in range(3):
                agg[region][j] += num(r[j + 1])
        tot = [sum(v[j] for v in agg.values()) for j in range(3)]
        out = {reg: {"s": round(v[0], 1), "p": round(v[1], 1), "t": round(v[2], 1)} for reg, v in agg.items()}
        out["TOTAL"] = {"s": round(tot[0], 1), "p": round(tot[1], 1), "t": round(tot[2], 1)}
        out["_ok"] = True
        done[prod] = out
        sellos[prod] = sello
        save_json(STORE, store)
        dp = tot[0] / tot[1] if tot[1] else 0
        falta = (time.time() - t0) / k * (len(pend) - k) / 60
        print(f"  [{C.periodo_label(P)}] {k:>4}/{len(pend)} {prod:<14} DP%MEN={dp:5.3f} "
              f"({time.time()-t1:.0f}s · faltan ~{falta:.0f} min)")
    print(f"Listo en {(time.time()-t0)/60:.1f} min")
    q.close()


if __name__ == "__main__":
    main()
