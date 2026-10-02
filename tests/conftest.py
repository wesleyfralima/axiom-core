import builtins
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from typing import Any, Protocol
from uuid import UUID

import pytest

from a_core import Entity, IdPrefix, tracks_entity
from b_domain.entities import Context, Task, TimeEntry, User
from b_domain.entities.outbox_event import OutboxEvent
from b_domain.ports.providers import ClockProvider
from b_domain.ports.repositories import (
    CalendarDayRepository,
    ContextRepository,
    OutboxEventRepository,
    SyncStore,
    TaskHistoryRepository,
    TaskRepository,
    UserBehaviorMetricsRepository,
    UserBehaviorProfileRepository,
    UserRepository,
)
from b_domain.ports.repositories.filters import (
    OutboxEventFilter,
    TaskFilter,
    TimeEntryFilter,
    UserFilter,
)
from b_domain.ports.repositories.task_view_repository import TaskViewRepository
from b_domain.ports.repositories.time_entry_repository import TimeEntryRepository
from b_domain.ports.unit_of_work import UnitOfWork
from b_domain.services.sync_merge import MergePlan
from b_domain.value_objects import (
    ContextId,
    EnergyLevel,
    TaskId,
    UserBehaviorProfile,
    UserId,
)
from b_domain.value_objects.identifiers import TimeEntryId
from b_domain.value_objects.sync import (
    CREATED,
    FieldKey,
    Hlc,
    SyncEntity,
    SyncOperation,
    SyncState,
)
from b_domain.value_objects.task_history import TaskHistoryEntry
from b_domain.value_objects.task_view import TaskView, ViewScope
from b_domain.value_objects.user_behavior_metrics import UserBehaviorMetrics
from b_domain.value_objects.work_calendar import CalendarDay, HolidayRegion


class FakeClock(ClockProvider):
    def __init__(self, initial_time: datetime | None = None) -> None:
        self._now = initial_time or datetime(2026, 3, 5, 12, tzinfo=UTC)

    def now(self) -> datetime:
        return self._now

    def set_time(self, new_time: datetime) -> None:
        self._now = new_time


