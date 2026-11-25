# M4 — Dart Parser Port Specification (Part B-spec)

**Status:** SPEC ONLY — no Python code, no Flutter changes.
**Date:** 2026-11-21
**Sources (read-only):** `~/workspace/officerpath-ai/lib/services/mcq_parser.dart`
(5,734 lines), `answer_key.dart` (1,535 lines), `parse_validation.dart`
(254 lines), `paper_identity.dart` (387 lines),
`lib/services/extraction/format_registry.dart` (183 lines),
`lib/services/extraction/layout_patterns.dart` (233 lines),
`lib/models/question.dart` (583 lines), plus `lib/models/exam.dart`
(`Subject` enum) and `lib/services/book_structure.dart`
(`PageText`, `flattenPages`, `detectBookStructure`) and
`lib/services/pdf_text_extractor.dart` (bold-marker plumbing only).
No file in `~/workspace/officerpath-ai/` was modified.

**Purpose.** The Python engine (M4) ports the Flutter app's MCQ parser
rules — it does **not** invent new semantics. This spec extracts the
exact Dart rules with `file:line` references, states the Python port
requirement for each, and marks every place the Dart code has **no
rule** as **DECISION NEEDED** instead of inventing one.

**Standing rules (do not contradict):** truth over completeness (never
fabricate answers); category separation (digits only in number slots,
letters only in option markers); Urdu text preserved exactly (no
transliteration/stripping); sequence validation; paper-identity gate
(questions must belong to the same paper, never merge across
documents); duplicates flagged, never deleted; answer precedence:
manual verification > explicit key > inline answer > digital style >
visual > inferred. Note: the Dart precedence chain itself is
`answer-line > key > tick > bold > asterisk > AI inference`
(`mcq_parser.dart:85-91`); "manual verification" sits above it in the
app (manual correction overwrites with source `'manual'`, confidence
1.0 — see §5), "digital style" is the bold signal, "visual" is the
tick/asterisk signals, and "inferred" is the parked AI path.

**How to read the tables.** `Dart behaviour` is what the code does,
quoted or paraphrased with its exact regex where it matters.
`file:line` is the definition site (doc comments immediately above it
are part of the rule). `Python port requirement` is the behaviour M4
must reproduce. `DECISION NEEDED` means the Dart code has no rule and
M4 must decide — it is **not** a Dart rule.

**Entry points.** `parseMcqs(rawText, …)` for TXT/pasted text (page 0,
part `''`) — `mcq_parser.dart:531`. `parseMcqsFromPages(pages, …)` for
PDF/OCR, per-page text in page order; every question is tagged with
its 1-based PDF page and book part; `ocrPages` is the set of 1-based
pages whose text came from OCR — `mcq_parser.dart:576`. Both funnel
into `_parseImpl` (`mcq_parser.dart:2135`). Routing gate:
`localParseSuffices` — the deterministic local parser wins whenever
`parsedCount > 0`; AI is only a last resort at 0, and only with the
user asked first (`mcq_parser.dart:497`). AI generation/inference is
PARKED by the governing spec (19 Nov 2026); answerless questions stay
pending for manual correction, never guessed.

**Formats the Dart parser knows** (`format_registry.dart`, `FormatRegistry.all`;
`mcq_parser.dart:9-105` header doc):
| id | Shape | Code |
|---|---|---|
| `block` | Standard block: numbered Q + 4 option lines + answer line / key / tick / bold / asterisk | `_parseImpl` block loop |
| `one-liner` | Q + all 4 options on one line, markers `(a)`–`(d)` / `A.` / `1)` / `(i)` | `_parseOneLiner` (`mcq_parser.dart:5576`) |
| `q-only` | Q + direct answer, options built from the book's own answer pool | `_qOnlyAnswer` (`mcq_parser.dart:5713`) |
| `flashcard` | `?` + short plain answer, no options, no `Ans:` marker | `_scanFlashcards` (`mcq_parser.dart:4452`) |
| `table` | Printed `Question \| A \| B \| C \| D \| key \| type` grid, row-wise or column-wise | `parseTableFormat` (`mcq_parser.dart:2071`) |
| (fact cards) | `Label: Value` infographic facts, not MCQs | `_extractFacts` (`mcq_parser.dart:4936`) |

`ParseResult.formatCounts` reports counts per format (`block`,
`one-liner`, `q-only`, `table`) — `mcq_parser.dart:145-304`.

---

## 1. Question-number detection

| # | Rule | Dart behaviour | file:line | Python port requirement |
|---|---|---|---|---|
| 1.1 | Clean number regex | `^(?:Q\s*\.?\s*)?(\d+)\s*[\.\)\:](?!\d)`, case-insensitive. Accepts `Q12.`, `12.`, `Q.12:`, `Q.1:`, `12)`. The separator must NOT be followed by another digit — a decimal (`92.97 m …`) is not a question number. | `mcq_parser.dart:385` (`_questionNumberDetailed`, :384) | Port verbatim, including the `(?!\d)` guard and case-insensitivity. |
| 1.2 | OCR-misread number fallback | If the clean regex fails, retry with the number token as `ocrNumberTokenPattern` and separator `.` or `)` ONLY (never `:` — `S1:`/`S6:` are source-bank sequence labels, and `S1` decodes to 51), same `(?!\d)` guard. Decoded via `decodeOcrNumber`; a token with no real digit is not a number. `decoded=true` only when the number came from a misread token. | `mcq_parser.dart:394-406`; `answer_key.dart:144-153` (pattern), `:89` (decoder) | Port verbatim. A decoded number is evidence, never a fact — it must pass sequence validation (§4). |
| 1.3 | OCR digit-confusion map | `decodeOcrNumber`: `I/i/l/L→1`, `O/o→0`, `S/s/$/§→5`, `B/b→8`, `Z/z→2`. Only letters map to digits, never digit→digit. Pure-digit tokens: any length (books number past 999; the source bank runs to 3212), result must be ≥ 1. Letter-bearing tokens: max 3 chars, every char a digit or confusable letter, must contain ≥ 1 real digit; bare letter (`B.`, `S.`) → null. | `answer_key.dart:74-141` | Port verbatim, including the length cap and the ≥1-real-digit rule. |
| 1.4 | OCR number-token pattern | `ocrNumberTokenPattern = (?:\d+\|\d[0-9IiLlOoSsBbZz$§]{0,2}\|[IiLlOoSsBbZz$§]\d[0-9IiLlOoSsBbZz$§]?\|[IiLlOoSsBbZz$§]{2}\d)` — pure digits any length, else 1–3 chars with at least one real digit (alternation, because a regex cannot express "at least one digit" inside a character class). | `answer_key.dart:153` | Port verbatim. Use wherever a number is MATCHED; always decode via `decodeOcrNumber` where its VALUE is needed. |
| 1.5 | Misread-number start test | `isMisreadNumberStart`: `^(?:Q\s*\.?\s*)?([0-9IiLlOoSsBbZz$§]{1,3})\s*[\.\)](?!\d)\s*\S`, then `decodeOcrNumber(group 1) != null`. Separator `.`/`)` only, never `:`. Guards `6.2x20 = 124.` (decimal/equation, not Q6). | `mcq_parser.dart:424-430` | Port verbatim. Used by the block splitter (`_parseImpl`) as an alternative question-start test. |
| 1.6 | Bare number (`52 Who …?`) | `_bareNumberAtStartDetailed`: pure digits `^(\d+)\s+(?![a-z0-9])` (any length — a year like 1947 is a bare number too), else a misread token decoded via `decodeOcrNumber`. Case-sensitive on purpose (see 1.7). | `mcq_parser.dart:438-451` | Port verbatim. |
| 1.7 | Bare-number strip | `_stripQuestionNumberPrefix`: strips dotted/`Q` forms via `questionPrefixRe`, plus a BARE number only when the text ends with `?`/`؟` (a complete question stem). A wrapped stem with no `?` keeps its number; a list item (`3 apples are red.`) or year line never ends with `?` so never strips. Residual known ambiguity: a question OPENING with a year (`1947 Was a leap year?`) loses the year. The bare strip is case-sensitive because `questionPrefixRe` is case-insensitive and `[a-z]` would then also match capitals, rejecting `3 What …`. | `mcq_parser.dart:472-495` | Port verbatim, including the `?`/`؟` end-condition and the known year ambiguity (do not "fix" it silently). |
| 1.8 | Shared prefix regex | `questionPrefixRe = ^(?:Q\s*\.?\s*<ocrToken>\s*[\.\)\:]?\|Q\s*[\.\)\:]|<ocrToken>\s*[\.\)\:])\s*`, case-insensitive. Handles `Q.1:`, `Q1.`, `Q. 1.`, `Q.`, `1.`, `12)`. The bare-`Q` alternative requires a separator, so `Quality …` is never stripped. No bare-number alternative lives here (see 1.7). | `answer_key.dart:183` | Port verbatim. |
| 1.9 | Block-split question start | `_parseImpl` splits blocks at lines matching `^(Q\s*\d*[\.\)\:]|\d+[\.\)](?!\d))\s*\S` (case-insensitive) OR `isMisreadNumberStart`. | `mcq_parser.dart:2265-2275` | Port verbatim. |
| 1.10 | Unnumbered question start | A line ending in `?`/`؟`, length > 8, with ≥ 2 option lines following within 8 lines, is a question start — BUT only when the current block is not an unfinished question (current block already has option lines, or its first line is not a question start). A flashcard (`?` + short answer, no options) never splits. Guards: `firstOptionClose` — first option within 4 lines, at most 2 non-option lines between, and no intervening line > 70 chars (prose runs are long; genuine stems are short). | `mcq_parser.dart:2366-2400` (incl. `firstOptionClose`, `optionsFollow`) | Port verbatim, including all three guards (distance, count, length). |
| 1.11 | Bare-number question start | A line ending in `?`/`؟` whose leading bare number parses (`_bareNumberAtStart != null`) is a question start. The `?` terminator is what makes it safe: list items and years do not end with `?`. | `mcq_parser.dart:2406-2415` | Port verbatim. |
| 1.12 | Numberless stems | A plausible stem start (> 1 word, not a bare domain/junk line like `Mcqsplanet.com`, not digit-start, short enough to be an instruction line) can split a block after a finished question. PPSC-66 p1: Q3–Q9 have no number in the OCR and were swallowed into the previous block before this rule. | `mcq_parser.dart:2417-2600` (block-split loop) | Port verbatim. |
| 1.13 | Cut-off numbers at scan edges (page-edge clipping) | **No direct "clipped number" rule exists.** What exists is *number recovery by interpolation* (§4.3): a run of numberless OPTION-bearing blocks is numbered only when the run length exactly fills the gap between its numbered neighbours; a leading run before the first numbered block counts back from it (numbering starts at 1); a trailing run is left null (a new section may restart numbering there). Only option-bearing blocks consume a number; junk blocks never do. Grouping is by the paper of the block's FIRST OPTION line, not its first line (front matter before a paper heading carries the default paper). | `mcq_parser.dart:2594-2660` | Port the interpolation exactly, including the exact-fill condition and the trailing-run refusal. **DECISION NEEDED:** a number physically clipped mid-token (e.g. `1` with the `.` cut off, or a number split across two lines) has no Dart rule — M4 must decide whether to treat it as numberless (interpolation path) or leave it null. |
| 1.14 | Worked-solution blocks | `Solution:` … `Final Answer:` is ONE block with its question; numbered working steps (`2. Let x be …`) must never split the block. A solution with no answer line only splits at a question-start line when option lines follow within a few lines. `solutionHeadingRe = ^\s*solution\s*(?:[:\-]\s*(.*))?$` (case-insensitive); `finalAnswerRe = ^\s*final\s+answers?\s*:\s*(.+)$`. | `answer_key.dart:205-235`; `mcq_parser.dart:2260-2265`, block-split loop | Port verbatim. Solution working lines are explanation, never new questions/options. |
| 1.15 | Multi-line stems / cross-page stems | Question text = first line (prefix stripped) + continuation lines: plain lines after it, before the first option/answer/explanation/subject line, at most 3, stopping after a line ending in `?`/`؟`. A stem may cross a page break: continuation moves forward one page at a time (never backwards, never skip a page); page furniture at the boundary (footer `Page 1`, running header) is SKIPPED, never joined. Page 0 = unknown, no page check. The `?` test uses the CLEANED line (a trailing bold marker U+E000 after `?` would otherwise swallow the next line). | `mcq_parser.dart:4170-4255` (`_splitQuestionAndRest`) | Port verbatim, including max 3 continuations and the furniture skip. |

