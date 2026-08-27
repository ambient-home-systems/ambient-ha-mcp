from typing import cast

import pytest

from ambient_ha.models.control import ControlIntent, ControlResult, ControlStatus
from ambient_ha.policy.execution import ActionExecutor
from ambient_ha.tools.control import (
    control_climate,
    control_light,
    control_media_player,
)


class RecordingExecutor:
    def __init__(self) -> None:
        self.intents: list[ControlIntent] = []

    async def execute(self, intent: ControlIntent) -> ControlResult:
        self.intents.append(intent)
        return ControlResult(
            ok=True,
            status="accepted",
            message="accepted",
            request_id="request",
            correlation_id="correlation",
            action=intent.action.value,
            policy_decision="allow",
        )

    def reject_invalid(
        self,
        *,
        mcp_tool: str,
        domain: object,
        action: str,
        entity_ids: list[str],
    ) -> ControlResult:
        return ControlResult(
            ok=False,
            status="clarification_required",
            message="invalid",
            request_id="request",
            correlation_id="correlation",
            action=action,
            policy_decision="deny",
            matched_rules=["input_validation.invalid"],
            error_code="invalid_request",
        )


@pytest.mark.anyio
async def test_invalid_semantic_values_are_rejected_before_the_executor() -> None:
    recorder = RecordingExecutor()
    executor = cast(ActionExecutor, recorder)

    results = [
        await control_light(
            executor,
            entity_ids=["light.kitchen"],
            action="on",
            brightness_percent=101,
        ),
        await control_light(
            executor,
            entity_ids=["light.kitchen"],
            action="off",
            brightness_percent=50,
        ),
        await control_light(
            executor,
            entity_ids=["Kitchen Light"],
            action="on",
        ),
        await control_light(
            executor,
            entity_ids=["light.kitchen"],
            action="on",
            rgb_color=[1, 2],
        ),
        await control_media_player(
            executor,
            entity_ids=["media_player.den"],
            action="volume",
        ),
        await control_climate(
            executor,
            entity_ids=["climate.house"],
        ),
        await control_climate(
            executor,
            entity_ids=["climate.house"],
            target_temperature=20,
        ),
    ]

    assert recorder.intents == []
    assert all(result.status is ControlStatus.CLARIFICATION_REQUIRED for result in results)
    assert all(result.error_code == "invalid_request" for result in results)


@pytest.mark.anyio
async def test_valid_semantic_request_reaches_executor_without_confirmation_field() -> None:
    recorder = RecordingExecutor()

    result = await control_light(
        cast(ActionExecutor, recorder),
        entity_ids=["LIGHT.Kitchen"],
        action="on",
        brightness_percent=40,
    )

    assert result.ok is True
    assert recorder.intents[0].entity_ids == ["light.kitchen"]
    assert "confirmed" not in ControlIntent.model_fields
