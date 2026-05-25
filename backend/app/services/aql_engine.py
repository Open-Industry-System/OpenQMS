"""ISO 2859-1 / GB/T 2828.1 AQL Sampling Plan Auto-Calculation Engine.

Given lot_qty, aql_level, and inspection_level, computes:
- sample_size (应抽检数)
- accept_number (Ac, 合格判定数)
- reject_number (Re, 不合格判定数)
"""

# Table 1: Lot size ranges → sample size code letters
# (min_lot, max_lot) → default code letter for Inspection Level II
_LOT_RANGES: list[tuple[int, int, str]] = [
    (2, 8, "A"),
    (9, 15, "A"),
    (16, 25, "B"),
    (26, 50, "C"),
    (51, 90, "D"),
    (91, 150, "E"),
    (151, 280, "F"),
    (281, 500, "G"),
    (501, 1200, "H"),
    (1201, 3200, "J"),
    (3201, 10000, "K"),
    (10001, 35000, "L"),
    (35001, 150000, "M"),
    (150001, 500000, "N"),
    (500001, float("inf"), "P"),
]

# Inspection level adjustments relative to Level II
_LEVEL_ADJUST: dict[str, int] = {
    "S-1": -4, "S-2": -3, "S-3": -2, "S-4": -1,
    "I": -1, "II": 0, "III": 1,
}

# Ordered code letters for applying adjustments
_CODE_LETTERS = ["A", "B", "C", "D", "E", "F", "G", "H", "J", "K", "L", "M", "N", "P", "Q", "R"]

# Table 2: Code letter → sample size
_CODE_TO_SAMPLE_SIZE: dict[str, int] = {
    "A": 2, "B": 3, "C": 5, "D": 8, "E": 13,
    "F": 20, "G": 32, "H": 50, "J": 80, "K": 125,
    "L": 200, "M": 315, "N": 500, "P": 800, "Q": 1250, "R": 2000,
}

# Table 3: AQL values supported
AQL_VALUES = [
    0.010, 0.015, 0.025, 0.040, 0.065, 0.10, 0.15, 0.25, 0.40,
    0.65, 1.0, 1.5, 2.5, 4.0, 6.5, 10.0, 15.0, 25.0,
]

# Master table: (code_letter_index, aql_value) → (Ac, Re)
# Indexed by code letter position in _CODE_LETTERS and AQL position in AQL_VALUES
# null means use first plan below (↑) or use plan above (↓)
_MASTER_TABLE: dict[tuple[int, int], tuple[int, int] | None] = {
    # Row A (idx 0): only high AQL values applicable
    (0, 12): (0, 1), (0, 13): (1, 2), (0, 14): (1, 2),
    (0, 15): (2, 3), (0, 16): (3, 4), (0, 17): (5, 6),
    # Row B (idx 1)
    (1, 11): (0, 1), (1, 12): (1, 2), (1, 13): (1, 2),
    (1, 14): (2, 3), (1, 15): (3, 4), (1, 16): (5, 6), (1, 17): (7, 8),
    # Row C (idx 2)
    (2, 10): (0, 1), (2, 11): (1, 2), (2, 12): (1, 2),
    (2, 13): (2, 3), (2, 14): (3, 4), (2, 15): (5, 6), (2, 16): (7, 8), (2, 17): (10, 11),
    # Row D (idx 3)
    (3, 9): (0, 1), (3, 10): (1, 2), (3, 11): (1, 2),
    (3, 12): (2, 3), (3, 13): (3, 4), (3, 14): (5, 6), (3, 15): (7, 8), (3, 16): (10, 11), (3, 17): (14, 15),
    # Row E (idx 4)
    (4, 8): (0, 1), (4, 9): (1, 2), (4, 10): (1, 2),
    (4, 11): (2, 3), (4, 12): (3, 4), (4, 13): (5, 6), (4, 14): (7, 8), (4, 15): (10, 11), (4, 16): (14, 15),
    # Row F (idx 5)
    (5, 7): (0, 1), (5, 8): (1, 2), (5, 9): (1, 2),
    (5, 10): (2, 3), (5, 11): (3, 4), (5, 12): (5, 6), (5, 13): (7, 8), (5, 14): (10, 11), (5, 15): (14, 15),
    # Row G (idx 6)
    (6, 6): (0, 1), (6, 7): (1, 2), (6, 8): (1, 2),
    (6, 9): (2, 3), (6, 10): (3, 4), (6, 11): (5, 6), (6, 12): (7, 8), (6, 13): (10, 11), (6, 14): (14, 15),
    # Row H (idx 7)
    (7, 5): (0, 1), (7, 6): (1, 2), (7, 7): (1, 2),
    (7, 8): (2, 3), (7, 9): (3, 4), (7, 10): (5, 6), (7, 11): (7, 8), (7, 12): (10, 11), (7, 13): (14, 15),
    # Row J (idx 8)
    (8, 4): (0, 1), (8, 5): (1, 2), (8, 6): (2, 3),
    (8, 7): (3, 4), (8, 8): (5, 6), (8, 9): (7, 8), (8, 10): (10, 11), (8, 11): (14, 15),
    # Row K (idx 9)
    (9, 3): (0, 1), (9, 4): (1, 2), (9, 5): (2, 3),
    (9, 6): (3, 4), (9, 7): (5, 6), (9, 8): (7, 8), (9, 9): (10, 11), (9, 10): (14, 15),
    # Row L (idx 10)
    (10, 2): (0, 1), (10, 3): (1, 2), (10, 4): (2, 3),
    (10, 5): (3, 4), (10, 6): (5, 6), (10, 7): (7, 8), (10, 8): (10, 11), (10, 9): (14, 15),
    # Row M (idx 11)
    (11, 1): (0, 1), (11, 2): (1, 2), (11, 3): (2, 3),
    (11, 4): (3, 4), (11, 5): (5, 6), (11, 6): (7, 8), (11, 7): (10, 11), (11, 8): (14, 15),
    # Row N (idx 12)
    (12, 1): (1, 2), (12, 2): (2, 3), (12, 3): (3, 4),
    (12, 4): (5, 6), (12, 5): (7, 8), (12, 6): (10, 11), (12, 7): (14, 15),
    # Row P (idx 13)
    (13, 0): (0, 1), (13, 1): (2, 3), (13, 2): (3, 4),
    (13, 3): (5, 6), (13, 4): (7, 8), (13, 5): (10, 11), (13, 6): (14, 15),
    # Row Q (idx 14)
    (14, 0): (1, 2), (14, 1): (3, 4), (14, 2): (5, 6),
    (14, 3): (7, 8), (14, 4): (10, 11), (14, 5): (14, 15),
    # Row R (idx 15)
    (15, 0): (2, 3), (15, 1): (5, 6), (15, 2): (7, 8),
    (15, 3): (10, 11), (15, 4): (14, 15),
}


