const NIGHTLY = /^(\d{1,2}) (\d{1,2}) \* \* \*$/;

/** "M H * * *" → "HH:MM"; any other cron → null (edited as raw cron). */
export function nightlyFromCron(cron: string): string | null {
  const m = NIGHTLY.exec(cron.trim());
  if (!m) return null;
  const [min, hour] = [Number(m[1]), Number(m[2])];
  if (min > 59 || hour > 23) return null;
  return `${String(hour).padStart(2, "0")}:${String(min).padStart(2, "0")}`;
}

export function cronFromNightly(hhmm: string): string {
  const [hour, min] = hhmm.split(":").map(Number);
  return `${min} ${hour} * * *`;
}
