# -*- coding: utf-8 -*-
"""Unidades Siegfried por PRESENTACIÓN (DescripcionProductoIMS), ventana MAT.

Para qué: el tablero razona por MERCADO (Acemuk, Magnus…), pero la lista de
precios tiene un PSL por presentación, y dentro de un mismo mercado los precios
llegan a diferir 45x. Sin el mix de unidades por presentación, valorizar un
mercado a "un" PSL es elegir un número entre un piso y un techo que se llevan
6,3x. Este mix es el ponderador que convierte esa estimación en una cuenta.

Salida: ../datos/presentaciones.json
    datos[producto][presentación] = unidades MAT de Siegfried

Serial y resumible (checkpoint por producto), como el resto de los extractores.
Uso:  python extraer_presentaciones.py
"""
import json, os, sys, time
from qlik_client import Qix, connect_retry
import config as C

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "datos")
STORE = os.path.join(DATA, "presentaciones.json")
MAPJS = os.path.join(DATA, "mapeo_mercados.json")

# MAT de Siegfried: 12 meses hasta el último disponible
WSET = ("{<DescripcionLaboratorioIMS={'SIEGFRIED'},Flag_Rollback={0},MesesRollBack=,"
        "DescMercadoTipo=,[AñoMes_Num]={\">=$(=max(AñoMes_Num)-11)<=$(=max(AñoMes_Num))\"}>}")


def save_json(p, o):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    t = p + ".tmp"
    with open(t, "w", encoding="utf-8") as fh:
        json.dump(o, fh, ensure_ascii=False, indent=1)
    for i in range(10):
        try:
            os.replace(t, p); return
        except PermissionError:
            time.sleep(min(2.0 * (i + 1), 10))
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(o, fh, ensure_ascii=False, indent=1)


def main():
    mapping = json.load(open(MAPJS, encoding="utf-8"))
    store = {"meta": {}, "datos": {}}
    if os.path.exists(STORE):
        store = json.load(open(STORE, encoding="utf-8"))
    q, doc = connect_retry()
    q.clear_all(doc)
    max_p = int(round(float(str(q.evaluate(doc, "=Max([AñoMes_Num])")).replace(",", "."))))
    min_p = int(round(float(str(q.evaluate(doc, "=Min([AñoMes_Num])")).replace(",", "."))))
    store["meta"] = {"ventana": "MAT", "hasta": max_p, "label": C.periodo_label(max_p),
                     "campo": "DescripcionProductoIMS", "laboratorio": "SIEGFRIED"}
    print(f"Presentaciones Siegfried · MAT hasta {C.periodo_label(max_p)} · {len(mapping)} mercados")
    t0 = time.time()
    for i, (prod, merc) in enumerate(mapping.items(), 1):
        if prod in store["datos"]:
            continue
        rows = None
        for intento in range(3):
            try:
                q.clear_all(doc)
                q.select_text(doc, "TipoMercado", C.TIPO_MERCADO)
                q.select_num(doc, "AñoMes_Num", range(min_p, max_p + 1))
                q.select_text(doc, "DescripcionMercado", merc)
                q.check_selection(doc, "DescripcionMercado")
                obj = {"qInfo": {"qType": "p"}, "qHyperCubeDef": {
                    "qDimensions": [{"qDef": {"qFieldDefs": ["DescripcionProductoIMS"]}}],
                    "qMeasures": [{"qDef": {"qDef": "sum(%s MensualUnidades)" % WSET},
                                   "qSortBy": {"qSortByNumeric": -1}}],
                    "qInitialDataFetch": [{"qLeft": 0, "qTop": 0, "qWidth": 2, "qHeight": 200}]}}
                h = q.rpc("CreateSessionObject", doc, [obj])["qReturn"]["qHandle"]
                pg = q.rpc("GetLayout", h, [])["qLayout"]["qHyperCube"].get("qDataPages") or []
                rows = pg[0]["qMatrix"] if pg else []
                break
            except Exception as e:
                print(f"  {prod} intento {intento+1}: {str(e)[:70]}")
                try: q.close()
                except Exception: pass
                q, doc = connect_retry(pausa_inicial=3)
        if rows is None:
            print(f"  {prod}: FALLO, se saltea"); continue
        d = {}
        for r in rows:
            u = r[1].get("qNum")
            if isinstance(u, (int, float)) and u > 0:
                d[r[0]["qText"]] = round(u, 1)
        store["datos"][prod] = d
        save_json(STORE, store)
        print(f"  {i:>2}/{len(mapping)} {prod:<14} {len(d):>2} presentaciones · "
              f"{sum(d.values()):>12,.0f} u.")
    save_json(STORE, store)
    print(f"Listo en {(time.time()-t0)/60:.1f} min -> {STORE}")
    q.close()


if __name__ == "__main__":
    main()
