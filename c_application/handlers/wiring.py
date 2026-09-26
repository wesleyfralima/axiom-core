import inspect
from collections.abc import Callable
from typing import Any

from a_core import DomainEvent
from b_domain.events.task_events import (
    TaskCancelledEvent,
    TaskCompletedEvent,
    TaskDeletedEvent,
)
from b_domain.ports.event_bus import EventBus
from b_domain.ports.providers import ClockProvider
from b_domain.ports.unit_of_work import UnitOfWork, UowFactoryType
from b_domain.services.user_behavior_learner import UserBehaviorLearner
from b_domain.services.user_behavior_metrics_aggregator import (
    UserBehaviorMetricsAggregator,
)
from c_application.handlers.task_handlers.create_recurring_task_handler import (
    CreateRecurringTaskHandler,
)
from c_application.handlers.task_handlers.unlock_task_dependencies_handler import (
    UnlockTaskDependenciesHandler,
)
from c_application.handlers.user_handlers.update_user_behavior_handler import (
    UpdateUserBehaviorHandler,
)

type HandlerFactoryType = Callable[[UnitOfWork], Any]


def register_essential_handlers(
    bus: EventBus,
    uow_factory: UowFactoryType,
    clock: ClockProvider,
) -> None:
    """Register essential event handlers required for system integrity.

    These handlers are mandatory for the core task management workflow.
    They ensure that dependencies are properly unlocked and recurrence
    rules are enforced, preventing the system from breaking down.

    Args:
        bus (EventBus): The event bus instance used for publishing and
            subscribing events.
        uow_factory (UowFactoryType): Factory of UnitOfWork instances to
            manage transactional consistency.
        clock (Clock): Clock instance to manage transactional consistency.
    """

    # Unlocking task dependencies is vital for task flow:
    # When a task is completed, dependent tasks must be unlocked so that
    # users can continue progressing. Without this, blocked tasks would
    # remain inaccessible, breaking the GTD workflow and halting productivity.
    # A cancelled blocker will never be done, so it unlocks them too.
    # A deleted one neither (it used to keep its dependents blocked forever).
    for closed_event in (TaskCompletedEvent, TaskCancelledEvent, TaskDeletedEvent):
        _subscribe(
            bus,
            uow_factory,
            closed_event,
            UnlockTaskDependenciesHandler,
            clock=clock,
        )

    # Recurrence is a core business rule:
    # Completing a recurring task should automatically generate the next
    # occurrence. This ensures that recurring commitments (e.g., weekly
    # reports, daily routines) are preserved without manual intervention.
    # Without this handler, recurring tasks would stop after the first completion.
    # Cancelling one occurrence skips it: the series goes on (unless the
    # cancel ends the series, which the handler checks).
    for closed_event in (TaskCompletedEvent, TaskCancelledEvent):
        _subscribe(
            bus,
            uow_factory,
            closed_event,
            CreateRecurringTaskHandler,
        )


def register_optional_handlers(
    bus: EventBus,
    uow_factory: UowFactoryType,
    aggregator: UserBehaviorMetricsAggregator | None,
    learner: UserBehaviorLearner | None,
) -> None:
    """Register optional event handlers for advanced analytics and personalization.

    These handlers are optional and typically available only in premium
    versions of the system. They enhance the user experience by tracking
    behavior, aggregating metrics, and adapting productivity models.

    Args:
        bus (EventBus): The event bus instance used for publishing and
            subscribing events.
        uow_factory (UowFactoryType): Factory of UnitOfWork instances to
            manage transactional consistency.
        aggregator (Optional[UserBehaviorMetricsAggregator]): Aggregator
            for user behavior metrics.
        learner (Optional[UserBehaviorLearner]): Learner service for
            adapting user behavior models.
    """

    if not (aggregator and learner):
        return

    # User behavior tracking is optional but highly valuable:
    # If metrics aggregation and learning services are available, we subscribe
    # a handler that updates user behavior models whenever tasks are completed.
    # This supports analytics, personalization, and adaptive productivity features.
    # It is considered optional because it is typically available only in premium
    # versions of the system, but when enabled it provides deep insights into
    # user habits and helps optimize future recommendations.
    _subscribe(
        bus,
        uow_factory,
        TaskCompletedEvent,
        UpdateUserBehaviorHandler,
        aggregator=aggregator,
        learner=learner,
    )


def _subscribe(
    bus: EventBus,
    uow_factory: UowFactoryType,
    event_type: type[DomainEvent],
    handler_cls: type,
    **extras: Any,
) -> None:
    """Helper function to subscribe a handler to the event bus.

    Wraps the handler execution in its own UnitOfWork transaction to ensure
    isolation and consistency. This guarantees that each handler runs safely
    without leaking side effects across different event subscribers.

    Args:
        bus (EventBus): The event bus instance used for publishing
            and subscribing events.
        uow_factory (UowFactoryType): Factory of UnitOfWork instances
            to manage transactional consistency.
        event_type (Type[DomainEvent]): The domain event type to subscribe to.
        handler_cls (Type): The handler class to instantiate and execute.
        **extras (Any): Additional dependencies required by the handler.
    """

    async def handler(event: DomainEvent) -> None:

        async with uow_factory() as uow:
            instance = handler_cls(uow, **extras)

            # 1. Try to get the 'handle' method; if not present, use the instance itself
            target = getattr(instance, "handle", instance)

            # 2. Verify that the target is callable and check if it's async
            if callable(target):
                if inspect.iscoroutinefunction(target):
                    await target(event)
                else:
                    target(event)
            else:
                raise TypeError(
                    f"The handler '{handler_cls.__name__}' is not "
                    f"callable and does not contain a 'handle' method.'."
                )

    bus.subscribe(event_type, handler)
