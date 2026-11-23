import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "../../../auth/controller/AuthContext";
import { AppShell } from "../../../hr/view/components/AppShell";
import { ApplicantAppShell } from "../../../applicant/view/components/ApplicantAppShell";
import { EvaluatorAppShell } from "../../../evaluator/view/components/EvaluatorAppShell";
import { Logo } from "../../../../shared/ui/Logo";
import { PageHeader } from "../../../../shared/ui/PageHeader";
import { SearchIcon } from "../../../../shared/ui/icons";
import { manualFor, searchManual, type Audience, type Block } from "../../model/manual";

const ROLE_AUDIENCE: Record<string, Audience> = {
  applicant: "applicant",
  hr_admin: "hr",
  evaluator: "evaluator",
};

const ROLE_GUIDE: Record<Audience, string> = {
  all: "",
  applicant: "Applicant Guide",
  hr: "HR Admin Guide",
  evaluator: "Evaluator Guide",
};

/** The user manual inside ARKIVE (29 Oct 2026), reached from the ? in
 * every portal's top bar and from the sign-in page.
 *
 * One route for every role, in that role's own shell, so help opens
 * beside the work it explains rather than in a separate site. A signed-in
 * reader sees the parts of the manual for everyone plus their own role's
 * guide, numbered as one manual of their own (manual.ts, manualFor).
 * Signed out, it is the whole manual: whoever is reading has not told us
 * who they are yet.
 *
 * The ? button links to `/help#<topic>` for the page it was pressed on
 * (manual.ts, helpTopicFor), and this page scrolls to that topic. */
export function HelpPage() {
  const { user } = useAuth();
  const role = user ? (ROLE_AUDIENCE[user.role] ?? null) : null;

  if (role === "hr")
    return (
      <AppShell>
        <HelpContent role={role} />
      </AppShell>
    );
  if (role === "applicant")
    return (
      <ApplicantAppShell wide>
        <HelpContent role={role} />
      </ApplicantAppShell>
    );
  if (role === "evaluator")
    return (
      <EvaluatorAppShell>
        <HelpContent role={role} />
      </EvaluatorAppShell>
    );
  return (
    <PublicHelpShell>
      <HelpContent role={null} />
    </PublicHelpShell>
  );
}

function HelpContent({ role }: { role: Audience | null }) {
  const location = useLocation();
  const target = decodeURIComponent(location.hash.slice(1));
  const [query, setQuery] = useState("");

  const sections = useMemo(() => searchManual(manualFor(role), query), [role, query]);

  useEffect(() => {
    if (!target) return;
    const jump = () => document.getElementById(target)?.scrollIntoView({ block: "start" });
    // an effect runs once the topic is on the page, so it can go now
    jump();
    // On a reload the browser puts back the old scroll position once the
    // page has loaded, which would undo the jump; so jump again then.
    if (document.readyState === "complete") return;
    window.addEventListener("load", jump, { once: true });
    return () => window.removeEventListener("load", jump);
  }, [target]);

  return (
    <>
      <PageHeader
        title="Help"
        description={
          role ? `The ARKIVE user manual, with the ${ROLE_GUIDE[role]} for your account.` : "The ARKIVE user manual."
        }
        info={{
          summary: "Step-by-step guides for every part of ARKIVE, with answers to common questions.",
          points: [
            "Words in bold are buttons and menu items exactly as they appear on screen.",
            "The ? at the top of any page opens the part of this manual about that page.",
          ],
        }}
      />

      <div className="ark-help-frame">
        <div className="ark-help">
          <aside className="ark-help__aside">
            <form role="search" className="ark-search" onSubmit={(e) => e.preventDefault()}>
              <SearchIcon width={15} height={15} className="ark-search__icon" aria-hidden="true" />
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search the manual"
                aria-label="Search the manual"
                className="ark-search__input"
              />
            </form>

            <nav className="ark-help__toc" aria-label="Contents">
              {sections.map((section) => (
                <div key={section.id} className="ark-help__toc-group">
                  <Link to={{ hash: section.id }} className="ark-help__toc-section" onClick={() => setQuery("")}>
                    {section.label ? `${section.label.replace("Section ", "")}. ` : ""}
                    {section.title}
                  </Link>
                  {section.topics.map((topic) => (
                    <Link
                      key={topic.id}
                      to={{ hash: topic.id }}
                      className="ark-help__toc-topic"
                      aria-current={topic.id === target ? "location" : undefined}
                      onClick={() => setQuery("")}
                    >
                      {topic.title}
                    </Link>
                  ))}
                </div>
              ))}
            </nav>
          </aside>

          <div className="ark-help__body">
            {sections.length === 0 && (
              <div className="ark-help__empty">
                <p className="ark-help__empty-title">Nothing in the manual matches "{query}".</p>
                <p>Try another word, or contact the MSEUF HR office.</p>
              </div>
            )}

            {sections.map((section) => (
              <section key={section.id} id={section.id} className="ark-help__section">
                {section.label && <p className="ark-help__eyebrow">{section.label}</p>}
                <h2 className="ark-help__title">{section.title}</h2>
                <Blocks blocks={section.blocks} />
                {section.topics.map((topic) => (
                  <article
                    key={topic.id}
                    id={topic.id}
                    className="ark-help__topic"
                    data-current={topic.id === target || undefined}
                  >
                    <h3 className="ark-help__topic-title">{topic.title}</h3>
                    <Blocks blocks={topic.blocks} />
                  </article>
                ))}
              </section>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}

function Blocks({ blocks }: { blocks: Block[] }) {
  return (
    <>
      {blocks.map((block, i) => {
        switch (block.kind) {
          case "p":
            return (
              <p key={i} className="ark-help__p">
                <Rich text={block.text} />
              </p>
            );
          case "ol":
          case "ul":
          case "check": {
            const List = block.kind === "ol" ? "ol" : "ul";
            return (
              <List key={i} className={`ark-help__list ark-help__list--${block.kind}`}>
                {block.items.map((item, j) => (
                  <li key={j}>
                    <Rich text={item} />
                  </li>
                ))}
              </List>
            );
          }
          case "table":
            return (
              <div key={i} className="ark-help__table-wrap">
                <table className="ark-help__table">
                  <thead>
                    <tr>
                      {block.head.map((cell, j) => (
                        <th key={j} scope="col">
                          <Rich text={cell} />
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {block.rows.map((row, j) => (
                      <tr key={j}>
                        {row.map((cell, k) => (
                          <td key={k}>
                            <Rich text={cell} />
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
        }
      })}
    </>
  );
}

/** Text with the manual's **bold**: the on-screen names of buttons. */
function Rich({ text }: { text: string }) {
  const parts = text.split(/\*\*(.+?)\*\*/g);
  return <>{parts.map((part, i) => (i % 2 ? <strong key={i}>{part}</strong> : part))}</>;
}

/** Help for someone not signed in: the job board's brand, a way to sign
 *  in, and the manual. No portal shell, since there is no portal yet. */
function PublicHelpShell({ children }: { children: ReactNode }) {
  return (
    <div className="ark-help-public">
      <header className="ark-help-public__bar">
        <Link to="/" className="ark-help-public__brand">
          <Logo size={30} withWordmark subtitle="Help" />
        </Link>
        <Link to="/login" className="ark-help-public__signin">
          Sign in
        </Link>
      </header>
      <main className="ark-help-public__main">{children}</main>
    </div>
  );
}