def _get_code_letter(lot_qty: int, inspection_level: str) -> str:
    """Determine sample size code letter from lot size and inspection level."""
    base_letter = "A"
    for lo, hi, letter in _LOT_RANGES:
        if lo <= lot_qty <= hi:
            base_letter = letter
            break

    adjust = _LEVEL_ADJUST.get(inspection_level, 0)
    idx = _CODE_LETTERS.index(base_letter) + adjust
    idx = max(0, min(idx, len(_CODE_LETTERS) - 1))
    return _CODE_LETTERS[idx]


def calculate_aql_plan(
    lot_qty: int,
    aql_level: float,
    inspection_level: str = "II",
) -> dict:
    """Calculate AQL sampling plan per ISO 2859-1 / GB/T 2828.1.

    Args:
        lot_qty: Lot/batch size (批量)
        aql_level: Acceptable Quality Limit (可接收质量限), e.g. 0.65, 1.0, 2.5
        inspection_level: Inspection level (检验水平), e.g. "I", "II", "III", "S-1".."S-4"

    Returns:
        dict with: code_letter, sample_size, accept_number, reject_number, aql_level, inspection_level

    Raises:
        ValueError: if inputs are invalid or no plan exists for the combination.
    """
    if lot_qty < 2:
        raise ValueError("批量必须 ≥ 2")
    if inspection_level not in _LEVEL_ADJUST:
        raise ValueError(f"检验水平必须是: {', '.join(_LEVEL_ADJUST.keys())}")

    # Normalize AQL to nearest supported value
    aql_level = float(aql_level)
    nearest_aql = min(AQL_VALUES, key=lambda x: abs(x - aql_level))

    code_letter = _get_code_letter(lot_qty, inspection_level)
    sample_size = _CODE_TO_SAMPLE_SIZE[code_letter]

    code_idx = _CODE_LETTERS.index(code_letter)
    aql_idx = AQL_VALUES.index(nearest_aql)

    result = _MASTER_TABLE.get((code_idx, aql_idx))
    if result is None:
        # Try to find by walking up the AQL column until we find an entry
        for offset in range(1, len(AQL_VALUES)):
            for direction in [aql_idx + offset, aql_idx - offset]:
                if 0 <= direction < len(AQL_VALUES):
                    r = _MASTER_TABLE.get((code_idx, direction))
                    if r is not None:
                        result = r
                        break
            if result is not None:
                break

    if result is None:
        raise ValueError(
            f"无对应抽样方案: 批量={lot_qty}, AQL={nearest_aql}, "
            f"检验水平={inspection_level}, 代码={code_letter}。请调整参数。"
        )

    accept, reject = result
    return {
        "code_letter": code_letter,
        "sample_size": sample_size,
        "accept_number": accept,
        "reject_number": reject,
        "aql_level": nearest_aql,
        "inspection_level": inspection_level,
    }
