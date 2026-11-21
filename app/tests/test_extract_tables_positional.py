# OfficerPath AI — Phase 1, M5 tests: the positional
# (non-adjacent) consumption pass — ``consume_leftover_option_lines``.
# Measured case: TestPoint p8 Active/Passive Voice, where the line
# stream is COLUMN-ordered (all stems, then all A-options, then all
# B-options...) while pdfplumber rows are ROW-ordered, so the
# adjacency walk leaves every option line free.

from app.pipeline.extract.tables import (
    consume_leftover_option_lines,
    match_pdfplumber_rows_to_lines,
)


def _lines(texts, page=1):
    return [
        {"index": i, "page": page, "text": t, "paper": "Paper 1", "part": ""}
        for i, t in enumerate(texts)
    ]


def _row(number, text, options, page=1):
    return {
        "number": number,
        "text": text,
        "options": list(options),
        "correct_index": 0,
        "page": page,
    }


def test_positional_consumes_column_ordered_options():
    # Two stems first, then the section label, then ALL A-options,
    # then ALL B-options — the p8 shape. Pass 1 anchors the stems
    # but cannot reach the options (the label + the next stem break
    # the adjacency walk); the positional pass must consume them.
    lines = _lines(
        [
            "They greet me cheerfully every morning.",
            "You will praise her very much.",
            "Active and Passive Voice",
            "A. Every",
            "morning I",
            "was greeted",
            "cheerfully.",
            "A. She will",
            "praised very",
            "much by",
            "you.",
            "B. I am",
            "greeted",
            "cheerfully",
            "by them",
            "every",
            "morning",
            "B. She will",
            "be praised",
            "very much",
            "by you.",
        ],
        page=8,
    )
    rows = [
        _row(
            1,
            "They greet me cheerfully every morning.",
            [
                "Every morning I was greeted cheerfully.",
                "I am greeted cheerfully by them every morning.",
                "I am being greeted cheerfully by them every morning.",
                "Cheerful greeting is done by them every morning to me.",
            ],
            page=8,
        ),
        _row(
            2,
            "You will praise her very much.",
            [
                "She will praised very much by you.",
                "She will be praised very much by you.",
                "She will being praised very much by you.",
                "She will been praised very much by you.",
            ],
            page=8,
        ),
    ]
    consumed = match_pdfplumber_rows_to_lines(rows, lines)
    # Pass 1 anchors both stems (0, 1) and nothing else — the
    # option lines are not adjacent to their stems.
    assert consumed == {0, 1}
    extra = consume_leftover_option_lines(rows, lines, consumed)
    # Every option line (3..20) is consumed. The section label (2)
    # is not an option line and stays free (harmless: no options
    # follow it).
    assert extra == set(range(3, 21)), sorted(extra)


def test_positional_handles_merged_garbage_cell_values():
    # pdfplumber merged adjacent cells: option B carries the
    # previous cell's tail ("morning. B. She will be praised...")
    # and option C is corrupted ("eCv. eSrhye will being...").
    # The true option text is still a substring / long common
    # substring of the cell value, so the run still matches.
    lines = _lines(
        [
            "They greet me cheerfully every morning.",
            "You will praise her very much.",
            "Active and Passive Voice",
            "B. She will",
            "be praised",
            "very much",
            "by you.",
            "C. She will",
            "being",
            "praised very",
            "much by",
            "you",
        ],
        page=8,
    )
    rows = [
        _row(
            1,
            "They greet me cheerfully every morning.",
            [
                "Every morning I was greeted cheerfully.",
                "I am greeted cheerfully by them every morning.",
                "I am being greeted cheerfully by them every morning.",
                "Cheerful greeting is done by them every morning to me.",
            ],
            page=8,
        ),
        _row(
            2,
            "You will praise her very much.",
            [
                "She will praised very much by you.",
                "morning. B. She will be praised very much by you.",
                "eCv. eSrhye will being praised very much by",
                "mD.e S.he will been praised very much by",
            ],
            page=8,
        ),
    ]
    consumed = match_pdfplumber_rows_to_lines(rows, lines)
    # Pass 1 anchors both stems (0, 1); the label (2) breaks the
    # walk, so the B/C option lines stay free for this pass.
    assert consumed == {0, 1}
    extra = consume_leftover_option_lines(rows, lines, consumed)
    assert extra == set(range(3, 12)), sorted(extra)


