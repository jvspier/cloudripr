import { cronFromNightly, nightlyFromCron } from "@/lib/schedule";

test.each([
  ["0 3 * * *", "03:00"],
  ["30 23 * * *", "23:30"],
  ["5 7 * * *", "07:05"],
  ["0 3 * * 1", null],
  ["*/5 * * * *", null],
  ["0 3,15 * * *", null],
  ["0 24 * * *", null],
  ["garbage", null],
])("nightlyFromCron(%s) = %s", (cron, expected) => {
  expect(nightlyFromCron(cron)).toBe(expected);
});

test("cronFromNightly round-trips", () => {
  expect(cronFromNightly("03:00")).toBe("0 3 * * *");
  expect(cronFromNightly("23:30")).toBe("30 23 * * *");
  expect(nightlyFromCron(cronFromNightly("07:05"))).toBe("07:05");
});
