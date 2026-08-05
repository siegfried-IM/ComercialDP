# Generador del tablero DP% (Distribución Ponderada) — Siegfried

Regenera `index.html` a partir de datos extraídos de la app QlikCloud **"Siegfried DDD"**
(hoja "Distribución Farmacias Diego"), acumulando el histórico mes a mes.

## Qué es el DP%
**Distribución Ponderada** = `farmacias con Siegfried / farmacias del núcleo Pareto 80-20` del mercado,
por trimestre (actual vs mismo trimestre del año anterior), por región.
Los "productos" del tablero son **mercados IQVIA** (`DescripcionMercado`); las regiones son `RegionCUP`
agrupadas a 29 regiones / 7 zonas (mapeo en `config.py`).

## Requisitos
- Python 3 con `websocket-client` y `requests` (`pip install websocket-client requests`).
- Token de API de QlikCloud en `generador/qlik_token.txt` **o** en la variable de entorno `QLIK_TOKEN`.
  (El archivo está gitignoreado; nunca se commitea. Se genera en Qlik Cloud → Settings → API keys.)

## Actualización mensual (cuando hay un mes nuevo en Qlik)
Con `P` = período nuevo y `M` = su mes (Jun-2026 → `P=24318`, `M=6`):

```bash
cd generador
python extraer.py P                              # TRIM por región      -> historico.json
python extraer_ventanas.py P P-1 P-3 P-6 P-12 P-M  # 5 ventanas x región -> historico_win.json
python extraer_unidades.py P                     # unidades por región  -> unidades_region.json
python extraer_unidades_depto.py P               # unidades por depto   -> unidades_depto.json
python extraer_depto.py MEN,TRI,SEM,MAT,YTD P    # 5 ventanas x depto   -> depto_win.json
python verificar.py P                            # 16 chequeos; exit!=0 si algo falla
python generar_html.py P                         # regenera ../index.html
```
Jun-2026 fue: `python extraer_ventanas.py 24318 24315 24312 24306` (24317 ya estaba de mayo).
Los períodos extra del paso 2 son los que el tablero compara: `P-1` mensual, `P-3` trimestre,
`P-6` semestre, `P-12` año anterior y MAT, `P-M` inicio del YTD. Los que ya estén en el store se saltean.
Tarda 2-3 h en total; `python monitor_progreso.py` en paralelo escribe `../progreso.html` con el avance.

- **Todo es serial** (las sesiones de Qlik comparten estado de selección; no paralelizar) y **resumible**:
  checkpoint por mercado, así que si se corta se relanza el mismo comando y retoma. Cada mercado
  tarda 15-60 s según el extractor.
- **No publiques sin correr `verificar.py`.** En Jun-2026 una consulta volvió sin error con la
  selección contaminada (mercado `Acneclin` sumado con `Acneclin PBA`): DP% 99,8% en vez de 89,6%,
  un número plausible que sólo se cae cruzándolo por otro camino. Hoy `qlik_client.check_selection`
  corta esa consulta y la reintenta, pero la verificación es la red que queda abajo.
- Período = `Año*12 + Mes` (Jun-2026 = 24318, Ene-2026 = 24313). Sin argumento, cada extractor usa
  el máximo disponible en la app; `generar_html.py` usa el máximo del store.

## Archivos
- `qlik_client.py` — cliente Engine API (websocket JSON-RPC), `connect_retry` (reconexión con
  backoff ante cortes de red/DNS) y `check_selection` (aborta si la selección se contaminó).
- `config.py` — IDs de medidas, mapeo RegionCUP→región, zonas.
- `extraer.py` — extracción Qlik → `../datos/historico.json`.
- `extraer_ventanas.py`, `extraer_unidades.py`, `extraer_unidades_depto.py`, `extraer_depto.py` —
  los otros cuatro stores (ver secuencia mensual arriba). Están gitignoreados por tamaño.
- `verificar.py` — 16 chequeos sobre los stores antes de generar. Correr siempre.
- `monitor_progreso.py` — escribe `../progreso.html` con el avance en vivo. Actualizar el período
  y las listas objetivo del encabezado cada mes.
- `generar_html.py` — store → `../index.html`.
- `plantilla_base.html` — template (diseño + vista de evolución). **Editar acá el diseño**, no el `index.html`.
- `../datos/mapeo_mercados.json` — 41 productos → mercado IQVIA exacto.
- `../datos/historico.json` — store histórico acumulado (conteos por período/mercado/región). **Commitear** para preservar historia.

## Notas
- El store guarda **conteos** (SIE / 80-20 / Total Mercado), no porcentajes, para poder agregar
  regiones/compañía como *ratio de sumas* (no promedio de %).
- Diferencias <1pp respecto de reportes viejos son normales: IQVIA reexpresa datos entre reloads.
