# -*- coding: utf-8 -*-
"""Factor marginal del núcleo Pareto, por mercado.

Para qué: al ganar puntos de DP% no se entra en una farmacia PROMEDIO del núcleo
80-20, se entra por las más chicas — las que quedaron afuera justamente porque
cuestan más. Suponer la promedio sobreestima el volumen atribuible unas 2,6 veces.

Este script mide, para cada mercado, cuánto vende una farmacia del último tramo
del núcleo (acumulado de Pareto entre 0,70 y 0,80) respecto de la farmacia
promedio del núcleo. Ese cociente es el factor con el que hay que corregir.

Sigue siendo generoso: los puntos que se ganan son decenas o centenas de
farmacias, o sea la cola misma del núcleo, todavía más chica que el promedio de
ese último tramo.

Salida: ../datos/factor_marginal.json
Uso:  python extraer_factor_marginal.py
"""
import json, os, time
from qlik_client import Qix, connect_retry
import config as C

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "datos")
STORE = os.path.join(DATA, "factor_marginal.json")
MAPJS = os.path.join(DATA, "mapeo_mercados.json")

W = ("{$<CPA=,MesesRollBack={0},DescripcionTipo={'Mensual'},[AñoSeleccion]=,MesSeleccion=,"
     "Flag_Rollback={0},[AñoMes_Num]={\">=$(=max(AñoMes_Num)-2)<=$(=max(AñoMes_Num))\"}>}")
ACUM = ("Rangesum(Above(Sum(%s MensualUnidades)/Sum(%s total MensualUnidades),0,RowNo()))" % (W, W))
DIM = "(CPA,(=Sum(%s MensualUnidades),Desc))" % W
CORTE = 0.8
BANDA = 0.7          # último tramo del núcleo: acumulado entre 0,70 y el corte


def save(o):
    tmp = STORE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(o, f, ensure_ascii=False, indent=1)
    for i in range(10):
        try:
            os.replace(tmp, STORE); return
        except PermissionError:
            time.sleep(min(2.0 * (i + 1), 10))
    with open(STORE, "w", encoding="utf-8") as f:
        json.dump(o, f, ensure_ascii=False, indent=1)


def main():
    mapping = json.load(open(MAPJS, encoding="utf-8"))
    out = {"meta": {}, "datos": {}}
    if os.path.exists(STORE):
        out = json.load(open(STORE, encoding="utf-8"))
    q, doc = connect_retry()
    q.clear_all(doc)
    min_p = int(round(float(str(q.evaluate(doc, "=Min([AñoMes_Num])")).replace(",", "."))))
    max_p = int(round(float(str(q.evaluate(doc, "=Max([AñoMes_Num])")).replace(",", "."))))
    out["meta"] = {"ventana": "TRIM", "periodo": max_p, "label": C.periodo_label(max_p),
                   "corte_pareto": CORTE, "banda_marginal": BANDA}

    def ev(e):
        r = q.evaluate(doc, "=" + e)
        try:
            return float(str(r).replace(".", "").replace(",", "."))
        except ValueError:
            return None

    print(f"Factor marginal del núcleo · {C.periodo_label(max_p)} · {len(mapping)} mercados")
    t0 = time.time()
    for i, (prod, merc) in enumerate(mapping.items(), 1):
        if prod in out["datos"]:
            continue
        for intento in range(3):
            try:
                q.clear_all(doc)
                q.select_text(doc, "TipoMercado", C.TIPO_MERCADO)
                q.select_num(doc, "AñoMes_Num", range(min_p, max_p + 1))
                q.select_text(doc, "DescripcionMercado", merc)
                q.check_selection(doc, "DescripcionMercado")
                un = ev("Sum(Aggr(If(%s<%s, Sum(%s MensualUnidades)), %s))" % (ACUM, CORTE, W, DIM))
                nn = ev("Count(Aggr(If(%s<%s, 1), %s))" % (ACUM, CORTE, DIM))
                um = ev("Sum(Aggr(If(%s<%s and %s>=%s, Sum(%s MensualUnidades)), %s))"
                        % (ACUM, CORTE, ACUM, BANDA, W, DIM))
                nm = ev("Count(Aggr(If(%s<%s and %s>=%s, 1), %s))" % (ACUM, CORTE, ACUM, BANDA, DIM))
                break
            except Exception as e:
                print(f"  {prod} intento {intento+1}: {str(e)[:60]}")
                try: q.close()
                except Exception: pass
                q, doc = connect_retry(pausa_inicial=3)
        prom = (un / nn) if (un and nn) else None
        marg = (um / nm) if (um and nm) else None
        f = round(marg / prom, 4) if (prom and marg) else None
        out["datos"][prod] = {"u_prom_nucleo": round(prom, 1) if prom else None,
                              "u_marg_nucleo": round(marg, 1) if marg else None,
                              "farmacias_nucleo": int(nn) if nn else None,
                              "farmacias_marginales": int(nm) if nm else None,
                              "factor": f}
        save(out)
        print(f"  {i:>2}/{len(mapping)} {prod:<14} prom={prom or 0:>7.0f}  marg={marg or 0:>7.0f}  "
              f"factor={f if f is not None else '—'}")
    fs = [v["factor"] for v in out["datos"].values() if v["factor"]]
    if fs:
        fs_ord = sorted(fs)
        print(f"\nfactor: min {min(fs):.2f} · mediana {fs_ord[len(fs_ord)//2]:.2f} · max {max(fs):.2f}")
    print(f"Listo en {(time.time()-t0)/60:.1f} min -> {STORE}")
    q.close()


if __name__ == "__main__":
    main()
