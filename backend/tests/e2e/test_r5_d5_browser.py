"""T9 real Chromium correction intent and checkpoint withdrawal persistence."""
import pytest
from tests.e2e.test_r5_d5_ui import run_r5_ui
from tests.services.agent_runtime.test_r5_model_binding import r5_case
from tests.e2e.d4_text_local_harness import d4_text_local_trial, owned_local_trial

pytestmark=[pytest.mark.ci_r5_native,pytest.mark.requires_db,pytest.mark.ci_browser]

@pytest.mark.asyncio
async def test_browser_explicit_correction_and_selected_checkpoint_withdrawal(r5_case,tmp_path):
    await run_r5_ui(r5_case,tmp_path,'r5-checkpoint-withdrawal.spec.ts')
