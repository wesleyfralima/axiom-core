import pytest

from b_domain.ports.unity_of_work import UnitOfWork


class FakeUnitOfWork(UnitOfWork):
    """Fake UnitOfWork used to test async context manager behavior.

    This fake implementation tracks whether `commit` or `rollback`
    was called, allowing verification of the abstract base class
    logic in `__aenter__` and `__aexit__`.
    """

    def __init__(self) -> None:
        self.committed: bool = False
        self.rolled_back: bool = False
        self._seen_entities = set()

    async def commit(self) -> None:
        """Mark the UnitOfWork as committed."""
        self.committed = True

    async def rollback(self) -> None:
        """Mark the UnitOfWork as rolled back."""
        self.rolled_back = True


# ============================================================
# Group: Async Context Manager Behavior
# ============================================================

@pytest.mark.asyncio
async def test_unit_of_work_commits_when_no_exception_is_raised() -> None:
    """Ensure UnitOfWork commits when exiting async context without exception.

    Given:
        A FakeUnitOfWork instance.
    When:
        Exiting the async context without raising an exception.
    Then:
        - `commit` must be called.
        - `rollback` must NOT be called.
    """

    uow: FakeUnitOfWork = FakeUnitOfWork()

    async with uow:
        pass

    assert uow.committed is True
    assert uow.rolled_back is False


@pytest.mark.asyncio
async def test_unit_of_work_rolls_back_when_exception_is_raised() -> None:
    """Ensure UnitOfWork rolls back when an exception is raised inside async context.

    Given:
        A FakeUnitOfWork instance.
    When:
        An exception is raised inside the async context.
    Then:
        - `rollback` must be called.
        - `commit` must NOT be called.
    """

    uow: FakeUnitOfWork = FakeUnitOfWork()

    with pytest.raises(RuntimeError):
        async with uow:
            raise RuntimeError("boom")

    assert uow.committed is False
    assert uow.rolled_back is True
