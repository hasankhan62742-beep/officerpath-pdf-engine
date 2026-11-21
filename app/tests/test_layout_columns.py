# OfficerPath AI — Phase 1, M3
# Shared column geometry: assignment + reading order.

from app.pipeline.interfaces import BoundingBox
from app.pipeline.layout.columns import assign_columns, reading_order_indices


def _box(x_min, y_min, x_max, y_max):
    return BoundingBox(x_min=x_min, y_min=y_min, x_max=x_max, y_max=y_max)


def test_single_column_all_zero():
    boxes = [_box(0.1, 0.1, 0.4, 0.2), _box(0.1, 0.3, 0.4, 0.4)]
    assert assign_columns(boxes) == [0, 0]


def test_two_columns_by_x_centre():
    boxes = [
        _box(0.05, 0.1, 0.45, 0.2),  # left
        _box(0.55, 0.1, 0.95, 0.2),  # right
        _box(0.05, 0.3, 0.45, 0.4),  # left, lower
    ]
    assert assign_columns(boxes) == [0, 1, 0]


def test_reading_order_is_column_major():
    boxes = [
        _box(0.55, 0.1, 0.95, 0.2),  # right, top
        _box(0.05, 0.3, 0.45, 0.4),  # left, lower
        _box(0.05, 0.1, 0.45, 0.2),  # left, top
    ]
    # left-top first, then left-lower, then right-top.
    assert reading_order_indices(boxes) == [2, 1, 0]


def test_empty_input():
    assert assign_columns([]) == []
    assert reading_order_indices([]) == []


def test_full_width_heading_does_not_define_columns():
    boxes = [
        _box(0.05, 0.02, 0.95, 0.08),  # full-width heading: spanning (-1)
        _box(0.05, 0.1, 0.45, 0.2),
        _box(0.55, 0.1, 0.95, 0.2),
    ]
    assert assign_columns(boxes) == [-1, 0, 1]


def test_spanning_heading_at_top_reads_first():
    boxes = [
        _box(0.55, 0.1, 0.95, 0.2),  # right column, top
        _box(0.05, 0.02, 0.95, 0.08),  # full-width heading, above both
        _box(0.05, 0.1, 0.45, 0.2),  # left column, top
    ]
    # Heading first, then left column, then right column.
    assert reading_order_indices(boxes) == [2, 0, 1]


def test_ppsc66_p1_left_edges_separate_two_columns():
    # Regression (M3 benchmark): on the real PPSC-66 p.1, Tesseract
    # blocks have left edges at 0.05-0.09 (left column) and 0.47-0.48
    # (right column). The old x-overlap clusterer chained them into
    # ONE column (long lines bridge the gutter) and reading order came
    # out interleaved (CER 0.61 vs the engine's own 0.06). Left-edge
    # clustering must give two columns with all left blocks first.
    boxes = [
        _box(0.32, 0.05, 0.53, 0.08),  # centred header (singleton)
        _box(0.08, 0.19, 0.41, 0.23),  # left
        _box(0.08, 0.23, 0.41, 0.27),  # left
        _box(0.47, 0.19, 0.80, 0.23),  # right
        _box(0.48, 0.23, 0.79, 0.27),  # right
        _box(0.09, 0.09, 0.78, 0.18),  # wide header (spanning)
    ]
    columns = assign_columns(boxes)
    assert columns[1] == columns[2] == 0
    assert columns[3] == columns[4] == 1
    assert columns[5] == -1
    ranks = reading_order_indices(boxes)
    # Every left block reads before every right block; the wide
    # header (top of page) reads before both columns.
    assert ranks[5] == 0
    assert max(ranks[1], ranks[2]) < min(ranks[3], ranks[4])


def test_wide_title_with_offset_centre_stays_single_column():
    # Regression: the M2 clean fixture's title is 0.5 of the page
    # wide with its centre right of the question stems. A centre-gap
    # clusterer wrongly split it into a second column and read it
    # last; x-overlap keeps the page single-column.
    boxes = [
        _box(0.118, 0.07, 0.613, 0.097),  # title (wide, centre ~0.37)
        _box(0.118, 0.137, 0.389, 0.156),  # stem (centre ~0.25)
        _box(0.137, 0.159, 0.249, 0.178),  # option (centre ~0.19)
    ]
    assert assign_columns(boxes) == [-1, 0, 0]
    assert reading_order_indices(boxes) == [0, 1, 2]
