"""The live pilot is an explicit approval for one exact provider recipient."""
from types import SimpleNamespace

import pytest

from app.services.workspace_agent import DraftArgs, approved_model_recipient, missing_preview_fields


def recipient(**changes):
    return SimpleNamespace(**({
        "kind": "cloud", "provider": "openai", "api_protocol": "chat_completions",
        "base_url": "https://api.openai.com/v1", "model": "gpt-4.1-mini",
        "allowed_addresses": ["104.18.33.45"],
    } | changes))


def approval(model=None):
    return SimpleNamespace(openai_trial_model=model, platform_port=5000)


def test_cloud_requires_explicit_model_and_does_not_fall_back_to_fixture():
    fixture = recipient(kind="local", base_url="http://127.0.0.1:5001/v1",
                        allowed_addresses=["127.0.0.1"])
    assert approved_model_recipient(fixture, approval())
    assert not approved_model_recipient(fixture, approval("gpt-4.1-mini"))
    assert not approved_model_recipient(recipient(), approval())
    assert approved_model_recipient(recipient(), approval("gpt-4.1-mini"))
    assert approved_model_recipient(
        recipient(allowed_addresses=["198.18.14.88"]), approval("gpt-4.1-mini"),
    )


@pytest.mark.parametrize("changes", [
    {"base_url": "https://api.openai.com.example.test/v1"},
    {"base_url": "https://api.openai.com/v1/additional"},
    {"base_url": "http://api.openai.com/v1"},
    {"api_protocol": "responses"},
    {"model": "different-model"},
    {"allowed_addresses": ["127.0.0.1"]},
    {"allowed_addresses": ["104.18.33.45", "10.0.0.1"]},
])
def test_live_pilot_rejects_recipient_changes(changes):
    assert not approved_model_recipient(recipient(**changes), approval("gpt-4.1-mini"))


def test_model_cannot_fill_a_draft_from_source_or_its_own_reply():
    fields = DraftArgs(title="首件复核 PFMEA", document_no="PFMEA-PI-TRIAL-01")
    messages = [
        {"role": "user", "content": "先创建草稿。另一个报告编号 PFMEA-PI-TRIAL-010。"},
        {"role": "tool", "content": fields.model_dump_json()},
        {"role": "assistant", "content": "我建议标题首件复核 PFMEA。"},
    ]
    assert missing_preview_fields(fields, messages) == ["标题", "单号"]
    messages.append({"role": "user", "content": "名字就叫「首件复核 PFMEA」。"})
    assert missing_preview_fields(fields, messages) == ["单号"]
    messages.append({"role": "user", "content": "登记编号用 PFMEA-PI-TRIAL-01。先给我看看。"})
    assert missing_preview_fields(fields, messages) == []
