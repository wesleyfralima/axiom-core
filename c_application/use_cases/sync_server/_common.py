from __future__ import annotations

import re
from abc import ABC, abstractmethod
from datetime import timedelta
from uuid import UUID

from a_core.exceptions import ValidationException
from b_domain.exceptions.sync import DeviceNotAllowedError
from b_domain.ports.providers import ClockProvider
from b_domain.ports.sync_server_store import SyncServerStore
from b_domain.value_objects.sync_server import (
    SyncDevice,
    secret_hash,
)
from c_application.dtos.sync_server_dtos import ServerDeviceOutputDTO

MAX_BATCH: int = 1000
"""The most operations a push takes, or a pull returns."""

MAX_CLOCK_AHEAD: timedelta = timedelta(days=1)
"""How far ahead of the server's time a device's clock may run: more, and
its changes would win over everything for as long."""

USERNAME: re.Pattern[str] = re.compile(r"[A-Za-z0-9._-]{3,32}")
MIN_PASSWORD: int = 8


class SyncServerUseCase[TRequest, TResponse](ABC):
    """A use case of the sync server."""

    def __init__(self, store: SyncServerStore, clock: ClockProvider):
        self.store = store
        self.clock = clock

    @abstractmethod
    async def execute(self, request: TRequest) -> TResponse:
        """Run it."""

    async def _device(self, token: str) -> SyncDevice:
        """The device a token belongs to.

        Raises:
            DeviceNotAllowedError: If the token is unknown or revoked.
        """
        device: SyncDevice | None = await self.store.device_by_token(secret_hash(token))
        if device is None or device.revoked_at is not None:
            raise DeviceNotAllowedError()
        return device


def parse_uuid(text: str, what: str) -> UUID:
    """A UUID from text.

    Raises:
        ValidationException: If it is not one.
    """
    try:
        return UUID(text)
    except (ValueError, AttributeError, TypeError) as e:
        raise ValidationException(f"Not a valid {what}: {text!r}.") from e


def device_output(device: SyncDevice) -> ServerDeviceOutputDTO:
    return ServerDeviceOutputDTO(
        device_id=str(device.device_id),
        name=device.name,
        joined_at=device.joined_at.isoformat(),
        last_seen_at=device.last_seen_at.isoformat() if device.last_seen_at else None,
        revoked=device.revoked_at is not None,
    )
