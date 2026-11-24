// Unit tests for web/lib/mathText.ts (M13).
//
// No test runner is installed in web/ (no vitest/jest), so these
// use Node's built-in runner. Run with:
//   npm run test:math
// which compiles this file + mathText.ts to /tmp and runs
// `node --test` on the compiled output. Nothing here touches
// the network, the database, or the stored bank data.

import { test } from "node:test";
import * as assert from "node:assert/strict";
import { formatMathText } from "./mathText";

function eq(input: string, expected: string): void {
  assert.equal(formatMathText(input), expected, `input: ${JSON.stringify(input)}`);
}

test("user's handshake example (exact)", () => {
  eq(
    "\\eqalign{ & \\frac{x \\times (x - 1)}{2} = 105 \\cr & x = 15 \\cr}",
    "x(x-1)/2 = 105\nx = 15",
  );
});

test("fractions", () => {
  eq("\\frac{1}{2}", "1/2");
  eq("\\frac12", "1/2");
  eq("$$\\frac{1}{2}$$", "1/2");
  eq("\\frac{x+1}{x-1}", "(x+1)/(x-1)");
  eq("\\frac{x + 1}{x}", "(x+1)/x");
  eq("\\frac{8}{2}", "8/2");
  eq("\\frac{\\frac{1}{2}}{3}", "(1/2)/3");
  eq("\\frac{x}{1}", "x/1");
  eq("\\frac{5 \\times 4}{3 \\times 9}", "(5\u00d74)/(3\u00d79)");
});

test("square roots", () => {
  eq("\\sqrt{x}", "sqrt(x)");
  eq("\\sqrt 2", "sqrt(2)");
  eq("\\sqrt{x+1}", "sqrt(x+1)");
  eq("x = 3 + 2\\sqrt 2", "x = 3 + 2sqrt(2)");
});

test("relations and operators", () => {
  eq("x \\le 5", "x <= 5");
  eq("x \\ge 5", "x >= 5");
  eq("x \\ne 5", "x != 5");
  eq("10 \\div 2 = 5", "10 \u00f7 2 = 5");
  eq("50\\% of 200", "50% of 200");
  eq("area = \\pi r^2", "area = pi r^2");
  eq("2 \\times 3 = 6", "2 \u00d7 3 = 6");
  eq("x \\times (x-1)", "x(x-1)");
  eq("a \\Rightarrow b", "a => b");
  eq("a \\Leftrightarrow b", "a <=> b");
  eq("90^\\circ", "90\u00b0");
  eq("90^ \\circ", "90\u00b0");
});

test("scripts", () => {
  eq("x^{2}", "x^2");
  eq("x^{n+1}", "x^(n+1)");
  eq("x_{1}", "x_1");
  eq("a_{ij}", "a_ij");
});

test("text, left/right, groups", () => {
  eq("{\\text{8}} \\times {\\text{2}}", "8 \u00d7 2");
  eq("\\left( x + 1 \\right)", "(x+1)");
  eq("\\frac{{x+1}}{2}", "(x+1)/2");
  eq("\\text{Total }x = 5", "Total x = 5");
});

test("eqalign with alignment padding", () => {
  eq(
    "$$\\eqalign{ & 3*5 + 5*3 \\cr & \\Rightarrow 3*5 = 6 \\cr & \\,\\,\\,\\,\\, = 6 \\cr} $$",
    "3*5 + 5*3\n=> 3*5 = 6\n= 6",
  );
  eq(
    "$$\\eqalign{ & {\\text{8}} \\times {\\text{2}} \\cr & = 8 + 2 + \\frac{8}{2} \\cr & = 14 \\cr} $$",
    "8 \u00d7 2\n= 8 + 2 + 8/2\n= 14",
  );
});

test("plain text passes through unchanged", () => {
  eq("Find the value of x.", "Find the value of x.");
  eq("x^2 - x - 210 = 0", "x^2 - x - 210 = 0");
  eq("The fee is $5 per test.", "The fee is $5 per test.");
  eq("", "");
});

test("unknown commands stay visible (fail-visible)", () => {
  eq("\\foo{bar}", "bar");
  eq("\\qed", "");
  eq("\\unknowncmd x = 1", "x = 1");
});

test("real bank shapes", () => {
  eq(
    "$$\\left( {{\\text{1 + }}\\frac{1}{x}} \\right)$$",
    "(1+1/x)",
  );
  eq(
    "\\frac{{\\left( {1 - \\frac{2}{3}} \\right)}}{2}",
    "(1-2/3)/2",
  );
  eq("a\\,b", "a b");
  eq("or\\,\\frac{c}{b} = 5", "or c/b = 5");
});