def test_positional_consumes_promo_and_ans_key_furniture():
    lines = _lines(
        [
            "TestPoint.pkاپٹس رپیپ احلص رکےن ےئلیک وگلگ رپ رسچ رکںی",
            "Books are a great source _______ happiness.",
            "A. of",
            "B. for",
            "C. on",
            "D. with",
            "A",
            "Ans",
            "Key",
        ]
    )
    rows = [
        _row(
            1,
            "Books are a great source _______ happiness.",
            ["of", "for", "on", "with"],
        )
    ]
    consumed = match_pdfplumber_rows_to_lines(rows, lines)
    extra = consume_leftover_option_lines(rows, lines, consumed)
    # Promo line 0 and Ans/Key footer lines 7-8 are furniture.
    assert {0, 7, 8} <= extra
    # The row's own lines stay consumed by pass 1, not re-added.
    assert extra.isdisjoint(consumed)


def test_positional_never_hides_an_unanchored_row():
    # The row's stem is nowhere in the lines, so pass 1 anchors
    # nothing — this pass must not consume the option-looking
    # lines, or the grid/block passes could never parse them.
    lines = _lines(
        [
            "Some other question entirely.",
            "A. of",
            "B. for",
            "C. on",
            "D. with",
            "A",
        ]
    )
    rows = [
        _row(
            1,
            "A question that is nowhere in these lines.",
            ["of", "for", "on", "with"],
        )
    ]
    consumed = match_pdfplumber_rows_to_lines(rows, lines)
    assert consumed == set()
    assert consume_leftover_option_lines(rows, lines, consumed) == set()


def test_positional_does_not_steal_a_following_stem():
    # A free stem line follows a complete option: the run stops
    # when the option completes, so the stem stays free for the
    # grid/block passes.
    lines = _lines(
        [
            "They greet me cheerfully every morning.",
            "A. Every morning I was greeted cheerfully.",
            "What is the capital of France?",
            "A. Paris",
            "B. London",
            "C. Rome",
            "D. Madrid",
            "A",
        ]
    )
    rows = [
        _row(
            1,
            "They greet me cheerfully every morning.",
            [
                "Every morning I was greeted cheerfully.",
                "I am greeted cheerfully by them every morning.",
                "I am being greeted cheerfully by them every morning.",
                "Cheerful greeting is done by them every morning to me.",
            ],
        )
    ]
    consumed = match_pdfplumber_rows_to_lines(rows, lines)
    assert consumed == {0, 1}
    extra = consume_leftover_option_lines(rows, lines, consumed)
    # Only the option line (1) is already consumed; nothing new —
    # the following question's lines are untouched.
    assert extra == set()


def test_positional_mid_word_split_option():
    # A word split across lines ("Retrospectiv" / "ely"): the
    # space-removed comparison still matches the cell value. The
    # column shape (stem far from its options) is what leaves the
    # lines free for this pass in the first place.
    lines = _lines(
        [
            "Choose the synonym of Retrospective?",
            "Synonyms",
            "A. Retrospectiv",
            "ely",
            "B. Free of cost",
            "C. Synopsis",
            "D. Summary",
            "A",
        ]
    )
    rows = [
        _row(
            1,
            "Choose the synonym of Retrospective?",
            ["Retrospectively", "Free of cost", "Synopsis", "Summary"],
        )
    ]
    consumed = match_pdfplumber_rows_to_lines(rows, lines)
    assert consumed == {0}
    extra = consume_leftover_option_lines(rows, lines, consumed)
    assert extra == {2, 3, 4, 5, 6}, sorted(extra)
