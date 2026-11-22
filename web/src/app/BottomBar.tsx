import { CloudDownload, Home, Images, Settings } from "lucide-react";
import { NavLink } from "react-router";

const TABS = [
  { to: "/", label: "Home", Icon: Home },
  { to: "/photos", label: "Photos", Icon: Images },
  { to: "/settings", label: "Settings", Icon: Settings },
] as const;

/** The main navigation: a bottom tab bar on phones, a left sidebar from tablet width. */
export function BottomBar({ attention }: { attention: boolean }) {
  return (
    <nav
      aria-label="Main"
      className="fixed inset-x-0 bottom-0 z-30 flex border-t border-line bg-card pb-[env(safe-area-inset-bottom)] md:inset-y-0 md:right-auto md:w-56 md:flex-col md:gap-1 md:border-r md:border-t-0 md:px-3 md:pb-6 md:pt-6"
    >
      <div className="mb-5 hidden items-center gap-2 px-3 text-[19px] font-bold tracking-tight md:flex">
        <CloudDownload aria-hidden className="size-6 text-accent" />
        cloudripr
      </div>
      {TABS.map(({ to, label, Icon }) => (
        <NavLink
          key={to}
          to={to}
          end={to === "/"}
          className={({ isActive }) =>
            `relative flex flex-1 flex-col items-center gap-0.5 pb-2 pt-2.5 text-[11px] font-semibold md:flex-none md:flex-row md:gap-3 md:rounded-xl md:px-3 md:py-2.5 md:text-[15px] ${
              isActive ? "text-accent md:bg-soft-violet" : "text-muted md:hover:bg-line/60"
            }`
          }
        >
          <Icon aria-hidden className="size-6 md:size-5" />
          {label}
          {to === "/" && attention && (
            <span
              aria-label="Needs you"
              className="absolute right-[calc(50%-18px)] top-2 size-2.5 rounded-full bg-red md:static md:ml-auto"
            />
          )}
        </NavLink>
      ))}
    </nav>
  );
}
