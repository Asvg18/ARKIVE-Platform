import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Logo } from "../../../../shared/ui/Logo";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../../../auth/controller/AuthContext";
import { ProfileMenu } from "../../../../shared/ui/ProfileMenu";
import {
  BriefcaseIcon,
  DocumentIcon,
  FunnelIcon,
  GridIcon,
  LayersIcon,
  PanelLeftIcon,
  PeopleIcon,
  PlusIcon,
  SearchIcon,
} from "../../../../shared/ui/icons";
import { NotificationBell } from "../../../notifications/view/components/NotificationBell";
import { HelpButton } from "../../../help/view/components/HelpButton";

interface NavItem {
  label: string;
  to: string;
  icon: (props: { width?: number; height?: number }) => ReactNode;
  /** Shown only to super admins. The API refuses everyone else anyway;
   *  this just keeps a page they can't use out of their way. */
  superAdminOnly?: boolean;
}

/** Where the hidden/shown choice is remembered, per browser. A preference
 *  about this screen, not data anyone else needs — so browser storage, and
 *  every read and write guarded, since a private window may refuse both. */
const SIDEBAR_KEY = "arkive_hr_sidebar_hidden";

function readSidebarHidden(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_KEY) === "1";
  } catch {
    return false;
  }
}

/** ⌘\ on a Mac, Ctrl+\ elsewhere — Figma's own shortcut for hiding its UI. */
const SHORTCUT = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform) ? "⌘\\" : "Ctrl+\\";

const NAV_ITEMS: NavItem[] = [
  { label: "HR Dashboard", to: "/hr", icon: GridIcon },
  { label: "Create Job Opening", to: "/hr/requisitions/new", icon: PlusIcon },
  { label: "HR Workflow", to: "/hr/pipelines", icon: FunnelIcon },
  { label: "Job Openings", to: "/hr/job-openings", icon: BriefcaseIcon },
  { label: "Workflow Builder", to: "/hr/workflow-builder", icon: LayersIcon },
  { label: "Pre-Screening Questions", to: "/hr/pre-screening-questions", icon: DocumentIcon },
  { label: "User Management", to: "/hr/user-management", icon: PeopleIcon, superAdminOnly: true },
];

/** Shared shell for every HR Admin route. Nav intentionally only lists
 * routes that work today, never a dead link to a page not built yet. */
export function AppShell({ children }: { children: ReactNode }) {
  const { me, logout } = useAuth();
  const location = useLocation();
  // The sidebar can be put away for more room, as in Figma. Remembered
  // across pages and visits (each page mounts its own shell, so without
  // this it would reappear on every click).
  const [sidebarHidden, setSidebarHidden] = useState(readSidebarHidden);
  const hideButton = useRef<HTMLButtonElement>(null);
  const showButton = useRef<HTMLButtonElement>(null);
  /** Set when a toggle *button* was used, so focus follows to the other
   *  button instead of being left on one that just disappeared. */
  const moveFocus = useRef(false);

  useEffect(() => {
    try {
      localStorage.setItem(SIDEBAR_KEY, sidebarHidden ? "1" : "0");
    } catch {
      /* not remembered this time; the toggle still works */
    }
    if (moveFocus.current) {
      moveFocus.current = false;
      (sidebarHidden ? showButton : hideButton).current?.focus();
    }
  }, [sidebarHidden]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key === "\\") {
        event.preventDefault();
        setSidebarHidden((hidden) => !hidden);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  function toggleFromButton() {
    moveFocus.current = true;
    setSidebarHidden((hidden) => !hidden);
  }

  return (
    // Dark chrome for HR: the admin console reads as a tool
    // with its pages set inside it, like Figma's canvas in its panels.
    <div className="ark-shell ark-shell--dark" data-sidebar={sidebarHidden ? "hidden" : "shown"}>
      <aside className="ark-shell__sidebar" aria-hidden={sidebarHidden || undefined}>
        <div className="ark-shell__brand-row">
          <Link to="/hr" className="ark-shell__brand">
            <Logo size={30} withWordmark subtitle="University HR" />
          </Link>
          <button
            ref={hideButton}
            type="button"
            className="ark-sidebar-toggle"
            onClick={toggleFromButton}
            aria-label="Hide sidebar"
            aria-keyshortcuts="Meta+Backslash Control+Backslash"
            title={`Hide sidebar (${SHORTCUT})`}
          >
            <PanelLeftIcon width={18} height={18} />
          </button>
        </div>

        <div className="ark-shell__label" aria-hidden="true">Menu</div>
        <nav className="ark-shell__nav" aria-label="HR Admin">
          {NAV_ITEMS.filter((item) => !item.superAdminOnly || me?.is_super_admin).map((item) => {
            // A page under a section keeps its section lit — one job's
            // detail page is still Job Openings. The Command Center is
            // "/hr" itself, a prefix of everything, so it matches exactly.
            const active =
              location.pathname === item.to || (item.to !== "/hr" && location.pathname.startsWith(`${item.to}/`));
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

        {/* No "Browse Job Board" here, unlike the other two portals: HR
            has nothing to apply to on the public board, and "/" sends a
            signed-in HR admin back to the Command Center (App.tsx). A
            posting is read on its own page under Job Openings instead. */}
      </aside>

      <div className="ark-shell__body">
        <header className="ark-shell__topbar">
          {sidebarHidden && (
            <button
              ref={showButton}
              type="button"
              className="ark-icon-btn ark-shell__show-sidebar"
              onClick={toggleFromButton}
              aria-label="Show sidebar"
              aria-keyshortcuts="Meta+Backslash Control+Backslash"
              title={`Show sidebar (${SHORTCUT})`}
            >
              <PanelLeftIcon width={18} height={18} />
            </button>
          )}
          <div className="ark-shell__topbar-inner">
            <TopbarSearch />
            <div className="ark-shell__topbar-end">
              <HelpButton />
              <NotificationBell allHref="/hr/notifications" />
              <span className="ark-shell__topbar-divider" aria-hidden="true" />
              <ProfileMenu
                name={me?.full_name ?? "HR"}
                email={me?.email}
                role="HR Admin"
                avatarUrl={me?.avatar_url}
                settingsHref="/hr/account"
                onLogout={logout}
              />
            </div>
          </div>
        </header>

        <main className="ark-shell__main">
          {/* One ceiling for the whole shell (--page-max). Without it a
              page runs the full width of whatever monitor it lands on,
              which is why the picker screens once looked like a narrow
              column stranded in an empty frame. Centred so the leftover
              space is shared rather than all of it piling up on the right. */}
          <div className="ark-shell__page">{children}</div>
        </main>
      </div>
    </div>
  );
}

/** Finds a candidate or a job from any HR page. The Pipelines page is
 *  where both are searched (its own box matches candidate names and job
 *  titles), so the term is handed over as `?q=` rather than this bar
 *  keeping a second search of its own that could disagree with it. */
function TopbarSearch() {
  const navigate = useNavigate();
  const [term, setTerm] = useState("");

  function submit(e: FormEvent) {
    e.preventDefault();
    const q = term.trim();
    if (!q) return;
    navigate(`/hr/pipelines?q=${encodeURIComponent(q)}`);
  }

  return (
    <form role="search" onSubmit={submit} className="ark-search" style={{ width: 300 }}>
      <SearchIcon width={15} height={15} className="ark-search__icon" aria-hidden="true" />
      <input
        type="search"
        value={term}
        onChange={(e) => setTerm(e.target.value)}
        placeholder="Search candidates or jobs…"
        aria-label="Search candidates or jobs"
        className="ark-search__input"
      />
    </form>
  );
}
