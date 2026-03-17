from datetime import datetime, timezone
from typing import Dict, Optional, List

import pytest

from b_domain.entities import Task, TimeEntry, User
from b_domain.ports.providers import ClockProvider
from b_domain.ports.repositories import TaskRepository, UserRepository, TaskFilter
from b_domain.ports.repositories.filters import UserFilter
from b_domain.ports.repositories.time_entry_repository import TimeEntryRepository
from b_domain.ports.repositories.user_behavior_metrics_repository import UserBehaviorMetricsRepository
from b_domain.ports.repositories.user_behavior_profile_repository import UserBehaviorProfileRepository
from b_domain.ports.unity_of_work import UnitOfWork
from b_domain.services.user_behavior_learner import UserBehaviorLearner
from b_domain.services.user_behavior_metrics_aggregator import UserBehaviorMetricsAggregator
from b_domain.value_objects import UserId, TaskId
from b_domain.value_objects.enums import EnergyLevel
from b_domain.value_objects.identifiers import ContextId, TimeEntryId
from b_domain.value_objects.user_behavior_metrics import UserBehaviorMetrics
from b_domain.value_objects.user_behavior_profile import UserBehaviorProfile


class FakeClock(ClockProvider):
    def __init__(self, initial_time: Optional[datetime] = None):
        self._now = initial_time or datetime(2026, 3, 5, 12, tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self._now

    def set_time(self, new_time: datetime):
        self._now = new_time


class FakeTaskRepository(TaskRepository):
    def __init__(self):
        # Usamos uma lista para manter a ordem de inserção (útil para testes de listagem)
        self.tasks: List[Task] = []

    async def add(self, task: Task) -> Task:
        self.tasks.append(task)
        return task

    async def update(self, task: Task) -> None:
        for i, t in enumerate(self.tasks):
            if t.id == task.id:
                self.tasks[i] = task
                return

    async def update_many(self, tasks: List[Task]) -> None:
        """Simula o update em lote no repositório fake."""
        for task in tasks:
            await self.update(task)

    async def delete(self, task_id: TaskId) -> None:
        self.tasks = [t for t in self.tasks if t.id != task_id]

    async def get_by_id(self, task_id: TaskId, user_id: Optional[UserId] = None) -> Optional[Task]:
        for task in self.tasks:
            if task.id == task_id:
                if user_id is None or task.user_id == user_id:
                    return task
        return None

    async def find_by_id_prefix(self, id_prefix: str, user_id: UserId = None) -> List[Task]:
        return [
            t for t in self.tasks
            if str(t.id).startswith(id_prefix) and (user_id is None or t.user_id == user_id)
        ]

    def _apply_filters(self, filters: TaskFilter) -> List[Task]:
        """Método auxiliar interno para reutilizar a lógica de filtro."""

        results = self.tasks

        if filters.user_id:
            results = [t for t in results if t.user_id == filters.user_id]
        if filters.status:
            results = [t for t in results if t.status == filters.status]
        if filters.context_id:
            results = [t for t in results if t.context_id == filters.context_id]

        return results

    async def list(self, filters: TaskFilter) -> List[Task]:
        filtered = self._apply_filters(filters)
        # Aplica OFFSET e LIMIT (Paginação em memória)
        start = filters.offset
        end = start + filters.limit
        return filtered[start:end]

    async def count(self, filters: TaskFilter) -> int:
        # O count ignora paginação, retorna o total do filtro
        return len(self._apply_filters(filters))

    # --- Hierarquia e Dependências ---

    async def get_subtasks(self, parent_id: TaskId, limit: int = 100, offset: int = 0) -> List[Task]:
        subs = [t for t in self.tasks if t.parent_id == parent_id]
        return subs[offset: offset + limit]

    async def find_tasks_blocked_by(self, task_id: TaskId) -> List[Task]:
        return [t for t in self.tasks if task_id in t.depends_on]

    # --- Método utilitário para o Axiom Context/Energy logic ---

    async def find_by_user(
            self,
            user_id: UserId,
            context_id: Optional[ContextId] = None,
            max_energy: Optional[EnergyLevel] = None
    ) -> List[Task]:
        results = [t for t in self.tasks if t.user_id == user_id]

        if context_id:
            results = [t for t in results if t.context_id == context_id]

        if max_energy:
            # required_energy_level é o campo que definimos na Task
            results = [t for t in results if t.required_energy_level <= max_energy]

        return results


class FakeUserRepository(UserRepository):
    def __init__(self):
        # Usamos um dicionário para busca rápida por ID (O(1))
        self.users: Dict[str, User] = {}

    async def add(self, user: User) -> None:
        self.users[str(user.id)] = user

    async def update(self, user: User) -> None:
        if str(user.id) in self.users:
            self.users[str(user.id)] = user

    async def delete(self, user_id: UserId) -> None:
        if str(user_id) in self.users:
            del self.users[str(user_id)]

    async def get_by_id(self, user_id: UserId) -> Optional[User]:
        return self.users.get(str(user_id))

    async def get_by_username(self, username: str) -> Optional[User]:
        """Busca linear por username (simula UNIQUE constraint)."""
        return next(
            (u for u in self.users.values() if u.username == username),
            None
        )

    # --- Implementação de Filtros e Paginação ---

    def _apply_filters(self, filters: UserFilter) -> List[User]:
        results = list(self.users.values())

        if filters.username:
            results = [
                u for u in results
                if filters.username.lower() in u.username.lower()
            ]

        # Se você decidir adicionar um campo 'is_active' na entidade User no futuro:
        # if filters.is_active is not None:
        #     results = [u for u in results if u.is_active == filters.is_active]

        return results

    async def list(self, filters: UserFilter) -> List[User]:
        filtered = self._apply_filters(filters)

        # Aplica paginação manual
        start = filters.offset
        end = start + filters.limit
        return filtered[start:end]

    async def count(self, filters: UserFilter) -> int:
        # Ignora offset/limit para retornar o total absoluto
        return len(self._apply_filters(filters))


class FakeTimeEntryRepository(TimeEntryRepository):
    def __init__(self):
        # Usamos uma lista para simular a tabela, mas poderíamos usar um dict
        # se quiséssemos busca por ID em O(1).
        self.entries: List[TimeEntry] = []

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

    async def update_all(self, entries: List[TimeEntry]) -> None:
        """Simula um update em lote."""
        for entry in entries:
            await self.update(entry)

    async def get_by_id(self, entry_id: TimeEntryId) -> Optional[TimeEntry]:
        """Busca uma entrada específica."""
        return next((e for e in self.entries if e.id == entry_id), None)

    async def get_actives_for_task(self, task_id: TaskId) -> List[TimeEntry]:
        """Retorna timers rodando para uma tarefa específica."""
        return [
            e for e in self.entries
            if e.task_id == task_id and e.end_time is None
        ]

    async def get_active_for_user(self, user_id: UserId) -> Optional[TimeEntry]:
        """
        Busca o timer atualmente ativo do usuário.
        Essencial para a regra de 'apenas um timer por vez'.
        """
        return next(
            (e for e in self.entries if e.user_id == user_id and e.end_time is None),
            None
        )

    async def find_by_user(self, user_id: UserId) -> List[TimeEntry]:
        """Retorna todo o histórico de trackings do usuário."""
        return [e for e in self.entries if e.user_id == user_id]


class FakeContextRepository:
    def __init__(self):
        self.contexts: Dict[str, any] = {}

    async def get_by_id(self, context_id):
        return self.contexts.get(str(context_id))

    async def get_active_for_user(self, user_id):
        # No Axiom, o contexto ativo agora vem do UserPrefs,
        # mas mantemos o repositório para buscas de metadados.
        return next((c for c in self.contexts.values() if c.user_id == user_id), None)


class FakeUserBehaviorMetricsRepository(UserBehaviorMetricsRepository):

    def __init__(self):
        self.metrics_store: Dict[str, UserBehaviorMetrics] = {}

    async def save(self, metrics: UserBehaviorMetrics) -> None:
        """Create or update metrics for a user."""
        self.metrics_store[str(metrics.user_id)] = metrics

    async def get_by_user_id(self, user_id: UserId) -> Optional[UserBehaviorMetrics]:
        """Retrieve metrics for a given user."""
        return self.metrics_store.get(str(user_id))

    async def delete(self, user_id: UserId) -> None:
        """Delete metrics associated with a user."""
        if str(user_id) in self.metrics_store:
            del self.metrics_store[str(user_id)]


class FakeUserBehaviorProfileRepository(UserBehaviorProfileRepository):

    def __init__(self):
        self.profiles: Dict[str, UserBehaviorProfile] = {}

    async def save(self, profile: UserBehaviorProfile) -> None:
        """Create or update the profile."""
        self.profiles[str(profile.user_id)] = profile

    async def get_by_user_id(self, user_id: UserId) -> Optional[UserBehaviorProfile]:
        """Retrieve the profile for a user."""
        return self.profiles.get(str(user_id))

    async def delete(self, user_id: UserId) -> None:
        """Delete the profile for a user."""
        if str(user_id) in self.profiles:
            del self.profiles[str(user_id)]


class FakeUnitOfWork(UnitOfWork):
    def __init__(self):
        self.tasks = FakeTaskRepository()
        self.users = FakeUserRepository()
        # Adicione estas duas linhas:
        self.time_entries = FakeTimeEntryRepository()
        self.contexts = FakeContextRepository()

        self.user_behavior_metrics = FakeUserBehaviorMetricsRepository()
        self.user_behavior_profiles = FakeUserBehaviorProfileRepository()

        self._seen_entities = set()

        self.committed = False
        self.rolled_back = False

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


@pytest.fixture
def fake_clock():
    return FakeClock()


@pytest.fixture
def fake_uow():
    return FakeUnitOfWork()


@pytest.fixture
def use_case_context(fake_uow, fake_clock):
    """Retorna um dicionário com todas as dependências prontas para um UseCase (genérico)."""
    return {
        "uow": fake_uow,
        "clock": fake_clock,
    }


@pytest.fixture
def create_use_case_context(fake_uow, fake_clock):
    """Retorna um dicionário com todas as dependências prontas para um CompleteTaskUseCase."""
    return {
        "uow": fake_uow,
        "clock": fake_clock,
    }
