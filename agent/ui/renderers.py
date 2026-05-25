import os
import tempfile

# Force non-interactive backend BEFORE any other matplotlib import (tkinter crashes in threads)
import matplotlib
matplotlib.use("Agg")

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
from osgeo import gdal
import folium
from folium.raster_layers import ImageOverlay
import chainlit as cl

# Suppress GDAL FutureWarning
gdal.DontUseExceptions()

# Configure matplotlib for Chinese font rendering
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

LULC_COLORS = ['#000000', '#FF0000', '#00FF00', '#0000FF', '#FFFF00',
               '#FF00FF', '#00FFFF', '#808080', '#FFA500', '#A52A2A']

CHART_COLORS = ['#2196F3', '#4CAF50', '#FF9800', '#E91E63', '#9C27B0',
                '#00BCD4', '#FF5722', '#795548', '#607D8B', '#CDDC39']


def render_raster(tif_path: str, title: str = ""):  # -> cl.Image | cl.Html | cl.Text
    """Render GeoTIFF as Folium interactive map. Fallback: Matplotlib static image."""
    if not os.path.exists(tif_path):
        return cl.Text(content=f"[File not found: {os.path.basename(tif_path)}]")
    try:
        return _render_folium(tif_path, title)
    except Exception:
        try:
            return _render_matplotlib(tif_path, title)
        except Exception:
            return cl.Text(content=f"[Raster: {os.path.basename(tif_path)}]")


def _render_folium(tif_path: str, title: str):  # -> cl.Html
    ds = gdal.Open(tif_path)
    if ds is None:
        raise ValueError(f"Cannot open raster: {tif_path}")
    band = ds.GetRasterBand(1)
    data = band.ReadAsArray()
    gt = ds.GetGeoTransform()
    minx, maxy = gt[0], gt[3]
    maxx = minx + gt[1] * ds.RasterXSize
    miny = maxy + gt[5] * ds.RasterYSize
    ds = None

    m = folium.Map(location=[(miny + maxy) / 2, (minx + maxx) / 2],
                   zoom_start=10, tiles="OpenStreetMap")

    scale = max(1, min(data.shape) // 2000)
    if scale > 1:
        data = data[::scale, ::scale]

    unique = np.unique(data)
    n = len(unique)
    colors = LULC_COLORS[:n] if n <= len(LULC_COLORS) else ['#%06X' % (i * 123457) for i in range(n)]
    cmap = ListedColormap(colors)
    bounds = [int(v) for v in unique] + [int(unique[-1]) + 1]
    norm = BoundaryNorm(bounds, cmap.N)
    colored = (cmap(norm(data))[:, :, :3] * 255).astype(np.uint8)

    ImageOverlay(colored, [[miny, minx], [maxy, maxx]], opacity=0.6).add_to(m)
    folium.LayerControl().add_to(m)

    return cl.Html(content=m.get_root().render(), name=title or os.path.basename(tif_path))


def _render_matplotlib(tif_path: str, title: str):  # -> cl.Image
    ds = gdal.Open(tif_path)
    if ds is None:
        raise ValueError(f"Cannot open raster: {tif_path}")
    data = ds.GetRasterBand(1).ReadAsArray()
    ds = None
    scale = max(1, min(data.shape) // 2000)
    if scale > 1:
        data = data[::scale, ::scale]

    fig, ax = plt.subplots(figsize=(10, 8))
    im = ax.imshow(data, cmap='tab10', interpolation='nearest')
    plt.colorbar(im, ax=ax, label='Class')
    ax.set_title(title or os.path.basename(tif_path))
    ax.axis('off')
    plt.tight_layout()

    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
        fig.savefig(tmp.name, dpi=100)
        plt.close(fig)
        return cl.Image(path=tmp.name, name=title or "Raster Preview")


def render_csv(csv_path: str):  # -> cl.Text | cl.Image
    """Render CSV: contribution CSVs get charts, others get text tables."""
    if not os.path.exists(csv_path):
        return cl.Text(content=f"[File not found: {os.path.basename(csv_path)}]")
    basename = os.path.basename(csv_path)
    if basename.startswith("Contribution"):
        chart_path = _render_contribution_chart(csv_path, basename)
        if chart_path:
            return cl.Image(path=chart_path, name=basename)
        return cl.Text(content=f"[Failed to render chart for {basename}]")
    import pandas as pd
    df = pd.read_csv(csv_path)
    return cl.Text(content=f"```\n{df.to_string()}\n```", language="text")


def _render_contribution_chart(csv_path: str, title: str) -> str | None:
    """Render a Contribution*.csv as horizontal bar charts. Returns temp PNG path or None."""
    try:
        rows = []
        with open(csv_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = [p.strip() for p in line.split(",") if p.strip()]
                rows.append(parts)
        if len(rows) < 4:
            return None

        rmse_original = float(rows[0][1]) if len(rows[0]) > 1 else 0.0
        factor_names = rows[1][1:]
        rmse_noise = [float(v) for v in rows[2][1:]]
        contributions = [float(v) for v in rows[3][1:]]
        n = len(factor_names)
        if n == 0:
            return None

        # Shorten display names
        short_names = []
        for fn in factor_names:
            fn = fn.replace(".tif", "").replace("wh_", "").replace("df_", "")
            if len(fn) > 25:
                fn = fn[:22] + "..."
            short_names.append(fn)

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, max(5, n * 0.3)))
        y_pos = range(n)
        colors = CHART_COLORS * (n // len(CHART_COLORS) + 1)

        # Contribution
        bars1 = ax1.barh(y_pos, contributions, color=colors[:n], edgecolor="white")
        ax1.set_yticks(y_pos)
        ax1.set_yticklabels(short_names, fontsize=8)
        ax1.invert_yaxis()
        ax1.set_xlabel("Contribution")
        ax1.set_title(f"{title}\nRMSE = {rmse_original:.4f}")
        for bar, val in zip(bars1, contributions):
            ax1.text(bar.get_width() + 0.001, bar.get_y() + bar.get_height() / 2,
                     f"{val:.3f}", va="center", fontsize=7)

        # Importance (RMSE)
        bars2 = ax2.barh(y_pos, rmse_noise, color=colors[:n], edgecolor="white")
        ax2.set_yticks(y_pos)
        ax2.set_yticklabels(short_names, fontsize=8)
        ax2.invert_yaxis()
        ax2.set_xlabel("RMSE after permutation")
        ax2.set_title("Importance (RMSE increase)")
        for bar, val in zip(bars2, rmse_noise):
            ax2.text(bar.get_width() + 0.001, bar.get_y() + bar.get_height() / 2,
                     f"{val:.3f}", va="center", fontsize=7)

        plt.tight_layout()
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            fig.savefig(tmp.name, dpi=120, bbox_inches="tight")
            plt.close(fig)
            return tmp.name
    except Exception as e:
        plt.close("all")
        return None


def render_text(text: str, title: str = "") -> cl.Text:
    """Render plain text."""
    return cl.Text(content=text, name=title)
