"""Regression runner: load a given SCUD version by file path and run start(wp, automatic=True).

Usage: python _run.py "<path-to-SCUD.py>" "<work-folder>"
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


if __name__ == "__main__":
    scud_path = sys.argv[1]
    wp = sys.argv[2]
    mod = load(scud_path, "scud_under_test")
    mod.start(wp, True)
    print("RUN OK")
