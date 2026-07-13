# -*- coding: utf-8 -*-
"""Explora medidas maestras, campos y variables del app Qlik buscando 'unidades'.
Solo lectura de metadatos (no toca selecciones). Uso: python explorar_medidas.py"""
import json, re
from qlik_client import Qix

TERMS = ["unidad", "unit", "mostrador", "venta", "potencial", "u.", "facturac", "valor", "sell", "demanda", "iqvia", "u tot", "cant"]


def main():
    q = Qix(); doc = q.open_doc()

    # --- Medidas maestras: título + definición ---
    obj = {"qInfo": {"qType": "MeasureList"}, "qMeasureListDef": {
        "qType": "measure", "qData": {"title": "/qMetaDef/title", "tags": "/qMetaDef/tags"}}}
    h = q.rpc("CreateSessionObject", doc, [obj])["qReturn"]["qHandle"]
    items = q.rpc("GetLayout", h, [])["qLayout"]["qMeasureList"]["qItems"]
    print(f"=== {len(items)} MEDIDAS MAESTRAS ===")
    meas = []
    for it in items:
        qid = it["qInfo"]["qId"]
        title = (it.get("qMeta") or {}).get("title") or (it.get("qData") or {}).get("title") or ""
        try:
            mh = q.rpc("GetMeasure", doc, [qid])["qReturn"]["qHandle"]
            ddef = q.rpc("GetLayout", mh, [])["qLayout"]["qMeasure"]["qDef"]
        except Exception as e:
            ddef = f"(err {e})"
        meas.append((qid, title, ddef))
    # imprimir las que matchean términos de unidades/ventas primero
    def hit(s): return any(t in (s or "").lower() for t in TERMS)
    print("\n--- MEDIDAS QUE MENCIONAN unidades/ventas/potencial ---")
    for qid, title, ddef in meas:
        if hit(title) or hit(ddef):
            print(f"[{qid}] {title!r}\n    def: {ddef}")
    print("\n--- TODAS (título) ---")
    for qid, title, ddef in meas:
        print(f"[{qid}] {title}")

    # --- Campos ---
    fobj = {"qInfo": {"qType": "FieldList"}, "qFieldListDef": {
        "qShowSystem": False, "qShowHidden": False, "qShowDerivedFields": True,
        "qShowSemantic": True, "qShowSrcTables": True}}
    fh = q.rpc("CreateSessionObject", doc, [fobj])["qReturn"]["qHandle"]
    fields = q.rpc("GetLayout", fh, [])["qLayout"]["qFieldList"]["qItems"]
    print(f"\n=== {len(fields)} CAMPOS ===")
    for f in fields:
        nm = f.get("qName", "")
        mark = "  <<<" if hit(nm) else ""
        print(f"  {nm}{mark}")

    # --- Variables ---
    try:
        vobj = {"qInfo": {"qType": "VariableList"}, "qVariableListDef": {
            "qType": "variable", "qShowReserved": False, "qShowConfig": True,
            "qData": {"definition": "/qDefinition"}}}
        vh = q.rpc("CreateSessionObject", doc, [vobj])["qReturn"]["qHandle"]
        vars_ = q.rpc("GetLayout", vh, [])["qLayout"]["qVariableList"]["qItems"]
        print(f"\n=== {len(vars_)} VARIABLES (con def de unidades) ===")
        for v in vars_:
            nm = v.get("qName", ""); dfn = (v.get("qData") or {}).get("definition", "")
            if hit(nm) or hit(dfn):
                print(f"  {nm} = {dfn}")
    except Exception as e:
        print("variables:", e)

    q.close()


if __name__ == "__main__":
    main()
