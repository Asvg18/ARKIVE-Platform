import { describe, expect, it } from "vitest";
import type { NotificationItem } from "../../../shared/api/notifications";
import {
  countLabel,
  emptyCopy,
  fullTime,
  groupByDay,
  mergeFresh,
  nextIndex,
  openActionFor,
  parseView,
  relativeTime,
  staysInView,
  viewQuery,
} from "./notifications";

// 15 Oct 2026, 06:00 UTC = 2:00 PM in the Philippines
const NOW = new Date(Date.UTC(2026, 9, 15, 6, 0));
const ago = (ms: number) => new Date(NOW.getTime() - ms).toISOString();
const MIN = 60 * 1000;
const HOUR = 60 * MIN;

function item(id: number, created: string): NotificationItem {
  return {
    id,
    title: `t${id}`,
    message: `n${id}`,
    link: null,
    kind: "system",
    read_at: null,
    archived_at: null,
    created_at: created,
    sender: { kind: "system", name: "ARKIVE", role: null, avatar_url: null },
    about: null,
    available: true,
  };
}

describe("relativeTime", () => {
  it("counts minutes, then hours, within the same day", () => {
    expect(relativeTime(ago(20 * 1000), NOW)).toBe("Now");
    expect(relativeTime(ago(5 * MIN), NOW)).toBe("5m");
    expect(relativeTime(ago(2 * HOUR), NOW)).toBe("2h");
  });

  it("says Yesterday by the Philippine day, not 24 hours", () => {
    // 11:30 PM on the 14th in Manila, only 14.5 hours before 2 PM on the 15th
    expect(relativeTime(new Date(Date.UTC(2026, 9, 14, 15, 30)).toISOString(), NOW)).toBe("Yesterday");
    // 12:30 AM on the 15th in Manila: the same day, though it is the 14th in UTC
    expect(relativeTime(new Date(Date.UTC(2026, 9, 14, 16, 30)).toISOString(), NOW)).toBe("13h");
  });

  it("names the weekday inside a week, then the date", () => {
    expect(relativeTime(new Date(Date.UTC(2026, 9, 12, 2, 0)).toISOString(), NOW)).toBe("Mon");
    expect(relativeTime(new Date(Date.UTC(2026, 9, 1, 2, 0)).toISOString(), NOW)).toBe("1 Oct");
    expect(relativeTime(new Date(Date.UTC(2025, 11, 20, 2, 0)).toISOString(), NOW)).toBe("20 Dec 2025");
  });
});

describe("fullTime", () => {
  it("reads in Philippine time", () => {
    expect(fullTime(NOW.toISOString())).toBe("Thu, 15 Oct 2026 · 2:00 PM");
  });
});

describe("groupByDay", () => {
  it("splits notices into Today, Yesterday and Earlier, newest first within each", () => {
    const groups = groupByDay(
      [item(5, ago(1 * HOUR)), item(4, ago(6 * HOUR)), item(3, ago(20 * HOUR)), item(2, ago(5 * 24 * HOUR))],
      NOW
    );
    expect(groups.map((g) => g.label)).toEqual(["Today", "Yesterday", "Earlier"]);
    expect(groups[0].items.map((i) => i.id)).toEqual([5, 4]);
  });

  it("leaves out a day with nothing in it", () => {
    expect(groupByDay([item(1, ago(10 * 24 * HOUR))], NOW).map((g) => g.label)).toEqual(["Earlier"]);
  });
});

describe("countLabel", () => {
  it("shows nothing for none and caps at 99+", () => {
    expect(countLabel(0)).toBe("");
    expect(countLabel(7)).toBe("7");
    expect(countLabel(99)).toBe("99");
    expect(countLabel(100)).toBe("99+");
  });
});

describe("openActionFor", () => {
  it("names the main button for where the notice leads", () => {
    expect(openActionFor("/hr/applications/4")?.label).toBe("Open candidate profile");
    expect(openActionFor("/applicant/applications/4?tab=exams")?.label).toBe("Open your application");
    expect(openActionFor("/evaluator/interviews/9")?.label).toBe("Open interview");
    expect(openActionFor("/hr/requisitions/2")).toEqual({ label: "Open", href: "/hr/requisitions/2" });
    expect(openActionFor(null)).toBeNull();
  });
});

describe("mergeFresh", () => {
  it("puts only newer notices on top and keeps what was loaded", () => {
    const loaded = [item(5, ago(HOUR)), item(4, ago(HOUR))];
    const merged = mergeFresh(loaded, [item(7, ago(0)), item(6, ago(0)), item(5, ago(HOUR))]);
    expect(merged.map((i) => i.id)).toEqual([7, 6, 5, 4]);
  });

  it("returns the same list when nothing is new, so nothing re-renders", () => {
    const loaded = [item(5, ago(HOUR))];
    expect(mergeFresh(loaded, [item(5, ago(HOUR))])).toBe(loaded);
  });
});

describe("nextIndex", () => {
  it("moves with the arrows and jumps with Home and End, stopping at the ends", () => {
    expect(nextIndex("ArrowDown", 0, 3)).toBe(1);
    expect(nextIndex("ArrowDown", 2, 3)).toBe(2);
    expect(nextIndex("ArrowUp", 0, 3)).toBe(0);
    expect(nextIndex("Home", 2, 3)).toBe(0);
    expect(nextIndex("End", 0, 3)).toBe(2);
    expect(nextIndex("a", 0, 3)).toBeNull();
    expect(nextIndex("ArrowDown", 0, 0)).toBeNull();
  });
});

describe("parseView", () => {
  it("reads the folder back from the address, and only kinds this role gets", () => {
    expect(parseView("unread", ["schedule"])).toBe("unread");
    expect(parseView("archived", ["schedule"])).toBe("archived");
    expect(parseView("decision", ["schedule", "decision"])).toBe("decision");
    expect(parseView("decision", ["schedule"])).toBe("inbox");
    expect(parseView("spam", ["schedule"])).toBe("inbox");
    expect(parseView(null, ["schedule"])).toBe("inbox");
  });
});

describe("viewQuery", () => {
  it("asks for a folder, or a kind inside the inbox", () => {
    expect(viewQuery("archived")).toEqual({ folder: "archived" });
    expect(viewQuery("schedule")).toEqual({ folder: "inbox", kind: "schedule" });
  });
});

describe("staysInView", () => {
  it("lets an archived notice leave the inbox and an unarchived one leave the archive", () => {
    const archived = { ...item(1, ago(0)), archived_at: ago(0) };
    const inInbox = item(2, ago(0));
    expect(staysInView(archived, "inbox")).toBe(false);
    expect(staysInView(archived, "schedule")).toBe(false);
    expect(staysInView(archived, "archived")).toBe(true);
    expect(staysInView(inInbox, "archived")).toBe(false);
    expect(staysInView({ ...inInbox, read_at: ago(0) }, "unread")).toBe(true);
  });
});

describe("emptyCopy", () => {
  it("gives every folder its own empty message, and a search its own", () => {
    const titles = (["inbox", "unread", "archived", "schedule"] as const).map((v) => emptyCopy(v, "").title);
    expect(new Set(titles).size).toBe(4);
    expect(emptyCopy("schedule", "").title).toBe("No schedules yet");
    expect(emptyCopy("inbox", "offer").title).toBe('Nothing matches "offer"');
  });
});