## 2. Option-marker detection and option splitting

| # | Rule | Dart behaviour | file:line | Python port requirement |
|---|---|---|---|---|
| 2.1 | Lowercase markers | **Yes — handled everywhere.** All option regexes use `[A-Da-d]` / `[A-Ea-e]` (case-insensitive classes). The Urdu NOA file's lowercase `a. b. c. d.` markers are therefore covered. | `mcq_parser.dart:4756` (`_optionRe`); `answer_key.dart:433` (`_optionLineRe`), `:455` (`_markerRe`) | Port verbatim. Never assume uppercase-only. |
| 2.2 | Option-line markers (own line) | `_optionRe = ^\(?([A-Da-d])[\)\.\:\-]\s*(.+)$\|^\(([80])[\)]\s*(.+)$`. Accepts `(A)`, `A.`, `A)`, `A:`, `A-`, `b.`, `(C)`. Misread digits `8`/`0` match ONLY parenthesised (`(8)`, `(0)`) — a bare `8.` is a question number (Q8), never an option marker. Groups: 1 = letter, 2 = letter rest, 3 = digit marker, 4 = digit rest; the single extraction site reads `2 ?? 4`. | `mcq_parser.dart:4756-4762` | Port verbatim, including the parenthesised-only digit rule and the `decodeOcrOptionLetter` decode (§2.5). |
| 2.3 | 5th option marker (E) | `_optionERe = ^\(?([Ee])[\)\.\:\-]\s*(.+)$` — used ONLY inside `_parseStandardBlock` after A–D are already collected, so prose `E. coli` is never mistaken for an option. `_optionRe` stays A–D everywhere else. | `mcq_parser.dart:4763-4767`; use at `:5428-5430` | Port verbatim (E is opt-in after A–D, never a general marker). |
| 2.4 | Inline markers (one-liner) | `_markerRe = [\(\[]?\s*(iv\|iii\|ii\|i\|[a-dA-D]\|[1-4])\s*[\)\.\:]`, case-insensitive. One-liner requires a complete consecutive sequence `a,b,c,d` or `1,2,3,4` or `i,ii,iii,iv` (checked as a 4-window over the marker matches) AND real question words (≥ 3 chars) before the first marker — so a compact key line `1. A 2. B 3. C 4. D` (no question words) is not a one-liner. Markers may be separated by spaces, commas or semicolons. | `answer_key.dart:455-460` (`_markerRe`); `:733-760` (`_isOneLinerQuestion`); `mcq_parser.dart:33-41` (doc) | Port verbatim. |
| 2.5 | OCR-misread option letters | `decodeOcrOptionLetter`: `8→B`, `0→D` only — they can never be option numbers (options are 1–4), so the decode is unambiguous. `4` is NOT decoded: it is both a valid option number (4th option = D) and a misread of A. Evidence: Tesseract on PPSC-66: `(0)` 26×, `(8)` 15×. | `answer_key.dart:156-166`; `_misreadAnswerLetterIndex` at `:1100-1110` | Port verbatim. Never decode `4`. |
| 2.6 | Multiple options on one line (split) | `_splitOptionLine`: marker regex `(?:^\|[\s\(,;])\(?\s*([A-Da-d])\s*[\)\.\:\]\|(?:^\|[\s,;])\(([80])\s*[\)\.\:]` — the marker must start at a word boundary (start of line, whitespace, `(`, `,`, `;`). Returns null when: fewer than 2 markers; markers are not a consecutive run (A,B / B,C / A,B,C,D …); a non-empty prefix does not open the set at A (a bare two-option line `(C) 1944 (D) 1946` may start at any letter); any option text is empty; or more than 4 options. Each option's trailing `[\s,;]+$` is trimmed. OCR-misread markers (`8`/`0`) are decoded BEFORE the consecutiveness check. The word-boundary rule exists because the old regex split `(B) 80 Sec. ✓` at the `c.` of `Sec.` into `["80 Se", "✓"]` with the tick landing on empty C. | `mcq_parser.dart:4272-4330` | Port verbatim, including the word-boundary requirement, the consecutive-run requirement, the prefix-must-start-at-A rule, and the ≤ 4 cap. |
| 2.7 | Options on own lines vs shared line | Standard block: options are collected line by line; two options MAY share one line (`(A) 1941 (B) 1942`, the scanned-paper shape) — the split line's question tail is appended to the question text when its options open the set. A line carrying option markers inline stops question-continuation collection (`_hasInlineOptionMarkers`). | `mcq_parser.dart:4259-4270`; `_parseStandardBlock` (~:5280-5560) | Port verbatim. |
| 2.8 | Wrapped options (continuation) | `_isOptionContinuation(lastOptionText, line)`: line ≤ 80 chars; last option must be an open sentence (no terminal `[.!?:;]`); line must start lowercase OR the last option must end with a function word (`the, a, an, and, or, of, to, in, on, for, with, is, are, was, were, but, not, both, at, by, as, from, that, which, who, when, where`). A long line is explanation prose, never a continuation. The tail (often the `*` marker, e.g. `key repeatedly*`) is joined and the signals are RE-extracted from the joined text. | `mcq_parser.dart:4054-4117` (`_isOptionContinuation`, `joinContinuation`) | Port verbatim, including the 80-char cap and the function-word list. |
| 2.9 | Exactly-4 rule | Every `Question` asserts `options.length == 4` (`question.dart`). Standard block returns null unless options are exactly 4 — or 5 with the E rule (§2.10). A block with 4 options but no usable answer becomes an answer-key candidate, not a question yet. | `mcq_parser.dart:5481` (`options.length != 4 && != 5 → null`); `question.dart:104-115` | Port verbatim. Never relax to 3 or 6. |
| 2.10 | 5 options → 4 normalisation | `_normaliseFiveOptions`: answer A–D → drop E (usually "None"/"None of these"); answer E → keep E's text as the 4th option, drop D (all of A–D are wrong when the answer is E); record which letter was dropped (`dropped: 'E'`/`'D'`). Counts: `ParseResult.fiveOptionNormalised`, `fiveOptionAnswerE`. A 5-option candidate with NO answer cannot become a pending question (normalising needs the answer) — it stays excluded. | `mcq_parser.dart:4777-4810`; counts at `mcq_parser.dart:254-259`, `:3258`, `:3563` | Port verbatim. **DECISION NEEDED:** a 3-option question has no Dart rule (see §8). |
| 2.11 | Option marker inside table cells | `_optionMarkerRe = ^\(?([A-Da-d])[\)\.\:\-]\s*(.+)$\|^\(([80])[\)]\s*(.+)$` — same shape as the block parser; a bare single letter (`A`) is NOT a marker (it can be the article "a" as an option value). A bare `8.`/`0.` is a question number, never a marker. | `mcq_parser.dart:693-706` | Port verbatim for the table path. |

## 3. Category separation / sanitisation

