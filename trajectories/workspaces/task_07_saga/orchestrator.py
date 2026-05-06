"""
Saga orchestrator: executes saga steps and runs compensations on failure.
"""
from __future__ import annotations
from saga import Saga, SagaResult


class SagaOrchestrator:
    """
    Runs a Saga's steps in sequence.  On failure, compensates all
    previously-completed steps.

    The invariant: compensations must run in REVERSE order of the
    original steps, because later steps may depend on resources created
    by earlier steps being still intact.  Undoing step 1 before step 2's
    compensation runs leaves step 2's compensation with nothing to act on.
    """

    def run(self, saga: Saga, context: dict | None = None) -> SagaResult:
        if context is None:
            context = {}

        completed: list = []   # steps that have run successfully
        result = SagaResult(success=True, context=context)

        # ── execute steps ──────────────────────────────────────────────
        for step in saga._steps:
            try:
                step.action(context)
                completed.append(step)
            except Exception as exc:
                result.success = False
                result.failed_step = step.name
                result.error = exc
                break

        # ── compensate on failure ──────────────────────────────────────
        if not result.success:
            for step in reversed(completed):
                try:
                    step.compensation(context)
                    result.compensations_run.append(step.name)
                except Exception as exc:
                    # Compensation failure — record and continue
                    result.compensations_run.append(f"{step.name}:FAILED:{exc}")

        return result
