# -*- coding: utf-8 -*-
"""Acneclin, parte 2: la composición del mercado NO cambió entre Jun-2025 y Jun-2026
(mismos 20 productos, ~7.400 farmacias/mes), pero las medidas maestras devuelven
~1,7x más en la corrida de Jun-2026 que en la de May-2026, tanto para el período
actual como para el año anterior.

Así que el salto está en el cálculo, no en el dato. Este script:
  1. imprime la definición de las 3 medidas maestras,
  2. las evalúa con la selección EXACTA del extractor para P=24317 y P=24318,
  3. compara contra un conteo manual de farmacias distintas en la misma ventana,
  4. repite todo con un producto de control para ver si es exclusivo de Acneclin.

Solo lectura.
"""
from qlik_client import connect_retry
import config as C

MEDIDAS = [("sie", C.MEAS["sie_act"]), ("p80", C.MEAS["p80_act"]), ("tot", C.MEAS["totmdo_act"])]
PRODUCTOS = ["Acneclin", "Micomazol"]   # Micomazol = control (se movió -1,4 pp, normal)


def main():
    q, doc = connect_retry()
    q.clear_all(doc)

    print("=== definición de las medidas maestras ===")
    defs = {}
    for nombre, mid in MEDIDAS:
        h = q.rpc("GetMeasure", doc, [mid])["qReturn"]["qHandle"]
        lay = q.rpc("GetLayout", h, [])["qLayout"]["qMeasure"]
        defs[nombre] = lay["qDef"]
        print("  %-4s %-38s %s" % (nombre, lay.get("qLabel") or "", lay["qDef"]))

    min_p = int(round(float(str(q.evaluate(doc, "=Min([AñoMes_Num])")).replace(",", "."))))
    print("\n  min_p de la app = %d (%s)" % (min_p, C.periodo_label(min_p)))

    mapping = __import__("json").load(open("../datos/mapeo_mercados.json", encoding="utf-8"))

    for prod in PRODUCTOS:
        merc = mapping[prod]
        print("\n" + "=" * 72)
        print("%s  (mercado %r)" % (prod, merc))
        print("=" * 72)
        print("%-10s %10s %10s %10s   %12s %12s" %
              ("corrida", "sie", "p80", "tot", "CPA dist 3m", "CPA mes"))
        for P in (24317, 24318):
            # selección idéntica a la del extractor
            q.clear_all(doc)
            q.select_text(doc, "TipoMercado", C.TIPO_MERCADO)
            q.select_num(doc, "AñoMes_Num", range(min_p, P + 1))
            q.select_text(doc, "DescripcionMercado", merc)
            vals = []
            for nombre, mid in MEDIDAS:
                h = q.rpc("GetMeasure", doc, [mid])["qReturn"]["qHandle"]
                d = q.rpc("GetLayout", h, [])["qLayout"]["qMeasure"]["qDef"]
                vals.append(q.evaluate(doc, "=" + d))
            # conteo manual: farmacias distintas del mercado en la ventana trimestral
            cpa3 = q.evaluate(doc, "=count(distinct {<[AñoMes_Num]={\">=$(=max(AñoMes_Num)-2)"
                                   "<=$(=max(AñoMes_Num))\"}>} CPA)")
            # y en el mes final solo
            q.clear_all(doc)
            q.select_text(doc, "TipoMercado", C.TIPO_MERCADO)
            q.select_text(doc, "DescripcionMercado", merc)
            q.select_num(doc, "AñoMes_Num", [P])
            cpa1 = q.evaluate(doc, "=count(distinct CPA)")
            print("%-10s %10s %10s %10s   %12s %12s" %
                  (C.periodo_label(P), vals[0], vals[1], vals[2], cpa3, cpa1))

    q.close()


if __name__ == "__main__":
    main()
