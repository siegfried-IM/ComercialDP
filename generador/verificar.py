# -*- coding: utf-8 -*-
"""Verificación de los stores antes de regenerar el tablero.

Nace de un bug real de Jun-2026: el mercado 'Acneclin' salió sumado con
'Acneclin PBA' en historico.json — sin excepción, sin log de error, y con un
DP% de 99,8% perfectamente plausible en vez de 89,6%. Lo cazó cruzar la misma
cifra por dos caminos, no mirar el proceso.

Cada chequeo imprime PASS/FAIL con las dos cifras y el ratio. Exit != 0 si hay
algún FAIL o SKIP, para poder encadenarlo:
    python verificar.py 24318 && python generar_html.py 24318

Uso:  python verificar.py [periodo]     (por defecto, el máximo del store)
"""
import json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "datos")

WINS = ["MEN", "TRI", "SEM", "MAT", "YTD"]
# Región descarta los RegionCUP sin mapear; departamento no. El gap es real y chico.
TOL_REG_DEPTO = 0.01
# Reexpresión de IQVIA entre reloads sobre períodos extraídos en corridas distintas.
TOL_REEXPRESION = 0.02

resultados = []


def chequeo(nombre, ok, detalle):
    estado = "PASS" if ok is True else ("SKIP" if ok is None else "FAIL")
    resultados.append(estado)
    print(f"  {estado}  {nombre:<46} {detalle}")


def cargar(nombre):
    p = os.path.join(DATA, nombre)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def ok_prods(store, pk):
    d = store.get("datos", {}).get(pk, {})
    return {k: v for k, v in d.items() if isinstance(v, dict) and v.get("_ok")}


def g0(P, stores):
    print("\nG0 · Que corra lo que creés que corre")
    print(f"  intérprete: {sys.executable}")
    print(f"  python    : {sys.version.split()[0]}")
    tmps = [f for f in os.listdir(DATA) if f.endswith(".tmp")]
    chequeo("sin .tmp colgados en datos/", not tmps, f"{len(tmps)} encontrados" + (f": {tmps}" if tmps else ""))
    for nombre, st in stores.items():
        if st is None:
            chequeo(f"{nombre} existe", False, "FALTA EL ARCHIVO")
            continue
        pk = str(P)
        prods = ok_prods(st, pk)
        fallidos = [k for k, v in st.get("datos", {}).get(pk, {}).items()
                    if isinstance(v, dict) and v.get("_ok") is False]
        chequeo(f"{nombre} · productos _ok en {P}", len(prods) == 42 and not fallidos,
                f"{len(prods)}/42" + (f" · _ok=False: {fallidos}" if fallidos else ""))


