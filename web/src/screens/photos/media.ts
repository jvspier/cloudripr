import type { LibraryItem } from "@/api/types";

export const thumbUrl = (id: number) => `/api/library/items/${id}/thumb`;
export const previewUrl = (id: number) => `/api/library/items/${id}/preview`;
export const originalUrl = (id: number) => `/api/library/items/${id}/original`;

export const isVideo = (item: LibraryItem) => item.kind === "video" || item.kind === "live_video";

/** "1:14" for 74 seconds. */
export function clock(seconds: number): string {
  const s = Math.round(seconds);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** "2.4 MB" (decimal units, like Finder and Files). */
export function fileSize(bytes: number): string {
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(1)} GB`;
  if (bytes >= 1e6) return `${(bytes / 1e6).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1e3))} kB`;
}

/** "November 2026" for "2026-11". */
export function monthLabel(ym: string): string {
  const [y, m] = ym.split("-").map(Number);
  return new Intl.DateTimeFormat("en-GB", { month: "long", year: "numeric" }).format(
    new Date(y, m - 1, 1)
  );
}

export const count = (n: number) => n.toLocaleString("en-US");
