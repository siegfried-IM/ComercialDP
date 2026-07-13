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
    mapa_part = load_opt("mapa_partido.json")

    productNames = parse_js_var(base, "productNames")
    zonesOrder = parse_js_var(base, "zonesOrder")
    zoneRegions = parse_js_var(base, "zoneRegions")

    periods = sorted(int(p) for p in store["datos"].keys())
    P = int(sys.argv[1]) if len(sys.argv) > 1 else periods[-1]
    if str(P) not in store["datos"]:
        sys.exit(f"Período {P} ({period_label(P)}) no está en el store.")
    pdata = store["datos"][str(P)]
    n_regions = sum(len(v) for v in zoneRegions.values())

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
              ("var mapaPartido = " + dump(mapa_part) + ";\n" if mapa_part else ""))
    html = html.replace("var currentView = 'summary';", inject + "var currentView = 'summary';", 1)

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Generado {OUT} para {lbl}.")
    print(f"DP%: prom={kpiDP['avg']*100:.1f}% >=80%:{kpiDP['above']} <50%:{kpiDP['below']}")
    print(f"DF%: prom={kpiDF['avg']*100:.1f}% >=80%:{kpiDF['above']} <50%:{kpiDF['below']}")
    print(f"Períodos en evolución: {data['DP']['evol']['labels']}")


if __name__ == "__main__":
    main()
