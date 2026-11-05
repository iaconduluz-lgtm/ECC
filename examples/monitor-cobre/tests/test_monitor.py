import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

import yaml

from monitor import __main__ as app
from monitor import alertas, cobre, costos, estado, noticias, trm

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TRM_ROWS = [{"valor": str(4000 + i * 10), "unidad": "COP", "vigenciadesde": f"2026-11-{10 - i:02d}T00:00:00.000"} for i in range(8)]
YAHOO = {"chart": {"result": [{
    "meta": {"regularMarketPrice": 4.50},
    "timestamp": [1762300800 + i * 86400 for i in range(7)],
    "indicators": {"quote": [{"close": [5.0, 4.95, None, 4.9, 4.8, 4.7, 4.5]}]},
}]}}
RSS = """<rss><channel>
<item><title>Comunidades bloquean corredor minero de Las Bambas: cobre en riesgo</title>
<link>https://ej.pe/1</link><pubDate>Wed, 04 Nov 2026 10:00:00 GMT</pubDate><source>Diario</source></item>
<item><title>Precio del cobre se mantiene estable</title><link>https://ej.pe/3</link>
<pubDate>Wed, 04 Nov 2026 09:00:00 GMT</pubDate></item>
<item><title>Receta de ceviche peruano</title><link>https://ej.pe/2</link>
<pubDate>Wed, 04 Nov 2026 10:00:00 GMT</pubDate></item>
</channel></rss>"""


