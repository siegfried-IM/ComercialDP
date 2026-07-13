# -*- coding: utf-8 -*-
"""Extractor a nivel DEPARTAMENTO (provincia, partido) para las ventanas.

Uso:
  python extraer_depto.py MEN,TRI,SEM,MAT,YTD 24317 24305     # ventanas del mapa (actual+año ant)
  python extraer_depto.py TRI all                             # histórico Trimestre (evolución x depto)

Salida: datos/depto_win.json  ->  datos[periodo][producto][geokey][ventana] = {s,p,t}
(geokey = clave normalizada provincia|partido, unida al geojson en el generador)
Serial, resumible (checkpoint por producto).
"""
import json, os, sys, time
from collections import defaultdict
from qlik_client import Qix
import config as C
import geo_match

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "datos")
STORE = os.path.join(DATA, "depto_win.json")
MAPJS = os.path.join(DATA, "mapeo_mercados.json")

SIE_ID = "79f5a08e-33dc-4638-a92e-d29ef3234728"
P80_ID = "69e8649d-3189-457b-98b1-c5d0dbd78da5"
TOT_ID = "sCCWeD"
DIM_PROV = "1949a1bb-36fe-4f21-b7fb-f03e3380760e"
DIM_PART = "3c30cde4-48f7-4433-91b7-e5caf333f6c7"
WIN_LEN = {"MEN": 0, "TRI": 2, "SEM": 5, "MAT": 11}


def load_json(p, d): return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else d
def save_json(p, o):
    """Guardado atómico resistente a locks transitorios (OneDrive/AV/lectores)."""
    os.makedirs(os.path.dirname(p), exist_ok=True); t = p + ".tmp"
    with open(t, "w", encoding="utf-8") as fh:
        json.dump(o, fh, ensure_ascii=False)
    for attempt in range(10):
        try:
            os.replace(t, p); return
        except PermissionError:
            time.sleep(min(2.0 * (attempt + 1), 10))
    for attempt in range(10):
        try:
            with open(p, "w", encoding="utf-8") as fh:
                json.dump(o, fh, ensure_ascii=False)
            break
        except PermissionError:
            time.sleep(min(2.0 * (attempt + 1), 10))
    try: os.remove(t)
    except OSError: pass
def num(c):
    v = c.get("qNum"); return v if isinstance(v, (int, float)) else 0.0
def month_of(p):
    m = p % 12; return 12 if m == 0 else m


def main():
    wins = sys.argv[1].split(",")
    mapping = json.load(open(MAPJS, encoding="utf-8"))
    q = Qix(); doc = q.open_doc(); q.clear_all(doc)
    def mdef(mid):
        h = q.rpc("GetMeasure", doc, [mid])["qReturn"]["qHandle"]
        return q.rpc("GetLayout", h, [])["qLayout"]["qMeasure"]["qDef"]
    sie_def, p80_def, tot_def = mdef(SIE_ID), mdef(P80_ID), mdef(TOT_ID)
    win = lambda d, S: d.replace("-2)", "-%d)" % S)
    min_p = int(round(float(str(q.evaluate(doc, "=Min([AñoMes_Num])")).replace(",", "."))))
    max_p = int(round(float(str(q.evaluate(doc, "=Max([AñoMes_Num])")).replace(",", "."))))
    if sys.argv[2] == "all":
        periods = list(range(max_p, min_p + 1, -1))
    else:
        periods = [int(x) for x in sys.argv[2:]]
    store = load_json(STORE, {"meta": {}, "datos": {}})
    store["meta"] = {"min_periodo": min_p, "max_periodo": max_p}

    def offset(w, P): return (month_of(P) - 1) if w == "YTD" else WIN_LEN[w]

    print(f"DEPTO | ventanas {wins} | períodos {[C.periodo_label(p) for p in periods]}")
    t0 = time.time()
    for P in periods:
        pk = str(P); store["datos"].setdefault(pk, {}); done = store["datos"][pk]
        ms, order = [], []
        for w in wins:
            S = offset(w, P)
            ms += [{"qDef": {"qDef": win(sie_def, S)}}, {"qDef": {"qDef": win(p80_def, S)}}, {"qDef": {"qDef": win(tot_def, S)}}]
            order += [(w, 0), (w, 1), (w, 2)]
        for i, (prod, merc) in enumerate(mapping.items(), 1):
            if prod in done and done[prod].get("_ok"): continue
            rows = None; t1 = time.time()
            for att in range(3):
                try:
                    q.clear_all(doc); q.select_text(doc, "TipoMercado", C.TIPO_MERCADO)
                    q.select_num(doc, "AñoMes_Num", range(min_p, P + 1)); q.select_text(doc, "DescripcionMercado", merc)
                    W = 2 + len(ms)
                    PAGE = max(1, 9000 // W)   # Qlik limita ~10k celdas por página: W(17)*529 < 10000
                    obj = {"qInfo": {"qType": "v"}, "qHyperCubeDef": {
                        "qDimensions": [{"qLibraryId": DIM_PROV}, {"qLibraryId": DIM_PART}],
                        "qMeasures": ms, "qInitialDataFetch": [{"qLeft": 0, "qTop": 0, "qWidth": W, "qHeight": PAGE}]}}
                    h = q.rpc("CreateSessionObject", doc, [obj])["qReturn"]["qHandle"]
                    lay = q.rpc("GetLayout", h, [])["qLayout"]["qHyperCube"]
                    dp0 = lay.get("qDataPages") or []
                    rows = dp0[0]["qMatrix"] if dp0 else []
                    top = len(rows); total = lay["qSize"]["qcy"]
                    while top < total:
                        pgs = q.rpc("GetHyperCubeData", h, ["/qHyperCubeDef", [{"qLeft": 0, "qTop": top, "qWidth": W, "qHeight": PAGE}]]).get("qDataPages") or []
                        pg = pgs[0]["qMatrix"] if pgs else []
                        if not pg: break
                        rows += pg; top += len(pg)
                    break
                except Exception as e:
                    print(f"  {prod} intento {att+1}: {e}")
                    try: q.close()
                    except Exception: pass
                    # Reconexión resistente a blips de red/DNS (getaddrinfo): reintenta
                    # con backoff en vez de crashear todo el run.
                    for _rc in range(40):
                        try:
                            time.sleep(3 if _rc == 0 else 15)
                            q = Qix(); doc = q.open_doc(); break
                        except Exception as e2:
                            print(f"    reconexión falló ({e2}); reintento en 15s ({_rc+1}/40)")
                    else:
                        raise RuntimeError("no se pudo reconectar tras varios intentos")
            if rows is None:
                done[prod] = {"_ok": False}; save_json(STORE, store); continue
            agg = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0, 0.0]))
            for r in rows:
                k = geo_match.key(r[0]["qText"], r[1]["qText"])
                for idx, (w, j) in enumerate(order):
                    agg[k][w][j] += num(r[idx + 2])
            done[prod] = {k: {w: {"s": round(v[0], 1), "p": round(v[1], 1), "t": round(v[2], 1)} for w, v in wv.items()} for k, wv in agg.items()}
            done[prod]["_ok"] = True
            save_json(STORE, store)
            print(f"  [{C.periodo_label(P)}] {i:>2}/{len(mapping)} {prod:<14} deptos={len(agg)} ({time.time()-t1:.0f}s)")
    print(f"Listo en {(time.time()-t0)/60:.1f} min")
    q.close()


if __name__ == "__main__":
    main()
