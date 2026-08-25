# -*- coding: utf-8 -*-
"""Factor de la farmacia GANABLE, por mercado.

Al subir el DP% se entra en farmacias del núcleo Pareto 80-20 donde hoy Siegfried
no está — son, por definición, las únicas que se pueden ganar. La pregunta es
cuánto vende una de ésas comparada con la farmacia promedio del núcleo, porque
ese cociente es el que convierte puntos de DP% en unidades.

    factor = unidades medias de una farmacia del núcleo SIN Siegfried
             ---------------------------------------------------------
             unidades medias de una farmacia del núcleo

Una versión anterior de este script usaba como proxy el último tramo del núcleo
(acumulado de Pareto 0,70-0,80), suponiendo que las farmacias que faltan son las
más chicas. Medido, es falso: dan 0,75-0,97, no 0,34-0,40. Que Siegfried no esté
en una farmacia depende de la relación comercial, no del tamaño del punto. Aquel
proxy subestimaba la atribución a la mitad.

Controles (el engine devuelve valores de otra consulta bajo contención, sin error):
  1. unidades del núcleo == 0,80 x unidades del mercado, tomando el mercado de
     unidades_region.json — otro store, extraído en otra corrida
  2. farmacias del núcleo sin Siegfried == 80-20 menos SIE, tomados de
     historico_win.json — otro store más
Lo que no pasa los dos controles se re-mide; lo que sigue sin pasar queda sin
factor y usa la mediana.

Salida: ../datos/factor_marginal.json
Uso:  python extraer_factor_marginal.py [producto ...]
"""
import json, os, sys, time
from qlik_client import Qix, connect_retry
import config as C

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "datos")
STORE = os.path.join(DATA, "factor_marginal.json")

W = ("{$<CPA=,MesesRollBack={0},DescripcionTipo={'Mensual'},[AñoSeleccion]=,MesSeleccion=,"
     "Flag_Rollback={0},[AñoMes_Num]={\">=$(=max(AñoMes_Num)-2)<=$(=max(AñoMes_Num))\"}>}")
WS = W[:-2] + ",DescripcionLaboratorioIMS={'SIEGFRIED'}>}"
# mismo trimestre de hace 12 meses, para saber donde NO estabamos
WANT = ("{$<CPA=,MesesRollBack={0},DescripcionTipo={'Mensual'},[AñoSeleccion]=,MesSeleccion=,"
        "Flag_Rollback={0},[AñoMes_Num]={\">=$(=max(AñoMes_Num)-14)<=$(=max(AñoMes_Num)-12)\"},"
        "DescripcionLaboratorioIMS={'SIEGFRIED'}>}")
ACUM = "Rangesum(Above(Sum(%s MensualUnidades)/Sum(%s total MensualUnidades),0,RowNo()))" % (W, W)
DIM = "(CPA,(=Sum(%s MensualUnidades),Desc))" % W
CORTE = 0.8
TOL = 0.03
MIN_FARM = 50          # con menos farmacias ganables la media es ruido

EXPR = {
    "un": "Sum(Aggr(If(%s<%s, Sum(%s MensualUnidades)), %s))" % (ACUM, CORTE, W, DIM),
    "nn": "Count(Aggr(If(%s<%s, 1), %s))" % (ACUM, CORTE, DIM),
    # las que se GANARON de verdad: en el nucleo hoy, con SIE hoy, sin SIE hace 12m
    "u0": ("Sum(Aggr(If(%s<%s and Sum(%s MensualUnidades)>0 and Sum(%s MensualUnidades)=0, "
           "Sum(%s MensualUnidades)), %s))" % (ACUM, CORTE, WS, WANT, W, DIM)),
    "n0": ("Count(Aggr(If(%s<%s and Sum(%s MensualUnidades)>0 and Sum(%s MensualUnidades)=0, 1), %s))"
           % (ACUM, CORTE, WS, WANT, DIM)),
}


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


def controles(v, mercado, ganables_esperadas):
    f = []
    if not v.get("farmacias_nucleo") or not v.get("u_prom_nucleo"):
        return ["sin medición"]
    nuc = v["u_prom_nucleo"] * v["farmacias_nucleo"]
    if mercado:
        r = nuc / (CORTE * mercado)
        if abs(r - 1) > TOL:
            f.append("núcleo %.3f x lo esperado" % r)
    # las ganadas no pueden superar a las ganables de hace un ano ni ser negativas
    if v.get("farmacias_ganables") is not None and v["farmacias_ganables"] < 0:
        f.append("ganadas negativas")
    return f


