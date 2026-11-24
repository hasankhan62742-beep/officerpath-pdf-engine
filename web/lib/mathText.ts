// OfficerPath AI — plain-text maths display (M13).
//
// The bank stores Maths explanations with LaTeX (e.g. \eqalign,
// \frac, \times) copied verbatim from the source. The app never
// renders LaTeX, and the user's client shows raw LaTeX as garbled
// text — so stored maths is converted to readable plain text AT
// DISPLAY TIME ONLY. The stored data is never rewritten
// (originals immutable); this function is pure and side-effect
// free, so it is safe to call in any server or client component.
//
// Rules:
// - Text with no LaTeX markers passes through byte-for-byte.
// - $$...$$, \[...\], \(...\) delimiters are stripped; a lone $
//   with no backslash anywhere is left alone (probably currency).
// - \frac{a}{b} -> a/b, parenthesising a numerator/denominator
//   only when it holds a top-level +, -, /, x, * or ÷ (so
//   (x+1)/(x-1) and (5 x 4)/(3 x 9), but x(x-1)/2 stays bare).
// - \eqalign{...} -> one readable line per \cr row, leading &
//   stripped.
// - \times before "(" is implicit multiplication and is dropped
//   (x \times (x-1) -> x(x-1)); elsewhere it is x.
// - Unknown constructs stay visible: an unknown \command is
//   dropped but a braced argument after it is kept. Nothing is
//   ever silently deleted except LaTeX markup itself.

const GREEK: Record<string, string> = {
  alpha: "alpha",
  beta: "beta",
  gamma: "gamma",
  delta: "delta",
  epsilon: "epsilon",
  zeta: "zeta",
  eta: "eta",
  theta: "theta",
  iota: "iota",
  kappa: "kappa",
  lambda: "lambda",
  mu: "mu",
  nu: "nu",
  xi: "xi",
  pi: "pi",
  rho: "rho",
  sigma: "sigma",
  tau: "tau",
  upsilon: "upsilon",
  phi: "phi",
  chi: "chi",
  psi: "psi",
  omega: "omega",
  Gamma: "Gamma",
  Delta: "Delta",
  Theta: "Theta",
  Lambda: "Lambda",
  Xi: "Xi",
  Pi: "Pi",
  Sigma: "Sigma",
  Phi: "Phi",
  Psi: "Psi",
  Omega: "Omega",
};

// Commands with a fixed plain-text replacement and no argument.
const SIMPLE: Record<string, string> = {
  ...GREEK,
  // Relations and operators.
  div: "\u00f7",
  cdot: "\u00b7",
  ast: "*",
  star: "*",
  le: "<=",
  leq: "<=",
  leqslant: "<=",
  ge: ">=",
  geq: ">=",
  geqslant: ">=",
  ne: "!=",
  neq: "!=",
  lt: "<",
  gt: ">",
  approx: "\u2248",
  equiv: "==",
  sim: "~",
  simeq: "~=",
  cong: "~=",
  propto: "~",
  pm: "+/-",
  mp: "-/+",
  circ: "\u00b0",
  // Arrows.
  to: "->",
  rightarrow: "->",
  leftarrow: "<-",
  leftrightarrow: "<->",
  Rightarrow: "=>",
  Leftarrow: "<=",
  Leftrightarrow: "<=>",
  implies: "=>",
  iff: "<=>",
  longrightarrow: "-->",
  longleftarrow: "<--",
  mapsto: "|->",
  uparrow: "\u2191",
  downarrow: "\u2193",
  therefore: "therefore",
  because: "because",
  // Sets and logic.
  in: "\u2208",
  notin: "\u2209",
  subset: "\u2282",
  subseteq: "\u2286",
  cup: "\u222a",
  cap: "\u2229",
  emptyset: "\u2205",
  forall: "\u2200",
  exists: "\u2203",
  infty: "infinity",
  partial: "\u2202",
  angle: "angle",
  // Functions (kept as their plain names).
  sin: "sin",
  cos: "cos",
  tan: "tan",
  cot: "cot",
  sec: "sec",
  csc: "csc",
  sinh: "sinh",
  cosh: "cosh",
  tanh: "tanh",
  arcsin: "arcsin",
  arccos: "arccos",
  arctan: "arctan",
  log: "log",
  ln: "ln",
  lg: "lg",
  exp: "exp",
  lim: "lim",
  limsup: "limsup",
  liminf: "liminf",
  min: "min",
  max: "max",
  sup: "sup",
  inf: "inf",
  det: "det",
  gcd: "gcd",
  deg: "deg",
  arg: "arg",
  dim: "dim",
  ker: "ker",
  hom: "hom",
  sum: "sum",
  prod: "product",
  int: "integral",
  Pr: "Pr",
  hbar: "h",
};

