/** 2D tactical map — ported from the legacy app's `map.js` (Leaflet, dark
 * CARTO basemap, pulsing marker + breadcrumb trail). */
import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

const MAX_PATH_POINTS = 1000;

interface Props {
  lat: number | null;
  lon: number | null;
  height?: number;
}

export default function TacticalMap({ lat, lon, height = 260 }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const markerRef = useRef<L.Marker | null>(null);
  const pathLineRef = useRef<L.Polyline | null>(null);
  const historyRef = useRef<[number, number][]>([]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const map = L.map(container, { zoomControl: true, attributionControl: true }).setView([0, 0], 2);
    mapRef.current = map;

    L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
      attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
      subdomains: "abcd",
      maxZoom: 20,
    }).addTo(map);

    const satIcon = L.divIcon({
      className: "gs-sat-icon",
      html: `<div style="width:14px;height:14px;background:#00d2ff;border:2px solid #fff;border-radius:50%;box-shadow:0 0 15px #00d2ff;"></div>`,
      iconSize: [14, 14],
      iconAnchor: [7, 7],
    });
    markerRef.current = L.marker([0, 0], { icon: satIcon }).addTo(map);
    pathLineRef.current = L.polyline([], { color: "#00d2ff", weight: 2, opacity: 0.6, dashArray: "5, 8" }).addTo(map);

    const onResize = () => setTimeout(() => map.invalidateSize(), 300);
    window.addEventListener("resize", onResize);

    return () => {
      window.removeEventListener("resize", onResize);
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current, marker = markerRef.current, pathLine = pathLineRef.current;
    if (!map || !marker || !pathLine || lat == null || lon == null || Number.isNaN(lat) || Number.isNaN(lon)) return;

    const newPos: [number, number] = [lat, lon];
    marker.setLatLng(newPos);

    const history = historyRef.current;
    history.push(newPos);
    if (history.length > MAX_PATH_POINTS) history.shift();
    pathLine.setLatLngs(history);

    const center = map.getCenter();
    const dist = map.distance(center, L.latLng(lat, lon));
    if (dist > 1_000_000) map.panTo(newPos, { animate: true, duration: 1.0 });
  }, [lat, lon]);

  return (
    <div className="rounded-xl ring-1 ring-border overflow-hidden bg-card">
      <div className="px-4 pt-3 pb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        Ground Track
      </div>
      <div ref={containerRef} style={{ height }} />
    </div>
  );
}
