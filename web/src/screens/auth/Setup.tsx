import { useState } from "react";
import { useSetup } from "@/api/queries";
import { Button, Field, inputClass } from "@/ui";
import { AuthCard } from "./AuthCard";

export function Setup() {
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [mismatch, setMismatch] = useState(false);
  const setup = useSetup();
  const submit = () => {
    setMismatch(password !== repeat);
    if (password === repeat) setup.mutate(password);
  };
  return (
    <AuthCard
      title="Set a password"
      intro="This protects the app on your network. You'll use it to log in."
      onSubmit={submit}
    >
      <Field label="New password">
        <input
          type="password"
          autoComplete="new-password"
          className={inputClass}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </Field>
      <Field
        label="Repeat password"
        error={mismatch ? "The passwords don't match." : setup.error?.message}
      >
        <input
          type="password"
          autoComplete="new-password"
          className={inputClass}
          value={repeat}
          onChange={(e) => setRepeat(e.target.value)}
        />
      </Field>
      <Button type="submit" busy={setup.isPending} disabled={!password}>
        Set password
      </Button>
    </AuthCard>
  );
}
