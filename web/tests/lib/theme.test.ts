import { applyTheme, getThemePref, setThemePref } from "@/lib/theme";

function mockSystemDark(dark: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockReturnValue({
      matches: dark,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })
  );
}

afterEach(() => {
  localStorage.clear();
  delete document.documentElement.dataset.theme;
});

test("defaults to automatic", () => {
  expect(getThemePref()).toBe("auto");
});

test("automatic follows the device", () => {
  mockSystemDark(true);
  applyTheme("auto");
  expect(document.documentElement.dataset.theme).toBe("dark");
  mockSystemDark(false);
  applyTheme("auto");
  expect(document.documentElement.dataset.theme).toBe("light");
});

test("a chosen theme is stored and applied", () => {
  mockSystemDark(true);
  setThemePref("light");
  expect(getThemePref()).toBe("light");
  expect(document.documentElement.dataset.theme).toBe("light");
});

test("unreadable storage falls back to automatic", () => {
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new Error("blocked");
  });
  expect(getThemePref()).toBe("auto");
});

test("an unknown stored value falls back to automatic", () => {
  localStorage.setItem("cloudripr.theme", "purple");
  expect(getThemePref()).toBe("auto");
});
