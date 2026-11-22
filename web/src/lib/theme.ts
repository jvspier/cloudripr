/** Light/dark per device, stored in this browser only.
 * index.html applies the stored choice before first paint with the same rules. */

export type ThemePref = "auto" | "light" | "dark";

const KEY = "cloudripr.theme";
const DARK = "(prefers-color-scheme: dark)";

export function getThemePref(): ThemePref {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : "auto";
  } catch {
    return "auto";
  }
}

let unfollow: (() => void) | null = null;

/** Sets data-theme on <html>; "auto" keeps following the device setting. */
export function applyTheme(pref: ThemePref): void {
  unfollow?.();
  unfollow = null;
  const root = document.documentElement;
  if (pref !== "auto") {
    root.dataset.theme = pref;
    return;
  }
  if (typeof window.matchMedia !== "function") {
    root.dataset.theme = "light";
    return;
  }
  const media = window.matchMedia(DARK);
  const update = () => {
    root.dataset.theme = media.matches ? "dark" : "light";
  };
  update();
  media.addEventListener("change", update);
  unfollow = () => media.removeEventListener("change", update);
}

export function setThemePref(pref: ThemePref): void {
  try {
    if (pref === "auto") localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, pref);
  } catch {
    // Private mode or blocked storage: still applies for this visit.
  }
  applyTheme(pref);
}
