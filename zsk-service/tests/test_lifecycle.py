import runpy
from pathlib import Path

def test_database_model_lifecycle():
    runpy.run_path(str(Path(__file__).with_name("check.py")), run_name="__main__")
