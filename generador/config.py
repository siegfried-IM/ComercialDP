# -*- coding: utf-8 -*-
"""Configuración del generador del tablero DP% (Distribución Ponderada) Siegfried.

Fuente: app QlikCloud "Siegfried DDD", hoja "Distribución Farmacias Diego".
DP% = Cant.PDV Siegfried / Cant.PDV 80-20 (Pareto), trimestral, por RegionCUP,
agregado a 29 regiones y ratio de sumas de conteos.
"""

# --- IDs de medidas maestras (conteos de farmacias / PDV) ---
MEAS = {
    "sie_act":  "79f5a08e-33dc-4638-a92e-d29ef3234728",  # Cant. PDV TRIM Act. Siegfried
    "p80_act":  "69e8649d-3189-457b-98b1-c5d0dbd78da5",  # Cant. PDV TRIM Act. 80-20
    "sie_ant":  "e030406e-ebe2-4b1c-940d-65ef3526a7ae",  # Cant. PDV TRIM Año Ant. Siegfried
    "p80_ant":  "849c1caf-6f2a-4aae-9c23-0830715bb381",  # Cant. PDV TRIM Año Ant. 80-20
    "totmdo_act": "sCCWeD",                               # Cant. PDV TRIM Act. Total Mercado (DF%)
    "totmdo_ant": "8854804a-f2cd-431e-ae40-466f9d284777", # Cant. PDV TRIM Año Ant. Total Mercado
}
DIM_REGIONCUP = "0f5cb004-9db6-464d-b564-4549fa922a00"
DIM_MERCADO   = "1f2593cd-e4ce-4f41-8b0b-88efac6173fa"

# Selecciones fijas del contexto del reporte
TIPO_MERCADO = "Etico"

# --- Período: AñoMes_Num = Año*12 + Mes ---
def periodo_num(anio, mes):
    return anio * 12 + mes

