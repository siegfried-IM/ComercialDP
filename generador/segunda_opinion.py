# -*- coding: utf-8 -*-
"""Segunda opinión: vuelve a consultar Qlik para los 42 productos y compara
contra lo que quedó guardado, SIN escribir nada.

Por qué existe: verificar.py cruza store contra store. Si un producto se
contaminara en los dos stores del par, el cruce pasaría igual. Esto compara
contra la fuente, que es el único camino verdaderamente independiente.

De paso ejercita qlik_client.check_selection 42 veces (el guardarraíl que se
agregó después de la corrida de Jun-2026 y nunca se había ejecutado), y prueba
a propósito que corte cuando la selección se contamina de verdad.

Uso:  python segunda_opinion.py [periodo]
"""
import json, os, sys, time
from collections import defaultdict
from qlik_client import Qix, connect_retry
import config as C

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "datos")
MEAS_ORDER = ["sie_act", "p80_act", "totmdo_act"]
TOL = 0.005   # 0,5%: la contaminación vista fue de 50-90%, la reexpresión <0,5%


def num(c):
    v = c.get("qNum")
    return v if isinstance(v, (int, float)) else 0.0


def agregar(filas):
    """Misma agregación que el extractor: sólo las RegionCUP mapeadas."""
    tot = {k: 0.0 for k in MEAS_ORDER}
    for r in filas:
        if C.REGIONCUP_TO_REGION.get(r[0]["qText"]) is None:
            continue
        for j, k in enumerate(MEAS_ORDER):
            tot[k] += num(r[j + 1])
    return tot


def releer(q, doc, min_p, P, merc):
    """Segunda lectura del mismo producto, para distinguir un store equivocado
    de una lectura equivocada."""
    try:
        time.sleep(1)
        q.clear_all(doc)
        q.select_text(doc, "TipoMercado", C.TIPO_MERCADO)
        q.select_num(doc, "AñoMes_Num", range(min_p, P + 1))
        q.select_text(doc, "DescripcionMercado", merc)
        q.check_selection(doc, "DescripcionMercado")
        return q.hypercube(doc, [C.DIM_REGIONCUP], [C.MEAS[k] for k in MEAS_ORDER])
    except Exception as e:
        print(f"   relectura falló: {e}")
        return None


def probar_guardarrail(q, doc, min_p, P):
    """El guardarraíl tiene que dejar pasar 1 mercado y cortar con 2."""
    print("=== prueba del guardarraíl check_selection ===")
    q.clear_all(doc)
    q.select_text(doc, "TipoMercado", C.TIPO_MERCADO)
    q.select_num(doc, "AñoMes_Num", range(min_p, P + 1))
    q.select_text(doc, "DescripcionMercado", "Acneclin")
    try:
        q.check_selection(doc, "DescripcionMercado")
        print("   1 mercado seleccionado  -> deja pasar   OK")
    except Exception as e:
        print(f"   1 mercado seleccionado  -> CORTO MAL: {e}")
        return False
    # el caso real que se nos escapó: los dos Acneclin juntos
    q.select_text(doc, "DescripcionMercado", ["Acneclin", "Acneclin PBA"])
    try:
        q.check_selection(doc, "DescripcionMercado")
        print("   2 mercados seleccionados -> NO CORTO: el guardarraíl no sirve")
        return False
    except RuntimeError as e:
        print(f"   2 mercados seleccionados -> corta      OK  ({e})")
    return True