class FakeTaskRepository(TaskRepository):
    def __init__(self, tasks: dict[str, Task] | None = None) -> None:
        self.tasks = tasks if tasks is not None else {}
        super().__init__(seen_entities=set())

    @tracks_entity
    async def add(self, task: Task) -> Task:
        self.tasks[str(task.id)] = task
        return task

    async def update(self, task: Task) -> Task:
        if str(task.id) in self.tasks:
            self.tasks[str(task.id)] = task
        return task

    async def update_many(self, tasks: list[Task]) -> list[Task]:
        """Simulate a bulk update in the fake repository."""
        return [await self.update(task) for task in tasks]

    async def delete(self, task_id: TaskId) -> None:
        del self.tasks[str(task_id)]

    @tracks_entity
    async def get_by_id(
        self, task_id: TaskId, user_id: UserId | None = None
    ) -> Task | None:
        found = self.tasks.get(str(task_id), None)

        if found is not None and user_id is not None:
            return found if str(found.user_id) == str(user_id) else None

        return found

    @tracks_entity
    async def find_by_id_prefix(
        self,
        id_prefix: IdPrefix,
        user_id: UserId | None = None,
        deleted: bool = False,
    ) -> list[Task]:
        # Scoped by user, as the real repository is
        return [
            task
            for key, task in self.tasks.items()
            if id_prefix.matches(key)
            and (user_id is None or task.user_id == user_id)
            and (task.deleted_at is not None) == deleted
        ]

    def _apply_filters(self, filters: TaskFilter) -> list[Task]:
        """Internal helper to reuse the filter logic."""

        results = [
            t
            for t in self.tasks.values()
            if filters.deleted is None or (t.deleted_at is not None) == filters.deleted
        ]
        if filters.series_id is not None:
            results = [t for t in results if t.series_id == filters.series_id]
        if filters.in_series is not None:
            results = [
                t for t in results if (t.series_id is not None) == filters.in_series
            ]
        if filters.ids is not None:
            wanted = {str(i) for i in filters.ids}
            results = [t for t in results if str(t.id) in wanted]

        if filters.user_id:
            results = [t for t in results if t.user_id == filters.user_id]
        if filters.status:
            results = [t for t in results if t.status == filters.status]
        if filters.exclude_statuses:
            results = [t for t in results if t.status not in filters.exclude_statuses]
        if filters.context_id:
            results = [t for t in results if t.context_id == filters.context_id]
        if filters.priority:
            results = [t for t in results if t.priority == filters.priority]
        if filters.complexity:
            results = [t for t in results if t.complexity == filters.complexity]
        if filters.parent_id:
            results = [t for t in results if t.parent_id == filters.parent_id]
        if filters.tags:
            results = [t for t in results if set(filters.tags) <= t.tags]
        if filters.has_context is not None:
            results = [
                t for t in results if (t.context_id is not None) == filters.has_context
            ]
        if filters.has_due_date is not None:
            results = [
                t for t in results if (t.due_date is not None) == filters.has_due_date
            ]
        # As the database compares them: the stored value, without its zone
        if filters.due_after is not None:
            after = filters.due_after.replace(tzinfo=None)
            results = [
                t
                for t in results
                if t.due_date and t.due_date.value.replace(tzinfo=None) >= after
            ]
        if filters.due_before is not None:
            before = filters.due_before.replace(tzinfo=None)
            results = [
                t
                for t in results
                if t.due_date and t.due_date.value.replace(tzinfo=None) <= before
            ]

        return results

    @tracks_entity
    async def list(self, filters: TaskFilter) -> list[Task]:
        filtered = self._apply_filters(filters)
        # Apply OFFSET and LIMIT (in-memory pagination)
        start = filters.offset
        end = start + filters.limit
        return filtered[start:end]

    async def count(self, filters: TaskFilter) -> int:
        # count ignores pagination and returns the filter total
        return len(self._apply_filters(filters))

    # --- Hierarchy and dependencies ---

    @tracks_entity
    async def get_subtasks(
        self, parent_id: TaskId, limit: int = 100, offset: int = 0
    ) -> builtins.list[Task]:
        # As the database does: live ones, oldest first
        subs = sorted(
            (
                t
                for t in self.tasks.values()
                if t.parent_id == parent_id and t.deleted_at is None
            ),
            key=lambda t: t.created_at,
        )
        return subs[offset : offset + limit]

    @tracks_entity
    async def find_tasks_blocked_by(self, task_id: TaskId) -> builtins.list[Task]:
        return [
            t
            for t in self.tasks.values()
            if task_id in t.depends_on and t.deleted_at is None
        ]

    async def purge_deleted(self, user_id: UserId, before: datetime) -> int:
        gone: list[str] = [
            key
            for key, t in self.tasks.items()
            if t.user_id == user_id
            and t.deleted_at is not None
            and t.deleted_at <= before
        ]
        for key in gone:
            del self.tasks[key]
        return len(gone)

    # --- Helper for the Axiom context/energy logic ---

    @tracks_entity
    async def find_by_user(
        self,
        user_id: UserId,
        context_id: ContextId | None = None,
        max_energy: EnergyLevel | None = None,
    ) -> builtins.list[Task]:
        results = [t for t in self.tasks.values() if t.user_id == user_id]

        if context_id:
            results = [t for t in results if t.context_id == context_id]

        if max_energy:
            # required_energy_level is the field defined on Task
            results = [t for t in results if t.required_energy_level <= max_energy]

        return results

    async def task_ids_from_id_prefixes(
        self, partial_ids: Iterable[IdPrefix]
    ) -> builtins.list[TaskId]:

        # Convert to a tuple, since startswith() accepts a tuple of strings
        # to check several possibilities at once.
        prefixes = tuple(str(p) for p in partial_ids)

        result: list[TaskId] = []

        # No prefixes: return an empty list to skip the work
        if not prefixes:
            return []

        for prefix in prefixes:
            pref_vo: IdPrefix = IdPrefix(value=prefix)
            found_tasks: list[Task] = await self.find_by_id_prefix(id_prefix=pref_vo)

            # Same messages as the real repository (axiom-enterprise)
            if not found_tasks:
                raise ValueError(f"No task found with ID prefix '{prefix}'.")
            if len(found_tasks) > 1:
                raise ValueError(f"Ambiguous prefix: {prefix}.")

            result.append(found_tasks[0].id)

        return result


