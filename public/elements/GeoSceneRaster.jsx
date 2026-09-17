import { useEffect, useRef, useState } from "react";

const GEOSCENE_CSS = "https://js.geoscene.cn/4.32/geoscene/themes/light/main.css";
const GEOSCENE_JS = "https://js.geoscene.cn/4.32/";

let geosceneLoader;

function loadGeoScene() {
  if (window.require) {
    return Promise.resolve(window.require);
  }

  if (!document.querySelector(`link[href="${GEOSCENE_CSS}"]`)) {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = GEOSCENE_CSS;
    document.head.appendChild(link);
  }

  if (!geosceneLoader) {
    geosceneLoader = new Promise((resolve, reject) => {
      const existing = document.querySelector(`script[src="${GEOSCENE_JS}"]`);
      if (existing) {
        existing.addEventListener("load", () => resolve(window.require), { once: true });
        existing.addEventListener("error", reject, { once: true });
        return;
      }

      const script = document.createElement("script");
      script.src = GEOSCENE_JS;
      script.async = true;
      script.onload = () => resolve(window.require);
      script.onerror = () => reject(new Error("GeoScene SDK failed to load"));
      document.body.appendChild(script);
    });
  }

  return geosceneLoader;
}

function requireModules(requireFn, modules) {
  return new Promise((resolve, reject) => {
    try {
      requireFn(modules, (...loaded) => resolve(loaded), reject);
    } catch (error) {
      reject(error);
    }
  });
}