| # | Rule | Dart behaviour | file:line | Python port requirement |
|---|---|---|---|---|
| 3.1 | Number slot = digits only | Every number slot (question numbers, key-entry numbers, bare numbers) is digits or an OCR-decodable token with ≥ 1 real digit (§1.3–1.4). A bare letter is never a number. Key-entry detection (`_isKeyOnlyLine`) requires EVERY number token on the line to decode, else the line is not a key line. | `answer_key.dart:536-580`; `mcq_parser.dart:384-430` | Port verbatim. Never let a letter into a number slot. |
| 3.2 | Letter slot = letters only | Option markers and answer letters are A–E (E only for 5-option); `resolveAnswerToken` bounds-checks the letter against `options.length`, so `E` for a 4-option question resolves to nothing (reported, never force-matched). Answer numbers are 1–`options.length`. | `answer_key.dart:1115-1200` | Port verbatim. |
| 3.3 | What is stripped (stored text) | `_cleanStored(s) = stripBoldMarkers(s).trim()` — ONLY the bold-run marker U+E000 and surrounding whitespace. That is the whole sanitiser for stored question/option/answer text. | `mcq_parser.dart:3994` | Port verbatim. Do not add extra stripping. |
| 3.4 | Bold marker plumbing | The PDF extractor appends U+E000 (private use, never in real book text) at the END of a bold text run; the parser reads it as the "bold" answer signal and strips it before storing anything. Bold detection in the extractor: the font's `/BaseFont` name contains `bold` (e.g. `DejaVuSans-Bold`). | `answer_key.dart:62-71`; `pdf_text_extractor.dart:613-617`, `:703-709`, `:1531-1535` | Python engine must reproduce the marker contract: font-name-contains-`bold` → bold run → marker consumed by the parser, never stored. If the engine's PDF layer cannot do font-bold detection, that is a **DECISION NEEDED** gap (bold signal unavailable, not silently approximated). |
| 3.5 | Tick stripping | `_stripTicks` removes ✓ U+2713 and ✔ U+2714 from stored text. `_stripLeadingTick` handles `✓ B) China`, `✔ B) China`, `(✓) B) China` at line start. | `mcq_parser.dart:3998-4045` | Port verbatim. |
| 3.6 | Asterisk stripping | `_stripAsterisks`: removes a trailing `*` (with optional space before, optional one trailing punctuation mark after: `HTML*`→`HTML`, `F5 *`→`F5`, `Flaming.*`→`Flaming.`). A `*` in the MIDDLE (`2 * 3 = 6`, multiplication) is never a marker and never stripped. | `mcq_parser.dart:4011-4031` | Port verbatim. |
| 3.7 | Ligatures | U+FB00–FB06 → `ff, fi, fl, ffi, ffl, st, st`, applied in `parseMcqs`, `parseMcqsFromPages`, and `_normalizeLigaturesLocal`; idempotent, so double normalisation is safe. | `mcq_parser.dart:507-529` | Port verbatim. |
| 3.8 | Spellings preserved | Spellings are preserved exactly as printed (`SECRATARY` never corrected). The only "repair" is `_recoverMonthDaySpace`, which restores a space the extractor lost between an all-caps word and a following number (`OCTOBER24. 1945` → `OCTOBER 24. 1945`) — and only for fact-card values. Source spellings (`ANTANIO`, `PURTEEGAL`) are left untouched. | `mcq_parser.dart:99-105`, `:4917-4934` | Port verbatim. Never spell-correct stored text. |
| 3.9 | Answer-token cleaning | `_cleanAnswerToken`: strips URLs (`https?://…`, `www.…`); cuts page-number + next-question bleed — (a) `.<space><1-3 digits><space>` when the remainder contains `?`; (b) first bare number when the remainder starts with ANOTHER bare number and contains `?` (with a question-word guard so `Henry 8` survives); (c) bare number + question-stem remainder ≥ 15 chars when it starts with a question word, or ≥ 25 chars when it starts with a capital (noun-start stem). Guards keep `Chapter 5 Summary.`, `Apollo 11 Mission Control`, `The 3 musketeers?` whole. A token that is ONLY a page indicator (`- 2 of 62`, `Page 11`) is footer debris, never an answer — but a bare number alone (`42`) CAN be a legit answer and is kept. | `mcq_parser.dart:5123-5182` | Port verbatim, including the 15/25-char thresholds and the question-word guard list (`hat|hich|ho|hom|hose|hen|here|hy|ow|ame`). |
| 3.10 | Answer-tail stripping | `_stripAnswerTail` removes a trailing `Ans: …` / `Answer: …` / `Correct: …` tail from question text (`\b((?:correct|right)\s+answers?|ans|answer|correct)\s*[:\-]`). | `mcq_parser.dart:4737-4754` | Port verbatim. |
| 3.11 | Case handling | Stored text is never lowercased. Lowercasing is used only for comparisons (answer-text matching, duplicate-text keys, title normalisation). | Throughout; e.g. `answer_key.dart:1115-1200`, `parse_validation.dart:150-160` | Port verbatim. |
| 3.12 | Noise filtering (lines) | `isNoiseLine`: bare digit line (`^\d{1,4}$`); promo lines containing `like`+`follow`+`facebook`, or `for more informative material`; running headers `Papers of YYYY NNN` and `NN … (Volume N)`; bare phone-number lines (only digits/spaces/`+ - ( ) .`, ≥ 7 digits, no letters). Exception: `_isNumericOptionRun` — a run of ≥ 3 consecutive bare-digit lines is a numeric option set (`3/4/5/6`), not page numbers, and is kept for the table pass. Noise lines are dropped BEFORE any heading/key/question check and counted in `noiseLinesFiltered`. | `answer_key.dart:469-534` | Port verbatim, including the ≥ 3 numeric-option-run exception. |
| 3.13 | Noise filtering (blocks) | `_isForeignScriptNoiseBlock`: a block with no question/option/answer structure whose letters are majority non-Latin, non-Arabic script (Bengali, U+0980–U+09FF). **Urdu/Arabic-script content is NEVER noise** — it lives inside question blocks, so the check only fires on blocks with no question structure. Counted as filtered noise, not silently dropped. | `mcq_parser.dart:4842-4875` | Port verbatim. Never classify Arabic-script content as noise. |
| 3.14 | Defective questions | `_defectReason`: an option matching `\[\s*(cut\s*off|missing|illegible|not\s*clear|unreadable|damaged|torn|blurred|incomplete)\s*\]` (case-insensitive), or a `could not (be) determine` / `cannot (be) determine` / `not determinable` note in the lines after the question text (never the stem itself). Defective questions are EXCLUDED with the book's own reason, never guessed, never silently dropped. | `mcq_parser.dart:4813-4839`, `:4998-5017` | Port verbatim. |
| 3.15 | Explanation / associated-information blocks | A whole-line `Explanation:` / `Associated Information:` heading (optional leading bullet/dash, optional colon) opens a drop: its prose + bullets are dropped from question lines — BUT only when a complete question (with options) precedes it (`questionHasOptions`), so an OCR line-break inside a stem (`… / explanation:` in PPSC-66 Q23) never deletes a question. The block ends at the next real question (question start with options following) or a heading. Known accepted limitation: a numberless stem after an explanation is swallowed (in that book the questions after explanations are numbered). | `answer_key.dart:405-420` (`_explanationHeadingRe`); `:906-1077` (`segmentLines`) | Port verbatim, including the `questionHasOptions` guard and the accepted limitation. |
| 3.16 | Notes | `(Note: …)` / `(Note - …)` / `Note: …` lines (`noteContent`, `answer_key.dart:240-260`): attached to the nearest preceding question's `explanation` (prefixed `Note: `); the full list is kept in `ParseResult.notes`, unmatched ones in `unmatchedNotes` — never silently discarded. `_noteMatchesOptions` is a cheap substring proxy; real matching is the AI agent's job. | `answer_key.dart:240-260`; `mcq_parser.dart:235-252` | Port verbatim. |

## 4. Sequence validation

