"""Public API tests for synchronization orchestration."""

import inspect

import applications.synchronization as synchronization_api
from applications.synchronization import (
    SynchronizationResult,
    SynchronizationWorkflow,
)


def test_synchronization_public_api_is_explicit() -> None:
    assert synchronization_api.__all__ == [
        "SynchronizationResult",
        "SynchronizationWorkflow",
    ]
    assert synchronization_api.SynchronizationResult is SynchronizationResult
    assert synchronization_api.SynchronizationWorkflow is SynchronizationWorkflow


def test_public_objects_and_methods_are_documented_and_typed() -> None:
    assert inspect.getdoc(SynchronizationResult)
    assert inspect.getdoc(SynchronizationResult.__post_init__)
    assert inspect.getdoc(SynchronizationWorkflow)
    assert inspect.getdoc(SynchronizationWorkflow.__init__)
    assert inspect.getdoc(SynchronizationWorkflow.run)
    assert inspect.signature(SynchronizationWorkflow.__init__).return_annotation is None
    assert (
        inspect.signature(SynchronizationWorkflow.run).return_annotation
        is SynchronizationResult
    )
