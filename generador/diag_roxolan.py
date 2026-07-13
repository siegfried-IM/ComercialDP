# -*- coding: utf-8 -*-
"""Diagnóstico: mercados 'Roxolan*' y, para Roxolan, unidades del mercado vs
unidades Siegfried vs MS% (participación en unidades) por ventana. Solo lectura."""
from qlik_client import Qix
import config as C

def wset(S, sie=False):
    lab = "DescripcionLaboratorioIMS={'SIEGFRIED'}," if sie else ""
    return ("{<" + lab + "Flag_Rollback={0},MesesRollBack=,DescMercadoTipo=,"
            "[AñoMes_Num]={\">=$(=max(AñoMes_Num)-%d)<=$(=max(AñoMes_Num)-0)\"}>}" % S)

def v(q, doc, e):
    r = q.evaluate(doc, "=" + e)
    try: return float(r)
    except Exception:
        return float(str(r).replace(".", "").replace(",", "."))


def main():
    q = Qix(); doc = q.open_doc(); q.clear_all(doc)
    q.select_text(doc, "TipoMercado", C.TIPO_MERCADO)

    # 1) listar mercados que contienen 'roxolan'
    obj = {"qInfo": {"qType": "l"}, "qHyperCubeDef": {
        "qDimensions": [{"qDef": {"qFieldDefs": ["DescripcionMercado"]}}],
        "qMeasures": [{"qDef": {"qDef": "sum(" + wset(0) + " MensualUnidades)"}}],
        "qInitialDataFetch": [{"qLeft": 0, "qTop": 0, "qWidth": 2, "qHeight": 400}]}}
    h = q.rpc("CreateSessionObject", doc, [obj])["qReturn"]["qHandle"]
    rows = q.rpc("GetLayout", h, [])["qLayout"]["qHyperCube"]["qDataPages"][0]["qMatrix"]
    print("=== mercados que contienen 'roxolan' ===")
    for r in rows:
        if "roxolan" in r[0]["qText"].lower():
            print(f"  {r[0]['qText']!r}   (unid MEN nac: {r[1].get('qNum')})")

    # 2) Roxolan: mercado vs Siegfried vs MS% por ventana
    q.clear_all(doc); q.select_text(doc, "TipoMercado", C.TIPO_MERCADO)
    q.select_text(doc, "DescripcionMercado", "Roxolan (Rosuvastatina)")
    print("\n=== Roxolan (nacional) ===")
    for wn, S in [("MEN", 0), ("TRI", 2), ("MAT", 11)]:
        tot = v(q, doc, "sum(%s MensualUnidades)" % wset(S))
        sie = v(q, doc, "sum(%s MensualUnidades)" % wset(S, True))
        gap = v(q, doc, "sum(aggr(if(sum(%s MensualUnidades)=0, sum(%s MensualUnidades),0),CPA))" % (wset(S, True), wset(S)))
        ms = 100 * sie / tot if tot else 0
        print(f"  {wn}: mercado={tot:,.0f}  siegfried={sie:,.0f}  MS%={ms:.1f}%  no_capt(present)={gap:,.0f} ({100*gap/tot:.1f}% del mdo)  mdo-sie={tot-sie:,.0f}")

    # 3) Roxolan en Buenos Aires (regiones de la provincia) para cotejar el 901K
    q.clear_all(doc); q.select_text(doc, "TipoMercado", C.TIPO_MERCADO)
    q.select_text(doc, "DescripcionMercado", "Roxolan (Rosuvastatina)")
    regs = [r for r, p in C.REGION_TO_PROVINCE.items() if p == "Buenos Aires"]
    cup = [c for c, r in C.REGIONCUP_TO_REGION.items() if r in regs]
    q.select_text(doc, "RegionCUP", cup)
    print("\n=== Roxolan en Buenos Aires (RegionCUP de la prov) ===")
    for wn, S in [("MEN", 0), ("TRI", 2)]:
        tot = v(q, doc, "sum(%s MensualUnidades)" % wset(S))
        sie = v(q, doc, "sum(%s MensualUnidades)" % wset(S, True))
        ms = 100 * sie / tot if tot else 0
        print(f"  {wn}: mercado={tot:,.0f}  siegfried={sie:,.0f}  MS%={ms:.1f}%")
    q.close()


if __name__ == "__main__":
    main()
