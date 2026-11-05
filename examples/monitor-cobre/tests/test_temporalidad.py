import unittest
from datetime import date, timedelta

from monitor import temporalidad as tp


def serie_diaria(inicio, dias, f):
    return [(inicio + timedelta(days=i), f(inicio + timedelta(days=i))) for i in range(dias)]


class TestVariaciones(unittest.TestCase):
    def test_plazos(self):
        s = serie_diaria(date(2025, 1, 1), 400, lambda d: 100 + (d - date(2025, 1, 1)).days * 0.1)
        v = tp.variaciones(s)
        ultimo = s[-1][1]
        self.assertAlmostEqual(v["1 semana"], round((ultimo - (ultimo - 0.7)) / (ultimo - 0.7) * 100, 2))
        self.assertIsNotNone(v["1 año"])
        self.assertIsNone(v["5 años"])  # no hay datos tan antiguos

    def test_serie_desordenada_y_vacia(self):
        s = [(date(2026, 1, 10), 110), (date(2026, 1, 1), 100), (date(2026, 1, 5), 105)]
        self.assertEqual(tp.variaciones(s)["1 semana"], 10.0)  # hace 7 días (3 ene) el último dato es el del 1 ene
        self.assertEqual(tp.variaciones([]), {})


class TestEstacionalidad(unittest.TestCase):
    def test_detecta_mes_caro_y_barato(self):
        # Tres años completos: marzo siempre 10 % más caro, octubre 10 % más barato.
        def precio(d):
            return 100 * (1.10 if d.month == 3 else 0.90 if d.month == 10 else 1.0)
        s = serie_diaria(date(2023, 1, 1), 365 * 3, precio)
        e = {x["nombre_mes"]: x for x in tp.estacionalidad(s)}
        self.assertGreater(e["Mar"]["desvio_pct"], 9)
        self.assertLess(e["Oct"]["desvio_pct"], -9)
        self.assertEqual(e["Mar"]["anios"], 3)
        self.assertEqual(tp.mejores_meses(list(e.values()), 1)[0]["nombre_mes"], "Oct")
        self.assertEqual(tp.mejores_meses(list(e.values()), 1, barato=False)[0]["nombre_mes"], "Mar")

    def test_ignora_anios_incompletos(self):
        s = serie_diaria(date(2025, 11, 1), 60, lambda d: 100.0)  # solo 2 meses
        self.assertTrue(all(x["desvio_pct"] is None for x in tp.estacionalidad(s)))

    def test_por_anio(self):
        s = [(date(2025, 1, 1), 10), (date(2025, 1, 2), 20), (date(2026, 1, 1), 30)]
        self.assertEqual([(r["anio"], r["mes"], r["promedio"]) for r in tp.por_anio(s)], [(2025, 1, 15), (2026, 1, 30)])


if __name__ == "__main__":
    unittest.main()