def cfg():
    with open(os.path.join(BASE, "config.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


class TestFuentes(unittest.TestCase):
    def test_trm_parse_ordena_y_descarta_invalidos(self):
        serie = trm.parse(TRM_ROWS + [{"valor": "x"}])
        self.assertEqual(serie[0], (datetime(2026, 11, 10).date(), 4000.0))
        self.assertEqual(len(serie), 8)

    def test_trm_usa_periodos_cortos_y_luego_mercado(self):
        llamadas = []
        def falso(url, params=None, headers=None):
            llamadas.append((url, params))
            if "datos.gov.co" in url and "$where" in params:
                raise ConnectionError("503 Service Unavailable")
            r = mock.Mock()
            r.json.return_value = TRM_ROWS
            return r
        errores = []
        with mock.patch("monitor.red.get", side_effect=falso):
            serie, fuente = trm.obtener(errores=errores)
        self.assertEqual(fuente, trm.OFICIAL)
        self.assertEqual(len(llamadas), 3)  # 5 años, 1 año, 30 días
        self.assertIn("30 días", errores[0])

        def todo_falla(url, params=None, headers=None):
            if "datos.gov.co" in url:
                raise ConnectionError("503")
            r = mock.Mock()
            r.json.return_value = {"chart": {"result": [{"timestamp": [1762300800, 1762387200],
                                   "indicators": {"quote": [{"close": [3950.5, 3961.2]}]}}]}}
            return r
        errores = []
        with mock.patch("monitor.red.get", side_effect=todo_falla):
            serie, fuente = trm.obtener(errores=errores)
        self.assertEqual(fuente, trm.MERCADO)
        self.assertEqual(serie[0][1], 3961.2)
        self.assertTrue(errores)

    def test_red_reintenta_errores_temporales(self):
        from monitor import red
        malo, bueno = mock.Mock(status_code=503), mock.Mock(status_code=200)
        with mock.patch("requests.get", side_effect=[malo, bueno]) as g, mock.patch("time.sleep"):
            self.assertIs(red.get("https://x"), bueno)
        self.assertEqual(g.call_count, 2)

    def test_cobre_convierte_libra_a_tonelada(self):
        actual, serie = cobre.parse(YAHOO)
        self.assertAlmostEqual(actual, 4.5 * 2204.62, places=1)
        self.assertEqual(len(serie), 6)  # el None se descarta
        self.assertGreater(serie[-1][1], serie[0][1])  # más reciente primero

    def test_stooq_csv(self):
        txt = "Date,Open,High,Low,Close,Volume\n2026-11-03,4.9,5,4.8,4.95,100\n2026-11-04,4.95,5.1,4.9,5.05,120\n"
        precio, serie = cobre.parse_stooq(txt)
        self.assertAlmostEqual(precio, 5.05 * 2204.62, places=1)
        self.assertEqual(serie[0][0].day, 4)
        with self.assertRaises(ValueError):
            cobre.parse_stooq("Exceeded the daily hits limit")

    def test_stooq_en_centavos(self):
        precio, _ = cobre.parse_stooq("Date,Open,High,Low,Close,Volume\n2026-11-04,1,1,1,495.0,1\n")
        self.assertAlmostEqual(precio, 4.95 * 2204.62, places=1)

    def test_westmetall_varios_formatos(self):
        html = """<table><tr><th>date</th><th>LME Copper Cash-Settlement</th></tr>
        <tr><td>04. November 2026</td><td>10,876.50</td><td>10,900.00</td></tr>
        <tr><td>03.11.2026</td><td>10.801,00</td></tr>
        <tr><td>basura</td><td>x</td></tr>
        <tr><td>02. November 2026</td><td>12</td></tr></table>"""
        precio, serie = cobre.parse_westmetall(html)
        self.assertEqual(precio, 10876.5)
        self.assertEqual([v for _, v in serie], [10876.5, 10801.0])  # el 12 queda fuera de rango
        with self.assertRaises(ValueError):
            cobre.parse_westmetall("<html>bloqueado</html>")

    def test_cadena_de_fuentes_usa_la_siguiente_si_falla(self):
        def falso(url, params=None, headers=None):
            if "yahoo" in url:
                raise ConnectionError("429 Too Many Requests")
            r = mock.Mock()
            r.text = "Date,Open,High,Low,Close,Volume\n2026-11-04,1,1,1,5.0,1\n"
            return r
        errores = []
        with mock.patch("monitor.red.get", side_effect=falso):
            precio, _, fuente = cobre.obtener({}, errores)
        self.assertIn("Stooq", fuente)
        self.assertGreater(precio, 10000)
        self.assertTrue(any("429" in e for e in errores))

    def test_cadena_todas_fallan(self):
        with mock.patch("monitor.red.get", side_effect=ConnectionError("sin red")):
            with self.assertRaises(RuntimeError) as cm:
                cobre.obtener({})
        self.assertIn("Westmetall", str(cm.exception))

    def test_cobre_manual(self):
        self.assertEqual(cobre.obtener({"precio_manual_usd_t": 9800})[0], 9800.0)


class TestCostos(unittest.TestCase):
    def test_costo_y_ranking(self):
        provs = {"a": {"prima_usd_t": 100, "flete_usd_t": 50, "arancel_pct": 10},
                 "b": {"prima_usd_t": 0, "flete_usd_t": 0}}
        r = costos.comparar(10000, 4000, provs)
        self.assertEqual(r[0]["clave"], "b")
        self.assertEqual(r[1]["usd_t"], 11165.0)
        self.assertEqual(r[1]["cop_t"], 44660000)

    def test_variacion_y_cobertura(self):
        serie = [(None, 95), (None, 0), (None, 0), (None, 0), (None, 0), (None, 100)]
        self.assertEqual(costos.variacion_pct(serie, 5), -5.0)
        self.assertIsNone(costos.variacion_pct(serie[:3], 5))
        self.assertEqual(costos.cobertura_dias(40, 80), 15.0)


class TestNoticias(unittest.TestCase):
    def test_puntaje(self):
        p, terms = noticias.puntaje("Huelga en Las Bambas paraliza envíos de cobre")
        self.assertGreaterEqual(p, 7)
        self.assertIn("las bambas", terms)
        self.assertEqual(noticias.puntaje("Comparo precios de autos")[0], 0)
        self.assertEqual(noticias.puntaje("Paro de transportistas en Lima")[0], 0)  # no es de cobre
        self.assertEqual(noticias.puntaje("Los futuros del cobre se consolidan")[0], 1)  # tema sí, riesgo no
        self.assertLess(noticias.puntaje("Las Bambas reanuda envíos de cobre tras acuerdo")[0],
                        noticias.puntaje("Las Bambas suspende envíos de cobre por bloqueo")[0])
        self.assertGreaterEqual(noticias.puntaje("Perú aprueba impuesto a las exportaciones de cobre")[0], 4)

    def test_filtrar_deduplica_y_descarta_irrelevantes(self):
        items = noticias.parse_rss(RSS)
        ahora = datetime(2026, 11, 5, tzinfo=timezone.utc)
        out = noticias.filtrar(items + items, 48, ahora=ahora)
        self.assertEqual(len(out), 2)  # el ceviche se descarta, la de precio estable se conserva
        self.assertIn("Las Bambas", out[0]["titulo"])
        self.assertEqual(out[1]["riesgo"], 1)
        self.assertEqual(noticias.filtrar(items, 1, ahora=ahora), [])  # demasiado viejas

    def test_gdelt(self):
        out = noticias.parse_gdelt({"articles": [{"title": "t", "url": "u", "domain": "d", "seendate": "20261104T100000Z"}]})
        self.assertEqual(out[0]["fecha"].day, 4)


    def test_google_busca_ultimos_dias_y_en_ingles(self):
        llamadas = []
        def falso(url, params=None, headers=None):
            llamadas.append(params)
            r = mock.Mock(); r.text = "<rss><channel></channel></rss>"; r.json.return_value = {}
            return r
        with mock.patch("monitor.red.get", side_effect=falso):
            noticias.obtener({"max_horas": 72, "google_news": ["cobre"], "google_news_en": ["copper"]}, [])
        self.assertEqual(llamadas[0]["q"], "cobre when:3d")
        self.assertEqual(llamadas[1]["hl"], "en-US")


class TestAlertas(unittest.TestCase):
    def test_reglas(self):
        c = cfg()
        ranking = costos.comparar(10000, 4000, c["proveedores"])
        ctx = {"fecha": "2026-11-05", "trm": 4000, "trm_var_semanal": 2.5, "cobre_var_semanal": -4.0,
               "ranking": ranking, "cobertura_dias": 10,
               "noticias": [{"id": "x", "riesgo": 8, "titulo": "Bloqueo Las Bambas", "url": "u"}]}
        niveles = [a["nivel"] for a in alertas.evaluar(ctx, c)]
        self.assertIn("OPORTUNIDAD", niveles)
        self.assertIn("URGENTE", niveles)
        self.assertIn("PELIGRO", niveles)
        self.assertEqual(niveles.count("ATENCION"), 1)

    def test_sin_credenciales_no_envia(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(alertas.enviar_telegram("x"))
            self.assertFalse(alertas.enviar_correo("a", "x"))


class TestEjecucion(unittest.TestCase):
    def test_ciclo_completo_con_red_simulada(self):
        def falso_get(url, params=None, headers=None):
            r = mock.Mock()
            if "datos.gov.co" in url:
                r.json.return_value = TRM_ROWS
            elif "yahoo" in url:
                r.json.return_value = YAHOO
            elif "news.google" in url:
                r.text = RSS.replace("2026", str(datetime.now().year)).replace("Wed, 04 Nov", datetime.now(timezone.utc).strftime("%a, %d %b"))
            else:
                raise ConnectionError("sin red")
            return r

        with tempfile.TemporaryDirectory() as tmp, mock.patch("monitor.red.get", side_effect=falso_get), \
                mock.patch.dict(os.environ, {}, clear=True):
            os.makedirs(os.path.join(tmp, "reportes"))
            ctx, todas, nuevas, errores, texto = app.ejecutar(cfg(), tmp, enviar=True)
            self.assertIn("ranking", ctx)
            self.assertTrue(any("GDELT" in e for e in errores))
            self.assertIn("Costo puesto en planta", texto)
            self.assertTrue(os.path.exists(os.path.join(tmp, "data", "historico.csv")))
            self.assertEqual(estado.cargar_enviadas(os.path.join(tmp, "data", "alertas_enviadas.json")), [])


if __name__ == "__main__":
    unittest.main()
