# -*- coding: utf-8 -*-
"""Pre-flight de la actualización mensual: se corre ANTES de lanzar horas de extracción.

Todo contra la app y de a una consulta (las sesiones de Qlik comparten estado de selección:
esto corre SOLO, nunca mientras hay un extractor andando).

  A. sello de reload y rango de períodos de la app
  B. los 42 mercados mapeados existen, una vez cada uno
  C. RegionCUP de la app sin mapear en config (se descartan EN SILENCIO al agregar)
  D. medidas y dimensiones maestras existen; la ventana de cada medida es parametrizable
  E. borde temporal: ¿el mes nuevo viene completo? unidades y farmacias vs meses vecinos

Uso:  python preflight.py [periodo_esperado] [--guardar]       (p.ej. 24320 = Ago-2026)
Sale con código != 0 si algo falla. Es de solo lectura salvo con --guardar, que registra la
huella de las medidas maestras en datos/medidas_hash.json para detectar el mes siguiente si
alguien las cambió en la app.

Por qué existe: IQVIA reexpresa meses pasados en cada reload (Trip D3 salió -8,6 pp de un
reload al siguiente, sin que cambiara nada en el negocio). El sello de reload que imprime
es el que hay que comparar con el de la corrida anterior antes de interpretar ningún delta.
"""
import hashlib, json, os, re, sys
from qlik_client import connect_retry
import config as C

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "datos")
res = []


def chk(nombre, ok, det):
    est = "PASS" if ok is True else ("SKIP" if ok is None else "FAIL")
    res.append(est)
    print("  %-4s %-54s %s" % (est, nombre, det))


def num(x):
    return float(str(x).replace(".", "").replace(",", "."))


def lista(q, doc, campo):
    q.clear_all(doc)
    q.select_text(doc, "TipoMercado", C.TIPO_MERCADO)
    obj = {"qInfo": {"qType": "pf"}, "qHyperCubeDef": {
        "qDimensions": [{"qDef": {"qFieldDefs": [campo]}, "qNullSuppression": False}],
        "qMeasures": [], "qInitialDataFetch": [{"qLeft": 0, "qTop": 0, "qWidth": 1, "qHeight": 2000}]}}
    h = q.rpc("CreateSessionObject", doc, [obj])["qReturn"]["qHandle"]
    pg = q.rpc("GetLayout", h, [])["qLayout"]["qHyperCube"]["qDataPages"][0]["qMatrix"]
    return [r[0]["qText"] for r in pg]


def sin_comentarios(formula):
    """Las medidas dejan la fórmula vieja comentada: no cuenta, el motor la ignora."""
    return re.sub(r"/[*].*?[*]/", "", formula, flags=re.S)


