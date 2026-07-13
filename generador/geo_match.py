# -*- coding: utf-8 -*-
"""Normalización y alias para unir (provincia, partido) de Qlik con el geojson de departamentos."""
import unicodedata, re

def _n(s):
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode()
    s = re.sub(r"[.\-']", ' ', s)                 # puntos, guiones y apóstrofes -> espacio
    s = ' '.join(s.upper().split())
    reps = [(r'\bGRAL\b', 'GENERAL'), (r'\bGRL\b', 'GENERAL'), (r'\bGDOR\b', 'GOBERNADOR'),
            (r'\bCNEL\b', 'CORONEL'), (r'\bTTE\b', 'TENIENTE'), (r'\bPTE\b', 'PRESIDENTE'),
            (r'\bSTO\b', 'SANTO'), (r'\bSTA\b', 'SANTA'), (r'\bDR\b', 'DOCTOR'),
            (r'\bBRIGADIER\b', '')]
    for a, b in reps:
        s = re.sub(a, b, s)
    return ' '.join(s.split())

# alias explícitos 1:1 (clave normalizada de Qlik -> clave normalizada del geojson)
_ALIAS = {
    "BUENOS AIRES|DE LA COSTA": "BUENOS AIRES|LA COSTA",
    "BUENOS AIRES|GENERAL MADARIAGA": "BUENOS AIRES|GENERAL JUAN MADARIAGA",
    "BUENOS AIRES|MIRAMAR": "BUENOS AIRES|GENERAL ALVARADO",
    "BUENOS AIRES|CORONEL ROSALES": "BUENOS AIRES|CORONEL DE MARINA LEONARDO ROSALES",
    "BUENOS AIRES|JOSE CLEMENTE PAZ": "BUENOS AIRES|JOSE C PAZ",
    "BUENOS AIRES|ADOLFO GONZALEZ CHAVES": "BUENOS AIRES|ADOLFO GONZALES CHAVES",
    "BUENOS AIRES|GENERAL LAMADRID": "BUENOS AIRES|GENERAL LA MADRID",
    "SALTA|GENERAL MARTIN M GUEMES": "SALTA|GENERAL GUEMES",
    "TUCUMAN|JUAN B ALBERDI": "TUCUMAN|JUAN BAUTISTA ALBERDI",
    "MISIONES|EL DORADO": "MISIONES|ELDORADO",
    "SAN LUIS|LA CAPITAL": "SAN LUIS|JUAN MARTIN DE PUEYRREDON",
    "LA PAMPA|CATRILLO": "LA PAMPA|CATRILO",
    "LA PAMPA|CAPALEUFU": "LA PAMPA|CHAPALEUFU",
    "SANTIAGO DEL ESTERO|GENERAL SAN MARTIN": "SANTIAGO DEL ESTERO|SAN MARTIN",
    "TIERRA DEL FUEGO|RIO USHUAIA": "TIERRA DEL FUEGO|USHUAIA",
}

def key(prov, partido):
    """Clave normalizada 'PROV|PARTIDO' para unir con el geojson (aplica alias)."""
    k = _n(prov) + "|" + _n(partido)
    return _ALIAS.get(k, k)
