# -*- coding: utf-8 -*-
"""Escribe ../progreso.html (auto-refresh) con el avance en vivo de las extracciones.
Corre en background; leer-solo, no toca Qlik."""
import json, os, time, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "datos")
OUT = os.path.join(ROOT, "progreso.html")

MESES = ["", "Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
def plabel(p):
    a, m = divmod(int(p), 12)
    if m == 0: a -= 1; m = 12
    return f"{MESES[m]}-{a}"

REGION_TARGET = ["24317", "24316", "24314", "24311", "24305"]   # 5 períodos × 41
DEPTO_WIN_TARGET = ["24317", "24305"]                            # 2 períodos × 41
NPROD = 41


def count_ok(store, pk):
    pd = store.get("datos", {}).get(pk, {})
    return sum(1 for v in pd.values() if isinstance(v, dict) and v.get("_ok"))


def load(name):
    p = os.path.join(DATA, name)
    try:
        return json.load(open(p, encoding="utf-8")), os.path.getmtime(p)
    except Exception:
        return None, 0


def phase_html(titulo, subtitulo, done, total, mtime):
    pct = (done * 100 // total) if total else 0
    age = time.time() - mtime if mtime else 9e9
    estado = "activo" if age < 200 else ("completo" if done >= total and total else "en espera")
    cls = {"activo": "act", "completo": "done", "en espera": "wait"}[estado]
    return f"""<div class="phase {cls}">
      <div class="ph-head"><span class="ph-t">{titulo}</span><span class="ph-badge">{estado}</span></div>
      <div class="ph-sub">{subtitulo}</div>
      <div class="bar"><span style="width:{pct}%"></span></div>
      <div class="ph-n">{done} / {total} &nbsp;({pct}%)</div>
    </div>"""


def build():
    win, wmt = load("historico_win.json")
    dep, dmt = load("depto_win.json")
    # Fase 1: región ventanas
    r_done = sum(count_ok(win, pk) for pk in REGION_TARGET) if win else 0
    r_total = len(REGION_TARGET) * NPROD
    r_detail = " · ".join(f"{plabel(pk)} {count_ok(win, pk) if win else 0}/41" for pk in REGION_TARGET)
    # Fase 2: depto ventanas (mapa)
    d2_done = sum(count_ok(dep, pk) for pk in DEPTO_WIN_TARGET) if dep else 0
    d2_total = len(DEPTO_WIN_TARGET) * NPROD
    # Fase 3: depto histórico (períodos != los 2 del mapa)
    d3_done = 0; d3_total = 20 * NPROD
    if dep:
        for pk in dep.get("datos", {}):
            if pk not in DEPTO_WIN_TARGET:
                d3_done += count_ok(dep, pk)
    ph = (phase_html("1 · Región × 5 ventanas", r_detail, r_done, r_total, wmt) +
          phase_html("2 · Departamento × ventanas (mapa)", "Actual + año anterior", d2_done, d2_total, dmt) +
          phase_html("3 · Departamento × histórico (evolución)", "Trimestre, 24 meses", d3_done, d3_total, dmt))
    overall_done = r_done + d2_done + d3_done
    overall_total = r_total + d2_total + d3_total
    opct = overall_done * 100 // overall_total
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="8">
<title>Extracción en vivo — {opct}%</title>
<style>
 body{{font-family:'Segoe UI',sans-serif;background:#f9f4f4;color:#3a2022;margin:0;padding:28px;}}
 h1{{color:#95232C;font-size:1.4rem;margin:0 0 4px;}}
 .ts{{color:#8a6d6f;font-size:.85rem;margin-bottom:18px;}}
 .overall{{background:linear-gradient(135deg,#95232C,#7A1E24);color:#fff;border-radius:12px;padding:18px 22px;margin-bottom:20px;}}
 .overall .big{{font-size:2.4rem;font-weight:700;}}
 .obar{{background:rgba(255,255,255,.25);border-radius:8px;height:12px;margin-top:10px;overflow:hidden;}}
 .obar span{{display:block;height:100%;background:#fff;border-radius:8px;}}
 .phase{{background:#fff;border:1px solid #efe0e1;border-left:5px solid #ccc;border-radius:10px;padding:14px 18px;margin-bottom:12px;}}
 .phase.act{{border-left-color:#e8a33d;}} .phase.done{{border-left-color:#198754;}} .phase.wait{{border-left-color:#d9c2c4;opacity:.75;}}
 .ph-head{{display:flex;justify-content:space-between;align-items:center;}}
 .ph-t{{font-weight:700;font-size:1rem;}}
 .ph-badge{{font-size:.7rem;text-transform:uppercase;letter-spacing:.5px;background:#f2e6e7;color:#95232C;padding:2px 8px;border-radius:10px;}}
 .phase.act .ph-badge{{background:#fbe6cf;color:#a5701a;}} .phase.done .ph-badge{{background:#d6efdf;color:#198754;}}
 .ph-sub{{color:#8a6d6f;font-size:.8rem;margin:2px 0 8px;}}
 .bar{{background:#f0e4e5;border-radius:6px;height:14px;overflow:hidden;}}
 .bar span{{display:block;height:100%;background:linear-gradient(90deg,#A52A2A,#95232C);border-radius:6px;transition:width .5s;}}
 .ph-n{{text-align:right;font-weight:700;font-size:.85rem;margin-top:5px;}}
 .note{{color:#8a6d6f;font-size:.78rem;margin-top:16px;}}
</style></head><body>
<h1>&#128225; Extracci&oacute;n QlikCloud en vivo</h1>
<div class="ts">Actualiza cada 8 s &middot; {ts}</div>
<div class="overall"><div>Avance total</div><div class="big">{opct}%</div>
  <div>{overall_done} / {overall_total} consultas</div>
  <div class="obar"><span style="width:{opct}%"></span></div></div>
{ph}
<div class="note">Corren en secuencia (Qlik es serial). Cuando cada fase termina, el tablero se regenera y deploya. Pod&eacute;s cerrar esta pesta&ntilde;a cuando quieras.</div>
</body></html>"""


def main():
    for _ in range(30000):
        try:
            html = build()
            tmp = OUT + ".tmp"
            open(tmp, "w", encoding="utf-8").write(html)
            os.replace(tmp, OUT)
        except Exception:
            pass
        time.sleep(8)


if __name__ == "__main__":
    main()
