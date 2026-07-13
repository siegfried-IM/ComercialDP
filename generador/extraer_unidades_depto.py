# -*- coding: utf-8 -*-
"""Unidades por DEPARTAMENTO (provincia, partido) para el ranking del mapa depto.
Mismas medidas que extraer_unidades.py (tot = mercado, gap = potencial no capturado),
5 ventanas, período actual. Salida: datos/unidades_depto.json
  datos[periodo][producto][geokey][ventana] = {"tot":..., "gap":...}

Uso:  python extraer_unidades_depto.py            # período actual
      python extraer_unidades_depto.py 24317
"""
import json, os, sys, time
from collections import defaultdict
from qlik_client import Qix
import config as C
import geo_match

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "datos")
STORE = os.path.join(DATA, "unidades_depto.json")
MAPJS = os.path.join(DATA, "mapeo_mercados.json")
DIM_PROV = "1949a1bb-36fe-4f21-b7fb-f03e3380760e"
DIM_PART = "3c30cde4-48f7-4433-91b7-e5caf333f6c7"
FIXED_WIN = {"MEN": 0, "TRI": 2, "SEM": 5, "MAT": 11}


def load_json(p, d): return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else d
def save_json(p, o):
    os.makedirs(os.path.dirname(p), exist_ok=True); t = p + ".tmp"
    with open(t, "w", encoding="utf-8") as fh:
        json.dump(o, fh, ensure_ascii=False)
    for att in range(10):
        try: os.replace(t, p); return
        except PermissionError: time.sleep(min(2.0 * (att + 1), 10))
    for att in range(10):
        try:
            with open(p, "w", encoding="utf-8") as fh:
                json.dump(o, fh, ensure_ascii=False)
            break
        except PermissionError: time.sleep(min(2.0 * (att + 1), 10))
    try: os.remove(t)
    except OSError: pass
def num(c):
    v = c.get("qNum"); return v if isinstance(v, (int, float)) else 0.0
def month_of(p):
    m = p % 12; return 12 if m == 0 else m


def wset(S, sie=False):
    lab = "DescripcionLaboratorioIMS={'SIEGFRIED'}," if sie else ""
    return ("{<" + lab + "Flag_Rollback={0},MesesRollBack=,DescMercadoTipo=,"
            "[AñoMes_Num]={\">=$(=max(AñoMes_Num)-%d)<=$(=max(AñoMes_Num)-0)\"}>}" % S)
def u_tot(S): return "sum(%s MensualUnidades)" % wset(S)
def u_sie(S): return "sum(%s MensualUnidades)" % wset(S, True)
def u_gap(S): return "sum(aggr(if(sum(%s MensualUnidades)=0, sum(%s MensualUnidades), 0), CPA))" % (wset(S, True), wset(S))
FLD_IDX = {"tot": 0, "gap": 1, "sie": 2}


def main():
    mapping = json.load(open(MAPJS, encoding="utf-8"))
    q = Qix(); doc = q.open_doc(); q.clear_all(doc)
    min_p = int(round(float(str(q.evaluate(doc, "=Min([AñoMes_Num])")).replace(",", "."))))
    max_p = int(round(float(str(q.evaluate(doc, "=Max([AñoMes_Num])")).replace(",", "."))))
    periods = [int(x) for x in sys.argv[1:]] or [max_p]

    def windows_for(P):
        w = dict(FIXED_WIN); w["YTD"] = month_of(P) - 1; return w

    store = load_json(STORE, {"meta": {}, "datos": {}})
    store["meta"] = {"schema": "unidades_depto", "min_periodo": min_p, "max_periodo": max_p}
    print(f"UNIDADES depto | períodos {[C.periodo_label(p) for p in periods]}")
    t0 = time.time()
    for P in periods:
        pk = str(P); store["datos"].setdefault(pk, {}); done = store["datos"][pk]
        ms, order = [], []
        for wn, S in windows_for(P).items():
            ms.append({"qDef": {"qDef": u_tot(S)}}); order.append((wn, "tot"))
            ms.append({"qDef": {"qDef": u_gap(S)}}); order.append((wn, "gap"))
            ms.append({"qDef": {"qDef": u_sie(S)}}); order.append((wn, "sie"))
        W = 2 + len(ms); PAGE = max(1, 9000 // W)
        for i, (prod, merc) in enumerate(mapping.items(), 1):
            if prod in done and done[prod].get("_ok"):
                continue
            rows = None; t1 = time.time()
            for att in range(3):
                try:
                    q.clear_all(doc); q.select_text(doc, "TipoMercado", C.TIPO_MERCADO)
                    q.select_num(doc, "AñoMes_Num", range(min_p, P + 1)); q.select_text(doc, "DescripcionMercado", merc)
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
                    time.sleep(3); q = Qix(); doc = q.open_doc()
            if rows is None:
                done[prod] = {"_ok": False}; save_json(STORE, store); continue
            agg = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0, 0.0]))  # geokey->win->[tot,gap,sie]
            for r in rows:
                k = geo_match.key(r[0]["qText"], r[1]["qText"])
                for idx, (wn, fld) in enumerate(order):
                    v = num(r[idx + 2]); j = FLD_IDX[fld]
                    agg[k][wn][j] += v
            done[prod] = {k: {w: {"tot": round(v[0], 1), "gap": round(v[1], 1), "sie": round(v[2], 1)} for w, v in wv.items()} for k, wv in agg.items()}
            done[prod]["_ok"] = True
            save_json(STORE, store)
            print(f"  [{C.periodo_label(P)}] {i:>2}/{len(mapping)} {prod:<14} deptos={len(agg)} ({time.time()-t1:.0f}s)")
    print(f"Listo en {(time.time()-t0)/60:.1f} min")
    q.close()


if __name__ == "__main__":
    main()
