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


def build_windows(winstore, productNames, zonesOrder, zoneRegions):
    """Desde historico_win.json (conteos por producto/región/ventana/período)
    arma, por ventana y métrica, los datasets de período actual con 2 variaciones.
    Devuelve dict listo para inyectar; ausencia de período de comparación => variación null."""
    datos = winstore.get("datos", {})
    if not datos:
        return None
    CUR = max(int(k) for k in datos)
    regions = [r for z in zonesOrder for r in zoneRegions[z]]

    def counts(prod, region, win, period):
        d = datos.get(str(period), {}).get(prod, {}).get(region)
        if not d or win not in d:
            return None
        c = d[win]
        return (c["s"], c["p"], c["t"])

    def ratio(prod, region_list, win, period, metric):
        s = den = 0.0; any_ = False
        for r in region_list:
            c = counts(prod, r, win, period)
            if c:
                any_ = True; s += c[0]; den += c[1] if metric == "DP" else c[2]
        if not any_ or den == 0:
            return None
        return round(s / den, 6)

    def var_periods(win):
        L = _month(CUR) if win == "YTD" else WIN_LEN[win]
        return CUR - 12, CUR - L      # (año anterior, período anterior)

    # regiones que componen cada ubicación
    prov_regions = {}
    for r in regions:
        prov_regions.setdefault(C.REGION_TO_PROVINCE.get(r), []).append(r)

    out = {"order": WIN_ORDER, "label": WIN_LABEL, "current": CUR, "curLabel": period_label(CUR),
           "win": {}, "prov": {}, "provOrder": C.PROVINCES}
    for W in WIN_ORDER:
        ant_p, prev_p = var_periods(W)
        out["win"][W] = {}
        out["prov"][W] = {}
        for M in ("DP", "DF"):
            # heatmap: TOTAL + regiones, valor actual por producto
            rows = []
            total = {"zona": "", "region": "TOTAL", "values": {}}
            for pn in productNames:
                total["values"][pn] = ratio(pn, ["TOTAL"], W, CUR, M)
            rows.append(total)
            for z in zonesOrder:
                for reg in zoneRegions[z]:
                    row = {"zona": z, "region": reg, "values": {}}
                    for pn in productNames:
                        row["values"][pn] = ratio(pn, [reg], W, CUR, M)
                    rows.append(row)
            # product tables: por producto, por región: act / año ant / período ant
            prod = {}
            for pn in productNames:
                arr = [{"zona": "", "region": "TOTAL",
                        "act": ratio(pn, ["TOTAL"], W, CUR, M),
                        "ay": ratio(pn, ["TOTAL"], W, ant_p, M),
                        "ap": ratio(pn, ["TOTAL"], W, prev_p, M)}]
                for z in zonesOrder:
                    for reg in zoneRegions[z]:
                        arr.append({"zona": z, "region": reg,
                                    "act": ratio(pn, [reg], W, CUR, M),
                                    "ay": ratio(pn, [reg], W, ant_p, M),
                                    "ap": ratio(pn, [reg], W, prev_p, M)})
                prod[pn] = arr
            # zonas (para el ranking de Crecimiento por zona): Σ conteos de sus regiones
            zn = {}
            for pn in productNames:
                zn[pn] = {}
                for z in zonesOrder:
                    regs = zoneRegions[z]
                    zn[pn][z] = {"act": ratio(pn, regs, W, CUR, M),
                                 "ay": ratio(pn, regs, W, ant_p, M),
                                 "ap": ratio(pn, regs, W, prev_p, M)}
            out["win"][W][M] = {"dp": rows, "prod": prod, "zone": zn, "antP": ant_p, "prevP": prev_p,
                                "antLabel": period_label(ant_p), "prevLabel": period_label(prev_p)}
            # provincias (para el mapa): por producto + TOTAL COMPAÑÍA
            pv = {}
            comp_regions = regions
            for pn in productNames:
                pv[pn] = {}
                for prov, regs in prov_regions.items():
                    if not prov:
                        continue
                    pv[pn][prov] = {"act": ratio(pn, regs, W, CUR, M),
                                    "ay": ratio(pn, regs, W, ant_p, M),
                                    "ap": ratio(pn, regs, W, prev_p, M)}
            # TOTAL COMPAÑÍA por provincia = Σ conteos sobre todos los productos
            comp = {}
            for prov, regs in prov_regions.items():
                if not prov:
                    continue
                def comp_ratio(period):
                    s = den = 0.0; any_ = False
                    for pn in productNames:
                        for r in regs:
                            c = counts(pn, r, W, period)
                            if c:
                                any_ = True; s += c[0]; den += c[1] if M == "DP" else c[2]
                    return round(s / den, 6) if (any_ and den) else None
                comp[prov] = {"act": comp_ratio(CUR), "ay": comp_ratio(ant_p), "ap": comp_ratio(prev_p)}
            pv["TOTAL COMPAÑÍA"] = comp
            out["prov"][W][M] = pv
    return out


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
            prov_out[pn] = pmap
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
                if c and (c["tot"] or c["gap"]):
                    wm[W] = {"t": int(round(c["tot"])), "g": int(round(c["gap"])), "s": int(round(c.get("sie", 0)))}
            if wm:
                gkmap[k] = wm
        prod[pn] = gkmap
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
                pp = tri.get("p", 0)
                if pp > 0:
                    series.setdefault(k, [None] * n)[i] = round(tri.get("s", 0) / pp, 3)
        gk = {k: arr for k, arr in series.items() if sum(1 for x in arr if x is not None) >= 2}
        if gk:
            prod[pn] = gk
    return {"labels": labels, "prod": prod}


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

    productNames = parse_js_var(base, "productNames")
    zonesOrder = parse_js_var(base, "zonesOrder")
    zoneRegions = parse_js_var(base, "zoneRegions")

    unidepobj = build_unidades_depto(unidepstore, productNames) if unidepstore else None
    windepobj = build_depto_dp(deptowinstore, productNames) if deptowinstore else None
    deptoevolobj = build_depto_evol(deptowinstore, productNames) if deptowinstore else None

    # Re-clave los datos por partido a las claves del geojson: exacto -> subconjunto
    # de tokens (Coronel Brandsen->Brandsen) -> similitud, siempre dentro de la
    # misma provincia. Robusto y sin alias frágiles.
    if depto_geo and mapa_part:
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
    winobj = build_windows(winstore, productNames, zonesOrder, zoneRegions) if winstore else None
    if winobj:
        print(f"[ventanas] {winobj['order']} | período {winobj['curLabel']}")
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

    # evolData (DP/DF) + kpiData, antes de currentView
    inject = ("var evolDataDP = " + dump(data["DP"]["evol"]) + ";\n"
              "var evolDataDF = " + dump(data["DF"]["evol"]) + ";\n"
              "var evolData = evolDataDP;\n"
              "var kpiData = " + dump({"DP": kpiDP, "DF": kpiDF}) + ";\n"
              "var currentMetric = 'DP';\n"
              "var PERIODO_LBL = " + dump(lbl) + ";\n"
              "var provGeo = " + dump(prov_geo) + ";\n"
              "var regionProvincia = " + dump(C.REGION_TO_PROVINCE) + ";\n"
              "var provinciasOrden = " + dump(C.PROVINCES) + ";\n" +
              ("var provGeoDepto = " + dump(depto_geo) + ";\n" if depto_geo else "") +
              # mapaPartido reemplazado por WINDEP (DP/DF por depto y ventana, incl. TOTAL COMPAÑÍA)
              ("var WIN = " + dump(winobj) + ";\n" if winobj else "var WIN = null;\n") +
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
