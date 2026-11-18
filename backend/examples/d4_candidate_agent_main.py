"""D4 managed SDK loop. This source is bundled into its approved artifact."""
import json
import sys
import time

from openqms_agent_sdk import ManagedLaunch, RunClient, SDKError


def main():
    launch = ManagedLaunch.from_dict(json.load(sys.stdin))
    deadline = time.monotonic() + 120
    with RunClient.from_launch(launch) as run:
        batch = run.claim_messages()
        if batch.messages:
            run.ack_messages(batch_id=batch.batch_id,through_sequence=batch.messages[-1].sequence)
        calls = 0
        for turn in range(9):
            response = run.model_turn(turn=turn)
            if not response.tool_calls:
                run.save_d4_checkpoint()
                run.finish(status='completed')
                return
            for call in response.tool_calls:
                calls += 1
                if calls > 8: raise RuntimeError('Tool limit')
                retries = 0
                while True:
                    try:
                        result = run.model_tool(call_id=call.id)
                    except SDKError as error:
                        if error.status != 409 or retries >= 1: raise
                        retries += 1
                        continue
                    if result.status != 'waiting': break
                    if time.monotonic() >= deadline: raise TimeoutError('Round expired')
                    time.sleep(.1)
        raise RuntimeError('Round limit')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # No original body, model output, credential or token in process output.
        sys.exit(1)
