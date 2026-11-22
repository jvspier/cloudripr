import { fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { pol } from "../fixtures";
import { server } from "../msw";
import { renderAt } from "../render";

function serve(policy = pol()) {
  server.use(http.get("/api/policies/icloud", () => HttpResponse.json(policy)));
}

test("locked policy disables naming inputs", async () => {
  serve();
  renderAt("/settings/policies/icloud");
  const naming = await screen.findByRole("region", { name: "File naming" });
  expect(within(naming).getByLabelText("Folder structure")).toBeDisabled();
  expect(within(naming).getByLabelText("Download folder")).toBeDisabled();
  expect(within(naming).getByText("Locked to protect your existing downloads")).toBeInTheDocument();
});

test("unlock needs the exact name", async () => {
  let locked = true;
  let confirm: unknown = null;
  server.use(
    http.get("/api/policies/icloud", () => HttpResponse.json(pol({ naming_locked: locked }))),
    http.post("/api/policies/icloud/unlock", async ({ request }) => {
      confirm = await request.json();
      locked = false;
      return HttpResponse.json(pol({ naming_locked: false }));
    })
  );
  renderAt("/settings/policies/icloud");
  await userEvent.click(await screen.findByRole("button", { name: "Unlock" }));
  const dialog = await screen.findByRole("dialog");
  const go = within(dialog).getByRole("button", { name: "Unlock naming" });
  await userEvent.type(within(dialog).getByLabelText("Type icloud to confirm"), "iclou");
  expect(go).toBeDisabled();
  await userEvent.type(within(dialog).getByLabelText("Type icloud to confirm"), "d");
  await userEvent.click(go);
  expect(confirm).toEqual({ confirm: "icloud" });
  expect(await screen.findByLabelText("Folder structure")).toBeEnabled();
});

test("changing naming after unlock warns about the safety check", async () => {
  serve(pol({ naming_locked: false }));
  renderAt("/settings/policies/icloud");
  const input = await screen.findByLabelText("Folder structure");
  await userEvent.clear(input);
  await userEvent.type(input, "{{:%Y}");
  expect(screen.getByText(/Saving will run a safety check/)).toBeInTheDocument();
});

test("save sends the full body to PUT /api/policies/icloud", async () => {
  serve();
  let body: Record<string, unknown> | null = null;
  server.use(
    http.put("/api/policies/icloud", async ({ request }) => {
      body = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json(pol({ cron: "30 4 * * *" }));
    })
  );
  renderAt("/settings/policies/icloud");
  // jsdom's time input doesn't take typed keystrokes; set the value like the iOS picker does
  fireEvent.change(await screen.findByLabelText("Every night at"), { target: { value: "04:30" } });
  await userEvent.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByText("Saved")).toBeInTheDocument();
  expect(body).not.toBeNull();
  expect(body!.cron).toBe("30 4 * * *");
  expect(body!.icloudpd).toEqual(pol().icloudpd);
  expect(body!.filters).toEqual(pol().filters);
  expect(body).not.toHaveProperty("naming_locked");
  expect(body).not.toHaveProperty("last_run");
});

test("save error on a field shows next to that field", async () => {
  serve(pol({ cron: "*/5 * * * *" }));
  server.use(
    http.put("/api/policies/icloud", () =>
      HttpResponse.json({ error: "invalid cron", error_id: null, field: "cron" }, { status: 422 })
    )
  );
  renderAt("/settings/policies/icloud");
  // non-nightly cron opens Advanced with the raw cron field
  expect(await screen.findByLabelText("Cron")).toHaveValue("*/5 * * * *");
  await userEvent.click(screen.getByRole("button", { name: "Save" }));
  const cron = screen.getByLabelText("Cron");
  expect(await screen.findByText("invalid cron")).toBeInTheDocument();
  expect(cron).toHaveAttribute("aria-invalid", "true");
});

test("filters are edited one per line", async () => {
  serve();
  let body: { filters: { file_suffixes: string[] } } | null = null;
  server.use(
    http.put("/api/policies/icloud", async ({ request }) => {
      body = (await request.json()) as typeof body;
      return HttpResponse.json(pol());
    })
  );
  renderAt("/settings/policies/icloud");
  await userEvent.type(await screen.findByLabelText("File types to remove"), ".png{enter}.gif");
  await userEvent.click(screen.getByRole("button", { name: "Save" }));
  await screen.findByText("Saved");
  expect(body!.filters.file_suffixes).toEqual([".png", ".gif"]);
});

test("new policy starts from safe defaults", async () => {
  let body: Record<string, unknown> | null = null;
  server.use(
    http.put("/api/policies/family", async ({ request }) => {
      body = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json(pol({ name: "family" }));
    }),
    http.get("/api/policies/family", () => HttpResponse.json(pol({ name: "family" })))
  );
  renderAt("/settings/policies/new");
  await userEvent.type(await screen.findByLabelText("Name"), "family");
  await userEvent.click(screen.getByRole("button", { name: "Save" }));
  await screen.findByText("Saved");
  expect(body).toMatchObject({
    name: "family",
    directory: "/downloads/family",
    cron: "0 3 * * *",
    enabled: true,
    library_kind: "personal",
    icloudpd: {
      folder_structure: "{:%Y/%m}",
      size: ["original"],
      live_photo_size: "original",
      live_photo_mov_filename_policy: "suffix",
      file_match_policy: "name-size-dedup-with-suffix",
      align_raw: "original",
    },
  });
});

test("delete asks first and reports a conflict", async () => {
  serve();
  server.use(
    http.delete("/api/policies/icloud", () =>
      HttpResponse.json(
        { error: "Stop the running backup first.", error_id: null, field: null },
        { status: 409 }
      )
    )
  );
  renderAt("/settings/policies/icloud");
  await userEvent.click(await screen.findByRole("button", { name: "Delete policy" }));
  const dialog = await screen.findByRole("dialog");
  await userEvent.click(within(dialog).getByRole("button", { name: "Delete" }));
  expect(await within(dialog).findByText("Stop the running backup first.")).toBeInTheDocument();
});

test.each([
  [
    "naming",
    "File naming settings are locked to protect your existing downloads. Unlock them first.",
    409,
  ],
  ["icloudpd", "unknown icloudpd option", 422],
])(
  "a save error on field %s that has no input still shows its message",
  async (field, message, status) => {
    serve();
    server.use(
      http.put("/api/policies/icloud", () =>
        HttpResponse.json({ error: message, error_id: null, field }, { status })
      )
    );
    renderAt("/settings/policies/icloud");
    await userEvent.click(await screen.findByRole("button", { name: "Save" }));
    expect(await screen.findByText(`Couldn't save: ${message}`)).toBeInTheDocument();
  }
);