class FakeUserRepository(UserRepository):
    def __init__(self, users: dict[str, User] | None = None) -> None:
        self.users: dict[str, User] = users if users is not None else {}
        super().__init__(seen_entities=set())

    @tracks_entity
    async def add(self, user: User) -> None:
        self.users[str(user.id)] = user

    async def update(self, user: User) -> None:
        if str(user.id) in self.users:
            self.users[str(user.id)] = user

    async def delete(self, user_id: UserId) -> None:
        if str(user_id) in self.users:
            del self.users[str(user_id)]

    @tracks_entity
    async def get_by_id(self, user_id: UserId) -> User | None:
        return self.users.get(str(user_id), None)

    @tracks_entity
    async def get_by_username(self, username: str) -> User | None:
        """Busca linear por username (simula UNIQUE constraint)."""
        return next((u for u in self.users.values() if u.username == username), None)

    # --- Filters and pagination ---

    def _apply_filters(self, filters: UserFilter) -> list[User]:
        results = list(self.users.values())

        if filters.username:
            results = [
                u for u in results if filters.username.lower() in u.username.lower()
            ]

        # If the User entity gets an 'is_active' field in the future:
        # if filters.is_active is not None:
        #     results = [u for u in results if u.is_active == filters.is_active]

        return results

    @tracks_entity
    async def list(self, filters: UserFilter) -> list[User]:
        filtered = self._apply_filters(filters)

        # Manual pagination
        start = filters.offset
        end = start + filters.limit
        return filtered[start:end]

    async def count(self, filters: UserFilter) -> int:
        # Ignore offset/limit to return the absolute total
        return len(self._apply_filters(filters))

    @tracks_entity
    async def get_by_email(self, email: str) -> User | None:
        return None


class FakeTimeEntryRepository(TimeEntryRepository):
    def __init__(self, entries: list[TimeEntry] | None = None) -> None:
        # A list simulates the table (shared by the units of work of a test)
        self.entries: list[TimeEntry] = entries if entries is not None else []
        super().__init__(seen_entities=set())

    async def delete(self, entry_id: TimeEntryId) -> None:
        self.entries[:] = [e for e in self.entries if e.id.value != entry_id.value]

    @tracks_entity
    async def add(self, entry: TimeEntry) -> TimeEntry:
        """Simulate the INSERT into the database."""
        self.entries.append(entry)
        return entry

    async def update(self, entry: TimeEntry) -> None:
        """
        In memory, the object is usually already updated by reference.
        A real database would run the UPDATE here.
        """
        for i, existing in enumerate(self.entries):
            if existing.id == entry.id:
                self.entries[i] = entry
                break

    async def update_all(self, entries: list[TimeEntry]) -> None:
        """Simulate a bulk update."""
        for entry in entries:
            await self.update(entry)

    @tracks_entity
    async def get_by_id(self, entry_id: TimeEntryId) -> TimeEntry | None:
        """Fetch a specific entry."""
        return next((e for e in self.entries if e.id == entry_id), None)

    @tracks_entity
    async def get_actives_for_task(self, task_id: TaskId) -> list[TimeEntry]:
        """Return the running timers for a specific task."""
        return [e for e in self.entries if e.task_id == task_id and e.end_time is None]

    @tracks_entity
    async def get_active_for_user(self, user_id: UserId) -> TimeEntry | None:
        """
        Fetch the user's currently active timer.
        Essential for the 'only one timer at a time' rule.
        """
        return next(
            (e for e in self.entries if e.user_id == user_id and e.end_time is None),
            None,
        )

    @tracks_entity
    async def find_by_user(self, user_id: UserId) -> list[TimeEntry]:
        """Return the user's whole tracking history."""
        return [e for e in self.entries if e.user_id == user_id]

    @tracks_entity
    async def search(self, filters: TimeEntryFilter) -> list[TimeEntry]:
        found = list(self.entries)
        if filters.user_id is not None:
            found = [e for e in found if e.user_id == filters.user_id]
        if filters.task_id is not None:
            found = [e for e in found if e.task_id == filters.task_id]
        if filters.started_after is not None:
            found = [e for e in found if e.start_time >= filters.started_after]
        if filters.started_before is not None:
            found = [e for e in found if e.start_time < filters.started_before]
        return found


