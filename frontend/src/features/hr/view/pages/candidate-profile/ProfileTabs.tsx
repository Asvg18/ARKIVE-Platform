import { TAB_LABELS, TABLIST_ID, TABS, type Tab } from "./tabModel";

/** The record's tab bar, each tab with its count where it has one. */
export function ProfileTabs({
  tab,
  setTab,
  tabCount,
}: {
  tab: Tab;
  setTab: (tab: Tab) => void;
  tabCount: (tab: Tab) => string | null;
}) {
  return (
    <div className="ark-subnav" role="tablist" aria-label="Candidate record" id={TABLIST_ID}>
      {TABS.map((t) => {
        const count = tabCount(t);
        return (
          <button
            key={t}
            type="button"
            role="tab"
            id={`tab-${t}`}
            aria-selected={tab === t}
            aria-controls="candidate-tabpanel"
            className="ark-subnav__tab"
            onClick={() => setTab(t)}
          >
            {TAB_LABELS[t]}
            {count && <span className="ark-subnav__count">{count}</span>}
          </button>
        );
      })}
    </div>
  );
}
