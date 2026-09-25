import builtins
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

import pytest

from a_core import Entity, IdPrefix, tracks_entity
from b_domain.entities import Task, TimeEntry, User
from b_domain.ports.providers import ClockProvider
from b_domain.ports.repositories import (
    TaskRepository,
    UserBehaviorMetricsRepository,
    UserBehaviorProfileRepository,
    UserRepository,
)
from b_domain.ports.repositories.filters import (
    TaskFilter,
    TimeEntryFilter,
    UserFilter,
)
from b_domain.ports.repositories.time_entry_repository import TimeEntryRepository
from b_domain.ports.unit_of_work import UnitOfWork
from b_domain.value_objects import (
    ContextId,
    EnergyLevel,
    TaskId,
    UserBehaviorProfile,
    UserId,
)
from b_domain.value_objects.identifiers import TimeEntryId
from b_domain.value_objects.user_behavior_metrics import UserBehaviorMetrics


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

    async def update(self, task: Task) -> None:
        if str(task.id) in self.tasks:
            self.tasks[str(task.id)] = task

    async def update_many(self, tasks: list[Task]) -> None:
        """Simula o update em lote no repositório fake."""
        for task in tasks:
            await self.update(task)

    async def delete(self, task_id: TaskId) -> None:
        del self.tasks[str(task_id)]

    @tracks_entity
    async def get_by_id(
        self, task_id: TaskId, user_id: UserId | None = None
    ) -> Task | None:
        found = self.tasks.get(str(task_id), None)

        if user_id is not None:
            return found if str(found.user_id) == str(user_id) else None

        return found

    @tracks_entity
    async def find_by_id_prefix(
        self,
        id_prefix: IdPrefix,
        user_id: UserId | None = None,
    ) -> list[Task]:
        found_tasks: list[Task] = []
        for key, value in self.tasks.items():
            if key.startswith(str(id_prefix)):
                found_tasks.append(value)
        return found_tasks

    def _apply_filters(self, filters: TaskFilter) -> list[Task]:
        """Método auxiliar interno para reutilizar a lógica de filtro."""

        results = [t for t in self.tasks.values()]

        if filters.user_id:
            results = [t for t in results if t.user_id == filters.user_id]
        if filters.status:
            results = [t for t in results if t.status == filters.status]
        if filters.context_id:
            results = [t for t in results if t.context_id == filters.context_id]

        return results

    @tracks_entity
    async def list(self, filters: TaskFilter) -> list[Task]:
        filtered = self._apply_filters(filters)
        # Aplica OFFSET e LIMIT (Paginação em memória)
        start = filters.offset
        end = start + filters.limit
        return filtered[start:end]

    async def count(self, filters: TaskFilter) -> int:
        # O count ignora paginação, retorna o total do filtro
        return len(self._apply_filters(filters))

    # --- Hierarquia e Dependências ---

    @tracks_entity
    async def get_subtasks(
        self, parent_id: TaskId, limit: int = 100, offset: int = 0
    ) -> builtins.list[Task]:
        subs = [t for t in self.tasks.values() if t.parent_id == parent_id]
        return subs[offset : offset + limit]

    @tracks_entity
    async def find_tasks_blocked_by(self, task_id: TaskId) -> builtins.list[Task]:
        return [t for t in self.tasks.values() if task_id in t.depends_on]

    # --- Método utilitário para o Axiom Context/Energy logic ---

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
            # required_energy_level é o campo que definimos na Task
            results = [t for t in results if t.required_energy_level <= max_energy]

        return results

    async def task_ids_from_id_prefixes(
        self, partial_ids: Iterable[IdPrefix]
    ) -> builtins.list[TaskId]:

        # Convertemos para tupla, pois startswith() aceita uma tupla de strings
        # para verificar múltiplas possibilidades de uma vez.
        prefixes = tuple(str(p) for p in partial_ids)

        result: list[TaskId] = []

        # Se não houver prefixos, retornamos lista vazia para evitar processamento
        if not prefixes:
            return []

        for prefix in prefixes:
            pref_vo: IdPrefix = IdPrefix(value=prefix)
            found_tasks: list[Task] = await self.find_by_id_prefix(id_prefix=pref_vo)

            if not len(found_tasks) == 1:
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

    # --- Implementação de Filtros e Paginação ---

    def _apply_filters(self, filters: UserFilter) -> list[User]:
        results = list(self.users.values())

        if filters.username:
            results = [
                u for u in results if filters.username.lower() in u.username.lower()
            ]

        # Se houver um campo 'is_active' na entidade User no futuro:
        # if filters.is_active is not None:
        #     results = [u for u in results if u.is_active == filters.is_active]

        return results

    @tracks_entity
    async def list(self, filters: UserFilter) -> list[User]:
        filtered = self._apply_filters(filters)

        # Aplica paginação manual
        start = filters.offset
        end = start + filters.limit
        return filtered[start:end]

    async def count(self, filters: UserFilter) -> int:
        # Ignora offset/limit para retornar o total absoluto
        return len(self._apply_filters(filters))

    @tracks_entity
    async def get_by_email(self, email: str) -> User | None:
        return None