def main():
    mapping = json.load(open(os.path.join(DATA, "mapeo_mercados.json"), encoding="utf-8"))
    store = json.load(open(os.path.join(DATA, "historico.json"), encoding="utf-8"))
    P = int(sys.argv[1]) if len(sys.argv) > 1 else max(int(k) for k in store["datos"])
    guardado = store["datos"][str(P)]

    q, doc = connect_retry()
    q.clear_all(doc)
    min_p = int(round(float(str(q.evaluate(doc, "=Min([AñoMes_Num])")).replace(",", "."))))

    ok_guard = probar_guardarrail(q, doc, min_p, P)

    print(f"\n=== re-consulta de los {len(mapping)} productos para {C.periodo_label(P)} ===")
    print(f"{'producto':<16} {'medida':<11} {'store':>9} {'Qlik':>9} {'ratio':>8}")
    malos, inestables, comparadas, peor, peor_det = [], [], 0, 0.0, ""
    t0 = time.time()
    for i, (prod, merc) in enumerate(mapping.items(), 1):
        g = guardado.get(prod)
        if not isinstance(g, dict) or not g.get("_ok"):
            malos.append(f"{prod}: no está en el store"); continue
        filas = None
        for intento in range(3):
            try:
                q.clear_all(doc)
                q.select_text(doc, "TipoMercado", C.TIPO_MERCADO)
                q.select_num(doc, "AñoMes_Num", range(min_p, P + 1))
                q.select_text(doc, "DescripcionMercado", merc)
                q.check_selection(doc, "DescripcionMercado")
                filas = q.hypercube(doc, [C.DIM_REGIONCUP], [C.MEAS[k] for k in MEAS_ORDER])
                break
            except Exception as e:
                print(f"   {prod} intento {intento+1}: {e}")
                try: q.close()
                except Exception: pass
                q, doc = connect_retry(pausa_inicial=3)
        if filas is None:
            malos.append(f"{prod}: no se pudo re-consultar"); continue
        tot = agregar(filas)
        # El engine devuelve resultados equivocados SIN error cuando está bajo
        # contención (visto: una TRIM que traía el mensual, y un producto que
        # volvió al 5% de su tamaño). Antes de acusar al store, releemos: si las
        # dos lecturas no coinciden, la sospechosa es la lectura, no el dato.
        if any(abs(tot[k] / g["TOTAL"][k] - 1) > TOL for k in MEAS_ORDER if g["TOTAL"][k]):
            filas2 = releer(q, doc, min_p, P, merc)
            if filas2 is None:
                malos.append(f"{prod}: relectura fallida, sin veredicto"); continue
            tot2 = agregar(filas2)
            if any(abs(tot2[k] - tot[k]) > 0.5 for k in MEAS_ORDER):
                print(f"   {prod}: dos lecturas distintas entre sí ({tot} vs {tot2}) "
                      f"-> el engine está inestable, no se acusa al store")
                inestables.append(prod)
                continue
            tot = tot2
        for k in MEAS_ORDER:
            a, b = g["TOTAL"][k], tot[k]
            comparadas += 1
            d = abs(b / a - 1) if a else (0.0 if not b else 1.0)
            if d > peor:
                peor, peor_det = d, f"{prod}/{k}"
            if d > TOL:
                malos.append(f"{prod}/{k}: store {a:.0f} vs Qlik {b:.0f} ({b/a if a else 0:.2f}x)")
                print(f"{prod:<16} {k:<11} {a:>9.0f} {b:>9.0f} {b/a if a else 0:>7.2f}x  <-- DIFIERE")
        if i % 10 == 0:
            print(f"   ... {i}/{len(mapping)} productos ({time.time()-t0:.0f}s)")
    q.close()

    print(f"\n{comparadas} celdas comparadas contra Qlik en {(time.time()-t0)/60:.1f} min")
    print(f"peor desvío: {peor*100:.3f}%  ({peor_det})")
    print(f"guardarraíl: {'OK' if ok_guard else 'FALLA'}")
    if inestables:
        print(f"lecturas inestables (el engine se contradijo, sin veredicto): {inestables}")
    if malos:
        print(f"\n{len(malos)} DIFERENCIAS:")
        for m in malos:
            print("  ", m)
        return 1
    print("\nsin diferencias: el store coincide con la fuente")
    return 0 if (ok_guard and not inestables) else 1


if __name__ == "__main__":
    sys.exit(main())
