import { ChevronLeft, Smartphone } from "lucide-react";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router";
import {
  useAccount,
  useAttempt,
  useCancelReauth,
  useRequestSms,
  useRestartReauth,
  useStartReauth,
  useSubmitCode,
} from "@/api/queries";
import { FINAL_ATTEMPT_STATES, type Attempt } from "@/api/types";
import { Button, Card, Page, Spinner } from "@/ui";
import { CodeInput } from "./CodeInput";

const STEPS = ["Send code", "Enter code", "Done"];

function stepOf(attempt: Attempt | null): number {
  if (!attempt || attempt.state === "starting" || attempt.state === "cancelled") return 0;
  if (attempt.state === "succeeded") return 2;
  return 1;
}

function Steps({ current }: { current: number }) {
  return (
    <ol className="flex gap-2" aria-label="Progress">
      {STEPS.map((s, i) => (
        <li
          key={s}
          aria-current={i === current ? "step" : undefined}
          className={`flex-1 rounded-full py-1 text-center text-[12px] font-semibold ${
            i <= current ? "bg-violet text-white" : "bg-line text-muted"
          }`}
        >
          {s}
        </li>
      ))}
    </ol>
  );
}

function Waiting({ text }: { text: string }) {
  return (
    <Card className="flex items-center gap-3">
      <Spinner className="text-accent" />
      <p className="text-[15px]">{text}</p>
    </Card>
  );
}

function Problem({ text, children }: { text: string; children: ReactNode }) {
  return (
    <Card className="flex flex-col gap-3 border border-red/40">
      <p role="alert" className="text-[15px] font-semibold text-red">
        {text}
      </p>
      <div className="flex flex-wrap gap-2">{children}</div>
    </Card>
  );
}

export function Reauth() {
  const navigate = useNavigate();
  const account = useAccount();
  const attemptQ = useAttempt();
  const start = useStartReauth();
  const restart = useRestartReauth();
  const submit = useSubmitCode();
  const sms = useRequestSms();
  const cancel = useCancelReauth();
  const [resetKey, setResetKey] = useState(0);

  // The server keeps the last attempt until it restarts. A finished attempt only
  // counts if this screen saw it in progress; an old one must not drive the screen.
  const [seenActive, setSeenActive] = useState<ReadonlySet<string>>(() => new Set());
  const latest = attemptQ.data?.attempt ?? null;
  const active = !!latest && !FINAL_ATTEMPT_STATES.includes(latest.state);
  if (latest && active && !seenActive.has(latest.id)) {
    setSeenActive(new Set(seenActive).add(latest.id));
  }
  const attempt = latest && (active || seenActive.has(latest.id)) ? latest : null;
  const state = attempt?.state;

  // A rejected code clears the boxes, once per attempt and state change.
  const step = `${attempt?.id}:${state}`;
  const [prevStep, setPrevStep] = useState(step);
  if (step !== prevStep) {
    setPrevStep(step);
    if (state === "rejected") setResetKey((k) => k + 1);
  }

  useEffect(() => {
    if (state === "succeeded") navigate("/", { state: { reauthed: true } });
  }, [state, attempt?.id, navigate]);

  const onCode = useCallback((code: string) => submit.mutate(code), [submit]);
  const again = () => {
    setResetKey((k) => k + 1);
    restart.mutate();
  };
  const error = start.error ?? restart.error ?? submit.error ?? sms.error ?? cancel.error;

  const back = (
    <Link to="/" aria-label="Back" className="-ml-2 p-2 text-muted">
      <ChevronLeft className="size-6" />
    </Link>
  );

  if (!attemptQ.data || !account.data) {
    return (
      <Page title="Sign in again" back={back}>
        <Spinner className="mx-auto text-accent" />
      </Page>
    );
  }

  let body: ReactNode;
  if (!attempt || state === "cancelled") {
    body =
      account.data.state === "ok" ? (
        <Card className="flex flex-col gap-3">
          <p className="text-[17px] font-bold">You're signed in</p>
          <p className="text-[15px] text-muted">
            Apple accepted this server. Nothing to do right now.
          </p>
          <Link to="/" className="self-start font-semibold text-accent">
            Back to Home
          </Link>
        </Card>
      ) : (
        <Card className="flex flex-col gap-3">
          <Smartphone aria-hidden className="size-8 text-accent" />
          <p className="text-[15px]">
            Apple will send a 6-digit code to your iPhone. Keep it nearby — this takes about a
            minute.
          </p>
          <Button busy={start.isPending} onClick={() => start.mutate()}>
            Send code
          </Button>
        </Card>
      );
  } else if (state === "starting") {
    body = <Waiting text="Asking Apple for a code…" />;
  } else if (state === "sending_sms") {
    body = <Waiting text={`Texting ${attempt.sms_sent_to ?? "your phone"}…`} />;
  } else if (state === "verifying") {
    body = <Waiting text="Checking the code…" />;
  } else if (state === "awaiting_code" || state === "awaiting_sms_code") {
    body = (
      <Card className="flex flex-col gap-4">
        <p className="text-center text-[15px]">
          {state === "awaiting_sms_code"
            ? `Code sent to ${attempt.sms_sent_to ?? "your phone"}. Enter it below.`
            : "Enter the code shown on your iPhone."}
        </p>
        <CodeInput onComplete={onCode} disabled={submit.isPending} resetKey={resetKey} />
        {state === "awaiting_code" &&
          attempt.phones.map((p) => (
            <Button
              key={p.index}
              variant="ghost"
              busy={sms.isPending}
              onClick={() => sms.mutate(p.index)}
            >
              No pop-up? Text a code to {p.masked}
            </Button>
          ))}
        <Button variant="secondary" busy={restart.isPending} onClick={again}>
          Start over
        </Button>
      </Card>
    );
  } else if (state === "rejected") {
    body = (
      <Problem text={attempt.error ?? "Apple rejected that code."}>
        <Button busy={restart.isPending} onClick={again}>
          Send a new code
        </Button>
      </Problem>
    );
  } else if (state === "bad_password") {
    body = (
      <Problem text={attempt.error ?? "Apple rejected the Apple ID password."}>
        <Button busy={restart.isPending} onClick={again}>
          Try again
        </Button>
        <Link
          to="/settings#account"
          className="inline-flex min-h-11 items-center rounded-full bg-violet px-5 font-semibold text-white"
        >
          Update password
        </Link>
      </Problem>
    );
  } else {
    // expired, failed, or succeeded while the account state catches up
    body =
      state === "succeeded" ? (
        <Waiting text="Signed in. Finishing up…" />
      ) : (
        <Problem text={attempt.error ?? "The sign-in didn't finish."}>
          <Button busy={restart.isPending} onClick={again}>
            Start over
          </Button>
        </Problem>
      );
  }

  return (
    <Page title="Sign in again" back={back}>
      <Steps current={stepOf(attempt)} />
      {body}
      {error && (
        <p role="alert" className="text-[14px] text-red">
          {error.message}
        </p>
      )}
      {active && (
        <Button
          variant="ghost"
          busy={cancel.isPending}
          onClick={() => cancel.mutate(undefined, { onSuccess: () => navigate("/") })}
        >
          Cancel
        </Button>
      )}
    </Page>
  );
}
