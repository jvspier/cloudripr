import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { Route, Routes } from "react-router";
import { onUnauthorized } from "@/api/client";
import { qk, useAuthStatus } from "@/api/queries";
import { Login } from "@/screens/auth/Login";
import { Setup } from "@/screens/auth/Setup";
import { Home } from "@/screens/home/Home";
import { PolicyEditor } from "@/screens/policy/PolicyEditor";
import { Reauth } from "@/screens/reauth/Reauth";
import { RunDetail } from "@/screens/runs/RunDetail";
import { Settings } from "@/screens/settings/Settings";
import { MonthPhotos, RunPhotos } from "@/screens/photos/PhotoGrid";
import { Photos } from "@/screens/photos/Photos";
import { Card, Page, Spinner } from "@/ui";
import { Shell } from "./Shell";

function Stub({ name }: { name: string }) {
  return (
    <Page title={name}>
      <Card>{name}</Card>
    </Page>
  );
}

export function App() {
  const client = useQueryClient();
  const auth = useAuthStatus();
  useEffect(() => {
    onUnauthorized(() => void client.invalidateQueries({ queryKey: qk.auth }));
    return () => onUnauthorized(null);
  }, [client]);

  if (!auth.data) {
    return (
      <div className="flex min-h-dvh items-center justify-center">
        {auth.error ? (
          <p className="px-4 text-red">{auth.error.message}</p>
        ) : (
          <Spinner className="text-accent" />
        )}
      </div>
    );
  }
  if (auth.data.setup_required) return <Setup />;
  if (!auth.data.authenticated) return <Login />;
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Home />} />
        <Route path="photos" element={<Photos />} />
        <Route path="photos/month/:ym" element={<MonthPhotos />} />
        <Route path="settings" element={<Settings />} />
        <Route path="settings/policies/new" element={<PolicyEditor key="new" />} />
        <Route path="settings/policies/:name" element={<PolicyEditor key="edit" />} />
        <Route path="account/reauth" element={<Reauth />} />
        <Route path="runs/:id" element={<RunDetail />} />
        <Route path="runs/:id/photos" element={<RunPhotos />} />
        <Route path="*" element={<Stub name="Not found" />} />
      </Route>
    </Routes>
  );
}
