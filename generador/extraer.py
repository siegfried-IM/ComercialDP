# -*- coding: utf-8 -*-
"""Extractor de datos DP% desde QlikCloud hacia el store histórico.

Serial y resumible: guarda checkpoint tras cada mercado. Si se corta, al
reanudar saltea lo ya extraído.

Uso:
    python extraer.py                 # todos los períodos completos disponibles
    python extraer.py 24317           # solo el período May-2026
    python extraer.py 24313 24317     # rango de períodos (inclusive)
"""
import json, os, sys, time, datetime
from collections import defaultdict
from qlik_client import Qix
import config as C

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "datos")
STORE = os.path.join(DATA, "historico.json")
MAPJS = os.path.join(DATA, "mapeo_mercados.json")

MEAS_ORDER = ["sie_act", "p80_act", "totmdo_act", "sie_ant", "p80_ant", "totmdo_ant"]


def load_json(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def num(cell):
    v = cell.get("qNum")
    return v if isinstance(v, (int, float)) else 0.0


def extract_market(q, doc, period_num, min_period, mercado):
    """Devuelve dict region -> {sie_act,p80_act,...} + 'TOTAL'."""
    q.clear_all(doc)
    q.select_text(doc, "TipoMercado", C.TIPO_MERCADO)
    q.select_num(doc, "AñoMes_Num", range(min_period, period_num + 1))
    q.select_text(doc, "DescripcionMercado", mercado)
    rows = q.hypercube(doc, [C.DIM_REGIONCUP], [C.MEAS[k] for k in MEAS_ORDER])
    agg = defaultdict(lambda: {k: 0.0 for k in MEAS_ORDER})
    total = {k: 0.0 for k in MEAS_ORDER}
    unmapped = set()
    for r in rows:
        rc = r[0]["qText"]
        region = C.REGIONCUP_TO_REGION.get(rc)
        if region is None:
            unmapped.add(rc)
            continue
        for i, k in enumerate(MEAS_ORDER):
            v = num(r[i + 1])
            agg[region][k] += v
            total[k] += v
    out = {reg: vals for reg, vals in agg.items()}
    out["TOTAL"] = total
    return out, unmapped


def main():
    mapping = load_json(MAPJS, None)
    if not mapping:
        sys.exit(f"Falta {MAPJS} (mapeo producto->mercado). Corré resolver primero.")
    store = load_json(STORE, {"meta": {}, "periodos": {}, "datos": {}})

    q = Qix(); doc = q.open_doc(); q.clear_all(doc)
    min_p = int(round(float(str(q.evaluate(doc, "=Min([AñoMes_Num])")).replace(",", "."))))
    max_p = int(round(float(str(q.evaluate(doc, "=Max([AñoMes_Num])")).replace(",", "."))))

    args = [int(a) for a in sys.argv[1:]]
    if len(args) == 0:
        # trimestres completos, MÁS RECIENTE PRIMERO (para tener ya el período
        # actual y que el histórico se complete hacia atrás)
        periods = list(range(max_p, min_p + 1, -1))
    elif len(args) == 1:
        periods = [args[0]]
    else:
        periods = list(range(args[0], args[1] + 1))

    print(f"App min={min_p} ({C.periodo_label(min_p)}) max={max_p} ({C.periodo_label(max_p)})")
    print(f"Períodos a extraer: {[C.periodo_label(p) for p in periods]}")
    print(f"Mercados: {len(mapping)}")

    all_unmapped = set()
    t_start = time.time()
    for p in periods:
        pk = str(p)
        store["periodos"].setdefault(pk, {"label": C.periodo_label(p), "num": p})
        store["datos"].setdefault(pk, {})
        done = store["datos"][pk]
        for i, (prod, mercado) in enumerate(mapping.items(), 1):
            if prod in done and done[prod].get("_ok"):
                continue
            t0 = time.time()
            data = unmapped = None
            for attempt in range(3):
                try:
                    data, unmapped = extract_market(q, doc, p, min_p, mercado)
                    break
                except Exception as e:
                    print(f"  [{C.periodo_label(p)}] {prod!r} intento {attempt+1}/3 err: {e}")
                    try:
                        q.close()
                    except Exception:
                        pass
                    time.sleep(3)
                    q = Qix(); doc = q.open_doc()
            if data is None:
                print(f"  [{C.periodo_label(p)}] {prod!r} FALLO tras 3 intentos -- se saltea")
                done[prod] = {"_ok": False, "_mercado": mercado}
                save_json(STORE, store)
                continue
            all_unmapped |= unmapped
            data["_ok"] = True
            data["_mercado"] = mercado
            done[prod] = data
            tot = data["TOTAL"]
            dp = tot["sie_act"] / tot["p80_act"] if tot["p80_act"] else 0
            print(f"  [{C.periodo_label(p)}] {i:>2}/{len(mapping)} {prod:<14} DP%={dp:6.3f} ({time.time()-t0:.1f}s)")
            save_json(STORE, store)   # checkpoint
    store["meta"] = {"app": q.app_id, "tipo_mercado": C.TIPO_MERCADO,
                     "actualizado": datetime.datetime.now().isoformat(timespec="seconds"),
                     "min_periodo": min_p, "max_periodo": max_p}
    save_json(STORE, store)
    if all_unmapped:
        print("RegionCUP sin mapear (revisar config):", sorted(all_unmapped))
    print(f"Listo en {(time.time()-t_start)/60:.1f} min. Store: {STORE}")
    q.close()


if __name__ == "__main__":
    main()
