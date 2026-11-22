import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { installFakeEventSource } from "./fakeEventSource";
import { server } from "./msw";

beforeAll(() => server.listen({ onUnhandledFrame: "error" }));
beforeEach(() => installFakeEventSource());
afterEach(() => {
  vi.unstubAllGlobals();
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());
