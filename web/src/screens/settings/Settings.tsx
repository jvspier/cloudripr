import { useEffect } from "react";
import { useLocation } from "react-router";
import { Page } from "@/ui";
import { AccountSection } from "./AccountSection";
import { AppSection } from "./AppSection";
import { EmailSection } from "./EmailSection";
import { PolicyList } from "./PolicyList";

export function Settings() {
  const { hash } = useLocation();
  useEffect(() => {
    if (hash) document.getElementById(hash.slice(1))?.scrollIntoView?.();
  }, [hash]);
  return (
    <Page title="Settings">
      <AccountSection />
      <EmailSection />
      <section id="policies" aria-labelledby="policies-title" className="scroll-mt-4">
        <h2
          id="policies-title"
          className="mb-2 px-1 text-[13px] font-bold uppercase tracking-wide text-muted"
        >
          Policies
        </h2>
        <PolicyList />
      </section>
      <AppSection />
    </Page>
  );
}