def periodo_label(num):
    anio, mes = divmod(num, 12)
    if mes == 0:
        anio -= 1; mes = 12
    meses = ["", "Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    return f"{meses[mes]}-{anio}"

# --- Mapeo RegionCUP (44 crudos) -> 29 regiones del tablero (validado 28/29 con Acemuk) ---
REGIONCUP_TO_REGION = {
    "_CAPITAL FEDERAL": "CABA",
    "_SUBURBANO NORTE": "BUENOS AIRES", "_SUBURBANO OESTE": "BUENOS AIRES", "_SUBURBANO SUR": "BUENOS AIRES",
    "SUBURBANO OESTE": "BUENOS AIRES", "PILAR - ESCOBAR": "BUENOS AIRES", "LUJAN Y ALREDEDORES": "BUENOS AIRES",
    "ZARATE - CAMPANA": "BUENOS AIRES", "JUNIN-CHIVILCOY-PERGAMINO": "BUENOS AIRES",
    "BARADERO-SAN PEDRO-RAMALLO-SAN NICOLAS": "BUENOS AIRES",
    "LA PLATA": "LA PLATA", "M.DEL PLATA": "MDQ", "AZUL-OLAVARRIA-TANDIL": "TANDIL-OLAVARRIA",
    "BAHIA BLANCA": "BAHIA BLANCA",
    "SANTA FE": "SANTA FE", "RAFAELA-NTE SANTA FE": "SANTA FE", "ROSARIO": "ROSARIO",
    "CORDOBA": "CORDOBA", "RIO IV Y ALREDEDORES": "CORDOBA", "SAN FCO-ESTE Y NORTE": "CORDOBA",
    "SANTA ROSA": "LA PAMPA",
    "MENDOZA": "MENDOZA", "SAN RAFAEL": "MENDOZA", "SAN JUAN": "SAN JUAN", "SAN LUIS": "SAN LUIS",
    "TUCUMAN": "TUCUMAN", "SALTA": "SALTA", "JUJUY": "JUJUY", "CATAMARCA": "CATAMARCA",
    "LA RIOJA": "LA RIOJA", "SANTIAGO DEL ESTERO": "SANTIAGO DEL ESTERO",
    "CORRIENTES": "CORRIENTES", "RESISTENCIA": "CHACO", "MISIONES": "MISIONES", "POSADAS": "MISIONES",
    "FORMOSA": "FORMOSA", "PARANA": "ENTRE RIOS", "CONCORDIA": "ENTRE RIOS",
    "NEUQUEN": "NEUQUEN", "RIO NEGRO": "RIO NEGRO", "TRELEW": "CHUBUT", "COMODORO RIVADAVIA": "CHUBUT",
    "SANTA CRUZ": "SANTA CRUZ", "TIERRA DEL FUEGO": "TIERRA DEL FUEGO",
}

# Zonas -> regiones (orden del tablero)
ZONES = {
    "CABA": ["CABA"],
    "BUENOS AIRES": ["BUENOS AIRES", "LA PLATA", "MDQ", "TANDIL-OLAVARRIA", "BAHIA BLANCA"],
    "CENTRO": ["SANTA FE", "ROSARIO", "CORDOBA", "LA PAMPA"],
    "CUYO": ["MENDOZA", "SAN JUAN", "SAN LUIS"],
    "NOA": ["TUCUMAN", "SALTA", "JUJUY", "CATAMARCA", "LA RIOJA", "SANTIAGO DEL ESTERO"],
    "NEA": ["CORRIENTES", "CHACO", "MISIONES", "FORMOSA", "ENTRE RIOS"],
    "PATAGONIA": ["NEUQUEN", "RIO NEGRO", "CHUBUT", "SANTA CRUZ", "TIERRA DEL FUEGO"],
}
ZONES_ORDER = ["CABA", "BUENOS AIRES", "CENTRO", "CUYO", "NOA", "NEA", "PATAGONIA"]

# --- Mapeo región (29) -> provincia (nombres del geojson jazzido, 24) ---
PROVINCES = ["Capital Federal", "Buenos Aires", "Santa Fe", "Cordoba", "La Pampa",
             "Mendoza", "San Juan", "San Luis", "Tucuman", "Salta", "Jujuy", "Catamarca",
             "La Rioja", "Santiago del Estero", "Corrientes", "Chaco", "Misiones", "Formosa",
             "Entre Rios", "Neuquen", "Rio Negro", "Chubut", "Santa Cruz", "Tierra del Fuego"]
REGION_TO_PROVINCE = {
    "CABA": "Capital Federal",
    "BUENOS AIRES": "Buenos Aires", "LA PLATA": "Buenos Aires", "MDQ": "Buenos Aires",
    "TANDIL-OLAVARRIA": "Buenos Aires", "BAHIA BLANCA": "Buenos Aires",
    "SANTA FE": "Santa Fe", "ROSARIO": "Santa Fe",
    "CORDOBA": "Cordoba", "LA PAMPA": "La Pampa",
    "MENDOZA": "Mendoza", "SAN JUAN": "San Juan", "SAN LUIS": "San Luis",
    "TUCUMAN": "Tucuman", "SALTA": "Salta", "JUJUY": "Jujuy", "CATAMARCA": "Catamarca",
    "LA RIOJA": "La Rioja", "SANTIAGO DEL ESTERO": "Santiago del Estero",
    "CORRIENTES": "Corrientes", "CHACO": "Chaco", "MISIONES": "Misiones", "FORMOSA": "Formosa",
    "ENTRE RIOS": "Entre Rios", "NEUQUEN": "Neuquen", "RIO NEGRO": "Rio Negro",
    "CHUBUT": "Chubut", "SANTA CRUZ": "Santa Cruz", "TIERRA DEL FUEGO": "Tierra del Fuego",
}

# --- Mapeo producto (nombre tablero) -> DescripcionMercado exacto ---
# 32 son match exacto; los 9 ambiguos se resuelven por valor (ver resolver_mercados.py)
PRODUCTO_A_MERCADO = {
    # se completa/serializa en datos/mapeo_mercados.json
}