export default function GeoSceneRaster() {
  const containerRef = useRef(null);
  const viewRef = useRef(null);
  const layerRef = useRef(null);
  const [error, setError] = useState("");
  const [opacity, setOpacity] = useState(props.opacity ?? 0.72);

  useEffect(() => {
    let cancelled = false;

    async function createMap() {
      setError("");

      if (!props.imageUrl || !props.bounds) {
        setError("Raster preview is missing image metadata.");
        return;
      }

      try {
        const requireFn = await loadGeoScene();
        const [
          GeoSceneMap,
          MapView,
          MediaLayer,
          ImageElement,
          ExtentAndRotationGeoreference,
          Extent,
          Expand,
          LayerList,
        ] = await requireModules(requireFn, [
          "geoscene/Map",
          "geoscene/views/MapView",
          "geoscene/layers/MediaLayer",
          "geoscene/layers/support/ImageElement",
          "geoscene/layers/support/ExtentAndRotationGeoreference",
          "geoscene/geometry/Extent",
          "geoscene/widgets/Expand",
          "geoscene/widgets/LayerList",
        ]);

        if (cancelled || !containerRef.current) return;

        const extent = new Extent({
          xmin: props.bounds.xmin,
          ymin: props.bounds.ymin,
          xmax: props.bounds.xmax,
          ymax: props.bounds.ymax,
          spatialReference: { wkid: props.bounds.wkid || 4326 },
        });

        const imageElement = new ImageElement({
          image: props.imageUrl,
          georeference: new ExtentAndRotationGeoreference({ extent }),
        });

        const rasterLayer = new MediaLayer({
          title: props.title || props.sourceName || "Raster",
          source: [imageElement],
          opacity,
        });

        const map = new GeoSceneMap({
          basemap: "osm",
          layers: [rasterLayer],
        });

        const view = new MapView({
          container: containerRef.current,
          map,
          extent,
          constraints: { snapToZoom: false },
          popup: { dockEnabled: true },
        });

        layerRef.current = rasterLayer;
        viewRef.current = view;

        view.when(() => {
          if (cancelled) return;
          view.goTo(extent.expand(1.08)).catch(() => {});
          const layerList = new LayerList({ view });
          view.ui.add(new Expand({ view, content: layerList, expanded: false }), "top-right");
        });
      } catch (err) {
        if (!cancelled) {
          setError(err?.message || String(err));
        }
      }
    }

    createMap();

    return () => {
      cancelled = true;
      if (viewRef.current) {
        viewRef.current.destroy();
        viewRef.current = null;
      }
      layerRef.current = null;
    };
  }, [props.imageUrl, props.bounds?.xmin, props.bounds?.ymin, props.bounds?.xmax, props.bounds?.ymax]);

  useEffect(() => {
    if (layerRef.current) {
      layerRef.current.opacity = opacity;
    }
  }, [opacity]);

  const stats = props.stats || {};
  const sizeText = Array.isArray(props.rasterSize) ? `${props.rasterSize[0]} x ${props.rasterSize[1]}` : "";

  return (
    <div className="plus-geoscene">
      <div className="plus-geoscene__bar">
        <div className="plus-geoscene__title">{props.title || props.sourceName || "Raster"}</div>
        <label className="plus-geoscene__opacity">
          <span>{Math.round(opacity * 100)}%</span>
          <input
            type="range"
            min="0"
            max="1"
            step="0.05"
            value={opacity}
            onChange={(event) => setOpacity(Number(event.target.value))}
            aria-label="Raster opacity"
          />
        </label>
      </div>

      <div className="plus-geoscene__map" ref={containerRef}>
        {error ? (
          <div className="plus-geoscene__fallback">
            <img src={props.imageUrl} alt={props.title || "Raster preview"} />
            <div className="plus-geoscene__error">GeoScene map unavailable: {error}</div>
          </div>
        ) : null}
      </div>

      <div className="plus-geoscene__meta">
        <span>{props.renderer === "categorical" ? `${stats.classCount ?? "-"} classes` : `${stats.min?.toPrecision?.(4) ?? "-"} - ${stats.max?.toPrecision?.(4) ?? "-"}`}</span>
        <span>{sizeText}</span>
      </div>

      {Array.isArray(props.legend) && props.legend.length ? (
        <div className="plus-geoscene__legend">
          {props.legend.slice(0, 12).map((item, index) => (
            <div className="plus-geoscene__legend-item" key={`${item.label}-${index}`}>
              <span className="plus-geoscene__swatch" style={{ background: item.color }} />
              <span>{item.label}</span>
            </div>
          ))}
        </div>
      ) : null}

      <style>{`
        .plus-geoscene {
          border: 1px solid rgba(31, 41, 55, 0.16);
          border-radius: 8px;
          overflow: hidden;
          background: #ffffff;
          color: #111827;
          font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        }
        .plus-geoscene__bar {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          min-height: 44px;
          padding: 8px 10px;
          border-bottom: 1px solid rgba(31, 41, 55, 0.12);
          background: #f8fafc;
        }
        .plus-geoscene__title {
          min-width: 0;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          font-size: 14px;
          font-weight: 650;
        }
        .plus-geoscene__opacity {
          display: flex;
          align-items: center;
          gap: 8px;
          flex: 0 0 132px;
          font-size: 12px;
          color: #475569;
        }
        .plus-geoscene__opacity input {
          width: 82px;
        }
        .plus-geoscene__map {
          position: relative;
          width: 100%;
          height: min(62vh, 620px);
          min-height: 430px;
          background: #e5e7eb;
        }
        .plus-geoscene__fallback {
          position: absolute;
          inset: 0;
          display: grid;
          place-items: center;
          padding: 12px;
          background: #f1f5f9;
          z-index: 2;
        }
        .plus-geoscene__fallback img {
          max-width: 100%;
          max-height: calc(100% - 34px);
          object-fit: contain;
          image-rendering: pixelated;
        }
        .plus-geoscene__error {
          align-self: end;
          color: #9f1239;
          font-size: 12px;
          line-height: 1.4;
          text-align: center;
        }
        .plus-geoscene__meta {
          display: flex;
          justify-content: space-between;
          gap: 12px;
          padding: 8px 10px;
          border-top: 1px solid rgba(31, 41, 55, 0.12);
          font-size: 12px;
          color: #475569;
        }
        .plus-geoscene__legend {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(104px, 1fr));
          gap: 6px 10px;
          padding: 0 10px 10px;
          font-size: 12px;
          color: #334155;
        }
        .plus-geoscene__legend-item {
          display: flex;
          align-items: center;
          min-width: 0;
          gap: 6px;
        }
        .plus-geoscene__swatch {
          width: 12px;
          height: 12px;
          border-radius: 3px;
          border: 1px solid rgba(15, 23, 42, 0.18);
          flex: 0 0 auto;
        }
      `}</style>
    </div>
  );
}
