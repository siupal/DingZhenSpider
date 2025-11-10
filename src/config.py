import os
import yaml


def load_config(config_path: str | None = None) -> dict:
    path = config_path or os.path.join(os.getcwd(), "config.yaml")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}
    return data


def merge_config(base: dict, override: dict) -> dict:
    out = dict(base or {})
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge_config(out[k], v)
        elif v is not None:
            out[k] = v
    return out
