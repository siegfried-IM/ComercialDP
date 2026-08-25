# -*- coding: utf-8 -*-
"""Valida y repara datos/factor_marginal.json.

El engine de Qlik devuelve, bajo contencion, valores de OTRA consulta sin tirar
error: en la primera corrida 5 de 32 productos quedaron con lecturas prestadas de
un producto vecino, todas plausibles. Dos controles independientes las delatan:

  1. unidades del nucleo == 0,80 x unidades del mercado
     (el 0,80 es vParetoCorte; el mercado sale de unidades_region.json, que es
     otro store extraido en otra corrida, asi que es un control de verdad
     independiente y no una comprobacion del dato contra si mismo)
  2. unidades de la banda 0,70-0,80 == 12,5% de las del nucleo
     (10 puntos de Pareto sobre 80, por construccion)

Lo que falla se vuelve a medir leyendo DOS veces: si las dos lecturas no
coinciden, la sospechosa es la lectura y se reintenta.

Uso:  python reparar_factor_marginal.py          # valida y repara
      python reparar_factor_marginal.py --solo-validar
"""
import json, os, sys, time
from qlik_client import Qix, connect_retry
import config as C

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "datos")
STORE = os.path.join(DATA, "factor_marginal.json")

W = ("{$<CPA=,MesesRollBack={0},DescripcionTipo={'Mensual'},[AñoSeleccion]=,MesSeleccion=,"
     "Flag_Rollback={0},[AñoMes_Num]={\">=$(=max(AñoMes_Num)-2)<=$(=max(AñoMes_Num))\"}>}")
ACUM = "Rangesum(Above(Sum(%s MensualUnidades)/Sum(%s total MensualUnidades),0,RowNo()))" % (W, W)
DIM = "(CPA,(=Sum(%s MensualUnidades),Desc))" % W
CORTE, BANDA = 0.8, 0.7
TOL_NUCLEO = 0.03      # nucleo vs 0,80 x mercado
BANDA_MIN, BANDA_MAX = 0.09, 0.16    # banda / nucleo, esperado 0,125


def validar(v, tot_mercado):
    """Devuelve la lista de controles que NO pasa este producto."""
    fallas = []
    if not v.get("u_prom_nucleo") or not v.get("farmacias_nucleo"):
        return ["sin medicion"]
    nuc = v["u_prom_nucleo"] * v["farmacias_nucleo"]
    if tot_mercado:
        r = nuc / (CORTE * tot_mercado)
        if abs(r - 1) > TOL_NUCLEO:
            fallas.append("nucleo %.3f x lo esperado" % r)
    if not v.get("u_marg_nucleo") or not v.get("farmacias_marginales"):
        fallas.append("sin banda")
    else:
        rb = (v["u_marg_nucleo"] * v["farmacias_marginales"]) / nuc
        if not (BANDA_MIN < rb < BANDA_MAX):
            fallas.append("banda %.1f%% del nucleo (esperado 12,5%%)" % (100 * rb))
    return fallas


def medir(q, doc, min_p, max_p, merc):
    """Una medicion completa del producto. Devuelve (prom, marg, nn, nm)."""
    q.clear_all(doc)
    q.select_text(doc, "TipoMercado", C.TIPO_MERCADO)
    q.select_num(doc, "AñoMes_Num", range(min_p, max_p + 1))
    q.select_text(doc, "DescripcionMercado", merc)
    q.check_selection(doc, "DescripcionMercado")

    def ev(e):
        r = q.evaluate(doc, "=" + e)
        try:
            return float(str(r).replace(".", "").replace(",", "."))
        except ValueError:
            return None
    un = ev("Sum(Aggr(If(%s<%s, Sum(%s MensualUnidades)), %s))" % (ACUM, CORTE, W, DIM))
    nn = ev("Count(Aggr(If(%s<%s, 1), %s))" % (ACUM, CORTE, DIM))
    um = ev("Sum(Aggr(If(%s<%s and %s>=%s, Sum(%s MensualUnidades)), %s))"
            % (ACUM, CORTE, ACUM, BANDA, W, DIM))
    nm = ev("Count(Aggr(If(%s<%s and %s>=%s, 1), %s))" % (ACUM, CORTE, ACUM, BANDA, DIM))
    return un, um, nn, nm


