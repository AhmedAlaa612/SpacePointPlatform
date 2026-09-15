/** Mission photo gallery — images the rig's camera captured, uploaded by the
 * on-site agent straight to R2 (`routers/ground_station/ingest.py::ingest_photo`).
 * No DB table: listed by prefix at request time (`storage.list_files`). */
import { useState } from "react";
import type { GroundStationPhoto } from "@/api/groundStation";

interface Props {
  photos: GroundStationPhoto[];
}

export default function MissionGallery({ photos }: Props) {
  const [lightbox, setLightbox] = useState<GroundStationPhoto | null>(null);

  if (photos.length === 0) {
    return (
      <div className="rounded-xl ring-1 ring-border p-6 text-center text-xs text-muted-foreground bg-card">
        No mission images archived yet.
      </div>
    );
  }

  return (
    <div className="rounded-xl ring-1 ring-border p-4 bg-card">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-3">
        Mission gallery
      </div>
      <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">
        {photos.map((p) => (
          <button
            key={p.path}
            type="button"
            onClick={() => setLightbox(p)}
            className="aspect-square rounded-lg overflow-hidden ring-1 ring-border"
          >
            <img src={p.url} alt="" className="w-full h-full object-cover" />
          </button>
        ))}
      </div>
      {lightbox && (
        <div
          className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-6"
          onClick={() => setLightbox(null)}
        >
          <img src={lightbox.url} alt="" className="max-w-full max-h-full rounded-lg" />
        </div>
      )}
    </div>
  );
}
