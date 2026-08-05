# -*- coding: utf-8 -*-
"""Cliente minimal de la Engine API (QIX) de QlikCloud sobre websocket.

El token se lee de (en orden):
  1. variable de entorno QLIK_TOKEN
  2. archivo generador/qlik_token.txt  (gitignoreado)

Uso:
    from qlik_client import Qix
    q = Qix(); doc = q.open_doc()
    q.clear_all(doc)
    q.select_text(doc, "TipoMercado", "Etico")
    q.select_num(doc, "AñoMes_Num", range(24294, 24314))
    rows = q.hypercube(doc, dims=[...], measures=[...])
    q.close()
"""
import json, ssl, itertools, os, time
import websocket

TENANT = "tableros.us.qlikcloud.com"
APP_ID = "a3a4907d-9340-46d0-93c4-f2ce7f004ff0"
HERE = os.path.dirname(os.path.abspath(__file__))


def _token():
    tok = os.environ.get("QLIK_TOKEN")
    if tok:
        return tok.strip()
    path = os.path.join(HERE, "qlik_token.txt")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    raise RuntimeError("No hay token: defini QLIK_TOKEN o crea generador/qlik_token.txt")


def connect_retry(intentos=40, espera=15, pausa_inicial=0.0,
                  app_id=APP_ID, tenant=TENANT, timeout=120):
    """Abre una conexión nueva reintentando ante blips de red/DNS (getaddrinfo).

    Devuelve (q, doc). La usan los extractores en dos lugares: al abrir la conexión
    del arranque y en el bloque `except` de cada consulta (ahí conviene pausa_inicial=3,
    para darle aire al engine antes de reconectar). Una corrida dura horas y un corte
    de red de un minuto no debe abortarla.

    Reintentar acá es seguro porque el llamador rehace el bloque completo
    (clear_all + selects + query), que es lo que exige la nota de rpc(): nunca
    reintentar una sola llamada suelta sobre una conexión que perdió el estado.
    """
    ultimo = None
    for i in range(intentos):
        try:
            if i == 0:
                if pausa_inicial:
                    time.sleep(pausa_inicial)
            else:
                time.sleep(espera)
            q = Qix(app_id=app_id, tenant=tenant, timeout=timeout)
            return q, q.open_doc()
        except Exception as e:
            ultimo = e
            print(f"    conexión falló ({e}); reintento en {espera}s ({i+1}/{intentos})")
    raise RuntimeError(f"no se pudo conectar tras {intentos} intentos: {ultimo}")


class Qix:
    def __init__(self, app_id=APP_ID, tenant=TENANT, timeout=120):
        self.app_id = app_id
        self.tenant = tenant
        self.timeout = timeout
        self._connect()

    def _connect(self):
        url = f"wss://{self.tenant}/app/{self.app_id}"
        self.ws = websocket.create_connection(
            url,
            header=[f"Authorization: Bearer {_token()}"],
            sslopt={"cert_reqs": ssl.CERT_NONE},
            timeout=self.timeout,
        )
        self._ids = itertools.count(1)
        # drenar el OnConnected inicial
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("method") == "OnConnected":
                break
            if "id" in msg:
                break

    def rpc(self, method, handle, params):
        # SIN auto-reconnect: si la conexión se cae, se pierde el estado de
        # selección (las sesiones lo comparten/reinician), así que reintentar
        # una sola llamada daría datos incorrectos en silencio. Preferimos
        # fallar limpio y que el llamador reintente el bloque completo
        # (clear_all + selects + query) sobre una conexión nueva.
        rid = next(self._ids)
        self.ws.send(json.dumps({"jsonrpc": "2.0", "id": rid, "method": method,
                                 "handle": handle, "params": params}))
        while True:
            resp = json.loads(self.ws.recv())
            if resp.get("id") == rid:
                break
        if "error" in resp:
            raise RuntimeError(f"{method} error: {resp['error']}")
        return resp["result"]

    def reconnect(self):
        try:
            self.ws.close()
        except Exception:
            pass
        self._connect()
        return self.open_doc()

    # --- helpers ---
    def open_doc(self):
        r = self.rpc("OpenDoc", -1, [self.app_id])
        self.doc = r["qReturn"]["qHandle"]
        return self.doc

    def clear_all(self, doc):
        self.rpc("ClearAll", doc, [True])

    def select_text(self, doc, field, values):
        if isinstance(values, str):
            values = [values]
        h = self.rpc("GetField", doc, [field])["qReturn"]["qHandle"]
        return self.rpc("SelectValues", h, [[{"qText": v} for v in values], False, False])

    def select_num(self, doc, field, numbers):
        h = self.rpc("GetField", doc, [field])["qReturn"]["qHandle"]
        vals = [{"qNumber": float(n), "qIsNumeric": True} for n in numbers]
        return self.rpc("SelectValues", h, [vals, False, False])

    def evaluate(self, doc, expr):
        return self.rpc("Evaluate", doc, [expr])["qReturn"]

    def check_selection(self, doc, field, esperado=1):
        """Corta si `field` no quedó con exactamente `esperado` valores seleccionados.

        Una consulta puede volver SIN error y con la selección contaminada: en la
        corrida de Jun-2026 el mercado 'Acneclin' salió sumado con 'Acneclin PBA'
        (DP% 99,8% en vez de 89,6%), sin excepción y con un número plausible. Los
        conteos quedaron ~1,7x y nadie se entera hasta que alguien mira la serie.

        Se llama después de los selects; al levantar excepción, el llamador rehace
        el bloque completo sobre una conexión nueva, que es su camino de reintento.
        """
        crudo = self.evaluate(doc, f"=GetSelectedCount([{field}])")
        try:
            n = int(round(float(str(crudo).replace(".", "").replace(",", "."))))
        except ValueError:
            raise RuntimeError(f"selección de {field}: conteo ilegible {crudo!r}")
        if n != esperado:
            raise RuntimeError(f"selección de {field} contaminada: {n} valores "
                               f"seleccionados, se esperaba {esperado}")

    def hypercube(self, doc, dims, measures, page=2000):
        """dims/measures: listas de qLibraryId (strings). Devuelve lista de filas;
        cada fila = lista de celdas con .qText/.qNum ya extraídos como dict."""
        qdims = [{"qLibraryId": d, "qNullSuppression": True} for d in dims]
        qmeas = [{"qLibraryId": m} for m in measures]
        width = len(dims) + len(measures)
        obj = {"qInfo": {"qType": "hc"}, "qHyperCubeDef": {
            "qDimensions": qdims, "qMeasures": qmeas,
            "qInitialDataFetch": [{"qLeft": 0, "qTop": 0, "qWidth": width, "qHeight": min(page, 10000 // width)}]}}
        h = self.rpc("CreateSessionObject", doc, [obj])["qReturn"]["qHandle"]
        lay = self.rpc("GetLayout", h, [])["qLayout"]["qHyperCube"]
        total = lay["qSize"]["qcy"]
        rows = list(lay["qDataPages"][0]["qMatrix"])
        top = len(rows)
        step = max(1, 10000 // width)
        while top < total:
            pg = self.rpc("GetHyperCubeData", h, ["/qHyperCubeDef",
                    [{"qLeft": 0, "qTop": top, "qWidth": width, "qHeight": min(step, total - top)}]])
            mat = pg["qDataPages"][0]["qMatrix"]
            if not mat:
                break
            rows += mat
            top += len(mat)
        return rows

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass
