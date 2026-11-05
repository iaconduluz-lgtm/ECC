"""Carga config.yaml y le aplica los ajustes guardados desde el tablero (data/ajustes.yaml)."""
import copy
import os

import yaml


def _fusionar(base, cambios):
    out = copy.deepcopy(base)
    for k, v in (cambios or {}).items():
        out[k] = _fusionar(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def ruta_ajustes(base):
    return os.path.join(base, "data", "ajustes.yaml")


def cargar(base, ruta_config=None):
    with open(ruta_config or os.path.join(base, "config.yaml"), encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    try:
        with open(ruta_ajustes(base), encoding="utf-8") as f:
            cfg = _fusionar(cfg, yaml.safe_load(f))
    except OSError:
        pass
    return cfg


def guardar_ajustes(base, ajustes):
    os.makedirs(os.path.join(base, "data"), exist_ok=True)
    with open(ruta_ajustes(base), "w", encoding="utf-8") as f:
        yaml.safe_dump(ajustes, f, allow_unicode=True, sort_keys=False)
