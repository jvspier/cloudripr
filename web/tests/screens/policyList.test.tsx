import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { PolicyList } from "@/screens/settings/PolicyList";
import { pol } from "../fixtures";
import { server } from "../msw";
import { renderWith } from "../render";

test("lists policies and reports import results", async () => {
  let sent = "";
  server.use(
    http.get("/api/policies", () => HttpResponse.json([pol()])),
    http.post("/api/policies/import", async ({ request }) => {
      sent = await request.text();
      return HttpResponse.json({
        created: ["family"],
        errors: [{ name: "icloud", error: "already exists" }],
      });
    })
  );
  renderWith(<PolicyList />);
  expect(await screen.findByRole("link", { name: /icloud/ })).toHaveAttribute(
    "href",
    "/settings/policies/icloud"
  );
  const toml = 'name = "family"\n';
  await userEvent.upload(screen.getByLabelText("Policy file"), new File([toml], "p.toml"));
  expect(await screen.findByText(/Imported: family/)).toBeInTheDocument();
  expect(screen.getByText("icloud: already exists")).toBeInTheDocument();
  expect(sent).toBe(toml);
});
