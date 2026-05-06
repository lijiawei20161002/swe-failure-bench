"""
Distributed saga orchestrator for multi-step business transactions.

A saga breaks a long-running distributed transaction into a sequence of
local steps.  Each step has a paired *compensation* action that undoes its
effect.  If any step fails the orchestrator runs the compensations of all
previously-completed steps to restore consistency.

Compensations MUST run in the REVERSE order of the original steps.  Step N
may depend on resources created by steps 1…N-1 still being alive; if step 1
is undone first, step 2's compensation has nothing to operate on.

    saga = Saga("book-trip")
    saga.step("reserve-flight",    reserve_flight,    cancel_flight)
    saga.step("reserve-hotel",     reserve_hotel,     cancel_hotel)
    saga.step("charge-card",       charge_card,       refund_card)

    result = orchestrator.run(saga, context)
    # On charge_card failure → compensate: refund_card (N/A, not charged)
    #                                      cancel_hotel
    #                                      cancel_flight
    # i.e., reverse order

Used in: e-commerce checkout, travel booking, microservice workflows.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Step:
    name: str
    action: Callable[[dict], Any]
    compensation: Callable[[dict], None]


@dataclass
class SagaResult:
    success: bool
    failed_step: str | None = None
    compensations_run: list[str] = field(default_factory=list)
    context: dict = field(default_factory=dict)
    error: Exception | None = None


class Saga:
    def __init__(self, name: str):
        self.name = name
        self._steps: list[Step] = []

    def step(
        self,
        name: str,
        action: Callable[[dict], Any],
        compensation: Callable[[dict], None],
    ) -> "Saga":
        self._steps.append(Step(name, action, compensation))
        return self
