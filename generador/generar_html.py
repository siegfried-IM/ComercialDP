# -*- coding: utf-8 -*-
"""Genera index.html a partir del store histórico (datos/historico.json).

- Reproduce el diseño actual (heatmap resumen + vistas por producto act vs año-ant).
- Emite AMBAS métricas: DP% (Ponderada = SIE/80-20) y DF% (Física = SIE/Total Mercado),
  con un selector en el tablero para alternar.
- Vista de EVOLUCIÓN (tendencia mes a mes) con "Total Compañía" + cada producto,
  etiquetas de datos y ambas métricas.

Uso:
    python generar_html.py            # usa el período máximo disponible en el store
    python generar_html.py 24317      # genera para un período específico (May-2026)
"""
import json, os, re, sys, datetime
import config as C

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BASE = os.path.join(HERE, "plantilla_base.html")
STORE = os.path.join(ROOT, "datos", "historico.json")
OUT = os.environ.get("TABLERO_OUT") or os.path.join(ROOT, "index.html")

MESES = ["", "Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
MESES_LARGO = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
               "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
COMPANY = "TOTAL COMPAÑÍA"
DEN = {"DP": "p80", "DF": "totmdo"}   # denominador según métrica


def period_label(num):
    a, m = divmod(num, 12)
    if m == 0:
        a -= 1; m = 12
    return f"{MESES[m]}-{a}"


def period_largo(num):
    a, m = divmod(num, 12)
    if m == 0:
        a -= 1; m = 12
    return f"{MESES_LARGO[m]} {a}"


def parse_js_var(src, name):
    i = src.index("var " + name + " = ") + len("var " + name + " = ")
    j = src.index("\n", i)
    return json.loads(src[i:j].rstrip().rstrip(";"))


def ratio(d, suf, metric):
    den = d.get(DEN[metric] + "_" + suf, 0)
    return (d.get("sie_" + suf, 0) / den) if den else 0.0


def build_dpdata(pdata, productNames, zonesOrder, zoneRegions, metric):
    rows = []
    total = {"zona": "", "region": "TOTAL", "values": {}}
    for pn in productNames:
        total["values"][pn] = round(ratio(pdata.get(pn, {}).get("TOTAL", {}), "act", metric), 6)
    rows.append(total)
    for zona in zonesOrder:
        for region in zoneRegions[zona]:
            row = {"zona": zona, "region": region, "values": {}}
            for pn in productNames:
                row["values"][pn] = round(ratio(pdata.get(pn, {}).get(region, {}), "act", metric), 6)
            rows.append(row)
    return rows


def build_productdata(pdata, productNames, zonesOrder, zoneRegions, metric):
    out = {}
    for pn in productNames:
        pd = pdata.get(pn, {})
        arr = [{"zona": "", "region": "TOTAL",
                "ant": round(ratio(pd.get("TOTAL", {}), "ant", metric), 6),
                "act": round(ratio(pd.get("TOTAL", {}), "act", metric), 6)}]
        for zona in zonesOrder:
            for region in zoneRegions[zona]:
                d = pd.get(region, {})
                arr.append({"zona": zona, "region": region,
                            "ant": round(ratio(d, "ant", metric), 6),
                            "act": round(ratio(d, "act", metric), 6)})
        out[pn] = arr
    return out


def build_evolution(store, productNames, zonesOrder, zoneRegions, metric):
    """Serie (act) por producto y ubicación (TOTAL / Zona / Región).
    Incluye 'TOTAL COMPAÑÍA' (agregado de todos los mercados). Todo por Σsie/Σden."""
    def completo(pk):
        pd = store["datos"][pk]
        ok = sum(1 for v in pd.values() if isinstance(v, dict) and v.get("_ok"))
        return ok >= len(productNames)
    periods = sorted(int(p) for p in store["datos"].keys() if completo(p))
    labels = [period_label(p) for p in periods]
    dkey = DEN[metric] + "_act"
    regions = [r for z in zonesOrder for r in zoneRegions[z]]
    # ubicaciones: TOTAL nacional, cada Zona, cada Provincia, cada Región
    locs = (["TOTAL"] + ["ZONA:" + z for z in zonesOrder] +
            ["PROV:" + p for p in C.PROVINCES] + regions)

    def counts(prod_dict, loc):
        """(sie, den) para un producto en una ubicación."""
        if loc.startswith("ZONA:"):
            regs = zoneRegions[loc[5:]]
        elif loc.startswith("PROV:"):
            prov = loc[5:]
            regs = [r for r in regions if C.REGION_TO_PROVINCE.get(r) == prov]
        elif loc == "TOTAL":
            regs = ["TOTAL"]
        else:
            regs = [loc]
        sie = den = 0.0
        for r in regs:
            c = prod_dict.get(r)
            if c:
                sie += c.get("sie_act", 0); den += c.get(dkey, 0)
        return sie, den

    series = {COMPANY: {}}
    for loc in locs:
        vals = []
        for p in periods:
            pdp = store["datos"][str(p)]
            sie = den = 0.0
            for pn in productNames:
                d = pdp.get(pn)
                if not d or not d.get("_ok"):
                    continue
                s, dd = counts(d, loc)
                sie += s; den += dd
            vals.append(round(sie / den, 6) if den else None)
        series[COMPANY][loc] = vals
    for pn in productNames:
        series[pn] = {}
        for loc in locs:
            vals = []
            for p in periods:
                d = store["datos"][str(p)].get(pn, {})
                s, dd = counts(d, loc) if d else (0, 0)
                vals.append(round(s / dd, 6) if dd else None)
            series[pn][loc] = vals
    return {"labels": labels, "periods": periods,
            "products": [COMPANY] + list(productNames), "series": series}


WIN_ORDER = ["MEN", "TRI", "SEM", "MAT", "YTD"]
WIN_LABEL = {"MEN": "Mensual", "TRI": "Trimestre", "SEM": "Semestre", "MAT": "MAT (12m)", "YTD": "YTD"}
WIN_LEN = {"MEN": 1, "TRI": 3, "SEM": 6, "MAT": 12}   # YTD depende del mes


def _month(p):
    m = p % 12
    return 12 if m == 0 else m


def build_counts(store, winstore, productNames, zonesOrder, zoneRegions):
    """Conteos CRUDOS por período / producto / ubicación, para que el navegador
    pueda armar cualquier período con cualquier ventana.

    Reemplaza a WIN + dpData + productData, que traían ratios ya calculados y de
    UN solo período (build_windows clavaba CUR = max del store e ignoraba el
    argumento de período). Con los conteos el front calcula DP% y DF% y agrega a
    zona / provincia / total como ratio de sumas, que es la única forma correcta
    de agregar: un promedio de porcentajes da otro número.

    Sale más liviano que lo que reemplaza porque no duplica la serie por métrica.

      TRIM.prod[producto][ubicación] = [[sie, p80, mercado], ...]  # 1 por período
      WINC.prod[producto][ubicación][ventana] = [[sie, p80, mercado], ...]

    TRIM cubre los 23 períodos de historico.json; WINC los 9 de historico_win.
    Las ubicaciones son TOTAL + las 29 regiones: zona, provincia y compañía se
    derivan sumando regiones en el front.
    """
    regions = [r for z in zonesOrder for r in zoneRegions[z]]
    locs = ["TOTAL"] + regions

    def completo(st, pk):
        pd = st["datos"][pk]
        return sum(1 for v in pd.values() if isinstance(v, dict) and v.get("_ok")) >= len(productNames)

    # --- TRIM (medida maestra trimestral), todos los períodos completos ---
    tper = sorted(int(p) for p in store["datos"] if completo(store, str(p)))
    tprod = {}
    for pn in productNames:
        porloc = {}
        for loc in locs:
            serie = []
            for p in tper:
                d = store["datos"][str(p)].get(pn, {})
                c = d.get(loc)
                serie.append([int(round(c.get("sie_act", 0))), int(round(c.get("p80_act", 0))),
                              int(round(c.get("totmdo_act", 0)))] if c else None)
            if any(serie):
                porloc[loc] = serie
        tprod[pn] = porloc
    TRIM = {"periodos": tper, "labels": [period_label(p) for p in tper],
            "regions": regions, "prod": tprod}

    # --- 5 ventanas, sólo en los períodos que se extrajeron ---
    WINC = None
    if winstore and winstore.get("datos"):
        wper = sorted(int(p) for p in winstore["datos"] if completo(winstore, str(p)))
        wprod = {}
        for pn in productNames:
            porloc = {}
            for loc in locs:
                porwin = {}
                # TRI no viaja: el front lo lee siempre de TRIM (la medida maestra de
                # historico.json), que cubre los 23 períodos y no sólo estos 9.
                for W in [x for x in WIN_ORDER if x != "TRI"]:
                    serie = []
                    for p in wper:
                        c = winstore["datos"][str(p)].get(pn, {}).get(loc, {}).get(W)
                        serie.append([int(round(c["s"])), int(round(c["p"])), int(round(c["t"]))] if c else None)
                    if any(serie):
                        porwin[W] = serie
                if porwin:
                    porloc[loc] = porwin
            wprod[pn] = porloc
        WINC = {"periodos": wper, "labels": [period_label(p) for p in wper],
                "regions": regions, "prod": wprod}
    return TRIM, WINC


def build_unidades(unistore, productNames, zonesOrder, zoneRegions):
    """Desde unidades_region.json arma, por ventana y producto, las unidades por
    ubicación: región (para tablas) y provincia (para el mapa). tot = unidades
    totales del mercado; gap = potencial no capturado (mercado en farmacias sin SIE).
    Ambas aditivas -> provincia = suma de sus regiones."""
    datos = unistore.get("datos", {})
    if not datos:
        return None
    CUR = max(int(k) for k in datos)
    cur = datos[str(CUR)]
    regions = [r for z in zonesOrder for r in zoneRegions[z]]
    prov_regions = {}
    for r in regions:
        prov_regions.setdefault(C.REGION_TO_PROVINCE.get(r), []).append(r)
    out = {"order": WIN_ORDER, "current": CUR, "curLabel": period_label(CUR), "win": {}}
    for W in WIN_ORDER:
        reg_out, prov_out = {}, {}
        comp_prov = {}   # provincia -> [Σtot, Σgap, Σsie] sobre todos los productos (TOTAL COMPAÑÍA)
        for pn in productNames:
            pd = cur.get(pn)
            if not pd or not pd.get("_ok"):
                continue
            rmap = {}
            for loc, wins in pd.items():
                if loc == "_ok":
                    continue
                c = wins.get(W)
                if c:
                    rmap[loc] = {"tot": int(round(c["tot"])), "gap": int(round(c["gap"])), "sie": int(round(c.get("sie", 0)))}
            reg_out[pn] = rmap
            pmap = {}
            for prov, regs in prov_regions.items():
                if not prov:
                    continue
                tot = gap = sie = 0.0; any_ = False
                for r in regs:
                    c = pd.get(r, {}).get(W)
                    if c:
                        any_ = True; tot += c["tot"]; gap += c["gap"]; sie += c.get("sie", 0)
                if any_:
                    pmap[prov] = {"tot": int(round(tot)), "gap": int(round(gap)), "sie": int(round(sie))}
                    cp = comp_prov.setdefault(prov, [0.0, 0.0, 0.0])
                    cp[0] += tot; cp[1] += gap; cp[2] += sie
            prov_out[pn] = pmap
        prov_out["TOTAL COMPAÑÍA"] = {prov: {"tot": int(round(v[0])), "gap": int(round(v[1])), "sie": int(round(v[2]))}
                                       for prov, v in comp_prov.items()}
        out["win"][W] = {"reg": reg_out, "prov": prov_out}
    return out


def build_unidades_depto(store, productNames):
    """Desde unidades_depto.json arma WINU_DEPTO.prod[producto][geokey][ventana] = {t,g}
    (geokey una sola vez por producto, claves cortas -> JSON compacto). t=unidades del
    mercado, g=potencial no capturado. Las geokeys se re-clavean al geojson en main()."""
    datos = store.get("datos", {})
    if not datos:
        return None
    CUR = max(int(k) for k in datos)
    cur = datos[str(CUR)]
    prod = {}
    comp = {}   # geokey -> W -> [Σtot, Σgap, Σsie]  (TOTAL COMPAÑÍA: unidades son aditivas)
    for pn in productNames:
        pd = cur.get(pn)
        if not pd or not pd.get("_ok"):
            continue
        gkmap = {}
        for k, wins in pd.items():
            if k == "_ok":
                continue
            wm = {}
            for W in WIN_ORDER:
                c = wins.get(W)
                if not c:
                    continue
                if c["tot"] or c["gap"]:
                    wm[W] = {"t": int(round(c["tot"])), "g": int(round(c["gap"])), "s": int(round(c.get("sie", 0)))}
                cc = comp.setdefault(k, {}).setdefault(W, [0.0, 0.0, 0.0])
                cc[0] += c["tot"]; cc[1] += c["gap"]; cc[2] += c.get("sie", 0)
            if wm:
                gkmap[k] = wm
        prod[pn] = gkmap
    compOut = {}
    for k, wm in comp.items():
        o = {}
        for W, v in wm.items():
            if v[0] or v[1]:
                o[W] = {"t": int(round(v[0])), "g": int(round(v[1])), "s": int(round(v[2]))}
        if o:
            compOut[k] = o
    prod["TOTAL COMPAÑÍA"] = compOut
    return {"order": WIN_ORDER, "current": CUR, "curLabel": period_label(CUR), "prod": prod}


def build_depto_dp(store, productNames):
    """Desde depto_win.json (conteos s/p/t por producto/geokey/ventana, período actual)
    arma DP%/DF% por departamento y ventana, para colorear el mapa depto siguiendo la
    ventana activa. Estructura compacta: prod[producto][geokey][W] = [dp, df, mkt]
    (dp=s/p ó null; df=s/t ó null; mkt=1 si hay mercado t>0). Incluye 'TOTAL COMPAÑÍA'
    (Σ conteos sobre todos los productos: aditivo)."""
    datos = store.get("datos", {})
    if not datos:
        return None
    CUR = max(int(k) for k in datos)
    cur = datos[str(CUR)]

    def cell(s, p, t):
        if t <= 0:
            return None  # sin mercado -> se omite
        return [round(s / p, 4) if p > 0 else None, round(s / t, 4) if t > 0 else None, 1]

    prod = {}
    comp = {}  # geokey -> W -> [Σs, Σp, Σt]
    for pn in productNames:
        pd = cur.get(pn)
        if not pd or not pd.get("_ok"):
            continue
        gk = {}
        for k, wins in pd.items():
            if k == "_ok":
                continue
            wm = {}
            for W in WIN_ORDER:
                c = wins.get(W)
                if not c:
                    continue
                r = cell(c.get("s", 0), c.get("p", 0), c.get("t", 0))
                if r:
                    wm[W] = r
                cc = comp.setdefault(k, {}).setdefault(W, [0.0, 0.0, 0.0])
                cc[0] += c.get("s", 0); cc[1] += c.get("p", 0); cc[2] += c.get("t", 0)
            if wm:
                gk[k] = wm
        prod[pn] = gk

    compOut = {}
    for k, wm in comp.items():
        o = {}
        for W, spt in wm.items():
            r = cell(spt[0], spt[1], spt[2])
            if r:
                o[W] = r
        if o:
            compOut[k] = o
    prod["TOTAL COMPAÑÍA"] = compOut
    return {"order": WIN_ORDER, "current": CUR, "curLabel": period_label(CUR), "prod": prod}


def build_depto_evol(store, productNames):
    """Serie trimestral (DP% = s/p) por producto y departamento a lo largo de todos
    los períodos, para el gráfico de evolución al hacer clic en un depto.
    DP% solo (métrica principal) para acotar el tamaño; se omiten series con < 2 puntos.
    Estructura: prod[producto][geokey] = [dp por período (o null)]. Geokeys se re-clavean."""
    datos = store.get("datos", {})
    if not datos:
        return None
    periods = sorted((int(p) for p in datos), key=lambda x: x)
    labels = [period_label(p) for p in periods]
    n = len(periods)
    prod = {}
    comp = {}   # geokey -> [ [Σs, Σp] por período ]  (TOTAL COMPAÑÍA, ratio de sumas)
    for pn in productNames:
        series = {}   # geokey -> [dp por período]
        for i, p in enumerate(periods):
            pd = datos[str(p)].get(pn)
            if not pd or not pd.get("_ok"):
                continue
            for k, wins in pd.items():
                if k == "_ok":
                    continue
                tri = wins.get("TRI")
                if not tri:
                    continue
                s = tri.get("s", 0); pp = tri.get("p", 0)
                if pp > 0:
                    series.setdefault(k, [None] * n)[i] = round(s / pp, 3)
                cc = comp.setdefault(k, [[0.0, 0.0] for _ in range(n)])
                cc[i][0] += s; cc[i][1] += pp
        gk = {k: arr for k, arr in series.items() if sum(1 for x in arr if x is not None) >= 2}
        if gk:
            prod[pn] = gk
    # TOTAL COMPAÑÍA: ratio de sumas Σs/Σp por período/geokey (consistente con build_depto_dp)
    compOut = {}
    for k, arr in comp.items():
        ser = [round(sp[0] / sp[1], 3) if sp[1] > 0 else None for sp in arr]
        if sum(1 for x in ser if x is not None) >= 2:
            compOut[k] = ser
    prod["TOTAL COMPAÑÍA"] = compOut
    return {"labels": labels, "periods": periods, "prod": prod}


def compute_kpis(dpTotalRow, productNames, n_regions):
    vals = [dpTotalRow["values"].get(pn, 0) for pn in productNames]
    nonzero = [v for v in vals if v > 0]
    avg = sum(nonzero) / len(nonzero) if nonzero else 0
    above = sum(1 for v in vals if v >= 0.80)
    below = sum(1 for v in vals if 0 < v < 0.50)
    return {"avg": round(avg, 6), "above": above, "below": below, "regions": n_regions}


def main():
    with open(BASE, encoding="utf-8") as f:
        base = f.read()
    store = json.load(open(STORE, encoding="utf-8"))
    prov_geo = json.load(open(os.path.join(ROOT, "datos", "provincias_svg.json"), encoding="utf-8"))

    def load_opt(name):
        p = os.path.join(ROOT, "datos", name)
        return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None
    depto_geo = load_opt("departamentos_svg.json")
    if depto_geo:
        # Unificar features que comparten geokey (CABA viene en 14 comunas -> 1 solo
        # polígono compuesto y una sola fila en el ranking).
        merged = {}
        order = []
        for f in depto_geo["feats"]:
            k = f["k"]
            if k in merged:
                merged[k]["d"] += " " + f["d"]
            else:
                merged[k] = dict(f); order.append(k)
        depto_geo["feats"] = [merged[k] for k in order]
    mapa_part = load_opt("mapa_partido.json")
    winstore = load_opt("historico_win.json")
    unistore = load_opt("unidades_region.json")
    unidepstore = load_opt("unidades_depto.json")
    deptowinstore = load_opt("depto_win.json")
    pslstore = load_opt("psl_ponderado.json")   # PSL ponderado por el mix de presentaciones
    margstore = load_opt("factor_marginal.json")  # cuanto rinde la farmacia marginal del nucleo

    productNames = parse_js_var(base, "productNames")
    zonesOrder = parse_js_var(base, "zonesOrder")
    zoneRegions = parse_js_var(base, "zoneRegions")

    unidepobj = build_unidades_depto(unidepstore, productNames) if unidepstore else None
    windepobj = build_depto_dp(deptowinstore, productNames) if deptowinstore else None
    deptoevolobj = build_depto_evol(deptowinstore, productNames) if deptowinstore else None

    # Re-clave los datos por partido a las claves del geojson: exacto -> subconjunto
    # de tokens (Coronel Brandsen->Brandsen) -> similitud, siempre dentro de la
    # misma provincia. Robusto y sin alias frágiles.
    if depto_geo:
        import difflib
        geoset = set(f["k"] for f in depto_geo["feats"])
        by_prov = {}
        for gk in geoset:
            by_prov.setdefault(gk.split("|", 1)[0], []).append(gk)

        def resolve(datakey):
            if datakey in geoset:
                return datakey
            if "|" not in datakey:
                return None
            prov, part = datakey.split("|", 1)
            qt = set(part.split())
            best, bestsc = None, 0.0
            for gk in by_prov.get(prov, []):
                gp = gk.split("|", 1)[1]
                gt = set(gp.split())
                sm = difflib.SequenceMatcher(None, part, gp).ratio()
                inter = qt & gt
                jac = len(inter) / len(qt | gt) if (qt | gt) else 0
                sc = max(sm, jac)
                if inter and (qt <= gt or gt <= qt):
                    sc = max(sc, 0.9)          # uno contiene al otro (prefijos tipo Coronel/General)
                if sc > bestsc:
                    bestsc, best = sc, gk
            return best if bestsc >= 0.72 else None

        allk = set()
        if mapa_part:
            for met in ("DP", "DF"):
                for prod in mapa_part[met]:
                    allk.update(mapa_part[met][prod].keys())
        # incluir claves de unidades y DP por depto para resolverlas con el mismo criterio
        if unidepobj:
            for prod in unidepobj["prod"]:
                allk.update(unidepobj["prod"][prod].keys())
        if windepobj:
            for prod in windepobj["prod"]:
                allk.update(windepobj["prod"][prod].keys())
        if deptoevolobj:
            for prod in deptoevolobj["prod"]:
                allk.update(deptoevolobj["prod"][prod].keys())
        resmap = {k: resolve(k) for k in allk}
        fuzzy = {k: v for k, v in resmap.items() if v and v != k}
        unres = sorted(k for k, v in resmap.items() if not v)
        if mapa_part:
            for met in ("DP", "DF"):
                for prod in list(mapa_part[met].keys()):
                    mapa_part[met][prod] = {resmap[k]: v for k, v in mapa_part[met][prod].items() if resmap.get(k)}
        if unidepobj:
            for prod in list(unidepobj["prod"].keys()):
                unidepobj["prod"][prod] = {resmap[k]: v for k, v in unidepobj["prod"][prod].items() if resmap.get(k)}
        if windepobj:
            for prod in list(windepobj["prod"].keys()):
                windepobj["prod"][prod] = {resmap[k]: v for k, v in windepobj["prod"][prod].items() if resmap.get(k)}
        if deptoevolobj:
            for prod in list(deptoevolobj["prod"].keys()):
                deptoevolobj["prod"][prod] = {resmap[k]: v for k, v in deptoevolobj["prod"][prod].items() if resmap.get(k)}
        print(f"[mapa depto] claves: {len(allk)} | fuzzy: {len(fuzzy)} | sin resolver: {len(unres)}")
        if unres:
            print("  sin resolver:", unres[:20])

    if windepobj:
        print(f"[mapa depto x ventana] productos: {len(windepobj['prod'])} | período {windepobj['curLabel']}")
    periods = sorted(int(p) for p in store["datos"].keys())
    P = int(sys.argv[1]) if len(sys.argv) > 1 else periods[-1]
    if str(P) not in store["datos"]:
        sys.exit(f"Período {P} ({period_label(P)}) no está en el store.")
    pdata = store["datos"][str(P)]
    n_regions = sum(len(v) for v in zoneRegions.values())
    trimc, wincobj = build_counts(store, winstore, productNames, zonesOrder, zoneRegions)
    if P not in trimc["periodos"]:
        sys.exit(f"Período {P} ({period_label(P)}) está en el store pero incompleto "
                 f"(build_counts exige los {len(productNames)} productos con _ok). "
                 f"Completá la extracción o generá para otro período.")
    print(f"[conteos TRIM] {len(trimc['periodos'])} períodos: "
          f"{trimc['labels'][0]}..{trimc['labels'][-1]}")
    if wincobj:
        print(f"[conteos ventanas] {len(wincobj['periodos'])} períodos: {', '.join(wincobj['labels'])}")
    # Metadata del segmentador: qué períodos se pueden elegir con cada ventana.
    # TRI sale de historico.json (todos); el resto sólo de los períodos extraídos.
    winmeta = {"order": WIN_ORDER, "label": WIN_LABEL, "len": WIN_LEN,
               "current": P, "curLabel": period_label(P),
               "periodos": {W: (trimc["periodos"] if W == "TRI"
                                else (wincobj["periodos"] if wincobj else []))
                            for W in WIN_ORDER},
               "labels": {W: (trimc["labels"] if W == "TRI"
                              else (wincobj["labels"] if wincobj else []))
                          for W in WIN_ORDER}}
    uniobj = build_unidades(unistore, productNames, zonesOrder, zoneRegions) if unistore else None
    if uniobj:
        nprod = len(uniobj["win"]["TRI"]["reg"])
        print(f"[unidades] período {uniobj['curLabel']} | productos con datos: {nprod}")

    data = {}
    for m in ("DP", "DF"):
        dpData = build_dpdata(pdata, productNames, zonesOrder, zoneRegions, m)
        data[m] = {
            "dp": dpData,
            "prod": build_productdata(pdata, productNames, zonesOrder, zoneRegions, m),
            "evol": build_evolution(store, productNames, zonesOrder, zoneRegions, m),
            "kpi": compute_kpis(dpData[0], productNames, n_regions),
        }

    lbl = period_largo(P)
    gen_ts = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    kpiDP, kpiDF = data["DP"]["kpi"], data["DF"]["kpi"]

    html = base
    html = re.sub(r"<title>.*?</title>", f"<title>DP% Report - {lbl}</title>", html, count=1)
    # El subtítulo del resumen lo fija el JS (updateMetricLabels) usando PERIODO_LBL.
    html = re.sub(r"Generado el [^\n]*?\| DP% Report - Datos [^\n<]*",
                  f"Generado el {gen_ts} | DP% Report - Datos {lbl}", html, count=1)
    # KPIs iniciales (DP); el JS los recalcula al alternar métrica
    html = re.sub(r'(id="kpiAvg">).*?(</div>)', rf'\g<1>{kpiDP["avg"]*100:.1f}%\g<2>', html, count=1)
    html = re.sub(r'(id="kpiAbove">).*?(</div>)', rf'\g<1>{kpiDP["above"]}\g<2>', html, count=1)
    html = re.sub(r'(id="kpiBelow">).*?(</div>)', rf'\g<1>{kpiDP["below"]}\g<2>', html, count=1)
    html = re.sub(r'(id="kpiRegions">).*?(</div>)', rf'\g<1>{kpiDP["regions"]}\g<2>', html, count=1)

    def dump(v):
        return json.dumps(v, ensure_ascii=False)

    # dpData / productData -> versiones DP y DF + var activa (DP por defecto)
    dp_block = ("var dpDataDP = " + dump(data["DP"]["dp"]) + ";\n"
                "var dpDataDF = " + dump(data["DF"]["dp"]) + ";\n"
                "var dpData = dpDataDP;\n")
    html = re.sub(r"var dpData = .*?;\n", lambda m: dp_block, html, count=1)
    prod_block = ("var productDataDP = " + dump(data["DP"]["prod"]) + ";\n"
                  "var productDataDF = " + dump(data["DF"]["prod"]) + ";\n"
                  "var productData = productDataDP;\n")
    html = re.sub(r"var productData = .*?;\n", lambda m: prod_block, html, count=1)

    # evolData (DP/DF) + conteos por período, antes de currentView
    inject = ("var evolDataDP = " + dump(data["DP"]["evol"]) + ";\n"
              "var evolDataDF = " + dump(data["DF"]["evol"]) + ";\n"
              "var evolData = evolDataDP;\n"
              "var currentMetric = 'DP';\n"
              "var PERIODO_LBL = " + dump(lbl) + ";\n"
              "var provGeo = " + dump(prov_geo) + ";\n"
              "var regionProvincia = " + dump(C.REGION_TO_PROVINCE) + ";\n"
              "var provinciasOrden = " + dump(C.PROVINCES) + ";\n" +
              ("var provGeoDepto = " + dump(depto_geo) + ";\n" if depto_geo else "") +
              # mapaPartido reemplazado por WINDEP (DP/DF por depto y ventana, incl. TOTAL COMPAÑÍA)
              # WIN ya no se inyecta: el front lo arma por período desde los conteos
              # (WINp() en la plantilla), así el segmentador puede moverse sin
              # multiplicar el payload por cada período.
              # Factor marginal: la farmacia que se gana al subir el DP% es de la COLA
              # del nucleo, no la promedio. Rinde ~0,39 de la promedio (medido por
              # producto). Sin esto la atribucion se sobreestima unas 2,6 veces.
              ("var FACTMARG = " + dump({k: v["factor"] for k, v in margstore["datos"].items()
                                         if v.get("factor")}) + ";\n"
               if margstore else "var FACTMARG = null;\n") +
              # PSL ponderado por el mix real de unidades de cada presentacion:
              # dentro de un mismo mercado los precios de lista llegan a diferir 45x,
              # asi que un PSL unico por producto seria un numero elegido a dedo.
              ("var PSL = " + dump({k: {"psl": v["psl_ponderado"], "cob": v["cobertura"]}
                                    for k, v in pslstore["datos"].items()
                                    if v.get("psl_ponderado")}) + ";\n"
               if pslstore else "var PSL = null;\n") +
              "var WINMETA = " + dump(winmeta) + ";\n" +
              "var TRIMC = " + dump(trimc) + ";\n" +
              ("var WINC = " + dump(wincobj) + ";\n" if wincobj else "var WINC = null;\n") +
              ("var WINU = " + dump(uniobj) + ";\n" if uniobj else "var WINU = null;\n") +
              ("var WINU_DEPTO = " + dump(unidepobj) + ";\n" if unidepobj else "var WINU_DEPTO = null;\n") +
              ("var WINDEP = " + dump(windepobj) + ";\n" if windepobj else "var WINDEP = null;\n") +
              ("var DEPTO_EVOL = " + dump(deptoevolobj) + ";\n" if deptoevolobj else "var DEPTO_EVOL = null;\n"))
    html = html.replace("var currentView = 'summary';", inject + "var currentView = 'summary';", 1)

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Generado {OUT} para {lbl}.")
    print(f"DP%: prom={kpiDP['avg']*100:.1f}% >=80%:{kpiDP['above']} <50%:{kpiDP['below']}")
    print(f"DF%: prom={kpiDF['avg']*100:.1f}% >=80%:{kpiDF['above']} <50%:{kpiDF['below']}")
    print(f"Períodos en evolución: {data['DP']['evol']['labels']}")


if __name__ == "__main__":
    main()
