import { useEffect, useRef, useState, type ClipboardEvent, type KeyboardEvent } from "react";

const LENGTH = 6;
const EMPTY = Array<string>(LENGTH).fill("");

/** Six one-digit boxes. Handles typing, paste and iOS one-time-code autofill. */
export function CodeInput({
  onComplete,
  disabled,
  resetKey,
}: {
  onComplete: (code: string) => void;
  disabled: boolean;
  resetKey: number;
}) {
  const [digits, setDigits] = useState<string[]>(EMPTY);
  const boxes = useRef<(HTMLInputElement | null)[]>([]);
  const sent = useRef<string | null>(null);

  const [prevKey, setPrevKey] = useState(resetKey);
  if (resetKey !== prevKey) {
    setPrevKey(resetKey);
    setDigits(EMPTY);
  }
  useEffect(() => {
    sent.current = null;
    boxes.current[0]?.focus();
  }, [resetKey]);

  useEffect(() => {
    const code = digits.join("");
    if (code.length < LENGTH) {
      sent.current = null;
    } else if (sent.current !== code) {
      sent.current = code;
      onComplete(code);
    }
  }, [digits, onComplete]);

  const fill = (start: number, chars: string) => {
    setDigits((old) => {
      const next = [...old];
      for (let k = 0; k < chars.length && start + k < LENGTH; k++) next[start + k] = chars[k];
      return next;
    });
    boxes.current[Math.min(start + chars.length, LENGTH - 1)]?.focus();
  };

  const change = (i: number, raw: string) => {
    const clean = raw.replace(/\D/g, "");
    if (clean.length >= LENGTH) return fill(0, clean.slice(0, LENGTH)); // autofill of the whole code
    if (clean.length === 0) {
      setDigits((old) => old.map((d, k) => (k === i ? "" : d)));
      return;
    }
    const prev = digits[i];
    let incoming = clean;
    if (prev && clean.length === prev.length + 1) {
      incoming = clean.startsWith(prev) ? clean.slice(prev.length) : clean.slice(0, 1);
    }
    fill(i, incoming);
  };

  const paste = (i: number, e: ClipboardEvent<HTMLInputElement>) => {
    e.preventDefault();
    const clean = e.clipboardData.getData("text").replace(/\D/g, "");
    if (clean) fill(clean.length >= LENGTH ? 0 : i, clean.slice(0, LENGTH));
  };

  const keyDown = (i: number, e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Backspace" && !digits[i] && i > 0) {
      e.preventDefault();
      boxes.current[i - 1]?.focus();
    }
  };

  return (
    <div className="flex justify-center gap-2" role="group" aria-label="Verification code">
      {digits.map((d, i) => (
        <input
          key={i}
          ref={(el) => {
            boxes.current[i] = el;
          }}
          type="text"
          inputMode="numeric"
          autoComplete={i === 0 ? "one-time-code" : "off"}
          aria-label={`Digit ${i + 1}`}
          value={d}
          disabled={disabled}
          onChange={(e) => change(i, e.target.value)}
          onPaste={(e) => paste(i, e)}
          onKeyDown={(e) => keyDown(i, e)}
          onFocus={(e) => e.target.select()}
          className="h-14 w-11 rounded-xl border border-line bg-card text-center text-[24px] font-bold text-text outline-none focus:border-violet disabled:opacity-50"
        />
      ))}
    </div>
  );
}