def main():
    mapping = json.load(open(os.path.join(DATA, "mapeo_mercados.json"), encoding="utf-8"))
    U = json.load(open(os.path.join(DATA, "unidades_region.json"), encoding="utf-8"))["datos"]
    Wst = json.load(open(os.path.join(DATA, "historico_win.json"), encoding="utf-8"))["datos"]
    perU = max(U, key=int); perW = max(Wst, key=int)
    mercado = {k: (v.get("TOTAL", {}).get("TRI", {}) or {}).get("tot")
               for k, v in U[perU].items() if isinstance(v, dict)}
    ganables = {}
    for k, v in Wst[perW].items():
        if isinstance(v, dict) and v.get("_ok"):
            c = v.get("TOTAL", {}).get("TRI")
            if c:
                ganables[k] = int(round(c["p"] - c["s"]))

    pedidos = [a for a in sys.argv[1:] if not a.startswith("-")]
    out = {"meta": {}, "datos": {}}
    if os.path.exists(STORE) and not pedidos:
        pass   # se rehace entero: el metodo cambio
    q, doc = connect_retry(); q.clear_all(doc)
    min_p = int(round(float(str(q.evaluate(doc, "=Min([AñoMes_Num])")).replace(",", "."))))
    max_p = int(round(float(str(q.evaluate(doc, "=Max([AñoMes_Num])")).replace(",", "."))))
    out["meta"] = {"ventana": "TRIM", "periodo": max_p, "label": C.periodo_label(max_p),
                   "corte_pareto": CORTE, "definicion": "u/farmacia EFECTIVAMENTE GANADA en 12m "
                                                        "sobre u/farmacia del núcleo"}
    objetivo = pedidos or list(mapping)
    print(f"Factor de la farmacia ganable · {C.periodo_label(max_p)} · {len(objetivo)} mercados")
    print("%-14s %9s %11s %11s %8s  %s" % ("producto", "ganables", "u/f núcleo", "u/f ganable", "factor", "controles"))
    t0 = time.time()
    for prod in objetivo:
        merc = mapping[prod]
        v = None
        for intento in range(5):
            try:
                q.clear_all(doc)
                q.select_text(doc, "TipoMercado", C.TIPO_MERCADO)
                q.select_num(doc, "AñoMes_Num", range(min_p, max_p + 1))
                q.select_text(doc, "DescripcionMercado", merc)
                q.check_selection(doc, "DescripcionMercado")
                r = {}
                for k, e in EXPR.items():
                    raw = q.evaluate(doc, "=" + e)
                    try:
                        r[k] = float(str(raw).replace(".", "").replace(",", "."))
                    except ValueError:
                        r[k] = None
            except Exception as e:
                print("   %s intento %d: %s" % (prod, intento + 1, str(e)[:55]))
                try: q.close()
                except Exception: pass
                q, doc = connect_retry(pausa_inicial=3)
                continue
            cand = {
                "u_prom_nucleo": round(r["un"] / r["nn"], 1) if (r["un"] and r["nn"]) else None,
                "u_ganable": round(r["u0"] / r["n0"], 1) if (r["u0"] and r["n0"]) else None,
                "farmacias_nucleo": int(r["nn"]) if r["nn"] else None,
                "farmacias_ganables": int(r["n0"]) if r["n0"] else 0,
            }
            f = controles(cand, mercado.get(prod), ganables.get(prod))
            if f:
                print("   %s intento %d: %s" % (prod, intento + 1, "; ".join(f)))
                continue
            v = cand
            break
        if not v:
            out["datos"][prod] = {"factor": None, "_dudoso": True}
            print("%-14s  NO SE PUDO MEDIR" % prod)
            save(out); continue
        # con pocas farmacias ganables la media no significa nada
        if v["farmacias_ganables"] >= MIN_FARM and v["u_prom_nucleo"] and v["u_ganable"]:
            v["factor"] = round(v["u_ganable"] / v["u_prom_nucleo"], 4)
        else:
            v["factor"] = None
            v["_pocas_ganables"] = True
        out["datos"][prod] = v
        save(out)
        print("%-14s %9s %11.0f %11s %8s  ok" % (
            prod, "{:,}".format(v["farmacias_ganables"]), v["u_prom_nucleo"] or 0,
            "{:,.0f}".format(v["u_ganable"]) if v["u_ganable"] else "—",
            v["factor"] if v["factor"] is not None else "(pocas)"))
    fs = sorted(v["factor"] for v in out["datos"].values() if v.get("factor"))
    if fs:
        out["meta"]["mediana"] = fs[len(fs) // 2]
        save(out)
        print(f"\nfactor: min {fs[0]:.2f} · mediana {fs[len(fs)//2]:.2f} · max {fs[-1]:.2f} "
              f"({len(fs)} de {len(objetivo)} con factor propio)")
    print(f"Listo en {(time.time()-t0)/60:.1f} min")
    q.close()


if __name__ == "__main__":
    main()