def g1(P, H, W, D):
    """Fidelidad: la misma cifra por dos caminos independientes."""
    print("\nG1 · Cierre entre caminos independientes")
    pk = str(P)

    # 1. ventana TRI (medida parametrizada) vs medida maestra TRIM. Mismo período,
    #    ambos extraídos hoy -> deben coincidir exacto.
    peor, peor_det = 0.0, ""
    n = 0
    for pn, h in ok_prods(H, pk).items():
        w = ok_prods(W, pk).get(pn)
        if not w:
            continue
        for k1, k2 in [("sie_act", "s"), ("p80_act", "p"), ("totmdo_act", "t")]:
            a, b = h["TOTAL"][k1], w["TOTAL"]["TRI"][k2]
            n += 1
            if a and abs(b / a - 1) > peor:
                peor, peor_det = abs(b / a - 1), f"{pn}/{k1}: {a:.0f} vs {b:.0f}"
    chequeo("historico[TRIM] == historico_win[TRI]", peor <= 0.005,
            f"{n} celdas · peor desvío {peor*100:.2f}%" + (f" ({peor_det})" if peor > 0.005 else ""))

    # 2. depto sumado vs región. El depto suma un poco más (regiones sin mapear).
    peor, peor_det, n = 0.0, "", 0
    for pn, w in ok_prods(W, pk).items():
        d = ok_prods(D, pk).get(pn)
        if not d:
            continue
        for win in WINS:
            a = w["TOTAL"].get(win)
            if not a:
                continue
            for k in "spt":
                b = sum(v.get(win, {}).get(k, 0) for gk, v in d.items() if gk != "_ok")
                n += 1
                if a[k] and abs(b / a[k] - 1) > peor:
                    peor, peor_det = abs(b / a[k] - 1), f"{pn}/{win}/{k}: {a[k]:.0f} vs {b:.0f}"
    chequeo("Σ departamentos == Σ regiones (5 ventanas)", peor <= TOL_REG_DEPTO,
            f"{n} celdas · peor desvío {peor*100:.2f}%" + (f" ({peor_det})" if peor > TOL_REG_DEPTO else ""))

    # 3. medida año-anterior contra el actual guardado de ese mismo mes.
    #    Es el chequeo que delató a Acneclin (1,70x).
    peor, peor_det, n = 0.0, "", 0
    ant_pk = str(P - 12)
    for pn, h in ok_prods(H, pk).items():
        g = H["datos"].get(ant_pk, {}).get(pn)
        if not isinstance(g, dict) or not g.get("_ok"):
            continue
        for k1, k2 in [("sie_ant", "sie_act"), ("p80_ant", "p80_act"), ("totmdo_ant", "totmdo_act")]:
            a, b = h["TOTAL"][k1], g["TOTAL"][k2]
            n += 1
            if b and abs(a / b - 1) > peor:
                peor, peor_det = abs(a / b - 1), f"{pn}/{k1}: {a:.0f} vs {b:.0f}"
    if not n:
        chequeo(f"año anterior ({ant_pk}) vs actual guardado", None, "el período no está en el store")
    else:
        chequeo(f"año anterior ({ant_pk}) vs actual guardado", peor <= TOL_REEXPRESION,
                f"{n} celdas · peor desvío {peor*100:.2f}%" + (f" ({peor_det})" if peor > TOL_REEXPRESION else ""))


def g2(P, H, W, U, UD):
    """Coherencia interna de cada artefacto."""
    print("\nG2 · Consistencia interna")
    pk = str(P)

    # TOTAL == Σ regiones dentro del propio store
    peor, peor_det, n = 0.0, "", 0
    for pn, h in ok_prods(H, pk).items():
        for k in ["sie_act", "p80_act", "totmdo_act"]:
            s = sum(v[k] for r, v in h.items() if r not in ("TOTAL", "_ok", "_mercado"))
            t = h["TOTAL"][k]
            n += 1
            if t and abs(s / t - 1) > peor:
                peor, peor_det = abs(s / t - 1), f"{pn}/{k}: Σ{s:.0f} vs TOTAL {t:.0f}"
    chequeo("historico · TOTAL == Σ regiones", peor <= 0.0001,
            f"{n} celdas · peor desvío {peor*100:.4f}%" + (f" ({peor_det})" if peor > 0.0001 else ""))

    # unidades: región vs departamento (ambas aditivas por farmacia)
    peor, peor_det, n = 0.0, "", 0
    for pn, u in ok_prods(U, pk).items():
        d = ok_prods(UD, pk).get(pn)
        if not d:
            continue
        for win in WINS:
            a = u["TOTAL"].get(win, {}).get("tot", 0)
            b = sum(v.get(win, {}).get("tot", 0) for gk, v in d.items() if gk != "_ok")
            n += 1
            if a and abs(b / a - 1) > peor:
                peor, peor_det = abs(b / a - 1), f"{pn}/{win}: {a:.0f} vs {b:.0f}"
    chequeo("unidades · región == departamento", peor <= TOL_REG_DEPTO,
            f"{n} celdas · peor desvío {peor*100:.2f}%" + (f" ({peor_det})" if peor > TOL_REG_DEPTO else ""))

    # identidades de unidades: siegfried + potencial no capturado <= mercado
    malos = []
    for pn, u in ok_prods(U, pk).items():
        for win in WINS:
            c = u["TOTAL"].get(win)
            if c and (c["gap"] > c["tot"] + 1 or c["sie"] + c["gap"] > c["tot"] + 1):
                malos.append(f"{pn}/{win}")
    chequeo("unidades · sie + gap <= mercado", not malos,
            f"{len(malos)} violaciones" + (f": {malos[:5]}" if malos else ""))

    # DP% <= DF%: el núcleo 80-20 es subconjunto del mercado, así que sie/p80 >= sie/tot
    malos = []
    for pn, h in ok_prods(H, pk).items():
        t = h["TOTAL"]
        if t["p80_act"] > t["totmdo_act"] + 1:
            malos.append(f"{pn}: 80-20 {t['p80_act']:.0f} > mercado {t['totmdo_act']:.0f}")
    chequeo("historico · núcleo 80-20 <= mercado total", not malos,
            f"{len(malos)} violaciones" + (f": {malos[:3]}" if malos else ""))


