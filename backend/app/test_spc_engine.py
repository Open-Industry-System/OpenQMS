import sys
from app.services.spc_calculation_engine import (
    calculate_xbar_r_limits,
    calculate_imr_limits,
    calculate_histogram_data,
    evaluate_western_electric,
    calculate_cp_cpk,
    calculate_pp_ppk,
    calculate_cm,
    calculate_ppm,
    get_capability_grade,
    get_capability_advice,
    calculate_p_limits,
    calculate_np_limits,
    calculate_c_limits,
    calculate_u_limits,
)


def test_xbar_r_limits():
    data = [[10, 12, 11, 10, 11], [11, 12, 10, 11, 12], [10, 11, 12, 10, 11]]
    result = calculate_xbar_r_limits(data)
    assert result["cl"] is not None
    assert result["ucl"] > result["cl"] > result["lcl"]
    assert result["r_ucl"] > result["r_lcl"]
    print(f"Pass: X-bar R limits: {result}")


def test_imr_limits():
    data = [10.2, 10.5, 10.1, 10.3, 10.4, 10.2, 10.6, 10.3, 10.5, 10.4]
    result = calculate_imr_limits(data)
    assert result["cl"] is not None
    assert result["ucl"] > result["cl"] > result["lcl"]
    print(f"Pass: I-MR limits: {result}")


def test_histogram():
    data = [1, 2, 2, 3, 3, 3, 4, 4, 5]
    result = calculate_histogram_data(data, bins=5)
    assert len(result) == 5
    assert sum(b["count"] for b in result) == 9
    print(f"Pass: Histogram bins: {len(result)}")


def test_rule_1():
    stats = [10, 11, 12, 50, 11, 10]
    limits = {"ucl": 15, "lcl": 5, "cl": 10}
    config = {f"rule_{i}": True for i in range(1, 9)}
    alarms = evaluate_western_electric(stats, limits, config)
    rule1 = [a for a in alarms if a["rule_no"] == 1]
    assert len(rule1) == 1
    assert rule1[0]["batch_index"] == 3
    print(f"Pass: Rule 1 detected out-of-control point at index 3")


def test_rule_2():
    stats = [12, 12, 12, 12, 12, 12, 12, 12, 12]
    limits = {"ucl": 15, "lcl": 5, "cl": 10}
    config = {f"rule_{i}": True for i in range(1, 9)}
    alarms = evaluate_western_electric(stats, limits, config)
    rule2 = [a for a in alarms if a["rule_no"] == 2]
    assert len(rule2) >= 1
    print(f"Pass: Rule 2 detected 9 points same side")


def test_capability():
    values = [10.2, 10.1, 10.3, 10.2, 10.1, 10.2, 10.3, 10.2, 10.1, 10.2]
    result = calculate_cp_cpk(values, usl=11.0, lsl=9.0)
    assert result["cp"] > 0
    assert result["cpk"] > 0
    grade = get_capability_grade(result["cpk"])
    advice = get_capability_advice(result["cpk"])
    print(f"Pass: Cp={result['cp']}, Cpk={result['cpk']}, Grade={grade}, Advice={advice}")


def test_ppm():
    values = [10.2, 10.1, 10.3, 10.2, 10.1, 10.2, 10.3, 10.2, 10.1, 10.2]
    result = calculate_ppm(values, usl=11.0, lsl=9.0)
    assert result["actual_ppm"] >= 0
    print(f"Pass: Theoretical PPM={result['theoretical_ppm']}, Actual PPM={result['actual_ppm']}")


def test_empty_data():
    """Test that empty data returns safe defaults."""
    result = calculate_xbar_r_limits([])
    assert result["ucl"] is None
    result2 = calculate_imr_limits([])
    assert result2["ucl"] is None
    result3 = calculate_histogram_data([])
    assert result3 == []
    result4 = calculate_cp_cpk([], usl=10, lsl=0)
    assert result4["cp"] == 0.0
    print("Pass: Empty data handled correctly")


def test_subgroup_size_validation():
    """Test subgroup size validation."""
    try:
        calculate_xbar_r_limits([[1, 2]])  # n=2 is valid
        print("Pass: n=2 accepted")
    except ValueError:
        assert False, "n=2 should be valid"

    try:
        calculate_xbar_r_limits([[1]])  # n=1 is invalid
        assert False, "n=1 should raise ValueError"
    except ValueError as e:
        assert "subgroup_size must be between 2 and 10" in str(e)
        print("Pass: n=1 rejected correctly")

    try:
        calculate_xbar_r_limits([[1] * 11])  # n=11 is invalid
        assert False, "n=11 should raise ValueError"
    except ValueError as e:
        assert "subgroup_size must be between 2 and 10" in str(e)
        print("Pass: n=11 rejected correctly")


def test_mismatched_subgroup_sizes():
    """Test that mismatched subgroup sizes raise an error."""
    try:
        calculate_xbar_r_limits([[1, 2, 3], [1, 2]])
        assert False, "Mismatched sizes should raise ValueError"
    except ValueError as e:
        assert "same size" in str(e)
        print("Pass: Mismatched subgroup sizes rejected correctly")


