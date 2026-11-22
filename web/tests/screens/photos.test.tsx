import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { LibraryItem } from "@/api/types";
import { pol, run } from "../fixtures";
import { server } from "../msw";
import { renderAt } from "../render";

const item = (over: Partial<LibraryItem> = {}): LibraryItem => ({
  id: 1,
  name: "IMG_8761.HEIC",
  folder: "2026/11",
  kind: "photo",
  size: 2_400_000,
  taken_at: "2026-11-21T18:02:00+00:00",
  duration: null,
  problem: null,
  run_id: null,
  ...over,
});

const night = run({
  id: "r9",
  status: "success",
  downloaded: 23,
  ended_at: "2026-11-22T03:12:00Z",
});

beforeEach(() => {
  server.use(
    http.get("/api/library/summary", () =>
      HttpResponse.json({
        on_disk: 75982,
        unreadable: 2,
        scanned_at: "2026-11-22T03:12:00+00:00",
        icloud: { count: 75993, seen_at: "2026-11-22T03:00:00+00:00" },
      })
    ),
    http.get("/api/library/runs", () =>
      HttpResponse.json([
        {
          run: night,
          count: 23,
          unreadable: 1,
          sample: [item({ id: 1, run_id: "r9" }), item({ id: 2, run_id: "r9" })],
        },
      ])
    ),
    http.get("/api/library/months", () =>
      HttpResponse.json([
        { month: "2026-11", count: 556, unreadable: 2 },
        { month: "2026-10", count: 612, unreadable: 0 },
      ])
    ),
    http.get("/api/library/items", ({ request }) => {
      const url = new URL(request.url);
      if (url.searchParams.get("month") === "2026-11" || url.searchParams.get("run") === "r9") {
        return HttpResponse.json([
          item({ id: 1, run_id: url.searchParams.get("run") }),
          item({ id: 2, name: "BAD.HEIC", problem: "Can't be read: the file is empty" }),
          item({ id: 3, name: "CLIP.MOV", kind: "video", duration: 74 }),
        ]);
      }
      return HttpResponse.json([]);
    })
  );
});

test("photos shows totals, recent runs and months", async () => {
  renderAt("/photos");
  expect(await screen.findByText(/75,982/)).toBeInTheDocument();
  expect(screen.getByText(/75,993/)).toBeInTheDocument();
  const runs = await screen.findByRole("region", { name: "Recent runs" });
  expect(within(runs).getByText("23 new")).toBeInTheDocument();
  expect(within(runs).getByText("⚠ 1")).toBeInTheDocument();
  expect(within(runs).getByRole("link", { name: /View/ })).toHaveAttribute(
    "href",
    "/runs/r9/photos"
  );
  const months = screen.getByRole("region", { name: "Library" });
  expect(within(months).getByRole("link", { name: /November 2026/ })).toHaveAttribute(
    "href",
    "/photos/month/2026-11"
  );
  expect(within(months).getByText("612")).toBeInTheDocument();
});

test("a month opens its grid and marks unreadable files", async () => {
  renderAt("/photos/month/2026-11");
  expect(await screen.findByRole("heading", { name: "November 2026" })).toBeInTheDocument();
  expect(
    await screen.findByRole("button", { name: /BAD\.HEIC.*can't be read/i })
  ).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /CLIP\.MOV/ })).toHaveTextContent("1:14");
});

test("tapping a photo opens the viewer with its info", async () => {
  renderAt("/photos/month/2026-11");
  await userEvent.click(await screen.findByRole("button", { name: /IMG_8761\.HEIC/ }));
  const viewer = await screen.findByRole("dialog");
  expect(within(viewer).getByRole("img")).toHaveAttribute("src", "/api/library/items/1/preview");
  expect(within(viewer).getByText("2026/11")).toBeInTheDocument();
  expect(within(viewer).getByText("2.4 MB")).toBeInTheDocument();
});

test("a video opens with a player", async () => {
  renderAt("/photos/month/2026-11");
  await userEvent.click(await screen.findByRole("button", { name: /CLIP\.MOV/ }));
  const viewer = await screen.findByRole("dialog");
  const video = viewer.querySelector("video");
  expect(video).not.toBeNull();
  expect(video).toHaveAttribute("src", "/api/library/items/3/original");
});

test("run photos list the run's files and link back to the run", async () => {
  renderAt("/runs/r9/photos");
  expect(await screen.findByRole("button", { name: /IMG_8761\.HEIC/ })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Back" })).toHaveAttribute("href", "/runs/r9");
});

test("run photos are reachable from the latest backup card", async () => {
  server.use(http.get("/api/policies", () => HttpResponse.json([pol({ last_run: night })])));
  renderAt("/");
  await waitFor(() =>
    expect(
      screen.getAllByRole("link", { name: "Photos" }).map((l) => l.getAttribute("href"))
    ).toContain("/runs/r9/photos")
  );
});

test("an unreadable file opens to an explanation instead of a broken image", async () => {
  renderAt("/photos/month/2026-11");
  await userEvent.click(await screen.findByRole("button", { name: /BAD\.HEIC/ }));
  const viewer = await screen.findByRole("dialog");
  expect(within(viewer).queryByRole("img")).toBeNull();
  expect(within(viewer).getAllByText("Can't be read: the file is empty").length).toBeGreaterThan(0);
});
