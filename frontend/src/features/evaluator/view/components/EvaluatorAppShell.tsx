import type { ReactNode } from "react";
import { Logo } from "../../../../shared/ui/Logo";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "../../../auth/controller/AuthContext";
import { ProfileMenu } from "../../../../shared/ui/ProfileMenu";
import { NotificationBell } from "../../../notifications/view/components/NotificationBell";
import { HelpButton } from "../../../help/view/components/HelpButton";
import { PeopleIcon } from "../../../../shared/ui/icons";

interface NavItem {
  label: string;
  to: string;
  icon: (props: { width?: number; height?: number }) => ReactNode;
}

const NAV_ITEMS: NavItem[] = [
  { label: "Review Queue", to: "/evaluator", icon: PeopleIcon },
];

/** Purpose-built shell for Evaluator routes —
 * deliberately not a copy of the HR AppShell. No HR-only nav items (the
 * Figma's Interviewer Dashboard had a stray "Create New Listing" button that
 * doesn't belong here), and no candidate-search box: evaluators only ever see
 * their own assigned interviews, never the full candidate list.
 *
 * Dark chrome, the same as HR's and the applicant's, and no
 * "Browse Job Board" link at the foot: an evaluator has no use for the
 * public listings, and the link was the one thing in the sidebar that
 * led out of the portal. */
export function EvaluatorAppShell({ children }: { children: ReactNode }) {
  const { me, logout } = useAuth();
  const location = useLocation();

  return (
    <div className="ark-shell ark-shell--dark">
      <aside className="ark-shell__sidebar">
        <Link to="/evaluator" className="ark-shell__brand">
          <Logo size={30} withWordmark subtitle="Evaluator" />
        </Link>

        <div className="ark-shell__label" aria-hidden="true">Menu</div>

        <nav className="ark-shell__nav" aria-label="Evaluator">
          {NAV_ITEMS.map((item) => {
            const active = location.pathname.startsWith(item.to);
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
              <NotificationBell allHref="/evaluator/notifications" />
              <span className="ark-shell__topbar-divider" aria-hidden="true" />
              <ProfileMenu
                name={me?.full_name ?? "Evaluator"}
                email={me?.email}
                role="Evaluator"
                avatarUrl={me?.avatar_url}
                settingsHref="/evaluator/account"
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
