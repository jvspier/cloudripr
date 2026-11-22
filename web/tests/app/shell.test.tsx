import { screen, within } from "@testing-library/react";
import { renderAt } from "../render";

test("bottom bar shows three tabs and marks the active one", async () => {
  renderAt("/settings");
  const nav = await screen.findByRole("navigation", { name: "Main" });
  expect(
    within(nav)
      .getAllByRole("link")
      .map((a) => a.textContent)
  ).toEqual(["Home", "Photos", "Settings"]);
  expect(within(nav).getByRole("link", { name: "Settings" })).toHaveAttribute(
    "aria-current",
    "page"
  );
});
