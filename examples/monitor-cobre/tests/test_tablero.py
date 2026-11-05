import os
import tempfile
import unittest
from unittest import mock

from monitor import __main__ as app
from monitor import configuracion, demo

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestConfiguracion(unittest.TestCase):
    def test_ajustes_sobrescriben_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(BASE, "config.yaml"), encoding="utf-8") as f, \
                    open(os.path.join(tmp, "config.yaml"), "w", encoding="utf-8") as g:
                g.write(f.read())
            configuracion.guardar_ajustes(tmp, {"empresa": {"inventario_toneladas": 7}, "proveedores": {"chile": {"flete_usd_t": 1}}})
            cfg = configuracion.cargar(tmp)
            self.assertEqual(cfg["empresa"]["inventario_toneladas"], 7)
            self.assertEqual(cfg["empresa"]["proveedor_actual"], "peru")  # lo demás se conserva
            self.assertEqual(cfg["proveedores"]["chile"]["flete_usd_t"], 1)
            self.assertEqual(cfg["proveedores"]["chile"]["prima_usd_t"], 135)


class TestSecretos(unittest.TestCase):
    def test_ajustes_por_variable_de_entorno(self):
        with mock.patch.dict(os.environ, {"MONITOR_AJUSTES": "proveedores:\n  peru:\n    prima_usd_t: 99\n"}):
            cfg = configuracion.cargar(BASE)
        self.assertEqual(cfg["proveedores"]["peru"]["prima_usd_t"], 99)
        self.assertEqual(cfg["proveedores"]["peru"]["flete_usd_t"], 85)

    def test_fusionar_no_modifica_original(self):
        base = {"a": {"b": 1, "c": 2}}
        self.assertEqual(configuracion.fusionar(base, {"a": {"b": 5}}), {"a": {"b": 5, "c": 2}})
        self.assertEqual(base["a"]["b"], 1)


class TestDemo(unittest.TestCase):
    def test_modo_demo_completo_y_sin_escribir_archivos(self):
        with tempfile.TemporaryDirectory() as tmp, demo.activar():
            ctx, todas, _, errores, _ = app.ejecutar(configuracion.cargar(BASE), tmp, enviar=False, guardar=False)
            self.assertEqual(errores, [])
            self.assertGreater(len(ctx["serie_trm"]), 1500)
            self.assertGreater(len(ctx["serie_cobre"]), 1000)
            self.assertTrue(any(a["nivel"] == "PELIGRO" for a in todas))
            self.assertEqual(os.listdir(tmp), [])


@unittest.skipUnless(__import__("importlib").util.find_spec("streamlit"), "streamlit no instalado")
class TestTablero(unittest.TestCase):
    def test_tablero_carga_sin_errores_en_modo_demo(self):
        from streamlit.testing.v1 import AppTest
        with mock.patch.dict(os.environ, {"MONITOR_DEMO": "1"}):
            at = AppTest.from_file(os.path.join(BASE, "app.py"), default_timeout=60).run()
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(at.title[0].value, "Monitor de cobre")
        self.assertEqual(len(at.metric), 13)

    def test_pestanas_y_simulador(self):
        from streamlit.testing.v1 import AppTest
        with mock.patch.dict(os.environ, {"MONITOR_DEMO": "1"}, clear=False):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            at = AppTest.from_file(os.path.join(BASE, "app.py"), default_timeout=60).run()
            self.assertEqual([t.label for t in at.tabs][:3], ["📊 Resumen", "📈 Gráficos", "🧮 Escenarios"])
            periodo = next(r for r in at.radio if r.label == "Periodo")
            for opcion in ("3 meses", "5 años", "Elegir meses"):
                periodo.set_value(opcion).run()
                self.assertEqual(len(at.exception), 0, opcion)
            next(r for r in at.radio if r.label == "Ver").set_value("Promedio mensual").run()
            self.assertEqual(len(at.exception), 0)
            at.slider[0].set_value(10).run()
            nuevo = next(m for m in at.metric if m.label == "Nuevo costo por tonelada")
            self.assertTrue(nuevo.delta.startswith("+"))
            self.assertTrue(any("ANTHROPIC_API_KEY" in i.value for i in at.info))

    def test_clave_de_acceso_bloquea_el_tablero(self):
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(os.path.join(BASE, "app.py"), default_timeout=60)
        at.secrets["clave_acceso"] = "secreta"
        at.run()
        self.assertEqual(len(at.metric), 0)  # sin clave no se ve nada
        at.text_input[0].input("mala").run()
        self.assertEqual(len(at.metric), 0)
        self.assertEqual(at.error[0].value, "Clave incorrecta.")
        with mock.patch.dict(os.environ, {"MONITOR_DEMO": "1"}):
            at.text_input[0].input("secreta").run()
        self.assertEqual(len(at.metric), 13)


if __name__ == "__main__":
    unittest.main()
