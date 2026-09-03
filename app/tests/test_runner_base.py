"""Tests for the runner-layer base contracts and registries."""

from __future__ import annotations

import pytest

from app.runner import base

_SAFE_REGISTRIES = (
    base.HTTP_EXECUTORS,
    base.AUTH_HANDLERS,
    base.ASSERTIONS,
    base.REPORTERS,
)


@pytest.fixture(autouse=True)
def _isolate_registries():
    """Snapshot the global registries and restore them after each test.

    The registries are module-level singletons, so tests that register dummy
    implementations would otherwise leak state into later tests.
    """
    snapshots = [dict(r) for r in _SAFE_REGISTRIES]
    yield
    for reg, snap in zip(_SAFE_REGISTRIES, snapshots):
        reg.clear()
        reg.update(snap)


def _register_dummy():
    @base.register_http_executor("dummy_exec")
    class _Dummy:
        def call(self, req):
            return None

    return _Dummy


def test_registry_registers_and_resolves():
    cls = _register_dummy()
    assert base.get_executor("DUMMY_EXEC") is cls


def test_registry_duplicate_rejected():
    _register_dummy()

    @base.register_auth_handler("some_auth")
    class _A:
        def apply(self, req, cfg):
            pass

    with pytest.raises(ValueError):

        @base.register_http_executor("dummy_exec")
        class _Dup:
            def call(self, req):
                return None


def test_registry_unknown_raises_keyerror():
    with pytest.raises(KeyError):
        base.get_executor("tidak_ada")


def test_assertion_outcome_labels():
    assert base.AssertionOutcome(passed=True).label == "PASS"
    assert base.AssertionOutcome(passed=False).label == "FAIL"
    assert base.AssertionOutcome(passed=False, skipped=True).label == "SKIP"


def test_verdict_builder_summary():
    _DummyVerdict = type(
        "_DummyVerdict",
        (),
        {
            "__init__": lambda self, s: setattr(self, "status", s),
            "model_dump": lambda self: {"status": self.status},
        },
    )
    vb = base.VerdictBuilder(base_url="http://x")
    vb.verdicts = [_DummyVerdict("PASS"), _DummyVerdict("FAIL"), _DummyVerdict("SKIPPED")]
    s = vb.summarize()
    assert s["total"] == 3
    assert s["passed"] == 1
    assert s["failed"] == 1
    assert s["skipped"] == 1
    assert s["base_url"] == "http://x"


def test_protocols_are_defined():
    assert base.HttpExecutor is not None
    assert base.AuthHandler is not None
    assert base.Assertion is not None
    assert base.Reporter is not None
