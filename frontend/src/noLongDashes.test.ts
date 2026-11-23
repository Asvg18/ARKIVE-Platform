/**
 * No long dash in any text ARKIVE shows a person: it reads as
 * machine-written.
 *
 * Every source file is read with the TypeScript scanner, so only what can
 * reach a screen is checked: string literals, template text and JSX text.
 * Comments are passed over, since nobody using ARKIVE reads them. The
 * short dash is fine: it marks ranges and empty values.
 *
 * Two kinds of file are left out: tests, which never reach a screen, and
 * shared/lib/displayText.ts, the one place that names the long dash, to
 * take it out of what the AI wrote. The backend has the same check
 * (backend/tests/test_no_long_dashes.py).
 */

import ts from "typescript";
import { describe, expect, it } from "vitest";

const LONG_DASH = "\u2014";

const SOURCES = import.meta.glob(["./**/*.{ts,tsx}", "!./**/*.test.{ts,tsx}", "!./shared/lib/displayText.ts"], {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

/** Each piece of text in `source` a screen could show that has a long
 * dash in it, with its line. */
function dashedText(path: string, source: string): { line: number; text: string }[] {
  const file = ts.createSourceFile(
    path,
    source,
    ts.ScriptTarget.Latest,
    true,
    path.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS
  );
  const found: { line: number; text: string }[] = [];
  const visit = (node: ts.Node) => {
    const isText =
      ts.isStringLiteral(node) ||
      ts.isNoSubstitutionTemplateLiteral(node) ||
      ts.isTemplateHead(node) ||
      ts.isTemplateMiddle(node) ||
      ts.isTemplateTail(node) ||
      ts.isJsxText(node);
    if (isText && node.text.includes(LONG_DASH)) {
      found.push({ line: file.getLineAndCharacterOfPosition(node.getStart()).line + 1, text: node.text.trim() });
    }
    ts.forEachChild(node, visit);
  };
  visit(file);
  return found;
}

describe("the long dash", () => {
  it("is read in strings, template text and JSX text, never in comments", () => {
    const sample = [
      `// a comment ${LONG_DASH} fine`,
      `const label = "Interview ${LONG_DASH} VP";`,
      `const hint = \`Pick ${LONG_DASH} \${count} left\`;`,
      `const view = <p>Not yet ${LONG_DASH} soon</p>;`,
      `/* fine ${LONG_DASH} too */`,
      `const range = "9:00 AM \u2013 11:30 AM";`,
    ].join("\n");
    expect(dashedText("sample.tsx", sample).map((found) => found.line)).toEqual([2, 3, 4]);
  });

  it("appears nowhere a person reads", () => {
    // the glob found the source: an empty match would pass for nothing
    expect(Object.keys(SOURCES).length).toBeGreaterThan(100);
    const offenders = Object.entries(SOURCES).flatMap(([path, source]) =>
      dashedText(path, source).map((found) => `${path.slice(2)}:${found.line}  ${found.text.slice(0, 80)}`)
    );
    expect(offenders, "Reword these by meaning: a comma, period, colon or brackets").toEqual([]);
  });
});
