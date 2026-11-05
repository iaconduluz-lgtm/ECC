import os
import unittest
from datetime import date
from unittest import mock

from monitor import inventario as inv

# Datos ficticios (los reales de la empresa van en los Secrets, nunca en el repositorio).
PLAN = {"anio": 2026, "inventario_inicial": 30,
        "compras_importacion": [0, 10, 0, 10, 0, 10, 0, 10, 0, 10, 0, 10],
        "compra_nacional": [0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        "producto_terminado": [2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        "ventas": [8] * 12,
        "ajuste": [0, 0, 0, 0, 0.5, 0, 0, 0, 0, 0, 0, 0]}


class TestPlan(unittest.TestCase):
    def test_formula(self):
        f = inv.proyectar(PLAN)
        self.assertEqual(f[0]["final"], 24)          # 30 + 2 (PT) - 8
        self.assertEqual(f[1]["inicial"], 24)
        self.assertEqual(f[1]["final"], 26)          # 24 + 10 - 8
        self.assertEqual(f[2]["final"], 19)          # 26 + 1 (nacional) - 8
        self.assertEqual(f[4]["final"], 13.5)        # 21 - 8 + 0.5 (ajuste)
        self.assertEqual(f[0]["meses_inventario"], 3)
        self.assertEqual(f[0]["dias_inventario"], 90)
        self.assertTrue(all(x["tipo"] == "Proyectado" for x in f))

    def test_cierres_reales(self):
        f = inv.proyectar({**PLAN, "cierres_reales": [24, 20]})
        self.assertEqual((f[1]["tipo"], f[1]["final"], f[1]["diferencia"]), ("Real", 20, -6))
        self.assertEqual(f[2]["inicial"], 20)        # se proyecta desde el cierre real
        self.assertEqual(f[2]["tipo"], "Proyectado")

    def test_situacion_y_criticos(self):
        sit = inv.situacion_actual(PLAN, date(2026, 11, 5))
        self.assertEqual(sit["mes"], "Noviembre")
        self.assertEqual(sit["consumo_mensual"], 8)  # promedio de noviembre y diciembre
        self.assertIsNone(inv.situacion_actual(PLAN, date(2027, 1, 5)))  # plan de otro año
        criticos = inv.meses_criticos({**PLAN, "ventas": [8] * 10 + [20, 20]}, 30, date(2026, 11, 5))
        self.assertEqual([c["mes"] for c in criticos], ["Noviembre", "Diciembre"])

    def test_compras_pendientes(self):
        sens = {"cobre_1pct_cop_t": 1000, "trm_1pct_cop_t": 2000}
        p = inv.compras_pendientes(PLAN, 40_000_000, sens, date(2026, 10, 5))
        self.assertEqual([x["mes"] for x in p], ["Octubre", "Diciembre"])
        self.assertEqual(p[0]["costo_estimado_cop"], 400_000_000)
        self.assertEqual(p[0]["si_cobre_sube_5pct"], 10 * 1000 * 5)

    def test_toml(self):
        t = inv.a_toml({**PLAN, "cierres_reales": [24]})
        self.assertIn("[ajustes.plan_inventario]", t)
        self.assertIn("compras_importacion = [0.0, 10.0, 0.0", t)
        self.assertIn("cierres_reales = [24.0]", t)
        import tomllib
        self.assertEqual(tomllib.loads(t)["ajustes"]["plan_inventario"]["ventas"], [8.0] * 12)

    def test_toml_valido_para_streamlit_cloud(self):
        # Streamlit Cloud valida con la librería `toml` antigua: no acepta listas que mezclan 9 y 9.2.
        try:
            import toml
        except ImportError:
            self.skipTest("librería toml no instalada")
        mezcla = {**PLAN, "ventas": [5.8, 9, 9.2] + [8] * 9, "producto_terminado": [3.95, 0] + [0] * 10,
                  "cierres_reales": [37.3, 24]}
        datos = toml.loads(inv.a_toml(mezcla))["ajustes"]["plan_inventario"]
        self.assertEqual(datos["ventas"][:3], [5.8, 9.0, 9.2])
        self.assertEqual(datos["cierres_reales"], [37.3, 24.0])


@unittest.skipUnless(__import__("importlib").util.find_spec("streamlit"), "streamlit no instalado")
class TestTableroInventario(unittest.TestCase):
    def test_plan_negativo_no_rompe(self):
        from streamlit.testing.v1 import AppTest
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with mock.patch.dict(os.environ, {"MONITOR_DEMO": "1"}):
            at = AppTest.from_file(os.path.join(base, "app.py"), default_timeout=60)
            at.secrets["plan_inventario"] = {"anio": date.today().year, "inventario_inicial": 10, "ventas": [5] * 12}
            at.run()
        self.assertEqual(len(at.exception), 0)
        self.assertTrue(any("sin material" in e.value for e in at.error))

    def test_plan_desde_secrets(self):
        from streamlit.testing.v1 import AppTest
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with mock.patch.dict(os.environ, {"MONITOR_DEMO": "1"}):
            at = AppTest.from_file(os.path.join(base, "app.py"), default_timeout=60)
            at.secrets["ajustes"] = {"plan_inventario": {**PLAN, "anio": date.today().year}}
            at.run()
        self.assertEqual(len(at.exception), 0)
        self.assertTrue(any(m.label == "Cierre de diciembre (proyectado)" for m in at.metric))
        self.assertTrue(any("[ajustes.plan_inventario]" in c.value for c in at.code))
        inv_lateral = next(n for n in at.sidebar.number_input if n.label == "Inventario actual (t)")
        self.assertEqual(inv_lateral.value, inv.situacion_actual({**PLAN, "anio": date.today().year})["inventario"])


if __name__ == "__main__":
    unittest.main()
