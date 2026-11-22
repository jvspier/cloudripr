const MAX_ROWS = 12;

/** Per-folder counts of the gate's sample paths, relative to the policy directory. */
export function folderBreakdown(
  sample: string[],
  root: string
): { folder: string; count: number }[] {
  const prefix = root.endsWith("/") ? root : `${root}/`;
  const counts = new Map<string, number>();
  for (const path of sample) {
    const rel = path.startsWith(prefix) ? path.slice(prefix.length) : path;
    const cut = rel.lastIndexOf("/");
    const folder = cut === -1 ? "(top folder)" : rel.slice(0, cut);
    counts.set(folder, (counts.get(folder) ?? 0) + 1);
  }
  const rows = [...counts]
    .map(([folder, count]) => ({ folder, count }))
    .sort((a, b) => b.count - a.count || a.folder.localeCompare(b.folder));
  if (rows.length <= MAX_ROWS + 1) return rows;
  const rest = rows.slice(MAX_ROWS).reduce((n, r) => n + r.count, 0);
  return [...rows.slice(0, MAX_ROWS), { folder: "Other folders", count: rest }];
}
