"""AIAG-VDA Action Priority lookup（镜像前端 utils/fmea.ts calculateAP）。

AP 是 (S, O, D) 的**查表结果**，不是 RPN 乘积 S*O*D。
Ref: AIAG-VDA FMEA Handbook (2019) Appendix C1.5。

前端是 spec：本函数逐行镜像 `calculateAP`，后端门禁（Step6 S=9-10 + AP=H/M
要求 management_review_evidence）据此计算 AP。任何改动必须与前端保持一致
（parity 测试见 tests/test_action_priority.py）。
"""


def calculate_ap(s: int, o: int, d: int) -> str:
    """返回 'H' / 'M' / 'L'，或 ''（S/O/D 越界）。逐行镜像前端 calculateAP。"""
    if s < 1 or s > 10 or o < 1 or o > 10 or d < 1 or d > 10:
        return ""
    # Severity 9-10
    if s >= 9:
        if o >= 4:
            return "H"
        if o == 3 or o == 2:
            return "H" if d >= 7 else "M" if d >= 5 else "L"
        return "L"  # o == 1
    # Severity 7-8
    if s >= 7:
        if o >= 8:
            return "H"
        if o == 6 or o == 7:
            return "H" if d >= 2 else "M"
        if o == 4 or o == 5:
            return "H" if d >= 7 else "M"
        if o == 2 or o == 3:
            return "M" if d >= 5 else "L"
        return "L"  # o == 1
    # Severity 4-6
    if s >= 4:
        if o >= 8:
            return "H" if d >= 5 else "M"
        if o == 6 or o == 7:
            return "M" if d >= 2 else "L"
        if o == 4 or o == 5:
            return "M" if d >= 7 else "L"
        return "L"  # o <= 3
    # Severity 1-3
    if o >= 8:
        return "M" if d >= 5 else "L"
    return "L"
