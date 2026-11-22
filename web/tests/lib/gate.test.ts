import { folderBreakdown } from "@/lib/gate";

test("breakdown groups by folder relative to root", () => {
  expect(
    folderBreakdown(
      ["/downloads/2024/05/a.jpg", "/downloads/2024/05/b.jpg", "/downloads/2023/01/c.jpg"],
      "/downloads"
    )
  ).toEqual([
    { folder: "2024/05", count: 2 },
    { folder: "2023/01", count: 1 },
  ]);
});

test("root given with a trailing slash and files directly in root", () => {
  expect(folderBreakdown(["/downloads/a.jpg", "/downloads/2024/b.jpg"], "/downloads/")).toEqual([
    { folder: "(top folder)", count: 1 },
    { folder: "2024", count: 1 },
  ]);
});

test("ties sort by name", () => {
  expect(folderBreakdown(["/d/b/x.jpg", "/d/a/y.jpg"], "/d").map((r) => r.folder)).toEqual([
    "a",
    "b",
  ]);
});

test("more than 12 folders collapse into Other folders", () => {
  const paths = Array.from({ length: 14 }, (_, i) => `/d/f${String(i).padStart(2, "0")}/x.jpg`);
  paths.push("/d/f00/y.jpg");
  const rows = folderBreakdown(paths, "/d");
  expect(rows).toHaveLength(13);
  expect(rows[0]).toEqual({ folder: "f00", count: 2 });
  expect(rows[12]).toEqual({ folder: "Other folders", count: 2 });
});
