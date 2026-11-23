import { describe, expect, it } from "vitest";
import { nounFor, paginate } from "./paging";

const nineteen = Array.from({ length: 19 }, (_, i) => i);

describe("paginate", () => {
  it("cuts the list into pages", () => {
    const first = paginate(nineteen, 0, 10);
    expect(first.pageCount).toBe(2);
    expect(first.visible).toEqual(nineteen.slice(0, 10));
    expect(paginate(nineteen, 1, 10).visible).toEqual(nineteen.slice(10));
  });

  it("keeps the reader on the last page when a search shrinks the list", () => {
    const shrunk = paginate(nineteen.slice(0, 4), 2, 10);
    expect(shrunk.page).toBe(0);
    expect(shrunk.visible).toEqual([0, 1, 2, 3]);
  });

  it("still has one page when the list is empty", () => {
    expect(paginate([], 0, 10)).toEqual({ pageCount: 1, page: 0, visible: [] });
  });

  it("never goes below the first page", () => {
    expect(paginate(nineteen, -1, 10).page).toBe(0);
  });
});

describe("nounFor", () => {
  it("is singular for one only", () => {
    expect(nounFor(1, "job")).toBe("job");
    expect(nounFor(19, "job")).toBe("jobs");
    expect(nounFor(0, "job")).toBe("jobs");
  });
});