class FakeContextRepository(ContextRepository):
    def __init__(
        self,
        contexts: dict[str, Context] | None = None,
        tasks: dict[str, Task] | None = None,
    ) -> None:
        self.contexts = contexts if contexts is not None else {}
        # The shared task store, so delete() can detach tasks like the port says
        self._tasks = tasks if tasks is not None else {}
        super().__init__(seen_entities=set())

    @tracks_entity
    async def add(self, context: Context) -> None:
        self.contexts[str(context.id)] = context

    async def update(self, context: Context) -> None:
        self.contexts[str(context.id)] = context

    async def delete(self, context_id: ContextId) -> None:
        self.contexts.pop(str(context_id), None)
        for task in self._tasks.values():
            if task.context_id == context_id:
                task.context_id = None

    @tracks_entity
    async def get_by_id(self, context_id: ContextId, user_id: UserId) -> Context | None:
        context = self.contexts.get(str(context_id))
        return context if context and context.user_id == user_id else None

    @tracks_entity
    async def list_by_user(self, user_id: UserId) -> list[Context]:
        return sorted(
            (c for c in self.contexts.values() if c.user_id == user_id),
            key=lambda c: c.name.casefold(),
        )


class FakeUserBehaviorMetricsRepository(UserBehaviorMetricsRepository):
    def __init__(self) -> None:
        self.metrics_store: dict[str, UserBehaviorMetrics] = {}

    async def save(self, metrics: UserBehaviorMetrics) -> None:
        """Create or update metrics for a user."""
        self.metrics_store[str(metrics.user_id)] = metrics

    async def get_by_user_id(self, user_id: UserId) -> UserBehaviorMetrics | None:
        """Retrieve metrics for a given user."""
        return self.metrics_store.get(str(user_id))

    async def delete(self, user_id: UserId) -> None:
        """Delete metrics associated with a user."""
        if str(user_id) in self.metrics_store:
            del self.metrics_store[str(user_id)]


class FakeUserBehaviorProfileRepository(UserBehaviorProfileRepository):
    def __init__(self) -> None:
        self.profiles: dict[str, UserBehaviorProfile] = {}

    async def save(self, profile: UserBehaviorProfile) -> None:
        """Create or update the profile."""
        self.profiles[str(profile.user_id)] = profile

    async def get_by_user_id(self, user_id: UserId) -> UserBehaviorProfile | None:
        """Retrieve the profile for a user."""
        return self.profiles.get(str(user_id))

    async def delete(self, user_id: UserId) -> None:
        """Delete the profile for a user."""
        if str(user_id) in self.profiles:
            del self.profiles[str(user_id)]


class FakeOutboxEventRepository(OutboxEventRepository):
    """The outbox as a list: what the unit of work wrote."""

    def __init__(self) -> None:
        self.events: list[OutboxEvent] = []

    async def add_many(self, events: list[OutboxEvent]) -> None:
        self.events.extend(events)

    async def get_unprocessed(self, limit: int = 50) -> list[OutboxEvent]:
        return [e for e in self.events if e.processed_at is None][:limit]

    async def update(self, event: OutboxEvent) -> None:
        return None

    async def delete_processed_before(self, cutoff: datetime) -> int:
        return 0

    async def search(self, filters: OutboxEventFilter) -> list[OutboxEvent]:
        return list(self.events)


class FakeTaskHistoryRepository(TaskHistoryRepository):
    def __init__(self, entries: list[TaskHistoryEntry] | None = None) -> None:
        self.entries: list[TaskHistoryEntry] = entries if entries is not None else []

    async def add_many(self, entries: list[TaskHistoryEntry]) -> None:
        self.entries.extend(entries)

    async def recent(self, user_id: UserId, limit: int = 200) -> list[TaskHistoryEntry]:
        mine = [e for e in self.entries if e.user_id == user_id]
        return list(reversed(mine))[:limit]

    async def caused_by(self, entry_id: UUID) -> list[TaskHistoryEntry]:
        return [e for e in self.entries if e.caused_by == entry_id]

    async def of_command(self, command_id: UUID) -> list[TaskHistoryEntry]:
        return [e for e in reversed(self.entries) if e.command_id == command_id]

    async def between(
        self, user_id: UserId, start: datetime, end: datetime
    ) -> list[TaskHistoryEntry]:
        return [
            e
            for e in self.entries
            if e.user_id == user_id and start <= e.occurred_at < end
        ]

    async def list_for_tasks(
        self, task_ids: list[TaskId], user_id: UserId
    ) -> list[TaskHistoryEntry]:
        return [
            e for e in self.entries if e.task_id in task_ids and e.user_id == user_id
        ]

    async def list_for_task(
        self, task_id: TaskId, user_id: UserId
    ) -> list[TaskHistoryEntry]:
        return [
            e for e in self.entries if e.task_id == task_id and e.user_id == user_id
        ]


