import os
import tempfile
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
from osgeo import gdal
import folium
from folium.raster_layers import ImageOverlay
import chainlit as cl

LULC_COLORS = ['#000000', '#FF0000', '#00FF00', '#0000FF', '#FFFF00',
               '#FF00FF', '#00FFFF', '#808080', '#FFA500', '#A52A2A']


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
    bounds = list(unique) + [unique[-1] + 1]
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


def render_csv(csv_path: str):  # -> cl.Text
    """Render CSV as formatted text table."""
    if not os.path.exists(csv_path):
        return cl.Text(content=f"[File not found: {os.path.basename(csv_path)}]")
    import pandas as pd
    df = pd.read_csv(csv_path)
    return cl.Text(content=f"```\n{df.to_string()}\n```", language="text")


def render_text(text: str, title: str = "") -> cl.Text:
    """Render plain text."""
    return cl.Text(content=text, name=title)