// Commands whose braced argument is the content: the command is
// dropped and the argument is formatted and kept.
const CONTENT_COMMANDS = new Set([
  "text",
  "operatorname",
  "mathop",
  "overline",
  "underline",
  "boxed",
  "mathrm",
  "mathbf",
  "mathit",
  "mathbb",
  "mathcal",
  "mathfrak",
]);

// Font switches and spacing/layout commands: dropped outright.
const DROP_COMMANDS = new Set([
  "bf",
  "it",
  "rm",
  "tt",
  "sf",
  "cal",
  "hfill",
  "limits",
  "nolimits",
  "displaystyle",
  "textstyle",
  "scriptstyle",
  "scriptscriptstyle",
  "noindent",
  "hline",
  "root",
  "of",
  "vphantom",
  "hphantom",
  "phantom",
]);

/** True when the formatted group needs parens as a fraction part:
 * it holds a top-level binary +, -, /, x, * or ÷ outside any
 * parens, and is not already wrapped in one balanced pair of
 * parens. Without this, 5 x 4 over 3 x 9 would render as
 * "5 x 4/3 x 9", which reads as 60 instead of 20/27. */
function needsParens(group: string): boolean {
  const s = group.trim();
  if (s.length <= 1) return false;
  if (s.startsWith("(") && matchingParen(s, 0) === s.length - 1) return false;
  let depth = 0;
  for (let k = 0; k < s.length; k++) {
    const ch = s[k];
    if (ch === "(") depth++;
    else if (ch === ")") depth--;
    else if (
      depth === 0 &&
      (ch === "+" ||
        ch === "/" ||
        ch === "\u00d7" ||
        ch === "*" ||
        ch === "\u00f7" ||
        ch === "\u00b7" ||
        (ch === "-" && k > 0))
    ) {
      return true;
    }
  }
  return false;
}

/** Index of the ")" matching the "(" at `open`, or -1. */
function matchingParen(s: string, open: number): number {
  let depth = 0;
  for (let k = open; k < s.length; k++) {
    if (s[k] === "(") depth++;
    else if (s[k] === ")") {
      depth--;
      if (depth === 0) return k;
    }
  }
  return -1;
}

class Parser {
  private s: string;
  private i = 0;

  constructor(s: string) {
    this.s = s;
  }

  /** Parse until the end, or until the closing brace that ends a
   * group (consumed when `stopAtBrace` is true). */
  parse(stopAtBrace: boolean): string {
    let out = "";
    while (this.i < this.s.length) {
      const ch = this.s[this.i];
      if (ch === "{") {
        // Bare group: braces are grouping only, keep the content.
        this.i++;
        out += this.parse(true);
      } else if (ch === "}") {
        if (stopAtBrace) {
          this.i++;
          return out;
        }
        // Unmatched brace: keep it visible rather than dropping it.
        out += ch;
        this.i++;
      } else if (ch === "\\") {
        out += this.parseCommand();
      } else if (ch === "^" || ch === "_") {
        out += this.parseScript(ch);
      } else if (ch === "$") {
        // Math delimiter: stripped (only reached when LaTeX ran).
        this.i++;
      } else {
        out += ch;
        this.i++;
      }
    }
    return out;
  }

  private skipSpaces(): void {
    while (this.i < this.s.length && this.s[this.i] === " ") this.i++;
  }

