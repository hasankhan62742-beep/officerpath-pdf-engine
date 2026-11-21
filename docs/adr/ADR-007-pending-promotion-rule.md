# ADR-007: Pending-question promotion rule

- **Status:** ACCEPTED (M6, 2026-11-22)
- **Context:** M5's answer resolution answered 42/68 verdicts on
  PPSC-66 live OCR (25 of them pending questions, answered by key
  evidences), but `apply_resolution` writes back only onto
  `result.questions` — the pending questions stayed pending in the
  ParseResult (`answered_questions_after` stayed 14,
  `changed_by_resolution` 0). The resolution knew the answers; the
  document did not. M6 had to decide when a pending question
  becomes a resolved MCQ.
- **Decision:** a pending question is promoted to an answered
  question ONLY when ALL of these hold (implemented in
  `app/pipeline/matching/promotion.py`, `promote_pending`):
  1. Its resolution verdict is "answered" (a letter, not UNKNOWN).
  2. The winning evidence's precedence rank is manual, key, inline,
     or style — NEVER visual alone (a pen mark needs review) and
     NEVER inferred alone (an inference is a guess).
  3. Confidence >= 0.9.
  4. No conflicts on the verdict.
  5. It has exactly 4 options.
  6. No already-answered question carries the same number.
  A promoted question carries `promoted_from_pending=True` and the
  promotion reason, and the promotion itself is reported (promoted
  + skipped with reasons) so the review list can audit it. Skipped
  pendings stay pending with the reason recorded — nothing is
  deleted, nothing is silently answered.
- **Rationale:** a key/inline/style verdict at confidence >= 0.9 is
  the same evidence that answers a full question, so withholding it
  from a pending question with 4 options would be false modesty; a
  visual or inferred verdict alone is not strong enough to CREATE
  an answer. Promotion uses the RAW (pre-calibration) confidence:
  calibration is a reporting adjustment, not evidence.
- **Consequences:**
  - On PPSC-66 live OCR the rule promotes the key-answered pendings
    (measured in the M6 benchmark; the exact count is in
    `docs/benchmarks/m6-benchmark-2026-11-22.json`).
  - A pending question whose verdict is visual-only or inferred-only
    stays pending even at high confidence — it appears in the review
    list, where a human (manual, top of precedence) can answer it.
  - The rule is deliberately conservative: a wrong promotion is
    worse than a missed one (a wrong answer presented as correct is
    the worst failure; an UNKNOWN answer is a correct outcome).
- **Alternatives considered:**
  - Promote on any answered verdict (including visual/inferred):
    rejected — visual marks and inferences are the two weakest
    signals in the precedence chain; promoting on them would
    manufacture answers the evidence does not support.
  - Promote only on a manual correction: rejected — it would leave
    the 25 key-answered PPSC-66 pendings unanswered forever, which
    is the false modesty the rule exists to fix.
  - Lower the confidence threshold to 0.7: rejected — the only
    verdicts below 0.9 in practice are style/visual/inferred, which
    are already excluded by rank; the threshold binds almost nothing
    and would only matter if a key verdict ever came in weak, in
    which case caution is correct.
