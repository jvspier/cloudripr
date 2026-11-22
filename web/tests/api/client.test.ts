import { http, HttpResponse } from "msw";
import { api, ApiError, onUnauthorized } from "@/api/client";
import { server } from "../msw";

test("error body becomes ApiError with field and ref", async () => {
  server.use(
    http.put("/api/account", () =>
      HttpResponse.json(
        { error: "Enter your Apple ID first.", error_id: null, field: "apple_id" },
        { status: 422 }
      )
    )
  );
  await expect(api("/account", { method: "PUT", json: {} })).rejects.toMatchObject({
    status: 422,
    field: "apple_id",
    message: "Enter your Apple ID first.",
  });
});

test("error_id is appended as a reference", async () => {
  server.use(
    http.get("/api/policies", () =>
      HttpResponse.json({ error: "Boom", error_id: "e42", field: null }, { status: 500 })
    )
  );
  await expect(api("/policies")).rejects.toMatchObject({
    message: "Boom (ref e42)",
    errorId: "e42",
  });
});

test("401 calls the unauthorized handler", async () => {
  const fn = vi.fn();
  onUnauthorized(fn);
  server.use(
    http.get("/api/policies", () =>
      HttpResponse.json(
        { error: "Not authenticated", error_id: null, field: null },
        { status: 401 }
      )
    )
  );
  await expect(api("/policies")).rejects.toBeInstanceOf(ApiError);
  expect(fn).toHaveBeenCalledOnce();
  onUnauthorized(null);
});

test("sends JSON bodies and parses JSON", async () => {
  server.use(
    http.post("/api/account/reauth/code", async ({ request }) =>
      HttpResponse.json({ echoed: await request.json() })
    )
  );
  await expect(
    api("/account/reauth/code", { method: "POST", json: { code: "123456" } })
  ).resolves.toEqual({ echoed: { code: "123456" } });
});
