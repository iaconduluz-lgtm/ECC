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

    def test_cobre_convierte_libra_a_tonelada(self):
        actual, serie = cobre.parse(YAHOO)
        self.assertAlmostEqual(actual, 4.5 * 2204.62, places=1)
        self.assertEqual(len(serie), 6)  # el None se descarta
        self.assertGreater(serie[-1][1], serie[0][1])  # más reciente primero

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

    def test_filtrar_deduplica_y_descarta_irrelevantes(self):
        items = noticias.parse_rss(RSS)
        ahora = datetime(2026, 11, 5, tzinfo=timezone.utc)
        out = noticias.filtrar(items + items, 48, ahora=ahora)
        self.assertEqual(len(out), 1)
        self.assertIn("Las Bambas", out[0]["titulo"])
        self.assertEqual(noticias.filtrar(items, 1, ahora=ahora), [])  # demasiado viejas

    def test_gdelt(self):
        out = noticias.parse_gdelt({"articles": [{"title": "t", "url": "u", "domain": "d", "seendate": "20261104T100000Z"}]})
        self.assertEqual(out[0]["fecha"].day, 4)


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
        self.assertIn("RIESGO SUMINISTRO", niveles)
        self.assertEqual(niveles.count("ATENCION"), 1)

    def test_sin_credenciales_no_envia(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(alertas.enviar_telegram("x"))
            self.assertFalse(alertas.enviar_correo("a", "x"))


class TestEjecucion(unittest.TestCase):
    def test_ciclo_completo_con_red_simulada(self):
        def falso_get(url, params=None):
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
