import { useState } from "react";
import { useLogin } from "@/api/queries";
import { Button, Field, inputClass } from "@/ui";
import { AuthCard } from "./AuthCard";

export function Login() {
  const [password, setPassword] = useState("");
  const login = useLogin();
  return (
    <AuthCard
      title="iCloud Photos"
      intro="Log in to manage your backups."
      onSubmit={() => login.mutate(password)}
    >
      <Field label="Password" error={login.error?.message}>
        <input
          type="password"
          autoComplete="current-password"
          className={inputClass}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </Field>
      <Button type="submit" busy={login.isPending} disabled={!password}>
        Log in
      </Button>
    </AuthCard>
  );
}
