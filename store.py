# -*- coding: utf-8 -*-
"""config.yaml 로드/저장(주석 보존) + 상태 파일(seen/digest/offset) 관리"""
import json
import os
from ruamel.yaml import YAML

yaml = YAML()
yaml.preserve_quotes = True

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")
STATE_DIR = os.path.join(os.path.dirname(__file__), "state")


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.load(f)


def save_config(cfg):
    """텔레그램 명령으로 키워드가 바뀌면 호출됨. 주석까지 그대로 보존."""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f)


def _state_path(name):
    os.makedirs(STATE_DIR, exist_ok=True)
    return os.path.join(STATE_DIR, name)


def load_state(name, default):
    path = _state_path(name)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def save_state(name, data):
    with open(_state_path(name), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
