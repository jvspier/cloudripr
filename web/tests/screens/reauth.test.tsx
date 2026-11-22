import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { Attempt } from "@/api/types";
import { CodeInput } from "@/screens/reauth/CodeInput";
import { acct } from "../fixtures";
import { FakeEventSource } from "../fakeEventSource";
import { server } from "../msw";
import { renderAt } from "../render";

const attempt = (over: Partial<Attempt> = {}): Attempt => ({
  id: "a1",
  state: "awaiting_code",
  phones: [{ index: "a", masked: "•••• 12" }],
  error: null,
  sms_sent_to: null,
  started_at: "2026-11-22T18:00:00+00:00",
  ended_at: null,
  ...over,
});

/** Open the screen on an attempt in progress, then let it finish as `final` (pushed over SSE). */
async function finishWhileOpen(final: Attempt) {
  withAttempt(attempt({ id: final.id }));
  renderAt("/account/reauth");
  await screen.findAllByRole("textbox");
  server.use(http.get("/api/account/reauth", () => HttpResponse.json({ attempt: final })));
  act(() => FakeEventSource.last!.emit("reauth", final));
}

function withAttempt(
  a: Attempt | null,
  account = acct({ state: a ? "reauthenticating" : "needs_reauth" })
) {
  server.use(
    http.get("/api/account/reauth", () => HttpResponse.json({ attempt: a })),
    http.get("/api/account", () => HttpResponse.json(account))
  );
}

describe("CodeInput", () => {
  test("typing six digits submits once", async () => {
    const onComplete = vi.fn();
    render(<CodeInput onComplete={onComplete} disabled={false} resetKey={0} />);
    await userEvent.type(screen.getAllByRole("textbox")[0], "482913");
    expect(onComplete).toHaveBeenCalledOnce();
    expect(onComplete).toHaveBeenCalledWith("482913");
  });

  test("autofill of all six digits into the first box submits once", () => {
    const onComplete = vi.fn();
    render(<CodeInput onComplete={onComplete} disabled={false} resetKey={0} />);
    fireEvent.change(screen.getAllByRole("textbox")[0], { target: { value: "482913" } });
    expect(screen.getAllByRole("textbox").map((b) => (b as HTMLInputElement).value)).toEqual([
      "4",
      "8",
      "2",
      "9",
      "1",
      "3",
    ]);
    expect(onComplete).toHaveBeenCalledOnce();
    expect(onComplete).toHaveBeenCalledWith("482913");
  });

  test("paste fills all boxes", async () => {
    const onComplete = vi.fn();
    render(<CodeInput onComplete={onComplete} disabled={false} resetKey={0} />);
    await userEvent.click(screen.getAllByRole("textbox")[0]);
    await userEvent.paste("123 456");
    expect(onComplete).toHaveBeenCalledOnce();
    expect(onComplete).toHaveBeenCalledWith("123456");
  });

  test("non-digits are ignored", async () => {
    const onComplete = vi.fn();
    render(<CodeInput onComplete={onComplete} disabled={false} resetKey={0} />);
    await userEvent.type(screen.getAllByRole("textbox")[0], "a1b");
    expect(
      screen
        .getAllByRole("textbox")
        .map((b) => (b as HTMLInputElement).value)
        .join("")
    ).toBe("1");
    expect(onComplete).not.toHaveBeenCalled();
  });

  test("backspace on an empty box moves back", async () => {
    render(<CodeInput onComplete={vi.fn()} disabled={false} resetKey={0} />);
    const boxes = screen.getAllByRole("textbox");
    await userEvent.type(boxes[0], "12");
    await userEvent.keyboard("{Backspace}{Backspace}");
    expect(boxes.map((b) => (b as HTMLInputElement).value).join("")).toBe("1");
  });

  test("resetKey clears the boxes", () => {
    const { rerender } = render(<CodeInput onComplete={vi.fn()} disabled={false} resetKey={0} />);
    fireEvent.change(screen.getAllByRole("textbox")[0], { target: { value: "482913" } });
    rerender(<CodeInput onComplete={vi.fn()} disabled={false} resetKey={1} />);
    expect(
      screen
        .getAllByRole("textbox")
        .map((b) => (b as HTMLInputElement).value)
        .join("")
    ).toBe("");
  });
});

