export const str = (v: unknown): string => (typeof v === "string" ? v : "");
export const bool = (v: unknown): boolean => v === true;