def g3(P, H):
    """Diff contra la versión anterior: lo que no debe moverse, no se movió."""
    print("\nG3 · Diff contra la versión commiteada")
    try:
        crudo = subprocess.run(["git", "--no-pager", "show", "HEAD:datos/historico.json"],
                               cwd=ROOT, capture_output=True, timeout=120)
        base = json.loads(crudo.stdout.decode("utf-8"))
    except Exception as e:
        chequeo("línea base desde git", None, f"no se pudo leer: {e}")
        return
    viejos = sorted(set(base["datos"]) & set(H["datos"]), key=int)
    movidos = [pk for pk in viejos if pk != str(P) and base["datos"][pk] != H["datos"][pk]]
    chequeo("períodos previos idénticos al commit", not movidos,
            f"{len(viejos)} períodos comparados" + (f" · se movieron: {movidos}" if movidos else ""))
    nuevos = sorted(set(H["datos"]) - set(base["datos"]), key=int)
    chequeo("períodos nuevos", nuevos == [str(P)], f"agregados: {nuevos or 'ninguno'}")
    # forma: cantidad de productos y de regiones
    prods = len(ok_prods(H, str(P)))
    regs = len({r for v in ok_prods(H, str(P)).values()
                for r in v if r not in ("TOTAL", "_ok", "_mercado")})
    base_regs = len({r for pk in viejos[-1:] for v in ok_prods(base, pk).values()
                     for r in v if r not in ("TOTAL", "_ok", "_mercado")})
    chequeo("forma · productos y regiones", prods == 42 and regs == base_regs,
            f"{prods} productos, {regs} regiones (base: {base_regs})")


def main():
    H = cargar("historico.json")
    W = cargar("historico_win.json")
    U = cargar("unidades_region.json")
    UD = cargar("unidades_depto.json")
    D = cargar("depto_win.json")
    P = int(sys.argv[1]) if len(sys.argv) > 1 else max(int(k) for k in H["datos"])

    a, m = divmod(P, 12)
    if m == 0:
        a -= 1; m = 12
    mes = ["", "Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"][m]
    print(f"Verificación del período {P} ({mes}-{a})")

    stores = {"historico": H, "historico_win": W, "unidades_region": U,
              "unidades_depto": UD, "depto_win": D}
    g0(P, stores)
    g1(P, H, W, D)
    g2(P, H, W, U, UD)
    g3(P, H)

    print()
    n_fail = resultados.count("FAIL")
    n_skip = resultados.count("SKIP")
    print(f"{resultados.count('PASS')} PASS · {n_fail} FAIL · {n_skip} SKIP")
    if n_fail or n_skip:
        print("NO PUBLICAR: hay chequeos en rojo o sin correr.")
    return 1 if (n_fail or n_skip) else 0


if __name__ == "__main__":
    sys.exit(main())