class FakeTimeEntryRepository(TimeEntryRepository):
    def __init__(self):
        # Usamos uma lista para simular a tabela, mas poderíamos usar um dict
        # se quiséssemos busca por ID em O(1).
        self.entries: list[TimeEntry] = []

    async def add(self, entry: TimeEntry) -> TimeEntry:
        """Simula o INSERT no banco de dados."""
        self.entries.append(entry)
        return entry

    async def update(self, entry: TimeEntry) -> None:
        """
        Em memória, o objeto já costuma estar atualizado por referência.
        Em um banco real, aqui faríamos o UPDATE.
        """
        for i, existing in enumerate(self.entries):
            if existing.id == entry.id:
                self.entries[i] = entry
                break

    async def update_all(self, entries: list[TimeEntry]) -> None:
        """Simula um update em lote."""
        for entry in entries:
            await self.update(entry)

    async def get_by_id(self, entry_id: TimeEntryId) -> TimeEntry | None:
        """Busca uma entrada específica."""
        return next((e for e in self.entries if e.id == entry_id), None)

    async def get_actives_for_task(self, task_id: TaskId) -> list[TimeEntry]:
        """Retorna timers rodando para uma tarefa específica."""
        return [e for e in self.entries if e.task_id == task_id and e.end_time is None]

    async def get_active_for_user(self, user_id: UserId) -> TimeEntry | None:
        """
        Busca o timer atualmente ativo do usuário.
        Essencial para a regra de 'apenas um timer por vez'.
        """
        return next(
            (e for e in self.entries if e.user_id == user_id and e.end_time is None),
            None,
        )

    async def find_by_user(self, user_id: UserId) -> list[TimeEntry]:
        """Retorna todo o histórico de trackings do usuário."""
        return [e for e in self.entries if e.user_id == user_id]

    async def search(self, filters: TimeEntryFilter) -> list[TimeEntry]:
        return []


class FakeContextRepository:
    def __init__(self, contexts: dict[str, Any] | None = None):
        self.contexts = contexts if contexts is not None else {}

    async def get_by_id(self, context_id):
        return self.contexts.get(str(context_id))

    async def get_active_for_user(self, user_id):
        # No Axiom, o contexto ativo agora vem do UserPrefs,
        # mas mantemos o repositório para buscas de metadados.
        return next((c for c in self.contexts.values() if c.user_id == user_id), None)


class FakeUserBehaviorMetricsRepository(UserBehaviorMetricsRepository):
    def __init__(self):
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
    def __init__(self):
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


class FakeUnitOfWork(UnitOfWork):
    def __init__(self, users_dict=None, tasks_dict=None, contexts_dict=None):

        # Passamos os dicionários compartilhados para os repositórios
        self.users: FakeUserRepository = FakeUserRepository(users=users_dict)
        self.tasks: FakeTaskRepository = FakeTaskRepository(tasks=tasks_dict)
        self.contexts: FakeContextRepository = FakeContextRepository(
            contexts=contexts_dict
        )

        self.time_entries: FakeTimeEntryRepository = FakeTimeEntryRepository()

        self.user_behavior_metrics: FakeUserBehaviorMetricsRepository = (
            FakeUserBehaviorMetricsRepository()
        )
        self.user_behavior_profilesFakeUserBehaviorProfileRepository = (
            FakeUserBehaviorProfileRepository()
        )

        self._seen_entities: set[Entity] = set()
        self._trigger_relay: bool = False

        self.committed: bool = False
        self.rolled_back: bool = False

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


@pytest.fixture
def fake_clock():
    return FakeClock()


@pytest.fixture
def fake_uow_factory():
    # Estado compartilhado (uma única vez por teste)
    shared_users = {}
    shared_tasks = {}
    shared_contexts = {}

    # incluir outros se necessário

    def factory():
        # Cada UOW é uma instância nova, mas aponta para os mesmos dicts
        return FakeUnitOfWork(
            users_dict=shared_users,
            tasks_dict=shared_tasks,
            contexts_dict=shared_contexts,
        )

    return factory


@pytest.fixture
def use_case_context(fake_uow_factory, fake_clock):
    """
    Retorna um dicionário com todas as dependências
     prontas para um UseCase (genérico).
    """
    return {
        "uow_factory": fake_uow_factory,
        "clock": fake_clock,
    }


@pytest.fixture
def create_use_case_context(fake_uow_factory, fake_clock):
    """
    Retorna um dicionário com todas as dependências
    prontas para um CompleteTaskUseCase.
    """
    return {
        "uow_factory": fake_uow_factory,
        "clock": fake_clock,
    }
