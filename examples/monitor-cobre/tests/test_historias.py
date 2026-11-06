import os
import unittest
from datetime import datetime, timedelta, timezone

import yaml

from monitor import alertas, historias, noticias

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AHORA = datetime(2026, 11, 6, 15, 0, tzinfo=timezone.utc)


def cfg():
    with open(os.path.join(BASE, "config.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def noticia(titulo, horas=1, fuentes=("Medio A", "Medio B"), dia=0):
    """Una noticia ya filtrada, como sale de noticias.filtrar()."""
    e = noticias.evaluar(titulo, ["Elcope"])
    return {"titulo": titulo, "url": f"https://x/{abs(hash(titulo))}", "id": str(abs(hash(titulo)))[:8],
            "fecha": AHORA - timedelta(days=dia, hours=horas), "fuentes": len(fuentes), "lista_fuentes": list(fuentes),
            "fuente": fuentes[0], **e}


BLOQUEO = "Comunidades bloquean el corredor minero sur y Las Bambas suspende envíos"


class TestSeguimiento(unittest.TestCase):
    def test_nueva_y_luego_sigue(self):
        est = historias.vacio()
        vis, _ = historias.actualizar(est, [noticia(BLOQUEO)], ahora=AHORA)
        self.assertEqual(vis[0]["estado_historia"], "Nueva")
        # Tres días después llega otra nota del mismo bloqueo.
        tarde = AHORA + timedelta(days=3)
        vis, _ = historias.actualizar(est, [noticia("Las Bambas: comunidades mantienen bloqueo del corredor minero sur", dia=-3)],
                                      ahora=tarde)
        self.assertEqual(len(est["historias"]), 1)
        self.assertEqual(vis[0]["estado_historia"], "Sigue")
        self.assertEqual(vis[0]["dias_historia"], 4)

    def test_estado_estable_aunque_se_abra_muchas_veces(self):
        est = historias.vacio()
        for _ in range(5):
            vis, _ = historias.actualizar(est, [noticia(BLOQUEO)], ahora=AHORA)
        self.assertEqual(vis[0]["estado_historia"], "Nueva")
        self.assertEqual(len(est["historias"]), 1)

    def test_empeora(self):
        est = historias.vacio()
        primero = noticia("Comunidades del corredor minero sur anuncian protesta en Las Bambas", dia=2)
        self.assertEqual(primero["nivel"], "Medio")  # un anuncio todavía no es un hecho
        historias.actualizar(est, [primero], ahora=AHORA - timedelta(days=2))
        vis, _ = historias.actualizar(est, [noticia("Bloqueo total paraliza el corredor minero sur y Las Bambas")], ahora=AHORA)
        self.assertEqual(vis[0]["estado_historia"], "Empeora")

    def test_buena_noticia_resuelve(self):
        est = historias.vacio()
        historias.actualizar(est, [noticia(BLOQUEO, horas=30)], ahora=AHORA - timedelta(days=1))
        vis, _ = historias.actualizar(est, [noticia(BLOQUEO, horas=30), noticia("Comunidades levantan el bloqueo del corredor minero sur")],
                                      ahora=AHORA)
        malo = next(n for n in vis if "bloquean" in n["titulo"])
        bueno = next(n for n in vis if "levantan" in n["titulo"])
        self.assertEqual(malo["estado_historia"], "Resuelta")
        self.assertEqual(malo["nivel"], "Bajo")  # ya no es un peligro
        self.assertEqual(bueno["estado_historia"], "Resuelve una historia")
        self.assertEqual(alertas.evaluar({"fecha": "x", "ranking": [], "cobertura_dias": 45, "noticias": vis}, cfg()), [])

    def test_sin_novedades(self):
        est = historias.vacio()
        historias.actualizar(est, [noticia(BLOQUEO, dia=4)], ahora=AHORA - timedelta(days=4))
        vis, _ = historias.actualizar(est, [noticia(BLOQUEO, dia=4)], ahora=AHORA)  # nada nuevo desde hace 4 días
        self.assertEqual(vis[0]["estado_historia"], "Sin novedades")

    def test_alerta_una_vez_por_historia_y_nivel(self):
        est = historias.vacio()
        a1, _ = historias.actualizar(est, [noticia(BLOQUEO)], ahora=AHORA)
        a2, _ = historias.actualizar(est, [noticia("Las Bambas: comunidades bloquean el corredor minero sur")], ahora=AHORA)
        ids = {a["id"] for lote in (a1, a2) for a in alertas.evaluar({"fecha": "x", "ranking": [], "cobertura_dias": 45,
                                                                        "noticias": lote}, cfg())}
        self.assertEqual(len(ids), 1)


    def test_no_une_hechos_distintos(self):
        est = historias.vacio()
        historias.actualizar(est, [noticia(BLOQUEO), noticia("Paro camionero bloquea la vía al Pacífico entre Buenaventura y Cali")],
                             ahora=AHORA)
        self.assertEqual(len(est["historias"]), 2)


class TestOpiniones(unittest.TestCase):
    def test_no_me_sirve_oculta_tambien_las_futuras(self):
        est = historias.vacio()
        vis, _ = historias.actualizar(est, [noticia("Precio del cobre en Londres sube por inventarios")], ahora=AHORA)
        historias.opinar(est, vis[0], "no_sirve")
        vis, ocultas = historias.actualizar(est, [noticia("Precio del cobre en Londres sube por menores inventarios")], ahora=AHORA)
        self.assertEqual((len(vis), len(ocultas)), (0, 1))
        historias.opinar(est, ocultas[0], "")
        vis, ocultas = historias.actualizar(est, [noticia("Precio del cobre en Londres sube por menores inventarios")], ahora=AHORA)
        self.assertEqual((len(vis), len(ocultas)), (1, 0))

    def test_me_sirve_va_primero(self):
        est = historias.vacio()
        lote = [noticia(BLOQUEO), noticia("Precio del cobre en Londres sube por inventarios")]
        vis, _ = historias.actualizar(est, lote, ahora=AHORA)
        historias.opinar(est, next(n for n in vis if "Londres" in n["titulo"]), "sirve")
        vis, _ = historias.actualizar(est, lote, ahora=AHORA)
        self.assertIn("Londres", vis[0]["titulo"])

    def test_medio_poco_util(self):
        est = historias.vacio()
        titulos = ["Precio del cobre en Londres sube", "Dólar en Colombia abre estable", "China compra más cobre refinado"]
        for t in titulos:
            vis, _ = historias.actualizar(est, [noticia(t, fuentes=("Medio Z",))], ahora=AHORA)
            historias.opinar(est, vis[0], "no_sirve")
        self.assertEqual(historias.medios_poco_utiles(est), ["Medio Z"])

    def test_guardar_y_cargar(self):
        import tempfile
        est = historias.vacio()
        historias.actualizar(est, [noticia(BLOQUEO)], ahora=AHORA)
        with tempfile.TemporaryDirectory() as tmp:
            ruta = os.path.join(tmp, "data", "historias.json")
            historias.guardar(ruta, est)
            self.assertEqual(len(historias.cargar(ruta)["historias"]), 1)
        self.assertEqual(historias.cargar("/no/existe.json"), historias.vacio())


class TestResumen(unittest.TestCase):
    def test_resumen_detecta_buena_noticia_y_proveedor(self):
        e = noticias.evaluar("Situación en el corredor minero sur", ["Elcope"], "Las comunidades levantan el bloqueo tras acuerdo")
        self.assertEqual(e["certeza"], "Buena noticia")
        e = noticias.evaluar("Huelga en planta de cables de Lima", ["Elcope"], "Los trabajadores de Elcope iniciaron la huelga")
        self.assertTrue(e["afecta_proveedor"])

    def test_resumen_no_suma_puntos_dos_veces(self):
        a = noticias.evaluar("Bloqueo en Las Bambas", [])
        b = noticias.evaluar("Bloqueo en Las Bambas", [], "Bloqueo bloqueo huelga paro Las Bambas")
        self.assertEqual(a["riesgo"], b["riesgo"])

    def test_google_agrupa_medios_y_cuenta_como_confirmacion(self):
        xml = ("<rss><channel><item><title>Bloqueo paraliza Las Bambas - Medio A</title><link>https://a/1</link>"
               "<pubDate>Fri, 06 Nov 2026 14:00:00 GMT</pubDate><source>Medio A</source>"
               "<description>&lt;ol&gt;&lt;li&gt;&lt;a href=\"x\"&gt;Bloqueo paraliza Las Bambas&lt;/a&gt;&lt;font color=\"#6f6f6f\"&gt;Medio A&lt;/font&gt;&lt;/li&gt;"
               "&lt;li&gt;&lt;a href=\"y\"&gt;Las Bambas paralizada por bloqueo&lt;/a&gt;&lt;font color=\"#6f6f6f\"&gt;Medio B&lt;/font&gt;&lt;/li&gt;&lt;/ol&gt;"
               "</description></item></channel></rss>")
        items = noticias.parse_rss(xml)
        self.assertEqual(items[0]["otros_medios"], ["Medio B"])
        out = noticias.filtrar(items, 72, ahora=AHORA)
        self.assertEqual(out[0]["fuentes"], 2)

    def test_buena_noticia_no_confirma_la_mala(self):
        out = noticias.filtrar([
            {"titulo": "Comunidades bloquean el corredor minero sur", "url": "https://a/1", "fuente": "Medio A", "fecha": AHORA},
            {"titulo": "Comunidades levantan el bloqueo del corredor minero sur", "url": "https://b/2", "fuente": "Medio B",
             "fecha": AHORA}], 72, ahora=AHORA)
        self.assertEqual(len(out), 2)
        self.assertTrue(all(n["fuentes"] == 1 for n in out))


class TestEstadoFuentes(unittest.TestCase):
    def test_estado_por_busqueda(self):
        from unittest import mock

        def falso(url, params=None, headers=None):
            if params and "falla" in params.get("q", ""):
                raise ConnectionError("sin red")
            r = mock.Mock()
            r.text = "<rss><channel></channel></rss>"
            r.json.return_value = {"articles": []}
            return r
        estado = []
        with mock.patch("monitor.red.get", side_effect=falso):
            noticias.obtener({"google_news": ["cobre", "falla"], "rss_directos": [{"nombre": "Medio X", "url": "https://x/rss"}],
                              "gdelt": ["copper"]}, [], estado)
        self.assertEqual([e["origen"] for e in estado], ["Google News · Perú", "Google News · Perú", "RSS directo", "GDELT"])
        self.assertEqual([bool(e["error"]) for e in estado], [False, True, False, False])


if __name__ == "__main__":
    unittest.main()