class FakeTaskViewRepository(TaskViewRepository):
    def __init__(self, views: list[TaskView] | None = None) -> None:
        self.views: list[TaskView] = views if views is not None else []

    async def list_by_user(self, user_id: UserId) -> list[TaskView]:
        return sorted(
            (v for v in self.views if v.user_id == user_id), key=lambda v: v.name
        )

    async def save(self, view: TaskView) -> None:
        self.views[:] = [v for v in self.views if v != view]
        self.views.append(view)

    async def remove(
        self, user_id: UserId, name: str, scope: ViewScope, now: datetime
    ) -> bool:
        before: int = len(self.views)
        self.views[:] = [
            v
            for v in self.views
            if (v.user_id, v.name, v.scope) != (user_id, name, scope)
        ]
        return len(self.views) < before


class FakeCalendarDayRepository(CalendarDayRepository):
    def __init__(self, days: dict[str, list[CalendarDay]] | None = None) -> None:
        self.days: dict[str, list[CalendarDay]] = days if days is not None else {}

    async def list_by_user(self, user_id: UserId) -> list[CalendarDay]:
        return sorted(self.days.get(str(user_id), []), key=lambda d: d.day)

    async def save(self, user_id: UserId, day: CalendarDay) -> None:
        await self.remove(user_id, day.day, day.yearly)
        self.days.setdefault(str(user_id), []).append(day)

    async def remove(self, user_id: UserId, day: date, yearly: bool) -> None:
        mine: list[CalendarDay] = self.days.get(str(user_id), [])
        mine[:] = [d for d in mine if (d.day, d.yearly) != (day, yearly)]


class FakeHolidayProvider:
    """Holidays by region, set by the test: ``by_region["BR"] = {date: "name"}``.

    A holiday counts in its year only; a region is supported once it has an
    entry. ``names`` are the regions it lists (a few countries and states);
    ``region_for_timezone`` knows ``America/Sao_Paulo`` (BR) when BR is
    supported.
    """

    def __init__(
        self,
        by_region: dict[str, dict[date, str]] | None = None,
        names: dict[str, str] | None = None,
    ) -> None:
        self.by_region: dict[str, dict[date, str]] = (
            by_region if by_region is not None else {}
        )
        self.names: dict[str, str] = names or {
            "BR": "Brazil",
            "BR-RJ": "Rio de Janeiro",
            "BR-SP": "São Paulo",
            "PT": "Portugal",
            "US": "United States",
            "US-CA": "California",
        }

    def supports(self, region: str) -> bool:
        return region in self.by_region

    def regions(self, country: str | None = None) -> list[HolidayRegion]:
        return [
            HolidayRegion(code, name)
            for code, name in sorted(self.names.items())
            if ("-" not in code if country is None else code.startswith(f"{country}-"))
        ]

    def holidays(self, region: str, year: int) -> Mapping[date, str]:
        return {
            d: name
            for d, name in self.by_region.get(region, {}).items()
            if d.year == year
        }

    def region_for_timezone(self, timezone: str) -> str | None:
        if timezone == "America/Sao_Paulo" and "BR" in self.by_region:
            return "BR"
        return None


