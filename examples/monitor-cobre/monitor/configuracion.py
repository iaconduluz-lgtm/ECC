"""Carga config.yaml y le aplica los ajustes guardados desde el tablero (data/ajustes.yaml)."""
import copy
import os

import yaml


def fusionar(base, cambios):
    """Mezcla `cambios` sobre `base` (recursivo) sin modificar los originales."""
    out = copy.deepcopy(base)
    for k, v in dict(cambios or {}).items():
        v = dict(v) if hasattr(v, "keys") else v  # los secrets de Streamlit no son dict puros
        out[k] = fusionar(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def ruta_ajustes(base):
    return os.path.join(base, "data", "ajustes.yaml")


def cargar(base, ruta_config=None):
    with open(ruta_config or os.path.join(base, "config.yaml"), encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    try:
        with open(ruta_ajustes(base), encoding="utf-8") as f:
            cfg = fusionar(cfg, yaml.safe_load(f))
    except OSError:
        pass
    # En GitHub Actions los costos reales llegan por el secret MONITOR_AJUSTES (texto YAML).
    if os.environ.get("MONITOR_AJUSTES"):
        cfg = fusionar(cfg, yaml.safe_load(os.environ["MONITOR_AJUSTES"]))
    return cfg


def guardar_ajustes(base, ajustes):
    os.makedirs(os.path.join(base, "data"), exist_ok=True)
    with open(ruta_ajustes(base), "w", encoding="utf-8") as f:
        yaml.safe_dump(ajustes, f, allow_unicode=True, sort_keys=False)