def main():
    solo = "--solo-validar" in sys.argv
    store = json.load(open(STORE, encoding="utf-8"))
    U = json.load(open(os.path.join(DATA, "unidades_region.json"), encoding="utf-8"))["datos"]
    per = max(U, key=int)
    mercado = {k: (v.get("TOTAL", {}).get("TRI", {}) or {}).get("tot")
               for k, v in U[per].items() if isinstance(v, dict)}

    sospechosos = {}
    for prod, v in store["datos"].items():
        f = validar(v, mercado.get(prod))
        if f:
            sospechosos[prod] = f
    print(f"{len(store['datos'])} productos · {len(sospechosos)} no pasan los controles")
    for p, f in sospechosos.items():
        print(f"   {p:<14} {'; '.join(f)}")
    if solo or not sospechosos:
        return 0 if not sospechosos else 1

    mapping = json.load(open(os.path.join(DATA, "mapeo_mercados.json"), encoding="utf-8"))
    q, doc = connect_retry()
    q.clear_all(doc)
    min_p = int(round(float(str(q.evaluate(doc, "=Min([AñoMes_Num])")).replace(",", "."))))
    max_p = int(round(float(str(q.evaluate(doc, "=Max([AñoMes_Num])")).replace(",", "."))))
    print("\nRe-midiendo con doble lectura:")
    for prod in list(sospechosos):
        merc = mapping[prod]
        bueno = None
        for intento in range(5):
            try:
                a = medir(q, doc, min_p, max_p, merc)
                time.sleep(1)
                b = medir(q, doc, min_p, max_p, merc)
            except Exception as e:
                print(f"   {prod} intento {intento+1}: {str(e)[:60]}")
                try: q.close()
                except Exception: pass
                q, doc = connect_retry(pausa_inicial=3)
                continue
            if a != b:
                print(f"   {prod} intento {intento+1}: las dos lecturas difieren, el engine esta inestable")
                continue
            un, um, nn, nm = a
            cand = {"u_prom_nucleo": round(un / nn, 1) if (un and nn) else None,
                    "u_marg_nucleo": round(um / nm, 1) if (um and nm) else None,
                    "farmacias_nucleo": int(nn) if nn else None,
                    "farmacias_marginales": int(nm) if nm else None}
            cand["factor"] = (round(cand["u_marg_nucleo"] / cand["u_prom_nucleo"], 4)
                              if (cand["u_prom_nucleo"] and cand["u_marg_nucleo"]) else None)
            fallas = validar(cand, mercado.get(prod))
            if fallas:
                print(f"   {prod} intento {intento+1}: sigue sin pasar ({'; '.join(fallas)})")
                continue
            bueno = cand
            break
        if bueno:
            store["datos"][prod] = bueno
            print(f"   {prod:<14} REPARADO factor={bueno['factor']}")
        else:
            store["datos"][prod] = dict(store["datos"][prod], factor=None, _dudoso=True)
            print(f"   {prod:<14} NO SE PUDO: queda sin factor y usara la mediana")
        with open(STORE, "w", encoding="utf-8") as f:
            json.dump(store, f, ensure_ascii=False, indent=1)
    q.close()

    quedan = {p: validar(v, mercado.get(p)) for p, v in store["datos"].items()
              if validar(v, mercado.get(p)) and not v.get("_dudoso")}
    print(f"\nsin resolver: {len(quedan)}")
    return 1 if quedan else 0


if __name__ == "__main__":
    sys.exit(main())