@dataclass
class FakeSyncStore(SyncStore):
    """A device's sync side in memory, with its data as plain rows.

    ``rows`` stands for the device's data: ``(entity, id) → fields``.
    ``change`` is a local change as the real store captures it: the row
    changes, an operation waits to be pushed and the field keeps its clock.
    ``apply`` changes the rows the way a database would.
    """

    sync_state: SyncState | None = None
    outbox: list[SyncOperation] = field(default_factory=list)
    kept: dict[FieldKey, Hlc] = field(default_factory=dict)
    rows: dict[tuple[SyncEntity, UUID], dict[str, Any]] = field(default_factory=dict)
    account_row: tuple[SyncEntity, UUID] | None = None
    adopted: list[tuple[UserId, UserId]] = field(default_factory=list)
    plans: list[MergePlan] = field(default_factory=list)
    # The device's users, for ``adopt_account`` to move one
    users: dict[str, User] = field(default_factory=dict)

    async def state(self) -> SyncState | None:
        return self.sync_state

    async def save_state(self, state: SyncState) -> None:
        self.sync_state = state

    async def pending(self, limit: int) -> list[SyncOperation]:
        return self.outbox[:limit]

    async def count_pending(self) -> int:
        return len(self.outbox)

    async def forget(self, op_ids: Collection[UUID]) -> None:
        self.outbox = [op for op in self.outbox if op.op_id not in op_ids]

    async def clocks(self, operations: Iterable[SyncOperation]) -> dict[FieldKey, Hlc]:
        rows = {(op.entity, op.entity_id) for op in operations}
        return {
            key: hlc
            for key, hlc in self.kept.items()
            if (key.entity, key.entity_id) in rows
        }

    async def apply(self, plan: MergePlan) -> None:
        self.plans.append(plan)
        for row in plan.rows:
            key = (row.entity, row.entity_id)
            if row.delete:
                self.rows.pop(key, None)
            elif row.create is not None:
                self.rows[key] = dict(row.create)
            elif key in self.rows:
                self.rows[key].update(row.fields)
        self.kept.update(plan.clocks)

    async def snapshot(self, clock: Hlc, include_account: bool) -> Hlc:
        for (entity, entity_id), fields in self.rows.items():
            if (entity, entity_id) == self.account_row and not include_account:
                continue
            clock = clock.tick(clock_time(clock))
            op = SyncOperation.created(clock, entity, entity_id, dict(fields))
            self.outbox.append(op)
            self.kept[FieldKey(entity=entity, entity_id=entity_id, field=CREATED)] = (
                clock
            )
            for name in fields:
                self.kept[FieldKey(entity=entity, entity_id=entity_id, field=name)] = (
                    clock
                )
        return clock

    async def adopt_account(self, local: UserId, account: UserId) -> None:
        self.adopted.append((local, account))
        user = self.users.pop(str(local), None)
        if user is not None:
            user.id = account
            self.users[str(account)] = user

    def change(
        self, now: datetime, entity: SyncEntity, entity_id: UUID, **fields: Any
    ) -> None:
        """A local change after joining, as the real store captures it."""
        assert self.sync_state is not None
        clock = self.sync_state.clock
        key = (entity, entity_id)
        if key not in self.rows:
            clock = clock.tick(now)
            self.rows[key] = dict(fields)
            self.outbox.append(SyncOperation.created(clock, entity, entity_id, fields))
            self.kept[FieldKey(entity=entity, entity_id=entity_id, field=CREATED)] = (
                clock
            )
            for name in fields:
                self.kept[FieldKey(entity=entity, entity_id=entity_id, field=name)] = (
                    clock
                )
        else:
            for name, value in fields.items():
                clock = clock.tick(now)
                self.rows[key][name] = value
                self.outbox.append(
                    SyncOperation(
                        entity=entity,
                        entity_id=entity_id,
                        field=name,
                        value=value,
                        hlc=clock,
                    )
                )
                self.kept[FieldKey(entity=entity, entity_id=entity_id, field=name)] = (
                    clock
                )
        self.sync_state = replace(self.sync_state, clock=clock)


def clock_time(clock: Hlc) -> datetime:
    """The time a clock was written at (for a snapshot: it does not move)."""
    return datetime.fromtimestamp(clock.wall_ms / 1000, UTC)


