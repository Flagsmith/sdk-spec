import os
from pathlib import Path

from pytest_bdd import scenarios

FEATURES_DIR = Path(
    os.environ.get("SPEC_FEATURES_DIR", Path(__file__).parents[2] / "features")
).resolve()

scenarios(str(FEATURES_DIR))