describe("Reauth screen", () => {
  test("no attempt and account ok shows signed-in state", async () => {
    withAttempt(null, acct({ state: "ok" }));
    renderAt("/account/reauth");
    expect(await screen.findByText("You're signed in")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to Home" })).toHaveAttribute("href", "/");
  });

  test("no attempt and needs_reauth shows Send code, which starts one", async () => {
    withAttempt(null);
    let started = false;
    server.use(
      http.post("/api/account/reauth", () => {
        started = true;
        return HttpResponse.json(attempt({ state: "starting" }));
      })
    );
    renderAt("/account/reauth");
    await userEvent.click(await screen.findByRole("button", { name: "Send code" }));
    expect(started).toBe(true);
    expect(await screen.findByText("Asking Apple for a code…")).toBeInTheDocument();
  });

  test("a running backup blocks the start with the server's reason", async () => {
    withAttempt(null);
    server.use(
      http.post("/api/account/reauth", () =>
        HttpResponse.json(
          {
            error: "A backup is running. Try again when it finishes.",
            error_id: null,
            field: null,
          },
          { status: 409 }
        )
      )
    );
    renderAt("/account/reauth");
    await userEvent.click(await screen.findByRole("button", { name: "Send code" }));
    expect(
      await screen.findByText("A backup is running. Try again when it finishes.")
    ).toBeInTheDocument();
  });

  test("entering the code submits it", async () => {
    withAttempt(attempt());
    let body: unknown = null;
    server.use(
      http.post("/api/account/reauth/code", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ attempt: attempt({ state: "verifying" }) });
      })
    );
    renderAt("/account/reauth");
    const boxes = await screen.findAllByRole("textbox");
    fireEvent.change(boxes[0], { target: { value: "482913" } });
    expect(await screen.findByText("Checking the code…")).toBeInTheDocument();
    expect(body).toEqual({ code: "482913" });
  });

  test("SMS option texts the chosen phone", async () => {
    withAttempt(attempt());
    let body: unknown = null;
    server.use(
      http.post("/api/account/reauth/sms", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({
          attempt: attempt({ state: "sending_sms", sms_sent_to: "•••• 12" }),
        });
      })
    );
    renderAt("/account/reauth");
    await userEvent.click(
      await screen.findByRole("button", { name: "No pop-up? Text a code to •••• 12" })
    );
    expect(body).toEqual({ index: "a" });
    expect(await screen.findByText("Texting •••• 12…")).toBeInTheDocument();
  });

  test("rejected shows Send a new code which restarts", async () => {
    let restarted = false;
    server.use(
      http.post("/api/account/reauth/restart", () => {
        restarted = true;
        return HttpResponse.json(attempt({ id: "a2", state: "starting" }));
      })
    );
    await finishWhileOpen(attempt({ state: "rejected", error: "Apple rejected that code." }));
    expect(await screen.findByText("Apple rejected that code.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Send a new code" }));
    expect(restarted).toBe(true);
  });

  test("a rejected code clears the boxes", async () => {
    let current = attempt();
    server.use(
      http.get("/api/account/reauth", () => HttpResponse.json({ attempt: current })),
      http.post("/api/account/reauth/code", () => {
        current = attempt({ state: "rejected", error: "Apple rejected that code." });
        return HttpResponse.json({ attempt: current });
      })
    );
    renderAt("/account/reauth");
    fireEvent.change((await screen.findAllByRole("textbox"))[0], { target: { value: "482913" } });
    expect(await screen.findByText("Apple rejected that code.")).toBeInTheDocument();
    const boxes = screen.queryAllByRole("textbox") as HTMLInputElement[];
    expect(boxes.map((b) => b.value).join("")).toBe("");
  });

  test("bad password links to the account settings", async () => {
    await finishWhileOpen(
      attempt({ state: "bad_password", error: "Apple rejected the Apple ID password." })
    );
    expect(await screen.findByText("Apple rejected the Apple ID password.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Update password" })).toHaveAttribute(
      "href",
      "/settings#account"
    );
  });

  test("succeeded navigates home with reauthed state", async () => {
    let current = attempt();
    let accountNow = acct({ state: "reauthenticating" });
    server.use(
      http.get("/api/account/reauth", () => HttpResponse.json({ attempt: current })),
      http.get("/api/account", () => HttpResponse.json(accountNow)),
      http.post("/api/account/reauth/code", () => {
        current = attempt({ state: "succeeded" });
        accountNow = acct({ state: "ok" });
        return HttpResponse.json({ attempt: current });
      })
    );
    renderAt("/account/reauth");
    fireEvent.change((await screen.findAllByRole("textbox"))[0], { target: { value: "482913" } });
    expect(await screen.findByText("All set")).toBeInTheDocument();
  });

  test("a leftover succeeded attempt does not bounce a needed re-auth back home", async () => {
    // the server keeps the last attempt in memory until restart (final review #1)
    withAttempt(attempt({ state: "succeeded" }), acct({ state: "needs_reauth" }));
    renderAt("/account/reauth");
    expect(await screen.findByRole("button", { name: "Send code" })).toBeInTheDocument();
    expect(screen.queryByText("iCloud needs you")).not.toBeInTheDocument();
  });

  test("a leftover succeeded attempt with the account ok shows signed in", async () => {
    withAttempt(attempt({ state: "succeeded" }), acct({ state: "ok" }));
    renderAt("/account/reauth");
    expect(await screen.findByText("You're signed in")).toBeInTheDocument();
  });

  test("a leftover failed attempt offers a fresh start", async () => {
    withAttempt(
      attempt({ state: "expired", error: "The sign-in timed out." }),
      acct({ state: "needs_reauth" })
    );
    renderAt("/account/reauth");
    expect(await screen.findByRole("button", { name: "Send code" })).toBeInTheDocument();
  });

  test("bad password can be retried after updating it", async () => {
    let restarted = false;
    server.use(
      http.post("/api/account/reauth/restart", () => {
        restarted = true;
        return HttpResponse.json(attempt({ id: "a2", state: "starting" }));
      })
    );
    await finishWhileOpen(
      attempt({ state: "bad_password", error: "Apple rejected the Apple ID password." })
    );
    await userEvent.click(await screen.findByRole("button", { name: "Try again" }));
    expect(restarted).toBe(true);
  });

  test("cancel deletes the attempt", async () => {
    withAttempt(attempt());
    let cancelled = false;
    server.use(
      http.delete("/api/account/reauth", () => {
        cancelled = true;
        return HttpResponse.json({ ok: true });
      })
    );
    renderAt("/account/reauth");
    await userEvent.click(await screen.findByRole("button", { name: "Cancel" }));
    expect(cancelled).toBe(true);
  });
});
