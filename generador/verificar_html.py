# -*- coding: utf-8 -*-
"""Verifica el index.html YA GENERADO contra los stores.

verificar.py chequea los stores; esto chequea el artefacto, que es otra cosa: el
HTML lleva los conteos crudos (TRIMC / WINC) y el navegador deriva DP%, DF%, zonas
y provincias. Si la inyección pierde o desalinea un período, los stores siguen
perfectos y el tablero muestra otra cosa.

Corre DESPUÉS de generar:
    python verificar.py P && python generar_html.py P && python verificar_html.py P
"""
import collections, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "datos")
HTML = os.environ.get("TABLERO_OUT") or os.path.join(ROOT, "index.html")

resultados = []


def chequeo(nombre, ok, detalle):
    estado = "PASS" if ok is True else ("SKIP" if ok is None else "FAIL")
    resultados.append(estado)
    print(f"  {estado}  {nombre:<48} {detalle}")


def js_var(src, nombre):
    marca = "var " + nombre + " = "
    i = src.index(marca) + len(marca)
    j = src.index("\n", i)
    return json.loads(src[i:j].rstrip().rstrip(";"))


def main():
    with open(HTML, encoding="utf-8") as f:
        src = f.read()
    H = json.load(open(os.path.join(DATA, "historico.json"), encoding="utf-8"))["datos"]
    W = json.load(open(os.path.join(DATA, "historico_win.json"), encoding="utf-8"))["datos"]
    TRIMC = js_var(src, "TRIMC")
    WINC = js_var(src, "WINC")
    META = js_var(src, "WINMETA")
    prods = js_var(src, "productNames")
    zonesOrder = js_var(src, "zonesOrder")
    zoneRegions = js_var(src, "zoneRegions")
    P = int(sys.argv[1]) if len(sys.argv) > 1 else META["current"]
    locs = ["TOTAL"] + [r for z in zonesOrder for r in zoneRegions[z]]

    print(f"Verificación del index.html generado ({os.path.getsize(HTML)/1e6:.2f} MB) "
          f"· período {META['curLabel']}")

    chequeo("período generado == el pedido", META["current"] == P,
            f"WINMETA.current={META['current']} · pedido={P}")

    # --- cobertura: la lista de referencia sale del STORE, no del HTML. Si se
    # recorriera TRIMC["periodos"] un período perdido en la inyección jamás se
    # miraría y el chequeo daría PASS sobre un artefacto incompleto.
    completos = sorted(int(p) for p in H
                       if sum(1 for v in H[p].values()
                              if isinstance(v, dict) and v.get("_ok")) >= len(prods))
    faltan = [p for p in completos if p not in TRIMC["periodos"]]
    sobran = [p for p in TRIMC["periodos"] if p not in completos]
    chequeo("TRIMC cubre todos los períodos completos del store", not faltan and not sobran,
            f"{len(completos)} completos en el store · {len(TRIMC['periodos'])} en el HTML" +
            (f" · faltan {faltan}" if faltan else "") + (f" · sobran {sobran}" if sobran else ""))

    # --- TRIMC: conteo a conteo contra historico.json ---
    mal, n = [], 0
    for i, per in enumerate(TRIMC["periodos"]):
        for pn in prods:
            for loc in locs:
                c = TRIMC["prod"].get(pn, {}).get(loc)
                cel = c[i] if c else None
                orig = H[str(per)].get(pn, {}).get(loc)
                esp = [int(round(orig["sie_act"])), int(round(orig["p80_act"])),
                       int(round(orig["totmdo_act"]))] if orig else None
                n += 1
                if cel != esp:
                    mal.append(f"{per}/{pn}/{loc}: html={cel} store={esp}")
    chequeo("TRIMC == historico.json", not mal,
            f"{n} celdas · {len(mal)} diferencias" + (f": {mal[:2]}" if mal else ""))

    # --- WINC: idem contra historico_win.json ---
    mal, n = [], 0
    for i, per in enumerate(WINC["periodos"]):
        for pn in prods:
            for loc in locs:
                for win in [x for x in META["order"] if x != "TRI"]:
                    c = WINC["prod"].get(pn, {}).get(loc, {}).get(win)
                    cel = c[i] if c else None
                    o = W[str(per)].get(pn, {}).get(loc, {}).get(win)
                    esp = [int(round(o["s"])), int(round(o["p"])), int(round(o["t"]))] if o else None
                    n += 1
                    if cel != esp:
                        mal.append(f"{per}/{pn}/{loc}/{win}: html={cel} store={esp}")
    trae_tri = any("TRI" in WINC["prod"].get(pn, {}).get(loc, {})
                   for pn in prods for loc in locs)
    chequeo("WINC no duplica TRI (lo aporta TRIM)", not trae_tri,
            "ausente" if not trae_tri else "TRI viaja sin leerse y puede discrepar con TRIM")
    chequeo("WINC == historico_win.json", not mal,
            f"{n} celdas · {len(mal)} diferencias" + (f": {mal[:2]}" if mal else ""))

    # --- el segmentador ofrece exactamente los períodos que tienen dato ---
    okp = True
    detalles = []
    for win in META["order"]:
        ofrecidos = META["periodos"][win]
        esperados = TRIMC["periodos"] if win == "TRI" else WINC["periodos"]
        if win != "TRI" and not WINC["periodos"]:
            esperados = []
        if ofrecidos != esperados:
            okp = False
            detalles.append(f"{win}: ofrece {len(ofrecidos)}, hay {len(esperados)}")
        else:
            detalles.append(f"{win}:{len(ofrecidos)}")
    chequeo("segmentador ofrece sólo períodos con dato", okp, " · ".join(detalles))

    # --- ninguna ventana puede ofrecer un período sin la comparación declarada:
    #     no es un error, pero hay que saber cuántos quedan sin año anterior ---
    sin_ant = {}
    for win in META["order"]:
        ps = META["periodos"][win]
        sin_ant[win] = sum(1 for p in ps if (p - 12) not in ps)
    chequeo("períodos sin año anterior (se muestran s/d)", True,
            " · ".join(f"{w}:{c}/{len(META['periodos'][w])}" for w, c in sin_ant.items()))

    # --- la evolucion por departamento usa los mismos periodos que la serie principal.
    #     depto_win conserva trimestres truncados de los meses mas viejos de la app; sin este
    #     filtro dibujaban un punto bajo falso al inicio de la evolucion por departamento ---
    DEPTO = js_var(src, "DEPTO_EVOL")
    if not DEPTO:
        chequeo("evolución por departamento sobre la serie principal", None, "el HTML no trae DEPTO_EVOL")
    else:
        fuera = [x for x in DEPTO["periods"] if x not in TRIMC["periodos"]]
        chequeo("evolución por departamento sobre la serie principal", not fuera,
                f"{len(DEPTO['periods'])} períodos de departamento · {len(TRIMC['periodos'])} en la serie"
                + (f" · fuera de la serie: {fuera}" if fuera else ""))

    # --- el pie declara el reload con el que se armaron los datos. Se calcula desde el
    #     STORE: si se leyera del HTML el chequeo compararia el pie consigo mismo ---
    sellos = json.load(open(os.path.join(DATA, "historico.json"), encoding="utf-8")).get("sellos", {})
    cont = collections.Counter(sellos.get(str(P), {}).values())
    pie = re.search(r'<div class="footer">(.*?)</div>', src, re.S)
    pie = pie.group(1) if pie else ""
    if not cont:
        chequeo("el pie declara el reload de IQVIA", None, "el store no tiene sellos de reload")
    else:
        actual = cont.most_common(1)[0][0]
        fecha = actual.split(" ")[0]
        pers = [str(x) for x in TRIMC["periodos"]]
        mixtos = [pn for pn in prods if any(sellos.get(x, {}).get(pn) != actual for x in pers)]
        ok_fecha = ("reload del " + fecha) in pie
        ok_resto = ("conserv" in pie) if mixtos else ("toda la serie" in pie)
        chequeo("el pie declara el reload de IQVIA", ok_fecha and ok_resto,
                f"reload {fecha} · {len(mixtos)} productos con períodos de otro reload"
                + ("" if ok_fecha and ok_resto else f" · pie: {pie.strip()[:90]!r}"))

    # --- variables que ya no deben viajar en el HTML (pesaban y estaban clavadas) ---
    muertas = [v for v in ("var WIN = ", "var kpiData = ") if v in src]
    chequeo("sin variables obsoletas (WIN, kpiData)", not muertas, f"{muertas or 'ninguna'}")

    print()
    nf = resultados.count("FAIL"); ns = resultados.count("SKIP")
    print(f"{resultados.count('PASS')} PASS · {nf} FAIL · {ns} SKIP")
    if nf or ns:
        print("NO PUBLICAR: el HTML no reproduce los stores.")
    return 1 if (nf or ns) else 0


if __name__ == "__main__":
    sys.exit(main())
