from typing import Any

import pytest

from b_domain.entities import User
from b_domain.exceptions.security import InvalidTokenError, NotAuthenticatedError
from b_domain.ports.providers import TokenProvider
from b_domain.ports.unit_of_work import UowFactoryType
from c_application.use_cases.auth.logout import LogoutInputDTO, LogoutUseCase
from c_application.use_cases.user.get_current import (
    GetCurrentUserInputDTO,
    GetCurrentUserUseCase,
)
from tests.conftest import FakeClock

pytestmark = [pytest.mark.asyncio, pytest.mark.uc]


class FakeTokenProvider(TokenProvider):
    """Token is the username itself; "bad" is a token that fails to decode."""

    def create_access_token(self, data: dict[str, Any]) -> str:
        return str(data["username"])

    def decode_access_token(self, token: str) -> dict[str, Any]:
        if token == "bad":
            raise InvalidTokenError()
        return {"username": token}


def _whoami(uow_factory: UowFactoryType, clock: FakeClock) -> GetCurrentUserUseCase:
    return GetCurrentUserUseCase(uow_factory, clock, FakeTokenProvider())


def _logout(uow_factory: UowFactoryType, clock: FakeClock) -> LogoutUseCase:
    return LogoutUseCase(uow_factory, clock, FakeTokenProvider())


@pytest.mark.parametrize("token", [None, ""])
async def test_whoami_without_token_is_not_authenticated(
    fake_uow_factory: UowFactoryType, fake_clock: FakeClock, token: str | None
) -> None:
    with pytest.raises(NotAuthenticatedError):
        await _whoami(fake_uow_factory, fake_clock).execute(
            GetCurrentUserInputDTO(token=token)
        )


async def test_whoami_with_bad_token_is_invalid(
    fake_uow_factory: UowFactoryType, fake_clock: FakeClock
) -> None:
    with pytest.raises(InvalidTokenError):
        await _whoami(fake_uow_factory, fake_clock).execute(
            GetCurrentUserInputDTO(token="bad")
        )


async def test_whoami_with_unknown_user_is_invalid(
    fake_uow_factory: UowFactoryType, fake_clock: FakeClock
) -> None:
    with pytest.raises(InvalidTokenError):
        await _whoami(fake_uow_factory, fake_clock).execute(
            GetCurrentUserInputDTO(token="ghost")
        )


async def test_whoami_returns_the_user(
    fake_uow_factory: UowFactoryType, fake_clock: FakeClock
) -> None:
    async with fake_uow_factory() as uow:
        await uow.users.add(User.create(username="wesley", email="w@test.com"))

    result = await _whoami(fake_uow_factory, fake_clock).execute(
        GetCurrentUserInputDTO(token="wesley")
    )

    assert result.username == "wesley"


async def test_logout_without_token_is_not_authenticated(
    fake_uow_factory: UowFactoryType, fake_clock: FakeClock
) -> None:
    with pytest.raises(NotAuthenticatedError):
        await _logout(fake_uow_factory, fake_clock).execute(
            LogoutInputDTO(access_token=None)
        )


@pytest.mark.parametrize("token", ["wesley", "bad"])
async def test_logout_tells_the_client_to_discard_the_token(
    fake_uow_factory: UowFactoryType, fake_clock: FakeClock, token: str
) -> None:
    result = await _logout(fake_uow_factory, fake_clock).execute(
        LogoutInputDTO(access_token=token)
    )

    assert result.success is True
    assert result.token_revoked is False