def main():
    guardar = "--guardar" in sys.argv
    pos = [a for a in sys.argv[1:] if not a.startswith("--")]
    esperado = int(pos[0]) if pos else None
    store = json.load(open(os.path.join(DATA, "historico.json"), encoding="utf-8"))
    ultimo_store = max(int(k) for k in store["datos"])
    q, doc = connect_retry(intentos=5, espera=10)
    q.clear_all(doc)

    print("\nA · sello y rango")
    sello = q.reload_time(doc)
    mx = int(num(q.evaluate(doc, "=Max([AñoMes_Num])")))
    mn = int(num(q.evaluate(doc, "=Min([AñoMes_Num])")))
    print("  ReloadTime:", sello, "| períodos %d (%s) .. %d (%s)" % (mn, C.periodo_label(mn), mx, C.periodo_label(mx)))
    antes = store.get("sellos", {}).get(str(ultimo_store), {})
    previos = sorted(set(antes.values()))
    print("  último período del store: %d (%s) · sello(s) con que se extrajo: %s" % (
        ultimo_store, C.periodo_label(ultimo_store), previos or "sin sello"))
    if previos and sello not in previos:
        print("  AVISO la app recargó desde la última extracción: los períodos ya guardados pueden estar "
              "reexpresados. Medir con una re-extracción del año anterior ANTES de interpretar deltas.")
    chk("la app no tiene menos que el store", mx >= ultimo_store,
        ("hay un período nuevo" if mx > ultimo_store else "el último ya está extraído") + " · app=%d · store=%d" % (mx, ultimo_store))
    if esperado:
        chk("el máximo de la app es el esperado", mx == esperado, "app=%d · esperado=%d" % (mx, esperado))

    print("\nB · mercados")
    mapping = json.load(open(os.path.join(DATA, "mapeo_mercados.json"), encoding="utf-8"))
    mercs = lista(q, doc, "DescripcionMercado")
    mal = [(p, m) for p, m in mapping.items() if mercs.count(m) != 1]
    chk("los %d mercados mapeados existen, cada uno 1 vez" % len(mapping), not mal,
        "%d en la app · problemas: %s" % (len(mercs), mal or "ninguno"))

    print("\nC · RegionCUP")
    regs = lista(q, doc, "RegionCUP")
    sinmap = sorted(r for r in regs if r not in C.REGIONCUP_TO_REGION)
    chk("toda RegionCUP de la app está mapeada", not sinmap,
        "%d en la app · %d en config · SIN MAPEAR: %s" % (len(regs), len(C.REGIONCUP_TO_REGION), sinmap or "ninguna"))
    huerf = sorted(set(C.REGIONCUP_TO_REGION) - set(regs))
    print("  claves de config que ya no existen en la app (inofensivo): %s" % (huerf or "ninguna"))

    print("\nD · medidas y dimensiones maestras")
    ids = {"SIE": C.MEAS["sie_act"], "P80": C.MEAS["p80_act"], "TOT": C.MEAS["totmdo_act"]}
    patron = "max(AñoMes_Num)-2)"
    huellas = {}
    HASHES = os.path.join(DATA, "medidas_hash.json")
    previas = json.load(open(HASHES, encoding="utf-8")).get("medidas", {}) if os.path.exists(HASHES) else {}
    for k, mid in ids.items():
        try:
            h = q.rpc("GetMeasure", doc, [mid])["qReturn"]["qHandle"]
            d = q.rpc("GetLayout", h, [])["qLayout"]["qMeasure"]["qDef"]
        except Exception as e:
            chk("medida %s existe" % k, False, str(e)[:80])
            continue
        vivo = sin_comentarios(d)
        n_off = vivo.count("-2)")
        n_ok = vivo.lower().count(patron.lower())
        # Los extractores reemplazan TODAS las '-2)' por el offset de cada ventana. Eso solo es
        # correcto si cada una es el offset de la ventana: si aparece otra, la reemplazaría también.
        huella = hashlib.sha1(d.encode("utf-8")).hexdigest()[:10]
        huellas[k] = huella
        chk("ventana de %s parametrizable" % k, n_off >= 1 and n_off == n_ok,
            "'-2)' vivas: %d · de ellas offset de ventana: %d · sha1 %s" % (n_off, n_ok, huella))
        if previas.get(k) and previas[k] != huella:
            print("  AVISO la definición de %s CAMBIÓ en la app (antes %s, ahora %s): revisar que la ventana "
                  "parametrizada siga igual a la medida TRIM oficial antes de extraer" % (k, previas[k], huella))
    for nombre, did in (("REGIONCUP", C.DIM_REGIONCUP), ("PROVINCIA", "1949a1bb-36fe-4f21-b7fb-f03e3380760e"),
                        ("PARTIDO", "3c30cde4-48f7-4433-91b7-e5caf333f6c7")):
        try:
            h = q.rpc("GetDimension", doc, [did])["qReturn"]["qHandle"]
            fd = q.rpc("GetLayout", h, [])["qLayout"]["qDim"]["qFieldDefs"]
            chk("dimensión maestra %s existe" % nombre, True, str(fd))
        except Exception as e:
            chk("dimensión maestra %s existe" % nombre, False, str(e)[:80])

    print("\nE · borde temporal (¿el mes nuevo viene completo?)")
    base = ("{$<CPA=,MesesRollBack={0},DescripcionTipo={'Mensual'},[AñoSeleccion]=,MesSeleccion=,"
            "Flag_Rollback={0},TipoMercado={'Etico'},[AñoMes_Num]={%d}>}")
    filas = {}
    for p in [mx, mx - 1, mx - 2, mx - 3, mx - 12, mx - 13, mx - 14, mx - 15]:
        q.clear_all(doc)
        u = num(q.evaluate(doc, "=Sum(%s MensualUnidades)" % (base % p)))
        n = num(q.evaluate(doc, "=Count(DISTINCT %s CPA)" % (base % p)))
        filas[p] = (u, n)
    print("  %-10s %16s %12s" % ("período", "unidades Ético", "farmacias"))
    for p, (u, n) in filas.items():
        print("  %-10s %16s %12s" % (C.periodo_label(p), "{:,.0f}".format(u), "{:,.0f}".format(n)))
    ru = filas[mx][0] / filas[mx - 1][0] if filas[mx - 1][0] else 0
    rn = filas[mx][1] / filas[mx - 1][1] if filas[mx - 1][1] else 0
    estac = filas[mx - 12][0] / filas[mx - 13][0] if filas[mx - 13][0] else 0
    chk("unidades mes nuevo / mes anterior (<0,85 = mes incompleto)", 0.85 <= ru <= 1.15,
        "razón %.3f (el año pasado, mismo par de meses: %.3f)" % (ru, estac))
    chk("farmacias mes nuevo / mes anterior", 0.95 <= rn <= 1.05, "razón %.3f" % rn)
    q.close()
    if guardar:
        with open(HASHES, "w", encoding="utf-8") as f:
            json.dump({"reload": sello, "medidas": huellas}, f, ensure_ascii=False, indent=1)
        print()
        print("huellas de las medidas guardadas en datos/medidas_hash.json (reload %s)" % sello)
    elif not previas:
        print()
        print("(no hay huellas previas de las medidas: correr con --guardar para registrarlas)")

    print("\n%d PASS · %d FAIL · %d SKIP" % (res.count("PASS"), res.count("FAIL"), res.count("SKIP")))
    return 0 if res.count("FAIL") == 0 and res.count("SKIP") == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
