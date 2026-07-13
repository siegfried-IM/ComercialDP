# -*- coding: utf-8 -*-
"""Extrae, por mercado (producto) y RegionCUP, para las 5 ventanas del período
actual, dos medidas de UNIDADES:
  - tot: unidades totales del mercado (todos los laboratorios)
  - gap: potencial NO capturado = unidades del mercado en farmacias (CPA) donde
         Siegfried NO está presente en la ventana  [validado: tot = gap + present]

Ambas son aditivas por farmacia, así que se agregan a región/zona/provincia
sumando. Salida: datos/unidades_region.json
  datos[periodo][producto][region][ventana] = {"tot":..., "gap":...}  (+ "TOTAL")

Uso:  python extraer_unidades.py            # período actual, 5 ventanas
      python extraer_unidades.py 24317      # período explícito
"""
import json, os, sys, time
from collections import defaultdict
from qlik_client import Qix
import config as C

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "datos")
STORE = os.path.join(DATA, "unidades_region.json")
MAPJS = os.path.join(DATA, "mapeo_mercados.json")
DIM_REGION = C.DIM_REGIONCUP

FIXED_WIN = {"MEN": 0, "TRI": 2, "SEM": 5, "MAT": 11}   # offset de inicio; YTD = mes-1


def load_json(p, d):
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else d

def save_json(p, o):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(o, fh, ensure_ascii=False)
    for att in range(10):
        try:
            os.replace(tmp, p); return
        except PermissionError:
            time.sleep(min(2.0 * (att + 1), 10))
    for att in range(10):
        try:
            with open(p, "w", encoding="utf-8") as fh:
                json.dump(o, fh, ensure_ascii=False)
            break
        except PermissionError:
            time.sleep(min(2.0 * (att + 1), 10))
    try: os.remove(tmp)
    except OSError: pass

def num(c):
    v = c.get("qNum")
    return v if isinstance(v, (int, float)) else 0.0

def month_of(p):
    m = p % 12
    return 12 if m == 0 else m


def wset(S, sie=False):
    lab = "DescripcionLaboratorioIMS={'SIEGFRIED'}," if sie else ""
    return ("{<" + lab + "Flag_Rollback={0},MesesRollBack=,DescMercadoTipo=,"
            "[AñoMes_Num]={\">=$(=max(AñoMes_Num)-%d)<=$(=max(AñoMes_Num)-0)\"}>}" % S)

def u_tot(S):
    return "sum(%s MensualUnidades)" % wset(S)

def u_sie(S):   # unidades que vende Siegfried
    return "sum(%s MensualUnidades)" % wset(S, True)

def u_gap(S):   # unidades del mercado en farmacias sin Siegfried (validado)
    return "sum(aggr(if(sum(%s MensualUnidades)=0, sum(%s MensualUnidades), 0), CPA))" % (wset(S, True), wset(S))

FLD_IDX = {"tot": 0, "gap": 1, "sie": 2}


def main():
    mapping = load_json(MAPJS, None)
    q = Qix(); doc = q.open_doc(); q.clear_all(doc)
    min_p = int(round(float(str(q.evaluate(doc, "=Min([AñoMes_Num])")).replace(",", "."))))
    max_p = int(round(float(str(q.evaluate(doc, "=Max([AñoMes_Num])")).replace(",", "."))))
    args = [int(a) for a in sys.argv[1:]]
    periods = args if args else [max_p]

    def windows_for(P):
        w = dict(FIXED_WIN); w["YTD"] = month_of(P) - 1; return w

    def measures_for(P):
        ms, order = [], []
        for wn, S in windows_for(P).items():
            ms.append({"qDef": {"qDef": u_tot(S)}}); order.append((wn, "tot"))
            ms.append({"qDef": {"qDef": u_gap(S)}}); order.append((wn, "gap"))
            ms.append({"qDef": {"qDef": u_sie(S)}}); order.append((wn, "sie"))
        return ms, order

    store = load_json(STORE, {"meta": {}, "datos": {}})
    store["meta"] = {"schema": "unidades", "min_periodo": min_p, "max_periodo": max_p}
    print(f"UNIDADES región | períodos {[C.periodo_label(p) for p in periods]} | ventanas {list(windows_for(max_p).keys())}")
    t0 = time.time()
    for P in periods:
        pk = str(P); store["datos"].setdefault(pk, {}); done = store["datos"][pk]
        ms, order = measures_for(P)
        W = 1 + len(ms)
        for i, (prod, merc) in enumerate(mapping.items(), 1):
            if prod in done and done[prod].get("_ok"):
                continue
            t1 = time.time(); rows = None
            for att in range(3):
                try:
                    q.clear_all(doc)
                    q.select_text(doc, "TipoMercado", C.TIPO_MERCADO)
                    q.select_num(doc, "AñoMes_Num", range(min_p, P + 1))
                    q.select_text(doc, "DescripcionMercado", merc)
                    obj = {"qInfo": {"qType": "v"}, "qHyperCubeDef": {
                        "qDimensions": [{"qLibraryId": DIM_REGION, "qNullSuppression": True}],
                        "qMeasures": ms,
                        "qInitialDataFetch": [{"qLeft": 0, "qTop": 0, "qWidth": W, "qHeight": 60}]}}
                    h = q.rpc("CreateSessionObject", doc, [obj])["qReturn"]["qHandle"]
                    lay = q.rpc("GetLayout", h, [])["qLayout"]["qHyperCube"]
                    dp0 = lay.get("qDataPages") or []
                    rows = dp0[0]["qMatrix"] if dp0 else []
                    break
                except Exception as e:
                    print(f"  {prod} intento {att+1}: {e}")
                    try: q.close()
                    except Exception: pass
                    time.sleep(3); q = Qix(); doc = q.open_doc()
            if rows is None:
                done[prod] = {"_ok": False}; save_json(STORE, store); continue
            agg = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0, 0.0]))  # region->win->[tot,gap,sie]
            tot = defaultdict(lambda: [0.0, 0.0, 0.0])
            for r in rows:
                region = C.REGIONCUP_TO_REGION.get(r[0]["qText"])
                if not region:
                    continue
                for idx, (wn, fld) in enumerate(order):
                    v = num(r[idx + 1]); j = FLD_IDX[fld]
                    agg[region][wn][j] += v
                    tot[wn][j] += v
            def cell(v):
                return {"tot": round(v[0], 1), "gap": round(v[1], 1), "sie": round(v[2], 1)}
            out = {reg: {w: cell(v) for w, v in wins.items()} for reg, wins in agg.items()}
            out["TOTAL"] = {w: cell(v) for w, v in tot.items()}
            out["_ok"] = True
            done[prod] = out
            save_json(STORE, store)
            tt = tot.get("TRI", [0, 0])
            print(f"  [{C.periodo_label(P)}] {i:>2}/{len(mapping)} {prod:<14} TRI tot={tt[0]:.0f} gap={tt[1]:.0f} ({time.time()-t1:.0f}s)")
    print(f"Listo en {(time.time()-t0)/60:.1f} min")
    q.close()


if __name__ == "__main__":
    main()
