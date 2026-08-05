# -*- coding: utf-8 -*-
"""Diagnóstico Acneclin: el mercado se duplicó de golpe en Jun-2026 y de forma
retroactiva (la corrida de junio ve Jun-2025 al doble de lo extraído en su momento).

Dos hipótesis a distinguir:
  A) IQVIA redefinió el mercado y reexpresó la historia -> hay 1 solo valor
     'Acneclin' y creció la cantidad de productos que lo componen.
  B) DescripcionMercado tiene 2 valores que se leen igual ('Acneclin' con espacio,
     otra capitalización) y select_text los toma a los dos, duplicando conteos
     -> GetSelectedCount = 2. Sería un bug de mapeo, no de IQVIA.

Solo lectura, no toca ningún store.
"""
from qlik_client import connect_retry
import config as C


def val(q, doc, expr):
    return q.evaluate(doc, "=" + expr)


def main():
    q, doc = connect_retry()
    q.clear_all(doc)
    q.select_text(doc, "TipoMercado", C.TIPO_MERCADO)

    # 1) ¿Cuántos valores de DescripcionMercado se leen como 'Acneclin'?
    obj = {"qInfo": {"qType": "l"}, "qHyperCubeDef": {
        "qDimensions": [{"qDef": {"qFieldDefs": ["DescripcionMercado"]}}],
        "qMeasures": [{"qDef": {"qDef": "count(distinct CPA)"}}],
        "qInitialDataFetch": [{"qLeft": 0, "qTop": 0, "qWidth": 2, "qHeight": 1000}]}}
    h = q.rpc("CreateSessionObject", doc, [obj])["qReturn"]["qHandle"]
    rows = q.rpc("GetLayout", h, [])["qLayout"]["qHyperCube"]["qDataPages"][0]["qMatrix"]
    print("=== valores de DescripcionMercado que contienen 'acneclin' ===")
    hits = [r for r in rows if "acneclin" in r[0]["qText"].lower()]
    for r in hits:
        print("   %-40s  CPA=%s" % (repr(r[0]["qText"]), r[1].get("qText")))
    print("   total de valores en el campo: %d" % len(rows))

    # 2) La prueba decisiva: al seleccionar por texto, ¿cuántos valores quedan?
    q.clear_all(doc)
    q.select_text(doc, "TipoMercado", C.TIPO_MERCADO)
    q.select_text(doc, "DescripcionMercado", "Acneclin")
    print("\n=== selección select_text('Acneclin') ===")
    print("   valores seleccionados:", val(q, doc, "GetSelectedCount(DescripcionMercado)"))
    print("   texto seleccionado   :", val(q, doc, "concat(distinct DescripcionMercado, ' | ')"))

    # 3) Composición del mercado: campos disponibles y conteos por período
    fl = {"qInfo": {"qType": "fl"}, "qFieldListDef": {"qShowSystem": False, "qShowHidden": False}}
    hf = q.rpc("CreateSessionObject", doc, [fl])["qReturn"]["qHandle"]
    campos = [i["qName"] for i in q.rpc("GetLayout", hf, [])["qLayout"]["qFieldList"]["qItems"]]
    cand = [c for c in campos if any(k in c.lower() for k in
            ("producto", "presenta", "molecula", "droga", "marca", "laboratorio"))]
    print("\n=== campos candidatos para componer el mercado ===")
    print("  ", cand)

    # 4) Comparar composición Jun-2025 (24306) vs Jun-2026 (24318)
    print("\n=== composición del mercado Acneclin por mes ===")
    for P, lbl in [(24306, "Jun-2025"), (24318, "Jun-2026")]:
        q.clear_all(doc)
        q.select_text(doc, "TipoMercado", C.TIPO_MERCADO)
        q.select_text(doc, "DescripcionMercado", "Acneclin")
        q.select_num(doc, "AñoMes_Num", [P])
        linea = "   %s  CPA=%s  unidades=%s" % (
            lbl,
            val(q, doc, "count(distinct CPA)"),
            val(q, doc, "sum(MensualUnidades)"))
        for c in cand[:4]:
            linea += "  %s=%s" % (c[:18], val(q, doc, "count(distinct [%s])" % c))
        print(linea)

    # 5) Qué productos componen el mercado hoy (para saber qué se agregó)
    for P, lbl in [(24306, "Jun-2025"), (24318, "Jun-2026")]:
        campo = cand[0] if cand else None
        if not campo:
            break
        q.clear_all(doc)
        q.select_text(doc, "TipoMercado", C.TIPO_MERCADO)
        q.select_text(doc, "DescripcionMercado", "Acneclin")
        q.select_num(doc, "AñoMes_Num", [P])
        obj = {"qInfo": {"qType": "p"}, "qHyperCubeDef": {
            "qDimensions": [{"qDef": {"qFieldDefs": [campo]}}],
            "qMeasures": [{"qDef": {"qDef": "sum(MensualUnidades)"},
                           "qSortBy": {"qSortByNumeric": -1}}],
            "qInitialDataFetch": [{"qLeft": 0, "qTop": 0, "qWidth": 2, "qHeight": 40}]}}
        h2 = q.rpc("CreateSessionObject", doc, [obj])["qReturn"]["qHandle"]
        rs = q.rpc("GetLayout", h2, [])["qLayout"]["qHyperCube"]["qDataPages"][0]["qMatrix"]
        print("\n=== %s en %s (top 15 por unidades) ===" % (campo, lbl))
        for r in rs[:15]:
            print("   %-45s %12s" % (r[0]["qText"][:45], r[1].get("qText")))

    q.close()


if __name__ == "__main__":
    main()
