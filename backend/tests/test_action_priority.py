# backend/tests/test_action_priority.py
"""Parity 测试：app.services.action_priority.calculate_ap 必须与前端
utils/fmea.ts calculateAP 完全一致（前端是 spec）。

期望值取自对前端 calculateAP 在全部 1728 组 (S,O,D)∈[0,11]³ 上执行的真值
（node 跑前端函数导出，与本模块比对 0 mismatch 后挑选的边界用例）。
"""
import pytest
from app.services.action_priority import calculate_ap


@pytest.mark.parametrize("s,o,d,expected", [
    # Severity 9-10
    (10, 5, 5, "H"),
    (9, 4, 1, "H"),   # s>=9, o>=4 → H（与 d 无关）
    (9, 3, 7, "H"),   # o∈{2,3}, d>=7 → H
    (9, 3, 6, "M"),   # o∈{2,3}, 5<=d<7 → M
    (9, 2, 7, "H"),
    (9, 2, 5, "M"),
    (9, 2, 4, "L"),   # o∈{2,3}, d<5 → L
    (9, 1, 10, "L"),  # o==1 → L
    # Severity 7-8
    (8, 8, 1, "H"),   # o>=8 → H
    (8, 7, 2, "H"),   # o∈{6,7}, d>=2 → H
    (8, 7, 1, "M"),   # o∈{6,7}, d<2 → M
    (8, 5, 7, "H"),   # o∈{4,5}, d>=7 → H
    (8, 5, 6, "M"),   # o∈{4,5}, d<7 → M
    (8, 3, 5, "M"),   # o∈{2,3}, d>=5 → M
    (8, 3, 4, "L"),   # o∈{2,3}, d<5 → L
    (8, 1, 10, "L"),  # o==1 → L
    (7, 8, 1, "H"),
    (7, 6, 2, "H"),
    (7, 5, 7, "H"),
    (7, 4, 7, "H"),
    (7, 4, 6, "M"),
    (7, 2, 5, "M"),
    (7, 2, 4, "L"),
    # Severity 4-6
    (6, 8, 5, "H"),   # o>=8, d>=5 → H
    (6, 8, 4, "M"),   # o>=8, d<5 → M
    (6, 7, 2, "M"),   # o∈{6,7}, d>=2 → M
    (6, 7, 1, "L"),   # o∈{6,7}, d<2 → L
    (6, 5, 7, "M"),   # o∈{4,5}, d>=7 → M
    (6, 5, 6, "L"),   # o∈{4,5}, d<7 → L
    (6, 3, 10, "L"),  # o<=3 → L
    (4, 8, 5, "H"),
    (4, 6, 2, "M"),
    (4, 4, 7, "M"),
    (4, 4, 6, "L"),
    (4, 2, 10, "L"),
    # Severity 1-3
    (3, 8, 5, "M"),   # o>=8, d>=5 → M
    (3, 8, 4, "L"),   # o>=8, d<5 → L
    (3, 7, 10, "L"),  # o<8 → L
    (2, 1, 1, "L"),
    (1, 1, 1, "L"),
    # 越界 → ""
    (0, 5, 5, ""),
    (11, 5, 5, ""),
    (5, 0, 5, ""),
    (5, 11, 5, ""),
    (5, 5, 0, ""),
    (5, 5, 11, ""),
])
def test_calculate_ap_parity(s, o, d, expected):
    assert calculate_ap(s, o, d) == expected
