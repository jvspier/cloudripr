import { toPolicyBody } from "@/lib/policyBody";
import { pol } from "../fixtures";

const SUMMARY_KEYS = [
  "next_run_at",
  "last_run",
  "last_success",
  "active_run",
  "gate",
  "gate_review",
  "naming_locked",
];

test("unknown icloudpd keys survive", () => {
  const orig = pol({
    icloudpd: { use_os_locale: false, threads_num: 4, folder_structure: "{:%Y/%m}" },
  });
  const body = toPolicyBody(orig, { ...orig, enabled: false });
  expect(body.icloudpd).toEqual({
    use_os_locale: false,
    threads_num: 4,
    folder_structure: "{:%Y/%m}",
  });
  expect(body.enabled).toBe(false);
  for (const k of SUMMARY_KEYS) expect(body).not.toHaveProperty(k);
});

test("unknown top-level keys survive", () => {
  const orig = pol({ some_future_key: "x" } as never);
  expect(toPolicyBody(orig, { ...orig })).toHaveProperty("some_future_key", "x");
});

test("locked naming values are restored", () => {
  const orig = pol({ naming_locked: true });
  const body = toPolicyBody(orig, {
    ...orig,
    directory: "/x",
    library_kind: "personal",
    icloudpd: {
      ...orig.icloudpd,
      folder_structure: "{:%Y}",
      size: ["medium"],
      file_match_policy: "name-id7",
    },
  });
  expect(body.directory).toBe("/downloads");
  expect(body.library_kind).toBe("shared");
  expect(body.icloudpd.folder_structure).toBe("{:%Y/%m}");
  expect(body.icloudpd.size).toEqual(["original"]);
  expect(body.icloudpd.file_match_policy).toBe("name-size-dedup-with-suffix");
});

test("locked naming key absent in the original stays absent", () => {
  const orig = pol({ naming_locked: true, icloudpd: { folder_structure: "{:%Y/%m}" } });
  const body = toPolicyBody(orig, {
    ...orig,
    icloudpd: { folder_structure: "{:%Y/%m}", align_raw: "alternative" },
  });
  expect(body.icloudpd).not.toHaveProperty("align_raw");
});

test("unlocked naming changes go through", () => {
  const orig = pol({ naming_locked: false });
  const body = toPolicyBody(orig, {
    ...orig,
    icloudpd: { ...orig.icloudpd, folder_structure: "{:%Y}" },
  });
  expect(body.icloudpd.folder_structure).toBe("{:%Y}");
});

test("new policy (no original) passes through", () => {
  const draft = { ...pol(), naming_locked: undefined } as never;
  expect(toPolicyBody(null, draft).directory).toBe("/downloads");
});

test("does not mutate its inputs", () => {
  const orig = pol({ naming_locked: true });
  const draft = { ...orig, icloudpd: { ...orig.icloudpd, folder_structure: "{:%Y}" } };
  toPolicyBody(orig, draft);
  expect(draft.icloudpd.folder_structure).toBe("{:%Y}");
  expect(orig).toHaveProperty("naming_locked", true);
});