  /** Read a braced group and return its RAW inner text. */
  private readRawGroup(): string | null {
    this.skipSpaces();
    if (this.s[this.i] !== "{") return null;
    this.i++;
    let depth = 1;
    const start = this.i;
    while (this.i < this.s.length && depth > 0) {
      if (this.s[this.i] === "{") depth++;
      else if (this.s[this.i] === "}") depth--;
      this.i++;
    }
    return this.s.slice(start, this.i - 1);
  }

  /** One "atom": a braced group, a single command, or one char. */
  private parseAtom(): string {
    this.skipSpaces();
    if (this.i >= this.s.length) return "";
    const ch = this.s[this.i];
    if (ch === "{") {
      this.i++;
      return this.parse(true);
    }
    if (ch === "\\") {
      return this.parseCommand();
    }
    this.i++;
    return ch;
  }

  /** Parse ^... / _... : braced group, command, or one char. A
   * multi-character exponent with a top-level operator is
   * parenthesised (x^(n+1), but x^2). */
  private parseScript(mark: string): string {
    this.i++; // consume ^ or _
    this.skipSpaces();
    if (this.i >= this.s.length) return mark;
    // Degree mark: ^\circ (or ^ \circ) is just the degree sign.
    if (mark === "^" && this.s.startsWith("\\circ", this.i)) {
      this.i += "\\circ".length;
      return "\u00b0";
    }
    const atom = this.parseAtom();
    if (atom === "") return mark;
    if (atom.length > 1 && needsParens(atom)) return `${mark}(${atom})`;
    return mark + atom;
  }

  private parseCommand(): string {
    // this.s[this.i] === "\\"
    this.i++;
    if (this.i >= this.s.length) return "\\";
    const ch = this.s[this.i];

    // Double backslash: a line break.
    if (ch === "\\") {
      this.i++;
      return "\n";
    }
    // One-character commands.
    if (!/[a-zA-Z]/.test(ch)) {
      this.i++;
      switch (ch) {
        case ",":
        case ";":
        case ":":
        case " ":
          return " ";
        case "!":
          return "";
        case "%":
          return "%";
        case "$":
          return "$";
        case "#":
          return "#";
        case "&":
          return "&";
        case "_":
          return "_";
        case "{":
          return "{";
        case "}":
          return "}";
        case "[":
        case "]":
        case "(":
        case ")":
          return "";
        default:
          // Unknown one-char command: keep the char visible.
          return ch;
      }
    }

    // A control word: letters.
    const start = this.i;
    while (this.i < this.s.length && /[a-zA-Z]/.test(this.s[this.i])) this.i++;
    const name = this.s.slice(start, this.i);

    if (name === "cr" || name === "par") return "\n";
    if (name === "n") return "\n";

    if (name === "frac" || name === "dfrac" || name === "tfrac") {
      const num = this.parseAtom();
      const den = this.parseAtom();
      const n = needsParens(num) ? `(${num})` : num;
      const d = needsParens(den) ? `(${den})` : den;
      return `${n}/${d}`;
    }

    if (name === "sqrt") {
      return `sqrt(${this.parseAtom()})`;
    }

    if (name === "eqalign") {
      const raw = this.readRawGroup();
      if (raw === null) return "";
      const body = new Parser(raw).parse(false);
      const lines = body
        .split("\n")
        .map((line) => line.replace(/^\s*&\s*/, "").trim())
        .filter((line) => line !== "");
      return lines.join("\n");
    }

    if (name === "text") {
      // Literal text: kept verbatim, never re-parsed.
      return this.readRawGroup() ?? "";
    }

    if (name === "begin" || name === "end") {
      // Environment name (and column spec, e.g. {array}{l}) are
      // markup, not content: drop every braced group that follows.
      while (this.readRawGroup() !== null) {
        /* consume */
      }
      return "";
    }

    if (name === "left" || name === "right") {
      // The delimiter itself is ordinary text; a "." delimiter
      // is invisible, so drop it too.
      this.skipSpaces();
      if (this.s[this.i] === ".") this.i++;
      return "";
    }

    if (name === "kern") {
      // Spacing: drop the command and its dimension argument.
      this.skipSpaces();
      const m = /^-?\d*\.?\d+(em|ex|pt|in|cm|mm|mu|sp)\b/.exec(
        this.s.slice(this.i),
      );
      if (m) this.i += m[0].length;
      return "";
    }

    if (name === "times") {
      // Implicit multiplication before "(": x \times (x-1) reads
      // as x(x-1). Elsewhere it is the multiplication sign.
      let j = this.i;
      while (this.s[j] === " ") j++;
      let k = j;
      if (this.s.startsWith("\\left", k)) {
        k += "\\left".length;
        while (this.s[k] === " ") k++;
      }
      if (this.s[k] === "(") {
        // Swallow the whitespace around the dropped command so
        // the "(" attaches to what came before it.
        this.i = k;
        return "\u0000TRIM\u0000";
      }
      return "\u00d7";
    }

    if (name in SIMPLE) return SIMPLE[name];

    if (CONTENT_COMMANDS.has(name)) {
      const raw = this.readRawGroup();
      if (raw === null) return "";
      return new Parser(raw).parse(false);
    }

    if (DROP_COMMANDS.has(name)) return "";

    // Unknown command: drop the name, keep a braced argument if
    // one follows (fail-visible: the content is never deleted).
    this.skipSpaces();
    if (this.s[this.i] === "{") {
      this.i++;
      return this.parse(true);
    }
    return "";
  }
}

