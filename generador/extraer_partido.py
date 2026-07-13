# -*- coding: utf-8 -*-
"""Extrae DP%/DF% por departamento (provincia, partido) para el período actual,
para todos los mercados. Salida: datos/mapa_partido.json { DP:{prod:{geokey:dp}}, DF:{...} }.

Uso: python extraer_partido.py [periodo]   (por defecto, el máximo disponible)
"""
import json, os, sys, time
from collections import defaultdict
from qlik_client import Qix
import config as C
import geo_match

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "datos")
MAPJS = os.path.join(DATA, "mapeo_mercados.json")
OUT = os.path.join(DATA, "mapa_partido.json")

DIM_PROV = "1949a1bb-36fe-4f21-b7fb-f03e3380760e"
DIM_PART = "3c30cde4-48f7-4433-91b7-e5caf333f6c7"
M = {"sie": "79f5a08e-33dc-4638-a92e-d29ef3234728",
     "p80": "69e8649d-3189-457b-98b1-c5d0dbd78da5",
     "tot": "sCCWeD"}


def num(c):
    v = c.get("qNum")
    return v if isinstance(v, (int, float)) else 0.0


def main():
    mapping = json.load(open(MAPJS, encoding="utf-8"))
    q = Qix(); doc = q.open_doc(); q.clear_all(doc)
    min_p = int(round(float(str(q.evaluate(doc, "=Min([AñoMes_Num])")).replace(",", "."))))
    max_p = int(round(float(str(q.evaluate(doc, "=Max([AñoMes_Num])")).replace(",", "."))))
    P = int(sys.argv[1]) if len(sys.argv) > 1 else max_p
    out = {"meta": {"periodo": P, "min_periodo": min_p}, "DP": {}, "DF": {}}
    t0 = time.time()
    for i, (prod, merc) in enumerate(mapping.items(), 1):
        for attempt in range(3):
            try:
                q.clear_all(doc)
                q.select_text(doc, "TipoMercado", C.TIPO_MERCADO)
                q.select_num(doc, "AñoMes_Num", range(min_p, P + 1))
                q.select_text(doc, "DescripcionMercado", merc)
                rows = q.hypercube(doc, [DIM_PROV, DIM_PART], [M["sie"], M["p80"], M["tot"]])
                break
            except Exception as e:
                print(f"  {prod} intento {attempt+1} err: {e}")
                try: q.close()
                except Exception: pass
                time.sleep(3); q = Qix(); doc = q.open_doc()
        agg = defaultdict(lambda: [0.0, 0.0, 0.0])   # geokey -> [sie, p80, tot]
        for r in rows:
            prov, part = r[0]["qText"], r[1]["qText"]
            k = geo_match.key(prov, part)
            agg[k][0] += num(r[2]); agg[k][1] += num(r[3]); agg[k][2] += num(r[4])
        out["DP"][prod] = {k: round(v[0] / v[1], 6) for k, v in agg.items() if v[1]}
        out["DF"][prod] = {k: round(v[0] / v[2], 6) for k, v in agg.items() if v[2]}
        print(f"  {i:>2}/{len(mapping)} {prod:<14} deptos={len(out['DP'][prod])} ({time.time()-t0:.0f}s)")
        json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)  # checkpoint
    print(f"Listo en {(time.time()-t0)/60:.1f} min -> {OUT}")
    q.close()


if __name__ == "__main__":
    main()