| # | Rule | Dart behaviour | file:line | Python port requirement |
|---|---|---|---|---|
| 4.1 | Gaps reported, never filled | `_computeNumberGaps`: from the sorted set of parsed numbers; any missing number between the lowest and highest is a gap, reported WITH the bounding pages, e.g. `Q9 missing between Q8 (page 1) and Q10 (page 2)`, `Q4–Q45 missing … (42 questions missing)`. A gap is a book problem (page not supplied, or a numbering error in the book), never a parse error. Empty when fewer than 2 numbers. Gaps are reported, never silently renumbered or filled. | `mcq_parser.dart:3942-3973` | Port verbatim. Output strings must carry the same information (range + bounding pages). |
| 4.2 | Duplicates reported, never merged | `_computeNumberDuplicates`: `Q8 appears twice (page 1, page 2)`. Both copies are kept as parsed (two different questions in the book); the duplication is reported in the preview diagnostics — never silently merged, never silently dropped. A number parsed twice on the SAME page is reported the same way. | `mcq_parser.dart:3975-3988` | Port verbatim. |
| 4.3 | Decoded-number demotion | A number from an OCR-misread token survives ONLY when it fits strictly between the trusted (clean-digit or sequence-interpolated) numbers around it in the SAME paper. Demote to null when: it duplicates a trusted number, or is not strictly after the previous accepted number, or is not strictly before the next trusted number. A demoted block stays pending and can never join a wrong key entry. Clean numbers are NEVER demoted (a genuinely misnumbered book is the book's own defect, reported by the diagnostics). Only option-bearing blocks are validated. | `mcq_parser.dart:2662-2760` | Port verbatim. This is the category-separation enforcement for numbers. |
| 4.4 | Number tracking | `parsedNumberPages: Map<int, List<int>>` — one entry per parsed question (a number parsed twice has two entries), driving the gap/duplicate diagnostics. Recorded only when a question is actually built (standard/one-liner/key-join paths call `recordNumber`). Bare-numbered books get NO gap report (`_questionNumber` deliberately does not accept bare numbers — a stray year would pollute the numbering diagnostics). | `mcq_parser.dart:2220-2235`, `:472-495` | Port verbatim, including the bare-number exclusion from gap diagnostics. |
| 4.5 | Validation layer (separate module) | `validateParseResult` (`parse_validation.dart`) never mutates, never repairs — it only reports. Missing answers → `info`; duplicate question TEXT (key = `text.trim().toLowerCase()`, counted per exact text) and duplicate NUMBERS → `error`; conflicting answers and unmatched key entries → `warning`; suspected fabrications → `warning`. | `parse_validation.dart:130-230` | Port as a separate validation step with the same severities. **DECISION NEEDED:** the duplicate-TEXT check lives in validation, not the parser — M4 must decide whether the Python engine reports it from the same layer or folds it into the parse result. |
| 4.6 | Fabrication suspects | `_looksFabricated` (only for `answerSource` `flashcard`/`q-only`): (a) starts with an option-letter marker `^\(?[A-Da-d]\)` — a key fragment, never a stem; (b) bullet label `^[-–—•]\s`; (c) dash-label tail `\s+[-–—]\s+[A-Z][^:]{0,40}:\s*$`; (d) short bare label ending `:` with no `?` and no instruction verb, ≤ 5 words (`choose, select, identify, what, which, who, when, where, give, name, find, translate, fill, complete` are instruction verbs and exempt). Flagged for review, never presented as verified. | `parse_validation.dart:232-254` | Port verbatim, including the instruction-verb exemption list. |

## 5. Paper-identity gate

| # | Rule | Dart behaviour | file:line | Python port requirement |
|---|---|---|---|---|
| 5.1 | Segments | `segmentText`/`segmentLines` split lines into question lines + key sections. Paper headings (`Paper 1`, `Paper No. 1`, `Test 2`, `Set A`, optional `Model` qualifier — `MODEL PAPER 66` counts), month headings (`January 2026`, incl. abbreviations normalised to full names), and chapter headings (`Chapter 1`, whole line only) each start a new key-join segment; questions are numbered within each segment. With no headings the whole book is one segment, label `Paper 1` (`defaultPaperLabel`). A chapter is NOT a paper-kind label for the multi-paper count. | `answer_key.dart:892-1077`; heading regexes `:380-460` | Port verbatim, including the `Model` qualifier and month-abbreviation normalisation. |
| 5.2 | Paper-heading shape | `_paperHeadingRe`: `^(?:model\s+)?(paper|test|set|part|section)\s*(?:no\.?|number|#)?\s*([0-9]+|[A-Z])\s*[:\-–—]?\s*$`, case-insensitive — the WHOLE line must be (just) the heading, so `Part 1: Introduction` is not one. Paper references anywhere in a line use `_paperRefRe` (same kinds/ids, `\b` terminated). | `answer_key.dart:380-400` | Port verbatim. |
| 5.3 | Bare key attribution | A bare key heading (no paper named) belongs to the paper whose questions immediately PRECEDE it (`lastQuestionPaper`, updated only outside key sections) — a key at the top of a page belongs to the paper that ended on the previous page, not the paper whose heading follows. | `answer_key.dart:26-35`, `:906-1077` | Port verbatim. Never attribute a bare key to the following paper. |
| 5.4 | Strict paper rule | A key entry joins the question with the same number in the SAME segment — never another paper, even when that paper's own key has no entry for the number. The old cross-paper "second chance" fallback is gone. An explicit paper with no questions is reported (`Key 'Paper 60' mili, lekin is PDF mein Paper 60 ke sawal nahi — key nahi lagayi.`), never silently applied elsewhere. Key entries are CONSUMED on join (`paperKeys.remove(number)`) — an entry that matched nothing in its own segment is reported as unmatched, never given a fallback second chance in another paper. | `answer_key.dart:49-56`; `mcq_parser.dart:3530-3620` | Port verbatim. This is the paper-identity gate. |
| 5.5 | Identity decision | `decideKeyMatch` (`paper_identity.dart:190`): Level 1 — different `sourceDocumentId` → MISMATCH (two books can both print "Model Paper 66"). Level 2 — paper number present on both and different → MISMATCH. Level 3 — title present on both and different after normalisation → MISMATCH. Level 4 — year/exam present on both and different → MISMATCH; agreement is corroboration, never identity. VERIFIED = number + title agree, OR number agrees with a second corroborating field (year/exam). HIGH CONFIDENCE = an identifier agrees + position + coverage, OR a bare key + position + coverage + (single paper in document OR exclusive coverage). NEEDS REVIEW = bare key in a multi-paper document with non-exclusive coverage, or an identifier agrees but position/coverage evidence is missing. UNVERIFIED = no identity and no evidence. Coverage alone is NEVER sufficient for VERIFIED; numbers alone are never sufficient. | `paper_identity.dart:54-387` | Port verbatim, including the confidence ladder. Only VERIFIED auto-assigns silently; HIGH CONFIDENCE is applied but flagged in `keyPaperReport` (preview + Save is the confirmation); NEEDS REVIEW / UNVERIFIED / MISMATCH are never applied — their entries are WITHHELD (removed from the join map, so they are never reported as "unmatched"; the decision reason is reported instead). |
| 5.6 | Title normalisation | `normalisePaperTitle`: lowercase, collapsed whitespace, leading qualifier (`model|mock|sample|past`) removed, trailing punctuation removed. `Model Paper 66` and `PAPER 66` normalise to the same string; `Model Paper 66` and `Model Paper 67` do not. | `paper_identity.dart:121-130` | Port verbatim. |
| 5.7 | PaperIdentity fields | `sourceDocumentId` (required), `exam`, `year`, `departmentOrPost`, `paperNumber` (string-compared, so `66`≠`67` and letter papers work), `paperTitle`, `shiftOrSubject`. Every field except `sourceDocumentId` is nullable: a missing field is "unknown", never "matches anything". | `paper_identity.dart:58-115` | Mirror the model (§9). Missing = unknown, never a wildcard match. |
| 5.8 | Orphan explicit-key adoption | `adoptOrphanExplicitKeys`: an explicit key whose named paper has NO questions is adopted for the document's single unlabelled paper ONLY when provably safe: exactly ONE explicit key exists; the key's named paper has no question lines; every question line is in ONE segment, the default paper; question numbers are unique; ≥ 80% of the key's entry numbers appear among the questions. Entries are MOVED into the questions' segment (overwriting a bare-key entry for the same number — explicit identity beats positional). Reported in `keyPaperReport` with the overlap %. Two papers merged with no headings are refused by the uniqueness check; a key covering a different paper's numbers is refused by the 80% check. This was added 21 Nov 2026 for the phone failure where the `MODEL PAPER 66` heading was not read by OCR and all 100 key entries came back "no matching question". | `answer_key.dart:1456-1498`; called at `mcq_parser.dart:2196-2200` | Port verbatim, including all five conditions and the 80% threshold. |
| 5.9 | Key-paper report | `ParseResult.keyPaperReport`: per-paper attribution (`Key 'Paper 60' se 42 jawab lage.`), HIGH CONFIDENCE flags (`… HIGH CONFIDENCE se lagi — <reason> Save karne se pehle tasdeeq karein.`), withheld-key reasons (`Key '<paper>' nahi lagayi — <reason>`), no-questions keys, and adopted-key notes. Human-readable strings (see §8 gap: no structured paper identity on `Question`). | `mcq_parser.dart:3855-3910` | Port verbatim (same strings, same Roman-Urdu wording). |
| 5.10 | Attached (separate) key | `applyAttachedKey` (`answer_key.dart:1238+`): a separately attached key (typed/pasted, or read from a key photo/PDF) is segmented exactly like book text; entries under a named paper scope to that paper ONLY; entries under NO named paper (bare key) apply to every pending question by number; a pending question looks in its own paper's entries first, then the bare entries. `?` stays pending; an entry resolving to no option is reported in `unresolvedNumbers`, never force-matched; zero parseable entries → `parseFailed`, guess nothing. | `answer_key.dart:1205-1370` | Port verbatim. **DECISION NEEDED:** whether M4 supports a separately attached key at all (it is an app flow, not a parse rule). |

## 6. Answer detection

| # | Rule | Dart behaviour | file:line | Python port requirement |
|---|---|---|---|---|
| 6.1 | Precedence | `answer-line > key > tick > bold > asterisk > AI inference`. Implemented in `_resolveSignals` (answer-line/tick/bold/asterisk) plus the second-pass key join (key outranks tick/bold — conflicts recorded when they disagree). When signals conflict, the higher-precedence one wins and the conflict is recorded in `ParseResult.conflicts` — never silently resolved. `answerSources` counts questions per source (`answer-line`, `key`, `tick`, `bold`, `asterisk`, `flashcard`, `ai`) for the preview. | `mcq_parser.dart:85-93`, `:4332-4420` (`_resolveSignals`), `:3530-3600` (key join) | Port verbatim. Manual correction sits above all of this in the app (`withCorrection` → source `manual`, verified, confidence 1.0). |
| 6.2 | Explicit answer line | `_answerLineRe = ^(?:Final\s+Answers?\|(?:Correct\|Right)\s+Answers?\|Correct\|Right\|Answers?\|Ans\|Key)\s*[:\-]\s*(?<token>.+)$`, case-insensitive. Covers `Answer: C`, `Ans: (c)`, `Correct: Islamabad`, `Correct Answer: B) Asif Ali Zardari`, `Right Answer: A`, `Answer Key: C`, `Final Answer: (C) 80`. A lone singular `Answer:` never OPENS a key section (see 6.4) — but it IS an answer line. | `mcq_parser.dart:5030-5033` | Port verbatim. |
| 6.3 | Bare answer line | `_bareAnswerRe = ^[\(\[]?\s*([A-Da-d1-4])\s*[\)\]]?\s*$` — a lone `(c)` / `C` / `3` on its own line is an answer (one-liner path). | `mcq_parser.dart:5034` | Port verbatim. |
| 6.4 | Answer-key section | Heading words after stripping paper refs/parens: `^(answer\s*keys?\|answers?\|answer\s*sheet\|correct\s*answers?\|keys?)\s*[:\-–—]?\s*$` (`_keyCoreRe`), incl. `(Answer Key)` and `Answer Key (January 2026)` forms. A key section runs until the next paper/key heading, the next real question, or end of text. Key-section lines are EXCLUDED from question parsing. A key section ends early at a question start with options following (lookahead ≤ 12 lines; option lookahead stops at the next heading/question start so a LATER question's options can never end the section early). | `answer_key.dart:405-420` (`_keyCoreRe`), `:602-660` (`isAnswerKeyHeading`), `:767-790` (`_startsQuestionWithOptions`), `:906-1077` | Port verbatim. |
| 6.5 | Merged key heading (OCR line-merge) | `keyHeadingRemainder`: a line whose START is a key heading but which carries more text (`ANSWER KEY: 1. (B) Broke out`, `ANSWER KEY: English Grammar`) opens the section and feeds the remainder back as its first content line — never dropped. The remainder must itself look like key content (a key-entry start, or a short title-cased subhead 3–45 chars, no trailing sentence punctuation). The plural is REQUIRED in the bare `Answers`/`Correct Answers` alternatives — singular `Answer:` would open a spurious section at every answered question. A bare answer token in parens (`(B)`) is never a subhead. | `answer_key.dart:663-732` | Port verbatim. This rule exists because of the v2.0.4 phone failure — see §10. |
| 6.6 | Key-entry parsing | `parseKeyEntries` treats a key section as ONE token stream (compact runs `1.C 2.A 3.B …` and multi-column layouts both work — lookup by number, never by position). Entry start: `(?:^\|\s)(?:Q\s*)?(<ocrToken>)\s*[\.\)\:\-,](?=\s\|[A-Ea-e]\b\|\(|$)` — separator also accepts a comma (OCR reads the entry period as a comma: `13, (B) …`); the lookahead blocks thousands separators (`138,000`) and decimals (`43.75%`). Shapes: `1. C`, `1-C`, `1) C`, `1: C`, `Q1: C`, `Q1 C` (rewritten to `Q1: C` first), `1. A) Asif Ali Zardari`, `61. (C) 3`, `62. (A) Portable Document Format`, `1. Asif Ali Zardari` (text). First entry wins when a number repeats. Separator-less rows (`1 B`, `1(B)`) count only as a second pass and only when the blob holds ≥ 3 of them, and never inside a separator entry's value span (`1. (B) 2 Brothers` — the `2 B` is answer text). | `answer_key.dart:433-446` (`_keyEntryStartRe`), `:792-835` (bare-Q normalisation, `_bareKeyEntryRe`), `:837-890` (`parseKeyEntries`) | Port verbatim, including the ≥ 3 separator-less guard and the first-wins rule. |
| 6.7 | Key token resolution | `resolveAnswerToken(token, options)`, tried in order: (1) `Option X` (`^option\s+([A-Ea-e1-580])\b`); (2) paren letter `(C) 80` / `(C)80` (letter wins; trailing value is a cross-check); (3) `B) Asif Ali Zardari` / `2. Paris` — letter/number first, text as fallback; (4) bare number 1–`options.length` → index-1; (5) single letter A–(A+len); (6) exact case-insensitive text match against the options; (7) bare misread letter `8`/`0` → B/D (only AFTER the text match, so a real numeric option value `8` still wins). Returns null when nothing matches. | `answer_key.dart:1115-1200` | Port verbatim IN THIS ORDER — the order is load-bearing (e.g. bare-number-before-text means `3` resolves as an index, not as option text `3`). |
| 6.8 | Unknown key token | `isUnknownKeyToken`: `?`, `??`, or `unknown` (case-insensitive). The question is EXCLUDED with reason, never guessed — and still becomes a `PendingQuestion` with reason `unknown-key` (when it has exactly 4 options). A tick/bold signal does NOT outrank an explicit `unknown`. | `answer_key.dart:447-453`; `mcq_parser.dart:3530-3570` | Port verbatim. |
| 6.9 | Key entry matching no question | Reported in `ParseResult.unmatchedKeyEntries` (`Paper 2 key entry 61 — no matching question`), plus an `errors` summary with a 2-entry sample. Never silently dropped, never force-joined to another paper's questions. Note: WITHHELD keys (§5.5) are removed from the join map and are NOT reported here — their decision reason goes in `keyPaperReport` instead. | `mcq_parser.dart:3601-3620` | Port verbatim. |
| 6.10 | Key-only lines without a heading | `_isKeyOnlyLine`: a whole line of nothing but key entries (`1. D 58. B 73. A 88. B`, `57. A`, separator-less rows of ≥ 3 contiguous pairs) is captured for the paper whose questions precede it — the fallback for key tables whose heading was separated from its entries by column reordering (MPT 4-column key table on a page shared with Q199/Q200). Every number token must decode; a bare letter (`B. C`) is a list marker, never a key entry. | `answer_key.dart:536-580` | Port verbatim. |
| 6.11 | Tick mark | ✓ U+2713 or ✔ U+2714, before or after the option text (`_hasTick`); leading forms `✓ B) China`, `(✓) B) China` (`_stripLeadingTick`). Exactly one ticked option is a signal; several ticked = ambiguous (null). Tick outranks bold and asterisk; loses to answer-line and key. | `mcq_parser.dart:3998-4045`; `_resolveSignals` `:4332-4420` | Port verbatim. |
| 6.12 | Bold option | Exactly one bold option = the correct answer. Bold is read from the extractor's U+E000 marker (see §3.4); per-option flags travel in `Question.boldOptions` (parallel to `options`, shuffled with them). More than one bold option → bold signal ignored AND a conflict recorded (`N options are bold (A, C) — bold signal ignored, answer still needed.`). | `mcq_parser.dart:4332-4420`; `question.dart:300-315` | Port verbatim. |
| 6.13 | Asterisk (Dogar marker) | Trailing `*` at the END of an option's text, with or without a space before it and one trailing punctuation mark after (`HTML*`, `F5 *`, `Flaming.*`) — `_hasAsterisk = \*\s*[.,;:\)]?\s*$`. This is the answer signal of Dogar-style Pakistani MCQ books, and the Paper 60 photo's star marks (`Q1 (C) F5*`, `Q2 (B) HTML*`). Exactly one asterisked option is a signal; several = ambiguous (null). Lowest precedence of the printed signals. | `mcq_parser.dart:4011-4031`; `_resolveSignals` | Port verbatim. |
| 6.14 | Final Answer cross-check | `_finalAnswerValueConflict`: for `Final Answer: (X) <value>`, the trailing value (e.g. `80`) should be the letter's option text. If it exactly matches a DIFFERENT option's text, a conflict is recorded but the LETTER still wins. If it confirms the letter or matches nothing (OCR junk), no conflict. The value trim is Unicode-aware (`[^\p{L}0-9]+$`) — an Urdu answer value ending in an Arabic-script letter must not be stripped as punctuation. | `mcq_parser.dart:5048-5080` | Port verbatim. |
| 6.15 | Inline answers (Q-only) | `_qOnlyAnswer`: same-line `Q … Ans: X` / `Answer:` / `Key:` (inline regex `\b((?:correct|right)\s+answers?|correct|right|ans|answer|key)\s*[:\-]\s*(.+)$`), else an answer line in the following lines (`_answerTokenFromLines`: first `_answerLineRe` match, else a bare-answer line). A wrapping text answer is joined from the next line when `_isAnswerContinuation` allows it. Footer debris as the "answer" is skipped and scanning continues. | `mcq_parser.dart:5713-5734`, `:5184-5210` | Port verbatim. |
| 6.16 | Answer continuations | `_isAnswerContinuation(next, answerPage)`: same page as the answer line (0 = unknown, no check); line ≤ 80 chars; must not end with `.` (a complete sentence is explanation prose, not a wrapped answer); must not be a bullet/dash line, page footer, header line, question/option/answer/explanation/subject/bare-answer line. Used for multi-line answers (`Correct Answer: Asif Ali` + `Zardari`) and wrapping flashcard answers. | `mcq_parser.dart:4143-4168` | Port verbatim. |
| 6.17 | One-liner answers | Answer on the same line after the last option (`Ans: (c)`, `Answer: C`, `Correct: Islamabad`) or on the next line (a bare `(c)` alone also works). Trailing answer tail is cut from the question text before splitting. | `mcq_parser.dart:5576-5703` (`_OneLiner`) | Port verbatim. |
| 6.18 | No answer → pending, never guessed | A question with 4 options but no usable answer is kept as an `_AnswerlessCandidate` (numbered only, so the key can join it by `(paper, number)`), then as a `PendingQuestion` (`reason: 'no-key-entry'` / `'unknown-key'` / `'option-marker-mismatch'`) with a `questionsMissingAnswers` entry in the same order (`Paper 1 Q4 — no key entry`). It is NEVER counted in `parsed`, NEVER guessed, and (governing spec) is for MANUAL CORRECTION — AI inference is parked. Unnumbered answerless questions cannot join a key and stay pending by text. | `mcq_parser.dart:332-371`, `:3530-3680`; `question.dart:1-100` | Port verbatim. |
| 6.19 | Handwriting | **No separation exists.** The text parser cannot distinguish a PRINTED tick/bold mark from a STUDENT'S handwritten tick on a scanned page — both arrive as the same glyph; that distinction needs the v2 vision step (print is uniform/aligned, handwriting irregular). The Dart rule is flagging, not separation: a tick/bold on an OCR page → question UNVERIFIED, confidence 0.54, `markProvenance='ocr'` (§7). A handwritten note line (`HANDWRITTEN:` / margin note) is handled only as a non-answer label in the flashcard trailing-split path, not as an answer signal. Star marks that are the BOOK's own print (Dogar `*`) are the asterisk signal (§6.13); a student's star is indistinguishable in text. | `question.dart:170-180`; `layout_patterns.dart` (`handwritten-mark`, partial); `mcq_parser.dart:4705-4710` | Port the flagging rule exactly. **DECISION NEEDED:** whether M4 (Python, text stage) adds any handwriting separation — the Dart code explicitly defers it to a vision step that does not exist in the parser. Do not claim separation from text alone. |
| 6.20 | Highlight / colour / italic / circle / underline / cross / OMR | **None detected.** `layout_patterns.dart` lists them as `unsupported` (italic: font-name check covers bold only; highlight/colour: no annotation or colour detection, preprocessing drops colour to grayscale before Tesseract; cross/circle/underline: need extractor geometry, not the parser; OMR: no bubble detection, no sheet alignment, no fill threshold). | `layout_patterns.dart:170-233` | Port as explicit non-support: these signals must NOT be inferred from text. **DECISION NEEDED:** whether the Python engine's image/layout stage adds any of them, and with what evidence — the Dart parser must not be credited with them. |

## 7. Confidence scoring

| # | Rule | Dart behaviour | file:line | Python port requirement |
|---|---|---|---|---|
| 7.1 | Per-question confidence (only) | `Question.confidenceForSource(source, {verified})`: `answer-line`/`key` → 1.0; `tick`/`bold`/`asterisk`/`flashcard` → 0.9; `manual` → 1.0; `ai` → 0.5; unknown → 0.0. Unverified → base × 0.6 (clamped 0–1). Never 1.0 for a mark. There is NO per-option confidence anywhere. | `question.dart:190-215` | Port verbatim. Do not invent per-option confidence. |
| 7.2 | Verified sources | `isVerifiedSource`: `answer-line`, `key`, `tick`, `bold`, `asterisk` ONLY. `flashcard` is explicitly NOT verified (PPSC-66, 20 Nov 2026): a q-only question's options are GENERATED from the answer pool — the book printed no A–D mark on them — so presenting one as verified would certify an answer the book never marked. `q-only` likewise surfaces unverified. | `question.dart:160-168` | Port verbatim. |
| 7.3 | OCR provenance downgrade | In `_parseImpl` post-processing: provenance is `ocr` when the question's page is in `ocrPages` (or `markProvenance == 'ocr'` on the string path), else `printed`. When provenance is `ocr` AND `answerSource` is `tick`/`bold`, the question is rewritten UNVERIFIED with confidence `0.9 × 0.6 = 0.54` and `markProvenance='ocr'`, until the user confirms it in manual correction. An asterisk, key or answer line is printed text, not a pen mark, so it stays verified even on an OCR page. A text-layer/pasted question is `printed`. | `mcq_parser.dart:3820-3850` | Port verbatim, including the 0.54 value and the asterisk/key/answer-line exemption. |
| 7.4 | Verification status | `verificationStatus`: `no-answer` (no answer — never scored, never shown as correct); `verified` (book's own printed/official signal); `unverified` (AI-inferred, conflicting signals, or OCR-sourced tick/bold); `manually-corrected` (user set the answer; `originalCorrectIndex` keeps the extracted one). `correctLetter` is `''` when there is no answer (never `@` — `65 + -1`); call sites must check `hasAnswer` before showing a "correct answer". | `question.dart:120-130`, `:230-260` | Mirror the status derivation. |
| 7.5 | Manual correction | `withCorrection(newCorrectIndex)`: keeps the original extracted index in `originalCorrectIndex` (unless one is already kept), sets source `manual`, verified, confidence 1.0. Correcting an answerless question keeps NO original. | `question.dart:262-285` | Mirror the fields; the correction UI itself is out of M4 scope. |
| 7.6 | Conflicts lower verification | A question whose signals conflicted is unverified (confidence scaled by 0.6 via the constructor default path) even if a winner was chosen — the conflict string is the record. | `question.dart:190-215`; `mcq_parser.dart:4332-4420` | Port verbatim. |

## 8. Duplicate handling

| # | Rule | Dart behaviour | file:line | Python port requirement |
|---|---|---|---|---|
| 8.1 | Duplicate numbers | Both copies kept as parsed; reported with pages (§4.2). Never merged, never dropped. | `mcq_parser.dart:3975-3988` | Port verbatim. |
| 8.2 | Duplicate question text | Detected in validation, not the parser: same `text.trim().toLowerCase()` parsed more than once → `ValidationIssue(error, duplicateQuestion, 'Question text parsed N times.')`. A duplicated question corrupts a test (same question twice, and a key entry could land on the wrong copy). Never merged silently. | `parse_validation.dart:150-165` | Port verbatim (see §4.5 decision note on layering). |
| 8.3 | Duplicate key entries | `parseKeyEntries`: first entry wins when a number repeats (e.g. a key printed twice). Key-join consumption (`remove`) means an entry is used once. | `answer_key.dart:837-890` | Port verbatim. |
| 8.4 | Duplicate pool answers (Q-only) | The distractor pool is a `Map` keyed by normalised (trim + lowercase) answer text — duplicates collapse to one entry; distractors are drawn distinct from the correct answer and from each other. | `mcq_parser.dart:3680-3730` | Port verbatim. |
| 8.5 | Duplicates flagged, never deleted | Standing rule confirmed by code: no dedup deletion exists anywhere in the parser or validation. | Throughout | Port verbatim. |

## 9. Table-format parsing

| # | Rule | Dart behaviour | file:line | Python port requirement |
|---|---|---|---|---|
| 9.1 | Two arrival orders | Column-wise (ML Kit/Tesseract on a scan): all questions, then all option-A values, then B, C, D, then the key letters, then the type labels. Row-wise (text PDF, or Gemini vision asked for rows): question line(s) + 4 bare option lines + key letter + type label, repeated. A row is only accepted when its 4 options are present; the key letter is the correct answer, so no answer-pool or guessing is involved. | `mcq_parser.dart:609-617` (header doc) | Port both orders. |
| 9.2 | Column-wise recognition | A run of ≥ 3 key letters is the anchor; the pre-key region must group into exactly 5N items (N questions + 4N options). Type labels follow the key run. | `format_registry.dart` (`table` descriptor); `mcq_parser.dart:1359-1420`, `:1557-1660` | Port verbatim, including the exactly-5N grouping check and the ≥ 3 key-letter anchor. |
| 9.3 | Row-wise recognition | Question line(s) + 4 bare option lines anchored by a key letter or a type label; ≥ 2 rows; stem ≤ 400 chars. Tick/bold on an option resolves a key-less row; a key-vs-tick/bold disagreement is a recorded conflict, key wins. Rows without a usable key become `PendingQuestion`s, never silently dropped. | `layout_patterns.dart` (`table-row-wise`); `mcq_parser.dart:1646-2130` | Port verbatim, including the ≥ 2-row minimum and the 400-char stem cap. |
| 9.4 | Table precedence | Key > tick > bold (same as the standard path, minus answer-line and asterisk — a table row has no answer line). Conflicts recorded the same way. Each row counts under ITS OWN `answerSource` (`key`/`tick`/`bold`) — the old code counted every row as `key`. | `mcq_parser.dart:1102-1260` | Port verbatim. |
| 9.5 | Table key letters | `_tableKeyLetterRe = ^\(?\s*([A-Ea-e])\s*[\)\.\:]?\s*$` — a standalone letter on its own line. `E` is included because a 5-option table's key can be E. A single A–D letter as an OPTION VALUE is also recognised (the article "a" printed as "A"; row 27: options `A`, `An`, `The`, `None of these`); `E` is never an option — it is always the key of a 5-option row. | `mcq_parser.dart:674-706` | Port verbatim. |
| 9.6 | Extra columns | A table with up to 10 columns is accepted: extra columns (a 5th option, a marks column, a row-number column) are normalised or ignored, never a reason to reject the book. Type labels (grammar type words in the last column, e.g. `Noun`, `Article and its Types`) anchor rows. | `mcq_parser.dart:609-617`; type-label helpers `:757-880` | Port verbatim. |
| 9.7 | Table consumption | `parseTableFormat` runs BEFORE the block loop; its consumed line indices are excluded from it, so the Q-only answer pool never steals a table row. | `mcq_parser.dart:2340-2365` | Port verbatim (table pass first, consume lines). |
| 9.8 | Sr# \| Question \| A \| B \| C \| D \| Ans \| Key tables | **No delimiter-based rule exists.** The Dart table pass is grid/sequence-based (cells, runs, key-letter anchors, type labels) — it never splits on `|` or any other column delimiter, and there is no `Sr#` header rule. The English 1000-MCQs fixture (86 pp, `Sr# | Question | A–D | Ans | Key` rows) therefore has NO Dart rule covering its exact shape; whether the existing row-wise machine accepts its rows is unmeasured. | (absence — verified by searching `mcq_parser.dart`, `answer_key.dart`, `extraction/*.dart` for `Sr`, `\|`, `pipe`, `delimiter`: no matches) | **DECISION NEEDED:** M4 must decide whether to add a delimiter-aware table path for `Sr#`-style grids, or to rely on the existing grid machine and measure it against the fixture. Do not claim the Dart parser handles `|`-delimited tables. |

## 10. Q&A without options, flashcards, and the v2.0.5 phone failure

| # | Rule | Dart behaviour | file:line | Python port requirement |
|---|---|---|---|---|
| 10.1 | Q-only (direct answer) | `Q. What is the capital of Pakistan? Ans: Islamabad` — imported with 4 options built from the correct answer + 3 distractors drawn from OTHER questions' answers in the same book (never the correct answer twice). If the book has fewer than 3 usable distinct distractors, the question is EXCLUDED with its reason — fake options are never invented and items are never dropped silently. Stem must be real: `_isRealQOnlyStem` — ≥ 10 chars, ≥ 2 words, a word ≥ 3 chars (guards against OCR debris like `Wh to e`, `All follo` becoming fake questions with pool-built options). | `mcq_parser.dart:43-53`, `:5704-5734`; Q-only pool build `:3680-3730` | Port verbatim. **DECISION NEEDED:** the pool shuffle uses Dart `Random()` (non-deterministic, unseeded) — M4 must decide whether distractor selection is seeded/deterministic in Python. |
| 10.2 | Computer Past Papers shape (answer right after `?`, no options) | Covered by the flashcard path, not by a dedicated rule: (a) answer on the NEXT line(s); (b) dash-inline (`—`/`–`, never a plain hyphen); (c) trailing answer after the LAST `?`/`:`/`؟` on the same line. Guards: the block must contain NO option line; the answer must be on the SAME page; ≤ 100 chars/line, ≤ 2 lines, ≤ 160 total; plain lines only (not question/option/answer/explanation/header); stop after a line ending in `.`; lines used by an earlier flashcard are never re-used. A `:` split needs a real stem (≥ 3 words / list entry / sentence tail) so a bare label never splits. Answer source `flashcard`, unverified (§7.2). | `mcq_parser.dart:4452-4685` (`_scanFlashcards`); `:4685-4730` (`_trailingAnswerSplit`); `layout_patterns.dart` (flashcard entries) | Port verbatim with all guards. Note the 100/2/160 limits — a long direct answer (e.g. a full sentence answer in the Computer file) that exceeds them has no Dart rule: **DECISION NEEDED** whether M4 keeps the caps or extends them for Q&A-without-options files. |
| 10.3 | Flashcard Urdu | `؟` (U+061F) counts as `?` everywhere it matters: stem-end tests, bare-number strip, trailing-answer split (`text.lastIndexOf(RegExp(r'[?؟]'))`). Comment: "Urdu flashcards (`…کیا تھا؟ قصواء`) end with ؟, not ?; without this they parse 0." | `mcq_parser.dart:4685-4700` | Port verbatim. |
| 10.4 | v2.0.5 phone failure (1 MCQ, 39 key entries matching none) | The code documents TWO mechanisms that produce exactly this shape, both as known phone-failure modes (not as speculation): (1) **Merged key heading** — `ANSWER KEY: 1. (B) …` on one OCR line opened no key section at all, so the key vanished; the Save dialog showed the green "no answers attached" notice although the key is on the page. The 21:38 run detected the key, so the merge is a run-varying ML Kit segmentation effect, not a constant. Fixed in Dart by `keyHeadingRemainder` (§6.5). (2) **Unread paper heading** — the `MODEL PAPER 66` heading was not read by OCR, every question landed under the default paper, and all 100 key entries came back "no matching question". Fixed in Dart by `adoptOrphanExplicitKeys` (§5.8). A third, structural fact: under the strict paper rule, a label mismatch yields UNMATCHED entries rather than wrong answers — by design. And withheld keys (§5.5) are removed from the join map and NOT reported as unmatched, so "39 unmatched" implies the entries WERE in the join map (decision allowed them) but no candidate numbers matched — consistent with a numbering/label mismatch, not a withheld key. Which mechanism caused the specific v2.0.5 run cannot be determined from the code alone. | `answer_key.dart:663-700` (merged-heading comment, incl. the v2.0.4 21:15/21:38 runs); `:1456-1470` (orphan-adoption comment); `mcq_parser.dart:3601-3620` | Port `keyHeadingRemainder` and `adoptOrphanExplicitKeys` exactly — they are the Dart fixes for this failure class. When M4 reports unmatched key entries, it must also report WHICH mechanism is suspected (heading-merge vs label-mismatch vs numbering gap) from the evidence, not guess. **DECISION NEEDED:** what M4 does when the count of unmatched entries is large (e.g. 39) — Dart only reports; it has no retry/fallback rule. |
| 10.5 | Skipped vs excluded vs pending | `skipped` (count) + `errors` entries: blocks that looked like questions but failed every path (need 4 options + an Answer line, a one-liner, or a `Q … Ans: …` line). A block that never looked like a question (title, header, footer) is dropped SILENTLY, not counted as skipped — EXCEPT a numbered/bare-numbered question start, which must be skipped with a reason, never silently dropped. `excluded`: Q-only items with too few distractors, `?`-key questions, defective questions, 5-option answerless candidates — each with its reason. `answerPending`: 4-option questions with no usable answer, for manual correction. | `mcq_parser.dart:3470-3530`, `:3530-3680` | Port the three-way distinction exactly. |

## 11. Urdu-specific handling

| # | Rule | Dart behaviour | file:line | Python port requirement |
|---|---|---|---|---|
| 11.1 | `؟` as question mark | Treated identically to `?` in: question-end tests, bare-number strip, unnumbered/bare-number question starts, flashcard splits, `_splitQuestionAndRest` continuation stops. | `mcq_parser.dart:462-475`, `:1739-1761`, `:2366-2415`, `:4188-4194`, `:4685-4700` | Port verbatim. |
| 11.2 | Urdu text preserved | Urdu/Arabic-script content is never noise (§3.13); the `_finalAnswerValueConflict` trim is Unicode-aware (`\p{L}`) so an Urdu answer value ending in an Arabic-script letter is not stripped as punctuation; statement facts in Urdu (`رسول اللہ ﷺ کے اونٹنی کا نام قصواء تھا۔`) are stored whole with `label == value`. No transliteration, no stripping, no script conversion anywhere in the parser. | `mcq_parser.dart:121-126`, `:5048-5080`, `:4842-4875` | Port verbatim. |
| 11.3 | Urdu digits | **No rule.** No handling of Eastern Arabic numerals (`٠-٩`) or Extended Arabic-Indic digits (`۰-۹`) in question numbers, key entries, option markers, or answer numbers — the digit classes are ASCII `\d` / `[0-9]` throughout. | (absence — verified: no `0660`, `06F0`, or Urdu-digit reference in the parser files) | **DECISION NEEDED:** whether M4 normalises Urdu digits to ASCII before number/marker matching, or treats them as unmatched. Do not assume the Dart behaviour covers them. |
| 11.4 | RTL / Nastaliq | **No rule.** No RTL handling, no Nastaliq-specific handling, no Urdu-script detection for segmentation. The parser operates on the OCR/text line order as given. | (absence) | **DECISION NEEDED:** M4's layout/OCR stage must decide reading order for Urdu lines; the text parser contributes nothing here. |
| 11.5 | Urdu MCQ markers | Lowercase `a. b. c. d.` markers (Urdu NOA file) are covered by the case-insensitive option regexes (§2.1). No Urdu-letter markers exist in the code. | `mcq_parser.dart:4756` | Port verbatim. |

## 12. Remaining edge cases the Dart code explicitly handles

| # | Rule | Dart behaviour | file:line | Python port requirement |
|---|---|---|---|---|
| 12.1 | Page furniture | Page footers (`Page 1`, `Page 1 of 71`, `PPSC Current Affairs \| 40 MCQs Page 1`) are never content: skipped in cross-page stems, never joined to an answer token as a "continuation" (`Correct Answer: B` + footer would corrupt the token to `B Page 1`, resolving to nothing). `_pageFooterRe = page\s*\d+\s*$`. | `mcq_parser.dart:4134-4142`, `:4170-4255` | Port verbatim. |
| 12.2 | `Explanation:` inside a stem | Guarded by `questionHasOptions` (§3.15). | `answer_key.dart:906-1077` | Port verbatim. |
| 12.3 | `E. coli` / abbreviations | `_optionERe` only after A–D (§2.3); `_splitOptionLine` word-boundary rule blocks splits at `Sec.`, `St.`, `No.`, `Rs.` (§2.6). | `mcq_parser.dart:4763-4767`, `:4272-4330` | Port verbatim. |
| 12.4 | Decimal / equation lines | `(?!\d)` guards (§1.1, §1.5); key-entry lookahead blocks decimals (`43.75%`) and thousands separators (`138,000`). | `mcq_parser.dart:385`; `answer_key.dart:433-446` | Port verbatim. |
| 12.5 | `Q1 Correct …` / `FAQ1 C` | `_normaliseBareQEntries` requires the letter not to be followed by a letter/digit and the `Q` not to be part of a longer word. | `answer_key.dart:792-805` | Port verbatim. |
| 12.6 | `Answer: (B)` vs key heading | The trailing-paren strip in `isAnswerKeyHeading` never strips a bare answer token (`(B)`, `1-4`, `A-E`); otherwise `Answer: (B)` would open a key section and swallow the following questions. Same guard in `_looksLikeKeySubhead`. | `answer_key.dart:602-660`, `:700-732` | Port verbatim. |
| 12.7 | Option-marker mismatch | If the option markers in a block disagree (e.g. the set does not run A–D), the question is pending with reason `option-marker-mismatch`, answer not trusted. | `mcq_parser.dart:3530-3570` (pending reason), `:2492-2500` (split guard) | Port verbatim. |
| 12.8 | Front matter / junk | Blocks that never looked like questions are dropped silently (not skipped), with orphan notes attached to the nearest preceding question. Foreign-script ad blocks are counted as filtered noise. | `mcq_parser.dart:3470-3530` | Port verbatim. |
| 12.9 | TODOs / FIXMEs | **None found.** A grep for `TODO|FIXME|XXX|HACK` across `mcq_parser.dart`, `parse_validation.dart`, `answer_key.dart`, `paper_identity.dart`, `extraction/*`, `models/question.dart` returns zero matches. Gaps are documented as `unsupported`/`unmeasured`/`partial` entries in `layout_patterns.dart` and as explicit comments (e.g. the accepted limitations in §3.15 and §1.7), not as TODOs. | (verified 2026-11-21) | No TODO port needed. Treat `layout_patterns.dart` `unsupported`/`unmeasured` entries as the gap list (§6.20, §8.8, §10.4). |
| 12.10 | Multi-question rows | **Unsupported by design:** "No code path splits one line into 2+ questions." (`layout_patterns.dart`, `multi-question-row`.) | `layout_patterns.dart` | **DECISION NEEDED:** M4 must not invent a splitter; if the engine's layout stage produces one question per row, that is an engine decision, not a Dart port. |
| 12.11 | 3-column / 4-column options on one line | **Unmeasured:** "No dedicated detector yet — the inline-option path likely handles it, but there is no real-file proof." | `layout_patterns.dart` (`options-3-4-column`) | **DECISION NEEDED:** measure against real fixtures before claiming coverage. |
| 12.12 | Compact key sequences | **Unmeasured:** "No dedicated detector yet — key sections are parsed line-wise; a compact inline sequence has no test." (Note: `parseKeyEntries` DOES handle compact runs as a token stream — the `unmeasured` status refers to proof, not to absence of code.) | `layout_patterns.dart` (`key-compact`) | Port `parseKeyEntries` (§6.6); treat the status as "needs a real sample + test", not as missing code. |

## 13. Question / output model fields to mirror in Python

### 13.1 `Question` (`lib/models/question.dart:104-380`)

| Field | Type / rule | Notes for Python |
|---|---|---|
| `id` | `int?` | DB id; null before save. |
| `text` | `String` | Stored question text, prefix-stripped, continuations joined with single spaces. |
| `options` | `List<String>`, ALWAYS exactly 4 | Constructor asserts length 4. |
| `correctIndex` | `int`, 0–3, or `-1` when the book gave no answer | `-1` = never guessed, never scored, "correct" never shown. `correctLetter` is `''` when `-1`. |
| `subject` | `Subject` enum | `gk` / `pakStudies` / `islamiat` / `currentAffairs` / `english` / `everydayScience` / `mathsComputer` with labels `General Knowledge`, `Pakistan Studies`, `Islamiat`, `Current Affairs`, `English`, `Everyday Science`, `Maths & Computer` (`exam.dart:11-31`). From a `Subject:` line in the block, else the caller default (GK). **Unknown stored labels silently become GK** (`Subject.fromLabel` + `debugPrint`) — an audited wart, port it or flag it as DECISION NEEDED; do not silently "improve" it without noting the change. |
| `sourceId` / `sourceLabel` | `String` | Which book/paper the question came from (e.g. `ppsc66`). `sourceId` is the `sourceDocumentId` for the paper-identity gate. |
| `explanation` | `String`, default `''` | From `Explanation:` lines; `(Note: …)` evidence appended prefixed `Note: `. |
| `page` | `int`, 1-based; 0 = unknown (TXT/pasted) | Set by the page-aware parse. |
| `part` | `String`, `''` = none | Book part/section (e.g. `Pakistan Current Affairs`, `Paper 1`); assigned by structure detection, preserved through the key join. |
| `answerSource` | `String` | One of `answer-line`, `key`, `tick`, `bold`, `asterisk`, `flashcard`, `manual`, `ai` (legacy only), or `''` (unknown / pre-signal rows). |
| `boldOptions` | `List<bool>`, parallel to `options` | Stored as a 4-char `"0100"` string in `toMap` (sqflite cannot bind a List). Shuffled with options. Empty when boldness was not tracked. |
| `answerVerified` | `bool` | True = book's own printed/official signal; false = AI-inferred, conflicting, or OCR-sourced tick/bold. Defaults from `isVerifiedSource(answerSource)` when not supplied. |
| `confidence` | `double`, 0–1 | Defaults from `confidenceForSource` (§7.1); lowered on conflict / OCR provenance. |
| `originalCorrectIndex` | `int?` | The extracted answer index, kept only when the user manually corrects the answer. Null = never corrected. |
| `markProvenance` | `String` | `printed` / `ocr` / `''` (unknown). Set from the import path (`ocrPages`). |
| `verificationStatus` (derived) | `no-answer` / `verified` / `unverified` / `manually-corrected` | See §7.4. |
| `hasAnswer` (derived) | `correctIndex != -1` | — |

### 13.2 `PendingQuestion` (`question.dart:1-100`)

`text`, `options` (exactly 4), `subject`, `explanation` (default `''`),
`page` (0 = unknown), `part`, `reason` (`no-key-entry` | `unknown-key` |
`option-marker-mismatch`), `number` (`int?`, null = unnumbered — a key
can never match it by number), `paper` (default `''`; e.g. `Paper 60`,
`January 2026`, `Paper 1`). `verificationStatus` is always
`unverified`. Serialised as `option_a…d` + `subject`/`explanation`/
`page`/`part`/`reason`/`number`/`paper`.

### 13.3 `ParseResult` (`mcq_parser.dart:145-304`)

`questions`, `parsed` (= `questions.length`), `skipped`,
`errors: List<String>`, `formatCounts: Map<String,int>`,
`generatedOptions: int` (q-only items whose options came from the
pool), `excluded: List<String>` (reasons), `keySectionsFound: int`,
`keyEntriesApplied: int`, `questionsMissingAnswers: List<String>`,
`parts: List<BookPart>` (only parts with ≥ 1 parsed question; a single
`Poori book` part when the book has no questions at all; empty for the
string path), `answerSources: Map<String,int>` (only non-zero sources),
`conflicts: List<String>`, `unmatchedKeyEntries: List<String>`,
`notes` / `unmatchedNotes: List<String>`,
`fiveOptionNormalised: int`, `fiveOptionAnswerE: int`,
`numberGaps` / `numberDuplicates: List<String>`,
`noiseLinesFiltered: int`, `facts: List<FactPair>`,
`answerPending: List<PendingQuestion>`,
`keyPaperReport: List<String>`. Plus `questionsByPart` (derived getter).

`FactPair`: `label`, `value`, `part`, `page`, `isStatement`
(`label == value ==` the statement text for dash/bullet statements,
e.g. Urdu statements).

### 13.4 `PaperIdentity` / `KeyMatchDecision` (`paper_identity.dart`)

See §5.7 and §5.5. `KeyMatchConfidence`: `verified` |
`highConfidence` | `needsReview` | `unverified` | `mismatch`.
`KeyMatchDecision`: `confidence`, `reason` (plain language),
`evidence: List<String>`; `mayAutoAssign` is true only for VERIFIED;
`mayAutoAssignIfApproved(approved)` adds HIGH CONFIDENCE with explicit
approval.

### 13.5 `ValidationReport` (`parse_validation.dart`)

`issues: List<ValidationIssue>` (`kind`, `severity`, `detail`,
`questionRef?`), `keyPaperNotes: List<String>` (verbatim
`ParseResult.keyPaperReport`). `ValidationKind`: `missingAnswer`,
`duplicateQuestion`, `duplicateNumber`, `conflictingAnswer`,
`unmatchedKeyEntry`, `fabricationSuspect`. `ValidationSeverity`:
`error` (must be fixed or explicitly accepted before scoring —
duplicates, wrong-paper keys), `warning` (needs a human look),
`info` (expected in normal operation). `hasErrors` = any error.
**Known limit (Part 13 gap, stated in the file):** `Question` carries
no structured paper identity (no paper number/title/year — only `part`
+ `sourceId`), and `keyPaperReport` is human-readable strings, so a key
applied to the WRONG paper cannot be detected from the result alone.
That check belongs in the key-join step, not in validation.

---

## 14. Known Dart parser limitations relevant to M4

1. **Silent-fallback history (v2.0.5 context).** The v2.0.5 phone run
   (1 MCQ, 39 key entries matching none) is explained by the two
   mechanisms in §10.4 — a run-varying ML Kit line-merge swallowing
   the key heading, and/or an unread paper heading stranding the key
   under a different segment label. Both now have Dart fixes
   (`keyHeadingRemainder`, `adoptOrphanExplicitKeys`); the fixes are
   text-level and portable, but they cannot repair a key whose entries
   were never OCR'd at all.
2. **No vision.** Tick/bold cannot be told apart from a student's pen
   marks; highlight/colour/italic/circle/underline/cross/OMR are
   undetected (§6.19–6.20). The parser's answer is flagging
   (unverified + 0.54), not separation.
3. **No structured paper identity on `Question`.** See §13.5 — the
   Part 13 gap. The Python engine should consider carrying a structured
   paper identity on its question record (DECISION NEEDED — this would
   be an addition, not a port).
4. **Bare-numbered books get no gap report** (§4.4); decoded numbers
   are demoted, never repaired; trailing numberless runs stay null
   (§1.13).
5. **Q-only/flashcard questions are reconstructions.** Their options
   are pool-built, their answers unverified by construction (§7.2).
   The Computer Past Papers shape (answer directly after `?`) is only
   covered within the flashcard length caps (§10.2).
6. **Table pass is grid-based, not delimiter-based** (§9.8) — the
   `Sr#`-table fixture has no Dart rule.
7. **Multi-question rows unsupported; 3/4-column inline options
   unmeasured; compact key sequences unmeasured** (§12.10–12.12).
8. **No per-option confidence; no Urdu-digit, RTL, or Nastaliq
   handling** (§7.1, §11.3–11.4).
9. **Non-deterministic distractor shuffle** (`Random()` unseeded,
   §10.1) — identical input can produce different option orders across
   runs.
10. **`Subject.fromLabel` silently maps unknown labels to GK**
    (§13.1) — port it as-is or record the change.

## 15. DECISION NEEDED — consolidated gap list (Dart has no rule)

| # | Gap | Where it bites | What M4 must decide |
|---|---|---|---|
| D1 | Urdu digits (`٠-٩`, `۰-۹`) in numbers/markers/answers | §11.3 | Normalise to ASCII before matching, or treat as unmatched. |
| D2 | RTL / Nastaliq / Urdu reading order | §11.4 | What the layout/OCR stage guarantees before the text parser runs. |
| D3 | Physically clipped numbers (separator cut off, number split across lines) | §1.13 | Treat as numberless (interpolation path) or leave null; no partial-number guessing. |
| D4 | Handwriting vs print separation | §6.19 | Vision/geometry step, or keep Dart's flag-only rule. |
| D5 | Highlight / colour / italic / circle / underline / cross / OMR signals | §6.20 | Whether the engine's image stage adds any, with what evidence. |
| D6 | 3-option (or 6+-option) questions | §2.10 | Reject, exclude with reason, or normalise — Dart only defines 4 and 5→4. |
| D7 | Multiple questions on one line | §12.10 | No splitter in Dart; engine layout decision, not a parser port. |
| D8 | `Sr# \| Question \| A \| B \| C \| D \| Ans \| Key` delimiter tables | §9.8 | Add a delimiter-aware table path, or measure the grid machine against the fixture. |
| D9 | Long direct answers in Q&A-without-options files (flashcard caps 100/2/160) | §10.2 | Keep the caps or extend them for the Computer Past Papers shape. |
| D10 | Non-deterministic Q-only distractor shuffle | §10.1 | Seed it (deterministic) or keep random; record the choice. |
| D11 | Large unmatched-key counts (e.g. 39) — report only, no retry | §10.4 | Whether M4 adds any recovery/retry, or reports like Dart. |
| D12 | Duplicate-text detection layering | §4.5 | Validation layer (as in Dart) or folded into the parse result. |
| D13 | Structured paper identity on the question record | §13.5 | Add it (new field) or keep Dart's `part` + `sourceId` only. |
| D14 | Unknown `Subject:` labels silently → GK | §13.1 | Port the silent mapping or flag unknown subjects. |
| D15 | Separately attached answer key flow | §5.10 | Whether M4 supports an attached key at all. |
| D16 | 3/4-column inline options; compact key sequences (unmeasured) | §12.11–12.12 | Measure against real fixtures before claiming coverage. |
| D17 | Bold-signal availability in the Python PDF layer | §3.4 | Reproduce the font-bold → marker contract, or record bold as unavailable (never approximate it from text). |
| D18 | Answer as a range / multiple letters (`A and C`) | §6.7 | `resolveAnswerToken` returns null → pending; confirm M4 keeps that (no multi-answer rule exists). |

---

## Appendix — file map (for the porter)

| Dart file | What lives there | Lines |
|---|---|---|
| `lib/services/mcq_parser.dart` | Formats, block/one-liner/q-only/flashcard/table parsing, `_parseImpl`, signals, confidence application, gaps/dups, sanitisation | 5,734 |
| `lib/services/answer_key.dart` | OCR-number decode, key segmentation/parsing/resolution, paper headings, noise filter, `keyMatchDecisions`, orphan-key adoption, attached-key flow | 1,535 |
| `lib/services/paper_identity.dart` | `PaperIdentity`, `normalisePaperTitle`, `decideKeyMatch`, confidence ladder | 387 |
| `lib/services/parse_validation.dart` | `validateParseResult`, severities, `_looksFabricated`, Part 13 gap note | 254 |
| `lib/services/extraction/format_registry.dart` | Format descriptors, try order (table first, then block → one-liner → q-only → flashcard), `TableFormatHandler` | 183 |
| `lib/services/extraction/layout_patterns.dart` | Supported / partial / unsupported / unmeasured pattern library (the honest gap list) | 233 |
| `lib/models/question.dart` | `Question`, `PendingQuestion`, `BookSource`, `AttemptRecord`, confidence/verification rules | 583 |
| `lib/models/exam.dart` | `Subject` enum + `fromLabel` | (enum at :11-31) |
| `lib/services/book_structure.dart` | `PageText`, `flattenPages`, `detectBookStructure`, `BookPart` | (entry points at :134, :564) |
| `lib/services/pdf_text_extractor.dart` | Font-bold detection → U+E000 marker (plumbing only; cited at §3.4) | (bold at :613-709, :1531-1535) |
