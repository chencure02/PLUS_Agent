"""Calculate PLUS CARS neighborhood weights from an expansion raster."""

from __future__ import annotations

import argparse
from pathlib import Path


def calculate_neighborhood_weights(
    expansion_raster: str | Path,
    num_classes: int,
    background_values: str = "0,255",
) -> str:
    """Return class proportions for CARS, excluding configured background values."""
    if num_classes < 1:
        raise ValueError("num_classes must be at least 1")

    import numpy as np
    from osgeo import gdal

    background = {int(value.strip()) for value in background_values.split(",") if value.strip()}
    dataset = gdal.Open(str(expansion_raster))
    if dataset is None:
        raise ValueError(f"无法打开扩张栅格: {expansion_raster}")

    band = dataset.GetRasterBand(1)
    if band is None:
        raise ValueError(f"扩张栅格不包含第一个波段: {expansion_raster}")

    raster = band.ReadAsArray()
    valid_mask = ~np.isin(raster, list(background))
    valid_count = int(valid_mask.sum())
    if valid_count == 0:
        raise ValueError("扩张栅格中没有可用于计算邻域权重的有效像元")

    weights = [float(((raster == class_id) & valid_mask).sum()) / valid_count for class_id in range(1, num_classes + 1)]
    return ",".join(f"{weight:.6f}" for weight in weights)


def main() -> int:
    parser = argparse.ArgumentParser(description="根据扩张栅格计算 PLUS CARS 邻域权重。")
    parser.add_argument("--expansion-raster", required=True, help="扩张栅格的绝对路径")
    parser.add_argument("--num-classes", required=True, type=int, help="土地利用类别数量")
    parser.add_argument("--background-values", default="0,255", help="忽略的背景值，使用逗号分隔")
    args = parser.parse_args()

    try:
        print(calculate_neighborhood_weights(args.expansion_raster, args.num_classes, args.background_values))
    except (ValueError, ImportError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
