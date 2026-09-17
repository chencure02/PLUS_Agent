"""Tool: calculate neighborhood weights from expansion raster."""
import numpy as np
from osgeo import gdal
from agent.tools.base import BaseTool, ToolResult


class NeighborhoodWeightTool(BaseTool):
    name = "neighborhood_weight"
    description = (
        "从 Expansion 模块生成的用地扩张栅格图计算邻域权重（Neighborhood Weight），"
        "传入 CARS 模块。核心逻辑：统计各用地类型的扩张像素占比。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "expansion_raster": {
                "type": "string",
                "description": "Expansion 模块输出的扩张栅格图绝对路径（实际输出带 _landuse_1to2 后缀）",
            },
            "num_classes": {
                "type": "integer",
                "description": "土地利用类型数量",
            },
            "background_values": {
                "type": "string",
                "default": "0,255",
                "description": "要排除的背景/无数据值，逗号分隔。默认 0（背景）,255（无数据）",
            },
        },
        "required": ["expansion_raster", "num_classes"]
    }

    def execute(self, params: dict) -> ToolResult:
        raster_path = params["expansion_raster"]
        num_classes = params["num_classes"]
        bg_str = params.get("background_values", "0,255")
        bg_values = set(int(v.strip()) for v in bg_str.split(",") if v.strip())

        # Open raster
        ds = gdal.Open(raster_path)
        if ds is None:
            return ToolResult(success=False, error=f"无法打开栅格: {raster_path}")

        band = ds.GetRasterBand(1)
        data = band.ReadAsArray()
        ds = None

        # Flatten and count
        flat = data.ravel()
        total_valid = 0
        counts = {}
        for v in flat:
            v = int(v)
            if v in bg_values:
                continue
            total_valid += 1
            counts[v] = counts.get(v, 0) + 1

        if total_valid == 0:
            return ToolResult(success=False, error="扩张栅格中无有效像素（全部为背景/无数据值）")

        # Build weight list for classes 1..num_classes
        weights = []
        detail_lines = []
        for cls_id in range(1, num_classes + 1):
            cnt = counts.get(cls_id, 0)
            ratio = cnt / total_valid if total_valid > 0 else 0.0
            weights.append(f"{ratio:.6f}")
            detail_lines.append(f"  类型 {cls_id}: {cnt} 像素, 权重 = {ratio:.6f}")

        weight_str = ",".join(weights)
        detail = "\n".join(detail_lines)
        msg = (
            f"计算完成：总有效扩张像素 = {total_valid}\n"
            f"{detail}\n\n"
            f"CARS Neighborhood Weight = `{weight_str}`"
        )
        return ToolResult(
            success=True,
            message=msg,
            artifacts={"neighborhood_weights": weight_str},
        )
