# -*- coding: utf-8 -*-
"""Extractor multi-ventana: por producto/período/región extrae los conteos
(SIE / 80-20 / Total Mercado) para 5 ventanas temporales — Mensual, Trimestre,
Semestre, MAT y YTD — construidas parametrizando la ventana de las medidas
maestras (validado contra la medida TRIM oficial: match exacto).

Salida: datos/historico.json con esquema:
  datos[periodo][producto][region][ventana] = {"s":SIE, "p":80-20, "t":TotMdo}
  (region incluye "TOTAL" = suma de regiones)

Serial y resumible (checkpoint por producto). Uso:
  python extraer_ventanas.py            # todos los períodos completos, todas las ventanas
  python extraer_ventanas.py 24317      # un período
"""
import json, os, sys, time
from collections import defaultdict
from qlik_client import Qix
import config as C

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "datos")
STORE = os.path.join(DATA, "historico_win.json")
MAPJS = os.path.join(DATA, "mapeo_mercados.json")

SIE_ID = "79f5a08e-33dc-4638-a92e-d29ef3234728"
P80_ID = "69e8649d-3189-457b-98b1-c5d0dbd78da5"
TOT_ID = "sCCWeD"
DIM_REGION = C.DIM_REGIONCUP

# ventanas de tamaño fijo (offset de inicio = largo-1); YTD se calcula por período
FIXED_WIN = {"MEN": 0, "TRI": 2, "SEM": 5, "MAT": 11}


def load_json(p, d):
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else d

def save_json(p, o):
    """Guardado atómico resistente a locks transitorios (OneDrive/AV/lectores).
    os.replace puede fallar con WinError 5 si el destino está abierto/sincronizando;
    reintenta con backoff y, como último recurso, escribe directo (no atómico)."""
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(o, fh, ensure_ascii=False)
    for attempt in range(10):
        try:
            os.replace(tmp, p)
            return
        except PermissionError:
            time.sleep(min(2.0 * (attempt + 1), 10))
    # fallback: escritura directa reintentada (OneDrive persistente)
    for attempt in range(10):
        try:
            with open(p, "w", encoding="utf-8") as fh:
                json.dump(o, fh, ensure_ascii=False)
            break
        except PermissionError:
            time.sleep(min(2.0 * (attempt + 1), 10))
    try:
        os.remove(tmp)
    except OSError:
        pass

def num(c):
    v = c.get("qNum")
    return v if isinstance(v, (int, float)) else 0.0

def month_of(p):
    m = p % 12
    return 12 if m == 0 else m


def main():
    mapping = load_json(MAPJS, None)
    q = Qix(); doc = q.open_doc(); q.clear_all(doc)

    def mdef(mid):
        h = q.rpc("GetMeasure", doc, [mid])["qReturn"]["qHandle"]
        return q.rpc("GetLayout", h, [])["qLayout"]["qMeasure"]["qDef"]
    sie_def, p80_def, tot_def = mdef(SIE_ID), mdef(P80_ID), mdef(TOT_ID)

    def win(defstr, S):
        return defstr.replace("-2)", "-%d)" % S)

    min_p = int(round(float(str(q.evaluate(doc, "=Min([AñoMes_Num])")).replace(",", "."))))
    max_p = int(round(float(str(q.evaluate(doc, "=Max([AñoMes_Num])")).replace(",", "."))))
    args = [int(a) for a in sys.argv[1:]]
    periods = args if args else list(range(max_p, min_p + 1, -1))   # lista explícita de períodos

    store = load_json(STORE, {"meta": {}, "periodos": {}, "datos": {}})
    store["meta"] = {"schema": "ventanas", "ventanas": list(FIXED_WIN.keys()) + ["YTD"],
                     "min_periodo": min_p, "max_periodo": max_p}

    def windows_for(P):
        w = dict(FIXED_WIN)
        w["YTD"] = month_of(P) - 1
        return w

    def measures_for(P):
        ms = []
        order = []
        for wname, S in windows_for(P).items():
            ms.append({"qDef": {"qDef": win(sie_def, S)}}); order.append((wname, "s"))
            ms.append({"qDef": {"qDef": win(p80_def, S)}}); order.append((wname, "p"))
            ms.append({"qDef": {"qDef": win(tot_def, S)}}); order.append((wname, "t"))
        return ms, order

    print(f"App {C.periodo_label(min_p)}..{C.periodo_label(max_p)} | períodos: {len(periods)} | ventanas: {list(windows_for(max_p).keys())}")
    t0 = time.time()
    for P in periods:
        pk = str(P)
        if month_of(P) == 1 and P - (month_of(P) - 1) < min_p:
            pass  # YTD siempre válido (>=1 mes)
        store["periodos"].setdefault(pk, {"label": C.periodo_label(P), "num": P})
        store["datos"].setdefault(pk, {})
        done = store["datos"][pk]
        ms, order = measures_for(P)
        for i, (prod, merc) in enumerate(mapping.items(), 1):
            if prod in done and done[prod].get("_ok"):
                continue
            t1 = time.time(); rows = None
            for attempt in range(3):
                try:
                    q.clear_all(doc)
                    q.select_text(doc, "TipoMercado", C.TIPO_MERCADO)
                    q.select_num(doc, "AñoMes_Num", range(min_p, P + 1))
                    q.select_text(doc, "DescripcionMercado", merc)
                    obj = {"qInfo": {"qType": "v"}, "qHyperCubeDef": {
                        "qDimensions": [{"qLibraryId": DIM_REGION, "qNullSuppression": True}],
                        "qMeasures": ms,
                        "qInitialDataFetch": [{"qLeft": 0, "qTop": 0, "qWidth": 1 + len(ms), "qHeight": 60}]}}
                    h = q.rpc("CreateSessionObject", doc, [obj])["qReturn"]["qHandle"]
                    rows = q.rpc("GetLayout", h, [])["qLayout"]["qHyperCube"]["qDataPages"][0]["qMatrix"]
                    break
                except Exception as e:
                    print(f"  {prod} intento {attempt+1}: {e}")
                    try: q.close()
                    except Exception: pass
                    time.sleep(3); q = Qix(); doc = q.open_doc()
            if rows is None:
                done[prod] = {"_ok": False}; save_json(STORE, store); continue
            agg = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0, 0.0]))  # region->win->[s,p,t]
            tot = defaultdict(lambda: [0.0, 0.0, 0.0])                        # win->[s,p,t]
            for r in rows:
                region = C.REGIONCUP_TO_REGION.get(r[0]["qText"])
                if not region:
                    continue
                for idx, (wname, fld) in enumerate(order):
                    v = num(r[idx + 1]); j = "spt".index(fld)
                    agg[region][wname][j] += v
                    tot[wname][j] += v
            out = {}
            for region, wins in agg.items():
                out[region] = {w: {"s": round(v[0], 1), "p": round(v[1], 1), "t": round(v[2], 1)} for w, v in wins.items()}
            out["TOTAL"] = {w: {"s": round(v[0], 1), "p": round(v[1], 1), "t": round(v[2], 1)} for w, v in tot.items()}
            out["_ok"] = True
            done[prod] = out
            dp = tot["TRI"][0] / tot["TRI"][1] if tot["TRI"][1] else 0
            print(f"  [{C.periodo_label(P)}] {i:>2}/{len(mapping)} {prod:<14} DP%TRI={dp:5.3f} ({time.time()-t1:.0f}s)")
            save_json(STORE, store)
    print(f"Listo en {(time.time()-t0)/60:.1f} min")
    q.close()


if __name__ == "__main__":
    main()