class FakeUnitOfWork(UnitOfWork):
    def __init__(
        self,
        users_dict: dict[str, User] | None = None,
        tasks_dict: dict[str, Task] | None = None,
        contexts_dict: dict[str, Context] | None = None,
        history: list[TaskHistoryEntry] | None = None,
        time_entries: list[TimeEntry] | None = None,
        calendar_days: dict[str, list[CalendarDay]] | None = None,
        holidays: FakeHolidayProvider | None = None,
        sync: FakeSyncStore | None = None,
        task_views: list[TaskView] | None = None,
    ) -> None:

        # Pass the shared dicts to the repositories
        self.users: FakeUserRepository = FakeUserRepository(users=users_dict)
        self.tasks: FakeTaskRepository = FakeTaskRepository(tasks=tasks_dict)
        self.contexts: FakeContextRepository = FakeContextRepository(
            contexts=contexts_dict, tasks=self.tasks.tasks
        )

        self.time_entries: FakeTimeEntryRepository = FakeTimeEntryRepository(
            time_entries
        )
        self.task_history: FakeTaskHistoryRepository = FakeTaskHistoryRepository(
            history
        )

        self.user_behavior_metrics: FakeUserBehaviorMetricsRepository = (
            FakeUserBehaviorMetricsRepository()
        )
        self.user_behavior_profiles: FakeUserBehaviorProfileRepository = (
            FakeUserBehaviorProfileRepository()
        )

        self.calendar_days: FakeCalendarDayRepository = FakeCalendarDayRepository(
            calendar_days
        )
        self.holidays: FakeHolidayProvider = holidays or FakeHolidayProvider()
        self.sync: FakeSyncStore = sync if sync is not None else FakeSyncStore()
        self.task_views: FakeTaskViewRepository = FakeTaskViewRepository(task_views)

        self._seen_entities: set[Entity] = set()
        self._trigger_relay: bool = False
        self.outbox_repo: FakeOutboxEventRepository = FakeOutboxEventRepository()

        # Like the real one: every repository tracks into the UoW's set, so
        # the events entities record are processed on exit (history, outbox)
        for repo in (self.tasks, self.users, self.contexts, self.time_entries):
            repo._seen_entities = self._seen_entities

        self.committed: bool = False
        self.rolled_back: bool = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


class FakeUowFactory(Protocol):
    """A ``UowFactoryType`` whose units of work are ``FakeUnitOfWork``.

    Tests type the fixture with this to reach the fakes' own attributes
    (``uow.tasks.tasks``, ``uow.committed``).
    """

    def __call__(self, trigger_relay: bool = False) -> FakeUnitOfWork: ...


UseCaseDeps = dict[str, Any]
"""Keyword arguments for a use case: ``uow_factory`` and ``clock``."""


@pytest.fixture
def fake_clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def fake_uow_factory() -> FakeUowFactory:
    # Shared state (once per test)
    shared_users: dict[str, User] = {}
    shared_tasks: dict[str, Task] = {}
    shared_contexts: dict[str, Context] = {}
    shared_history: list[TaskHistoryEntry] = []
    shared_time_entries: list[TimeEntry] = []
    shared_calendar_days: dict[str, list[CalendarDay]] = {}
    shared_holidays: FakeHolidayProvider = FakeHolidayProvider()
    shared_sync: FakeSyncStore = FakeSyncStore()
    shared_views: list[TaskView] = []

    # add others as needed

    def factory(trigger_relay: bool = False) -> FakeUnitOfWork:
        # Each UoW is a new instance, but points to the same dicts
        return FakeUnitOfWork(
            users_dict=shared_users,
            tasks_dict=shared_tasks,
            contexts_dict=shared_contexts,
            history=shared_history,
            time_entries=shared_time_entries,
            calendar_days=shared_calendar_days,
            holidays=shared_holidays,
            sync=shared_sync,
            task_views=shared_views,
        )

    return factory


@pytest.fixture
def use_case_context(
    fake_uow_factory: FakeUowFactory, fake_clock: FakeClock
) -> UseCaseDeps:
    """
    Return a dict with all the dependencies
    ready for a (generic) use case.
    """
    return {
        "uow_factory": fake_uow_factory,
        "clock": fake_clock,
    }


@pytest.fixture
def create_use_case_context(
    fake_uow_factory: FakeUowFactory, fake_clock: FakeClock
) -> UseCaseDeps:
    """
    Return a dict with all the dependencies
    ready for a CompleteTaskUseCase.
    """
    return {
        "uow_factory": fake_uow_factory,
        "clock": fake_clock,
    }
