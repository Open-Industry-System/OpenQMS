import os
os.environ.setdefault("SECRET_KEY", "test-secret-key")

import pytest

from app.api.fmea import _recommend_anchor


class TestRecommendAnchor:
    def test_failure_mode_uses_function_description(self):
        assert _recommend_anchor("failure_mode", {"function_description": "电压采集"}) == "电压采集"

    def test_failure_mode_falls_back_to_input_text(self):
        assert _recommend_anchor("failure_mode", {"input_text": "采集"}) == "采集"

    def test_empty_stored_key_does_not_gate_other_filled_field(self):
        # 空的 function_description 不能挡住已填的 input_text（`or` 链式回退）
        assert _recommend_anchor("failure_mode", {"function_description": "", "input_text": "采集"}) == "采集"

    def test_dfmea_tool_uses_task(self):
        assert _recommend_anchor("dfmea_tool", {"task": "分析DC-DC转换器"}) == "分析DC-DC转换器"

    def test_dfmea_trend_falls_back_to_title(self):
        assert _recommend_anchor("dfmea_trend", {"fmea_title": "DC-DC转换器设计FMEA"}) == "DC-DC转换器设计FMEA"

    def test_dfmea_tool_falls_back_to_team(self):
        assert _recommend_anchor("dfmea_tool", {"team": "质量小组"}) == "质量小组"

    def test_dfmea_trigger_input_text_last_resort(self):
        assert _recommend_anchor("dfmea_trend", {"input_text": "客户投诉"}) == "客户投诉"

    def test_dfmea_tool_empty_when_no_context(self):
        assert _recommend_anchor("dfmea_tool", {}) == ""

    def test_other_trigger_uses_failure_mode(self):
        assert _recommend_anchor("failure_effect", {"failure_mode": "焊缝气孔"}) == "焊缝气孔"

    def test_other_trigger_empty_when_no_failure_mode(self):
        assert _recommend_anchor("optimization", {}) == ""
