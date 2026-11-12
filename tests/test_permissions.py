import asyncio

from jarvis.config import AppConfig
from jarvis.core.errors import PermissionDenied
from jarvis.security.permissions import (
    ConfirmationRequest,
    ConfirmationResult,
    PermissionPolicy,
    Risk,
)


def test_low_risk_never_asks() -> None:
    policy = PermissionPolicy(AppConfig())
    assert policy.evaluate("open_app", Risk.LOW).needs_confirmation is False


def test_high_risk_blocked_by_default() -> None:
    policy = PermissionPolicy(AppConfig())
    decision = policy.evaluate("delete_path", Risk.HIGH)
    assert decision.needs_confirmation is False
    request = ConfirmationRequest("delete_path", Risk.HIGH, "Delete", human_args="path: C:/tmp/x")
    try:
        asyncio.run(policy.authorize("delete_path", Risk.HIGH, request))
    except PermissionDenied as exc:
        assert "disabled" in str(exc).lower()
    else:
        raise AssertionError("high risk should be denied by default")


def test_medium_requires_confirmation_and_can_deny() -> None:
    calls = []

    async def deny(_request):
        calls.append(_request)
        return ConfirmationResult.DENY

    policy = PermissionPolicy(AppConfig(), confirmer=deny)
    decision = policy.evaluate("create_file", Risk.MEDIUM)
    assert decision.needs_confirmation is True
    request = ConfirmationRequest("create_file", Risk.MEDIUM, "Create", human_args="path: x")
    try:
        asyncio.run(policy.authorize("create_file", Risk.MEDIUM, request))
    except PermissionDenied:
        pass
    else:
        raise AssertionError("denied confirmation should raise")
    assert len(calls) == 1


def test_medium_allow_always_skips_future_prompts() -> None:
    calls = []

    async def allow(_request):
        calls.append(_request)
        return ConfirmationResult.ALLOW_ALWAYS

    policy = PermissionPolicy(AppConfig(), confirmer=allow)
    request = ConfirmationRequest("create_file", Risk.MEDIUM, "Create")
    asyncio.run(policy.authorize("create_file", Risk.MEDIUM, request))
    asyncio.run(policy.authorize("create_file", Risk.MEDIUM, request))
    assert len(calls) == 1


def test_path_guard(tmp_path) -> None:
    from pathlib import Path

    cfg = AppConfig()
    cfg.allowed_roots = [str(tmp_path)]
    policy = PermissionPolicy(cfg)
    inside = tmp_path / "a.txt"
    assert policy.path_allowed(inside)
    assert not policy.path_allowed(Path("C:/Windows/System32"))


def test_confirmation_request_describe() -> None:
    request = ConfirmationRequest(
        "delete_path",
        Risk.HIGH,
        "Delete a folder",
        human_args="path: C:/Users/me/file",
        detail="Requires explicit confirmation",
    )
    text = request.describe()
    assert "delete_path" in text
    assert "C:/Users/me/file" in text
    assert "High risk" in text