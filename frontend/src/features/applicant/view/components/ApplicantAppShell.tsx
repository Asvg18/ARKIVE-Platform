import type { ReactNode } from "react";
import { Logo } from "../../../../shared/ui/Logo";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "../../../auth/controller/AuthContext";
import { BriefcaseIcon, GridIcon } from "../../../../shared/ui/icons";
import { NotificationBell } from "../../../notifications/view/components/NotificationBell";
import { HelpButton } from "../../../help/view/components/HelpButton";
import { ProfileMenu } from "../../../../shared/ui/ProfileMenu";

interface NavItem {
  label: string;
  to: string;
  icon: (props: { width?: number; height?: number }) => ReactNode;
}

const NAV_ITEMS: NavItem[] = [
  { label: "Dashboard", to: "/applicant", icon: GridIcon },
  // The full job browser, with search and filters. The public homepage
  // shows only six openings.
  { label: "Find Jobs", to: "/applicant/jobs", icon: BriefcaseIcon },
];

/** Shell for the authenticated Applicant portal. Nav intentionally only
 * lists "Dashboard" and "Find Jobs" -- other nav items have no
 * corresponding routes/pages yet, dropped rather than shown as dead
 * links. "Find Jobs" is the in-portal job browser (search, filters, a
 * job's full detail beside the list); the public homepage keeps a
 * six-opening preview that leads there.
 *
 * The top bar holds the bell and the account (ProfileMenu), the same as
 * the HR and Evaluator shells, so every role finds "log out" in the same
 * corner. The /notifications endpoints are role-agnostic. */
export function ApplicantAppShell({ children, wide = false }: { children: ReactNode; wide?: boolean }) {
  const { me, logout } = useAuth();
  const location = useLocation();

  return (
    // The applicant surface is a reading surface, not a data one — a
    // dashboard of application cards stretched to 1900px puts the status
    // badge a whole screen away from the job title it belongs to. Hence a
    // narrower ceiling than HR's for the page — but not the top bar, whose
    // bell and account sit at the right edge as in every portal.
    // `wide` is for the job browser's list-beside-detail layout, which
    // needs the room the reading pages don't.
    // Dark chrome, the same as HR's: one look for the
    // portals, the page set inside a dark frame.
    <div className="ark-shell ark-shell--dark" style={{ ["--shell-max" as string]: wide ? "1320px" : "1080px" }}>
      <aside className="ark-shell__sidebar">
        <Link to="/applicant" className="ark-shell__brand">
          <Logo size={30} withWordmark subtitle="Applicant Portal" />
        </Link>

        <div className="ark-shell__label" aria-hidden="true">Menu</div>

        <nav className="ark-shell__nav" aria-label="Applicant">
          {NAV_ITEMS.map((item) => {
            // The dashboard is "/applicant", a prefix of every page here, so
            // it lights only for itself and the application pages under it.
            const active =
              item.to === "/applicant"
                ? location.pathname === "/applicant" || location.pathname.startsWith("/applicant/applications")
                : location.pathname.startsWith(item.to);
            const Icon = item.icon;
            return (
              <Link
                key={item.to}
                to={item.to}
                className="ark-nav-item"
                aria-current={active ? "page" : undefined}
              >
                <Icon width={18} height={18} />
                {item.label}
              </Link>
            );
          })}
        </nav>
      </aside>

      <div className="ark-shell__body">
        <header className="ark-shell__topbar">
          <div className="ark-shell__topbar-inner">
            <div className="ark-shell__topbar-end">
              <HelpButton />
              <NotificationBell allHref="/applicant/notifications" />
              <span className="ark-shell__topbar-divider" aria-hidden="true" />
              <ProfileMenu
                name={me?.full_name ?? "Applicant"}
                email={me?.email}
                role="Applicant"
                avatarUrl={me?.avatar_url}
                settingsHref="/applicant/account"
                onLogout={logout}
              />
            </div>
          </div>
        </header>

        <main className="ark-shell__main">
          <div className="ark-shell__page">{children}</div>
        </main>
      </div>
    </div>
  );
}
