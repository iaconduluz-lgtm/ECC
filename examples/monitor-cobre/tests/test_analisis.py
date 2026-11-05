import json
import os
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest import mock

import yaml

from monitor import analisis, ia

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROV = {"prima_usd_t": 100, "flete_usd_t": 50, "seguro_usd_t": 0, "arancel_pct": 0}


def cfg():
    with open(os.path.join(BASE, "config.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def serie(valores):
    hoy = date(2026, 11, 5)
    return [(hoy - timedelta(days=i), v) for i, v in enumerate(valores)]


class TestEscenarios(unittest.TestCase):
    def test_sensibilidad(self):
        s = analisis.sensibilidad(10000, 4000, PROV, 80)
        self.assertAlmostEqual(s["cobre_1pct_cop_t"], 100 * 4000, delta=1)       # 1 % de 10.000 USD x TRM
        self.assertAlmostEqual(s["trm_1pct_cop_t"], 10150 * 40, delta=1)         # 1 % de la TRM sobre todo el costo
        self.assertAlmostEqual(s["cobre_1pct_mes"], s["cobre_1pct_cop_t"] * 80, delta=1)

    def test_matriz(self):
        filas = analisis.escenarios(10000, 4000, PROV, 10)
        self.assertEqual(len(filas), 25)
        cero = next(f for f in filas if f["cobre_pct"] == 0 and f["trm_pct"] == 0)
        self.assertEqual(cero["impacto_mensual_cop"], 0)
        peor = max(filas, key=lambda f: f["impacto_mensual_cop"])
        self.assertEqual((peor["cobre_pct"], peor["trm_pct"]), (10, 10))


class TestContexto(unittest.TestCase):
    def test_promedios_y_percentil(self):
        c = analisis.contexto(serie([90] + [100] * 400))
        self.assertEqual(c["vs_prom_90_pct"], round((90 - mean_90()) / mean_90() * 100, 2))
        self.assertEqual(c["percentil_1a"], 0)

    def test_promedio_mensual(self):
        s = [(date(2026, 10, 1), 10), (date(2026, 10, 2), 20), (date(2026, 11, 1), 30)]
        self.assertEqual(analisis.promedio_mensual(s), [("2026-10", 15), ("2026-11", 30)])


def mean_90():
    vals = [90] + [100] * 90
    return sum(vals) / len(vals)


class TestRecomendacion(unittest.TestCase):
    def base_ctx(self, **kw):
        ctx = {"contexto_cobre": {}, "contexto_trm": {}, "noticias": [], "cobertura_dias": 45, "cobre_var_semanal": 0}
        ctx.update(kw)
        return ctx

    def test_comprar_cuando_barato(self):
        r = analisis.recomendacion(self.base_ctx(contexto_cobre={"vs_prom_90_pct": -5, "percentil_1a": 20},
                                                 contexto_trm={"vs_prom_90_pct": -3}), cfg())
        self.assertEqual(r["tono"], "comprar")
        self.assertEqual(len(r["razones"]), 3)

    def test_esperar_cuando_caro(self):
        r = analisis.recomendacion(self.base_ctx(contexto_cobre={"vs_prom_90_pct": 8, "percentil_1a": 95}), cfg())
        self.assertEqual(r["tono"], "esperar")

    def test_urgente_si_falta_inventario(self):
        r = analisis.recomendacion(self.base_ctx(cobertura_dias=10, contexto_cobre={"vs_prom_90_pct": 8}), cfg())
        self.assertEqual(r["tono"], "urgente")

    def test_noticia_peru_sugiere_diversificar(self):
        n = {"titulo": "Bloqueo en Las Bambas detiene envíos", "riesgo": 9}
        r = analisis.recomendacion(self.base_ctx(noticias=[n]), cfg())
        self.assertTrue(r["diversificar"])

    def test_normal(self):
        self.assertEqual(analisis.recomendacion(self.base_ctx(), cfg())["tono"], "normal")


class TestNiveles(unittest.TestCase):
    PROV = ["Elcope", "Electro Conductores Peruanos"]

    def nivel(self, titulo):
        from monitor import noticias
        return noticias.evaluar(titulo, self.PROV)

    def test_escala(self):
        from monitor import noticias
        self.assertEqual([noticias.nivel(x) for x in (1, 3, 4, 5, 6, 7, 8, 10)],
                         ["Bajo", "Bajo", "Medio", "Medio", "Alto", "Alto", "Peligro", "Peligro"])

    def test_casos(self):
        casos = {
            "El precio del cobre se mantiene estable": "Bajo",
            "Antamina reporta producción récord de cobre": "Bajo",
            "Trabajadores amenazan con huelga en Cerro Verde": "Medio",     # amenaza: máximo Medio
            "Perú evalúa nuevo impuesto a las exportaciones mineras": "Medio",
            "Paro portuario en el Callao retrasa embarques": "Alto",
            "Inicia huelga indefinida en Cerro Verde": "Peligro",
            "Sindicato de Cerro Verde anuncia huelga indefinida desde el lunes": "Medio",  # anuncio, aún no hecho
            "Bloqueo en corredor minero sur cumple 10 días": "Peligro",      # duración
            "Comunidades levantan el bloqueo del corredor minero tras 15 días": "Bajo",  # buena noticia
            "Incendio en planta de Elcope paraliza producción": "Peligro",   # proveedor directo
            "Huelga en Electro Conductores Peruanos": "Peligro",
            "Trabajadores de Elcope amenazan con huelga": "Medio",
            # Colombia: ruta Buenaventura - Cali, dólar y aduana
            "Paro camionero bloquea la vía al Pacífico entre Buenaventura y Cali": "Peligro",
            "Derrumbe cierra la vía Buenaventura - Cali": "Peligro",
            "Dólar se dispara en Colombia y supera los 4.300 pesos": "Medio",
            "El dólar cierra estable en Colombia": "Bajo",
            "DIAN anuncia nuevos aranceles a importaciones": "Medio",
            "Levantan paro camionero y se normaliza la vía al Pacífico": "Bajo",
            "Bloqueos en Cali por paro nacional": "Peligro",  # bloqueos en la ciudad de la planta
        }
        for titulo, esperado in casos.items():
            self.assertEqual(self.nivel(titulo)["nivel"], esperado, titulo)

    def test_descarta_lo_que_no_afecta(self):
        from monitor import noticias
        for t in ("Festival de salsa en Cali", "Receta de ceviche peruano", "Colombia gana el partido"):
            self.assertEqual(noticias.evaluar(t, self.PROV)["riesgo"], 0, t)

    def test_tema_colombia(self):
        self.assertEqual(analisis.clasificar({"titulo": "Paro camionero bloquea la vía al Pacífico"})[0], "Logística / puertos")
        self.assertEqual(analisis.clasificar({"titulo": "Dólar se dispara en Colombia"})[0], "Dólar / economía")

    def test_proveedor_y_certeza(self):
        e = self.nivel("Elcope amplía su planta en Lima")
        self.assertTrue(e["afecta_proveedor"])
        self.assertEqual(e["nivel"], "Bajo")
        self.assertEqual(self.nivel("Trabajadores amenazan con huelga en Cerro Verde")["certeza"], "Posible")
        self.assertEqual(self.nivel("Bloqueo en corredor minero sur cumple 10 días")["duracion_dias"], 10)

    def test_alerta_desde_medio_si_es_tu_proveedor(self):
        from monitor import alertas
        base = {"fecha": "x", "ranking": [], "cobertura_dias": 45}
        prov = {"id": "a", "riesgo": 5, "nivel": "Medio", "afecta_proveedor": True, "titulo": "Elcope amenaza", "url": "u"}
        otra = {"id": "b", "riesgo": 5, "nivel": "Medio", "afecta_proveedor": False, "titulo": "Otra", "url": "u"}
        out = alertas.evaluar({**base, "noticias": [prov, otra]}, cfg())
        self.assertEqual([a["id"] for a in out], ["news-a"])
        self.assertIn("TU PROVEEDOR", out[0]["texto"])

    def test_peligro_en_proveedor_es_urgente(self):
        n = {"titulo": "Incendio en planta de Elcope", "riesgo": 9, "afecta_proveedor": True}
        r = analisis.recomendacion({"noticias": [n], "cobertura_dias": 45}, cfg())
        self.assertEqual(r["tono"], "urgente")
        self.assertIn("proveedor alternativo", r["accion"])


class TestClasificacion(unittest.TestCase):
    def test_categorias(self):
        self.assertEqual(analisis.clasificar({"titulo": "Huelga en Cerro Verde"})[0], "Suministro Perú")
        self.assertEqual(analisis.clasificar({"titulo": "Paro en el puerto del Callao"})[0], "Logística / puertos")
        self.assertEqual(analisis.clasificar({"titulo": "Estados Unidos sube aranceles al cobre"})[0], "Política / aranceles")
        self.assertEqual(analisis.clasificar({"titulo": "Codelco reduce producción"})[0], "Oferta mundial")
        g = analisis.resumen_noticias([{"titulo": "Huelga en Cerro Verde", "riesgo": 8},
                                       {"titulo": "Precio del cobre sube", "riesgo": 1}])
        self.assertEqual(g[0]["categoria"], "Suministro Perú")


RESPUESTA = {
    "resumen": "Mercado estable.", "presion_precio_cobre": "alcista", "riesgo_suministro_peru": "medio",
    "noticias_clave": [{"titulo": "t", "nivel": "Alto", "por_que_importa": "p", "efecto_precio": "sube", "afecta_suministro_peru": True}],
    "si_sube_cobre": "a", "si_sube_trm": "b", "recomendacion": "Comprar lo normal.", "acciones": ["x"],
    "proveedores_alternativos": "c",
}


class TestIA(unittest.TestCase):
    def cliente(self, stop="end_turn", texto=None):
        bloque = mock.Mock(type="text", text=texto if texto is not None else json.dumps(RESPUESTA))
        c = mock.Mock()
        c.beta.messages.create.return_value = mock.Mock(stop_reason=stop, content=[bloque])
        return c

    def ctx(self):
        return {"fecha_hora": "hoy", "trm": 4000, "cobre_usd_t": 10000, "ranking": [],
                "noticias": [{"titulo": "Huelga", "fuente": "x", "riesgo": 8, "fecha": datetime.now(timezone.utc)}]}

    def test_analiza_y_valida(self):
        c = self.cliente()
        r = ia.analizar(self.ctx(), cfg(), {"cobre_1pct_mes": 1, "trm_1pct_mes": 2}, {"accion": "x"}, cliente=c)
        self.assertEqual(r.presion_precio_cobre, "alcista")
        kw = c.beta.messages.create.call_args.kwargs
        self.assertEqual(kw["model"], "claude-opus-5-5")
        self.assertEqual(kw["output_config"]["format"]["type"], "json_schema")
        self.assertEqual(kw["fallbacks"], "default")
        self.assertIn("Huelga", kw["messages"][0]["content"])

    def test_rechazo(self):
        with self.assertRaises(RuntimeError):
            ia.analizar(self.ctx(), cfg(), None, {}, cliente=self.cliente(stop="refusal"))

    def test_esquema_coincide_con_modelo(self):
        self.assertEqual(set(ia.ESQUEMA["required"]), set(ia.Analisis.model_fields))
        self.assertEqual(set(ia.ESQUEMA["properties"]), set(ia.Analisis.model_fields))


if __name__ == "__main__":
    unittest.main()
