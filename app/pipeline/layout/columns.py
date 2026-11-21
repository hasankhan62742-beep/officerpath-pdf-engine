# OfficerPath AI — PDF Engine (Phase 1, M3)
# Shared column geometry (prompt §9): column assignment + reading
# order from block bboxes. Used by BOTH the digital extractor (its
# blocks must come out in reading order) and the layout analyser, so
# the two never disagree about what "column 1, then column 2" means.
#
# Method (geometry, not guesses): cluster narrow blocks by LEFT EDGE
# (x_min). Blocks in one column start at (nearly) the same x; blocks
# in different columns start far apart. A gap in the sorted x_mins
# wider than MIN_COLUMN_GAP_FRACTION of the page width splits
# columns. Singleton clusters (one block alone — a centred heading,
# a page number, an indented line) are merged into the nearest
# multi-block column instead of becoming a spurious column.
#
# Why left edges, not x-interval overlap: the first version clustered
# by overlap (single-linkage), and on the real PPSC-66 p.1 it chained
# all 37 Tesseract blocks into ONE column — long lines bridge the
# gutter, so overlap is transitive across the page. The result was
# y-order reading (left/right interleaved) and CER 0.61 where the
# engine's own order scores CER 0.06. Left-edge clustering separates
# p.1 cleanly (left x_min 0.05-0.09, right 0.47-0.48) and keeps the
# M2 clean fixture single-column (title x_min 0.118 = stem x_min).
# A block wider than SPAN_FRACTION of the page does NOT define a
# column — it spans (a heading, a wide stem, a table) and is
# assigned column -1; in reading order it is inserted by y among
# the column flow (before the first column block that starts below
# it). Reading order inside a column is top-to-bottom (y_min);
# columns read left-to-right.

from __future__ import annotations

from app.pipeline.interfaces import BoundingBox

# A gap in the sorted block left edges wider than this fraction of
# the page width splits two columns. 0.04 = 4% of the width. Left
# edges inside one column differ by indentation only (options are
# ~0.02 right of stems on the M2 fixtures); real column gutters are
# 0.15+ on PPSC-66 and 0.40 on the M2 two-column fixture.
MIN_COLUMN_GAP_FRACTION = 0.04
# A block wider than this fraction of the page spans columns and
# does not define one. 0.45 keeps a two-column page's title (often
# ~0.5 wide) out of the column clusters, while ordinary question
# stems/options (~0.3 wide) still define columns.
SPAN_FRACTION = 0.45
# A singleton cluster (one block) merges into the nearest
# multi-block column only when it sits within this fraction of the
# page width of that column's mean left edge. See assign_columns
# for the calibration (PPSC-66 p.1 headers: 0.10-0.16; a genuine
# sparse second column: ~0.50).
SINGLETON_MERGE_MAX_GAP = 0.20


def assign_columns(bboxes: list[BoundingBox]) -> list[int]:
    """Column index (0 = leftmost) for each bbox, in input order.

    Empty input returns []. A single column returns all zeros.
    Blocks wider than SPAN_FRACTION of the page are assigned -1
    (spanning: heading / wide stem / table) and never define a
    column. The rest are clustered by left-edge (x_min) gaps;
    singleton clusters merge into the nearest multi-block column.
    """
    if not bboxes:
        return []
    columns = [-1] * len(bboxes)
    narrow = [i for i, b in enumerate(bboxes) if (b.x_max - b.x_min) < SPAN_FRACTION]
    if not narrow:
        return columns
    ordered = sorted(narrow, key=lambda i: bboxes[i].x_min)
    clusters: list[list[int]] = [[ordered[0]]]
    for index in ordered[1:]:
        previous = clusters[-1][-1]
        if bboxes[index].x_min - bboxes[previous].x_min > MIN_COLUMN_GAP_FRACTION:
            clusters.append([index])
        else:
            clusters[-1].append(index)
    # Merge NEARBY singleton clusters into the nearest multi-block
    # column. A lone block close to a column is a heading, a page
    # number or an indented line — not a column of its own. A lone
    # block FAR from every column is a genuine sparse column and is
    # kept: on PPSC-66 p.1 the singletons sit 0.10-0.16 from a column
    # (centred headers), while a real second column with one block
    # sits ~0.50 away (the M2 two-column fixture). The 0.20 cut is
    # calibrated on those two cases, not derived.
    multi = [c for c in clusters if len(c) >= 2]
    if multi:
        merged: list[list[int]] = [c for c in clusters if len(c) >= 2]
        for cluster in clusters:
            if len(cluster) >= 2:
                continue
            singleton = cluster[0]
            nearest = min(
                multi,
                key=lambda c: abs(
                    bboxes[singleton].x_min - sum(bboxes[i].x_min for i in c) / len(c)
                ),
            )
            distance = abs(
                bboxes[singleton].x_min - sum(bboxes[i].x_min for i in nearest) / len(nearest)
            )
            if distance <= SINGLETON_MERGE_MAX_GAP:
                nearest.append(singleton)
            else:
                merged.append(cluster)
        clusters = merged
    ordered_clusters = sorted(
        clusters,
        key=lambda members: sum(bboxes[i].x_min for i in members) / len(members),
    )
    for column_index, members in enumerate(ordered_clusters):
        for i in members:
            columns[i] = column_index
    return columns


def column_boundaries(bboxes: list[BoundingBox]) -> list[float]:
    """x-split points between adjacent columns, from the column
    assignment: midpoint between the widest x of the left column's
    blocks and the narrowest x of the right column's blocks.
    Spanning blocks never create a boundary."""
    columns = assign_columns(bboxes)
    numbered = sorted({c for c in columns if c >= 0})
    boundaries: list[float] = []
    for left, right in zip(numbered, numbered[1:], strict=False):
        left_max = max(b.x_max for b, c in zip(bboxes, columns, strict=True) if c == left)
        right_min = min(b.x_min for b, c in zip(bboxes, columns, strict=True) if c == right)
        if right_min > left_max:
            boundaries.append(round((left_max + right_min) / 2.0, 3))
    return boundaries


def reading_order_indices(bboxes: list[BoundingBox]) -> list[int]:
    """Reading-order rank (0 = first read) for each bbox, in input
    order. Column-major: all of column 0 top-to-bottom, then column
    1, and so on. Spanning blocks (column -1) are inserted by y:
    each goes before the first column block that starts below the
    spanning block's bottom edge, so a heading at the top of the
    page reads first and a full-width separator reads where it
    sits. Ties in y break by x (left first)."""
    if not bboxes:
        return []
    columns = assign_columns(bboxes)
    order = sorted(
        (i for i in range(len(bboxes)) if columns[i] >= 0),
        key=lambda i: (columns[i], bboxes[i].y_min, bboxes[i].x_min),
    )
    spanning = sorted(
        (i for i in range(len(bboxes)) if columns[i] == -1),
        key=lambda i: (bboxes[i].y_min, bboxes[i].x_min),
    )
    for block_index in spanning:
        position = next(
            (k for k, other in enumerate(order) if bboxes[other].y_min > bboxes[block_index].y_max),
            len(order),
        )
        order.insert(position, block_index)
    ranks = [0] * len(bboxes)
    for rank, index in enumerate(order):
        ranks[index] = rank
    return ranks