/**
 * Tighten a converted string: collapse repeated spaces, drop
 * spaces inside parens around operators, attach "(" to a
 * single-character factor (x (x-1) -> x(x-1)), drop spaces
 * around ^ and _, and normalise line breaks. Only applied to
 * text that went through LaTeX conversion.
 */
function tighten(input: string): string {
  const collapsed = input.replace(/[ \t]+/g, " ");
  let out = "";
  let depth = 0;
  for (let k = 0; k < collapsed.length; k++) {
    const ch = collapsed[k];
    if (ch === "\n") {
      out += ch;
      continue;
    }
    if (ch === "(") depth++;
    if (ch === ")") depth = Math.max(0, depth - 1);
    if (ch === " ") {
      // Space before "(": attach to a 1-char factor or ")".
      let j = k + 1;
      while (collapsed[j] === " ") j++;
      if (collapsed[j] === "(") {
        const before = out.replace(/\s+$/, "");
        const last = before[before.length - 1] ?? "";
        const word = /[A-Za-z0-9_]+$/.exec(before)?.[0] ?? "";
        if (last === ")" || last === "]" || word.length === 1) {
          out = before;
          continue;
        }
      }
      // Space around ^ or _.
      const prev = out[out.length - 1] ?? "";
      let n = k + 1;
      while (collapsed[n] === " ") n++;
      if (prev === "^" || prev === "_" || collapsed[n] === "^" || collapsed[n] === "_") {
        continue;
      }
      if (depth > 0) {
        // Inside parens: drop spaces next to ( or ) and around
        // operators.
        if (prev === "(") continue;
        const next = collapsed[n] ?? "";
        if (next === ")") continue;
        const ops = "+-\u00d7\u00f7*/=<>";
        if (ops.includes(prev) || ops.includes(next)) continue;
      }
      out += ch;
      continue;
    }
    out += ch;
  }
  // One newline per line break; trim every line and the ends.
  return out
    .split("\n")
    .map((line) => line.trim())
    .filter((line, idx, lines) => {
      if (line !== "") return true;
      // Keep a single blank line between two non-empty lines.
      return idx > 0 && idx < lines.length - 1 && lines[idx - 1] !== "" && lines[idx + 1] !== "";
    })
    .join("\n")
    .trim();
}

export function formatMathText(text: string): string {
  if (!text) return text;
  // No LaTeX markers: plain text passes through byte-for-byte.
  // ^{...} / _{...} count as markers too: a bare x^{2} is LaTeX
  // even though it holds no backslash.
  if (
    !text.includes("\\") &&
    !text.includes("$$") &&
    !text.includes("^{") &&
    !text.includes("_{")
  ) {
    return text;
  }
  const parsed = new Parser(text).parse(false);
  // "\u0000TRIM\u0000" marks a dropped \times: remove the space
  // that preceded it (the "(" already follows it directly).
  const trimmed = parsed.replace(/ ?\u0000TRIM\u0000/g, "");
  return tighten(trimmed);
}
