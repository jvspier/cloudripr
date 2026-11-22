import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { pol, run } from "../fixtures";
import { server } from "../msw";
import { renderAt } from "../render";

const blocked = {
  ...run({
    id: "r1",
    status: "gate_blocked",
    dry_run: true,
    would_download: 412,
    reason:
      "Safety check: 412 files would be downloaded (limit 100). Review them before downloading.",
  }),
  file_count: 0,
  gate_review: {
    run_id: "r1",
    count: 412,
    sample: ["/downloads/2024/05/a.jpg", "/downloads/2024/05/b.jpg"],
  },
};

beforeEach(() => {
  server.use(
    http.get("/api/policies/icloud", () => HttpResponse.json(pol({ gate: "blocked" }))),
    http.get("/api/settings", () => HttpResponse.json({ gate_threshold: 100 }))
  );
});

test("gate review shows count, breakdown and sample", async () => {
  server.use(http.get("/api/runs/r1", () => HttpResponse.json(blocked)));
  renderAt("/runs/r1");
  expect(await screen.findByText("412 files would be downloaded")).toBeInTheDocument();
  expect(screen.getByText("2024/05")).toBeInTheDocument();
  expect(screen.getByText("/downloads/2024/05/a.jpg")).toBeInTheDocument();
  expect(screen.getByText(/From a sample of 2/)).toBeInTheDocument();
});

test("an early-stopped check says at least, and approving downloads all new files", async () => {
  const partial = {
    ...blocked,
    gate_review: { ...blocked.gate_review, count: 1001, partial: true },
  };
  server.use(http.get("/api/runs/r1", () => HttpResponse.json(partial)));
  renderAt("/runs/r1");
  expect(await screen.findByText("At least 1001 files would be downloaded")).toBeInTheDocument();
  expect(screen.getByText(/stopped counting early/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Download them" }));
  expect(screen.getByText("Download all new files into /downloads?")).toBeInTheDocument();
});

test("approve asks for confirmation and opens the new run", async () => {
  let approved = false;
  server.use(
    http.get("/api/runs/r1", () => HttpResponse.json(blocked)),
    http.post("/api/runs/r1/approve", () => {
      approved = true;
      return HttpResponse.json(run({ id: "r2", status: "queued" }));
    }),
    http.get("/api/runs/r2", () =>
      HttpResponse.json({
        ...run({ id: "r2", status: "running", downloaded: 1 }),
        file_count: 0,
        gate_review: null,
      })
    )
  );
  renderAt("/runs/r1");
  await userEvent.click(await screen.findByRole("button", { name: "Download them" }));
  expect(approved).toBe(false);
  expect(screen.getByText("Download 412 files into /downloads?")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Yes, download" }));
  expect(approved).toBe(true);
  expect(await screen.findByText("1 new so far")).toBeInTheDocument();
});

test("keep blocked goes home without approving", async () => {
  server.use(http.get("/api/runs/r1", () => HttpResponse.json(blocked)));
  renderAt("/runs/r1");
  await userEvent.click(await screen.findByRole("button", { name: "Keep blocked" }));
  expect(await screen.findByRole("heading", { name: "Backups" })).toBeInTheDocument();
});

test("approve is not offered for runs without gate_review", async () => {
  server.use(
    http.get("/api/runs/r1", () =>
      HttpResponse.json({
        ...run({ status: "failed", reason: "No activity for 30 min" }),
        file_count: 0,
        gate_review: null,
      })
    )
  );
  renderAt("/runs/r1");
  expect(await screen.findByText("No activity for 30 min")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Download them" })).not.toBeInTheDocument();
});

test("running run can be stopped", async () => {
  let stopped = false;
  server.use(
    http.get("/api/runs/r1", () =>
      HttpResponse.json({
        ...run({ status: "running", ended_at: null, downloaded: 4 }),
        file_count: 0,
        gate_review: null,
      })
    ),
    http.post("/api/runs/r1/stop", () => {
      stopped = true;
      return HttpResponse.json({ ok: true });
    })
  );
  renderAt("/runs/r1");
  await userEvent.click(await screen.findByRole("button", { name: "Stop" }));
  expect(stopped).toBe(true);
});

test("log opens on request", async () => {
  server.use(
    http.get("/api/runs/r1", () =>
      HttpResponse.json({ ...run(), file_count: 12, gate_review: null })
    ),
    http.get("/api/runs/r1/log", () =>
      HttpResponse.text("INFO Downloaded /downloads/2024/05/a.jpg\n")
    )
  );
  renderAt("/runs/r1");
  await userEvent.click(await screen.findByRole("button", { name: "Show log" }));
  expect(await screen.findByText(/INFO Downloaded/)).toBeInTheDocument();
});

test("unknown run shows Run not found", async () => {
  server.use(
    http.get("/api/runs/zz", () =>
      HttpResponse.json({ error: "Run not found", error_id: null, field: null }, { status: 404 })
    )
  );
  renderAt("/runs/zz");
  expect(await screen.findByText("Run not found")).toBeInTheDocument();
});