def test_pp_ppk():
    values = [10.2, 10.1, 10.3, 10.2, 10.1, 10.2, 10.3, 10.2, 10.1, 10.2]
    result = calculate_pp_ppk(values, usl=11.0, lsl=9.0)
    assert result["pp"] > 0
    assert result["ppk"] > 0
    print(f"Pass: Pp={result['pp']}, Ppk={result['ppk']}")


def test_cm():
    values = [10.2, 10.1, 10.3, 10.2, 10.1, 10.2, 10.3, 10.2, 10.1, 10.2]
    result = calculate_cm(values, usl=11.0, lsl=9.0)
    assert result["cm"] > 0
    assert result["cmk"] > 0
    print(f"Pass: Cm={result['cm']}, Cmk={result['cmk']}")


def test_capability_grades():
    assert get_capability_grade(1.67) == "优秀"
    assert get_capability_grade(1.5) == "合格"
    assert get_capability_grade(1.2) == "警告"
    assert get_capability_grade(0.8) == "不合格"
    print("Pass: Capability grades correct")


def test_western_electric_disabled_rules():
    """Test that disabled rules don't trigger."""
    stats = [10, 11, 12, 50, 11, 10]
    limits = {"ucl": 15, "lcl": 5, "cl": 10}
    config = {f"rule_{i}": False for i in range(1, 9)}
    alarms = evaluate_western_electric(stats, limits, config)
    assert len(alarms) == 0
    print("Pass: Disabled rules don't trigger")


# ============ Attribute Chart Tests ============


def test_calculate_p_limits_basic():
    batches = [
        {"inspected_count": 100, "defect_count": 5},
        {"inspected_count": 100, "defect_count": 3},
        {"inspected_count": 100, "defect_count": 7},
        {"inspected_count": 100, "defect_count": 4},
        {"inspected_count": 100, "defect_count": 6},
    ]
    result = calculate_p_limits(batches)
    assert "cl" in result
    assert "ucl_list" in result
    assert "lcl_list" in result
    assert len(result["ucl_list"]) == 5
    assert len(result["lcl_list"]) == 5
    assert abs(result["cl"] - 0.05) < 0.001
    expected_ucl = 0.05 + 3 * (0.05 * 0.95 / 100) ** 0.5
    assert abs(result["ucl_list"][0] - round(expected_ucl, 4)) < 0.001
    assert all(v >= 0 for v in result["lcl_list"])


def test_calculate_np_limits_basic():
    batches = [
        {"inspected_count": 50, "defect_count": 2},
        {"inspected_count": 50, "defect_count": 3},
        {"inspected_count": 50, "defect_count": 1},
        {"inspected_count": 50, "defect_count": 4},
        {"inspected_count": 50, "defect_count": 2},
    ]
    result = calculate_np_limits(batches)
    assert "cl" in result
    assert "ucl" in result
    assert "lcl" in result
    assert abs(result["cl"] - 2.4) < 0.001
    assert result["lcl"] >= 0


def test_calculate_np_limits_variable_n_raises():
    batches = [
        {"inspected_count": 50, "defect_count": 2},
        {"inspected_count": 60, "defect_count": 3},
    ]
    try:
        calculate_np_limits(batches)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "固定" in str(e) or "fixed" in str(e).lower()


def test_calculate_c_limits_basic():
    batches = [
        {"inspected_count": 1, "defect_count": 3},
        {"inspected_count": 1, "defect_count": 5},
        {"inspected_count": 1, "defect_count": 2},
        {"inspected_count": 1, "defect_count": 4},
        {"inspected_count": 1, "defect_count": 6},
    ]
    result = calculate_c_limits(batches)
    assert abs(result["cl"] - 4.0) < 0.001
    assert abs(result["ucl"] - 10.0) < 0.001
    assert result["lcl"] >= 0


def test_calculate_u_limits_basic():
    batches = [
        {"inspected_count": 10, "defect_count": 3},
        {"inspected_count": 20, "defect_count": 8},
        {"inspected_count": 15, "defect_count": 5},
        {"inspected_count": 10, "defect_count": 2},
        {"inspected_count": 20, "defect_count": 6},
    ]
    result = calculate_u_limits(batches)
    assert "cl" in result
    assert "ucl_list" in result
    assert "lcl_list" in result
    assert len(result["ucl_list"]) == 5
    assert all(v >= 0 for v in result["lcl_list"])


def test_lcl_truncated_to_zero():
    batches = [{"inspected_count": 100, "defect_count": 0} for _ in range(5)]
    batches[0]["defect_count"] = 1
    result = calculate_p_limits(batches)
    assert all(v >= 0 for v in result["lcl_list"])


if __name__ == "__main__":
    try:
        test_xbar_r_limits()
        test_imr_limits()
        test_histogram()
        test_rule_1()
        test_rule_2()
        test_capability()
        test_ppm()
        test_empty_data()
        test_subgroup_size_validation()
        test_mismatched_subgroup_sizes()
        test_pp_ppk()
        test_cm()
        test_capability_grades()
        test_western_electric_disabled_rules()
        test_calculate_p_limits_basic()
        test_calculate_np_limits_basic()
        test_calculate_np_limits_variable_n_raises()
        test_calculate_c_limits_basic()
        test_calculate_u_limits_basic()
        test_lcl_truncated_to_zero()
        print("\nAll SPC engine tests passed!")
        sys.exit(0)
    except Exception as e:
        print(f"\nTest failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
