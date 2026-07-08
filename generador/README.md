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
```bash
cd generador
python extraer.py            # extrae el/los período(s) nuevo(s) al store (saltea lo ya extraído)
python generar_html.py       # regenera ../index.html con el último período + evolución
```
- `extraer.py` es **serial** (las sesiones de Qlik comparten estado; no paralelizar) y **resumible**
  (checkpoint tras cada mercado en `../datos/historico.json`). Cada mercado tarda ~15 s.
- `python extraer.py 24317` extrae un período puntual; `python extraer.py 24313 24317` un rango.
  Período = `Año*12 + Mes` (May-2026 = 24317, Ene-2026 = 24313).
- `python generar_html.py 24317` genera para un período específico (por defecto usa el máximo del store).

## Archivos
- `qlik_client.py` — cliente Engine API (websocket JSON-RPC).
- `config.py` — IDs de medidas, mapeo RegionCUP→región, zonas.
- `extraer.py` — extracción Qlik → `../datos/historico.json`.
- `generar_html.py` — store → `../index.html`.
- `plantilla_base.html` — template (diseño + vista de evolución). **Editar acá el diseño**, no el `index.html`.
- `../datos/mapeo_mercados.json` — 41 productos → mercado IQVIA exacto.
- `../datos/historico.json` — store histórico acumulado (conteos por período/mercado/región). **Commitear** para preservar historia.

## Notas
- El store guarda **conteos** (SIE / 80-20 / Total Mercado), no porcentajes, para poder agregar
  regiones/compañía como *ratio de sumas* (no promedio de %).
- Diferencias <1pp respecto de reportes viejos son normales: IQVIA reexpresa datos entre reloads.
