import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "neighborhood_weight.py"


class _FakeBand:
    def ReadAsArray(self):
        return np.array([[0, 1, 1], [2, 255, 3]], dtype=np.uint8)


class _FakeDataset:
    def GetRasterBand(self, index):
        self.last_band_index = index
        return _FakeBand()


class _FakeGdal:
    def Open(self, path):
        self.opened_path = path
        return _FakeDataset()


def _load_script_module():
    spec = importlib.util.spec_from_file_location("skill_neighborhood_weight", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class NeighborhoodWeightScriptTests(unittest.TestCase):
    def test_calculates_weights_from_valid_pixels_only(self):
        """A background pixel must not dilute class proportions passed to CARS."""
        fake_gdal = _FakeGdal()
        fake_osgeo = types.SimpleNamespace(gdal=fake_gdal)

        with patch.dict(sys.modules, {"osgeo": fake_osgeo}):
            module = _load_script_module()
            weights = module.calculate_neighborhood_weights("sample_expansion.tif", 3)

        self.assertEqual(weights, "0.500000,0.250000,0.250000")
        self.assertEqual(fake_gdal.opened_path, "sample_expansion.tif")


if __name__ == "__main__":
    unittest.main()
