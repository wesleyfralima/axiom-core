"""Sync use cases: join, sync, status and devices, against a fake server."""

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from a_core import EntityNotFound
from a_core.exceptions import AmbiguousIdentifierError, InvalidValueError
from b_domain.entities import User
from b_domain.exceptions.sync import (
    AlreadyJoinedError,
    NotJoinedError,
    SyncRefusedError,
    SyncUnavailableError,
)
from b_domain.ports.password_hasher import PasswordHasher
from b_domain.ports.sync_transport import (
    DeviceAccess,
    DeviceInfo,
    PullPage,
    SyncTransport,
)
from b_domain.value_objects.sync import Hlc, SyncEntity, SyncOperation
from c_application.dtos.sync_dtos import (
    JoinSyncInputDTO,
    RevokeSyncDeviceInputDTO,
    RunSyncInputDTO,
    SyncTokenInputDTO,
)
from c_application.use_cases.sync import (
    GetSyncStatusUseCase,
    JoinSyncUseCase,
    ListSyncDevicesUseCase,
    RevokeSyncDeviceUseCase,
    RunSyncUseCase,
)
from tests.conftest import (
    FakeClock,
    FakeSyncStore,
    FakeUnitOfWork,
    FakeUowFactory,
)

pytestmark = pytest.mark.unit

URL = "https://api.example.com"
NOW = datetime(2026, 9, 26, 12, tzinfo=UTC)
TASK = SyncEntity.TASK


class FakeHasher(PasswordHasher):
    def hash(self, password: str) -> str:
        return f"hashed:{password}"

    def verify(self, plain_password: str, hashed_password: str) -> bool:
        return hashed_password == f"hashed:{plain_password}"


@dataclass
class _Device:
    device_id: UUID
    name: str
    account_id: UUID
    joined_at: datetime
    revoked: bool = False


@dataclass
class FakeServer(SyncTransport):
    """The server's side in memory: one log per account, sequences from 1."""

    invites: set[str] = field(default_factory=lambda: {"INVITE-1"})
    accounts: dict[str, tuple[UUID, str]] = field(default_factory=dict)
    devices_by_token: dict[str, _Device] = field(default_factory=dict)
    log: list[tuple[UUID, dict[str, Any]]] = field(default_factory=list)
    offline: bool = False
    pushes: int = 0

    def _check(self, url: str) -> None:
        assert url == URL
        if self.offline:
            raise SyncUnavailableError("The server did not answer.")

    def _device(self, token: str) -> _Device:
        device = self.devices_by_token.get(token)
        if device is None or device.revoked:
            raise SyncRefusedError("This device cannot sync.")
        return device

    async def create_account(
        self,
        server_url: str,
        *,
        invite: str,
        account_id: UUID,
        username: str,
        email: str,
        password: str,
    ) -> None:
        self._check(server_url)
        if invite not in self.invites:
            raise SyncRefusedError("Unknown invite.")
        self.invites.discard(invite)
        self.accounts[username] = (account_id, password)

    async def register_device(
        self,
        server_url: str,
        *,
        username: str,
        password: str,
        device_id: UUID,
        device_name: str,
    ) -> DeviceAccess:
        self._check(server_url)
        account = self.accounts.get(username)
        if account is None or account[1] != password:
            raise SyncRefusedError("Wrong username or password.")
        token = f"token-{device_name}-{uuid4().hex[:6]}"
        self.devices_by_token[token] = _Device(device_id, device_name, account[0], NOW)
        return DeviceAccess(account_id=account[0], token=token)

    async def push(
        self, server_url: str, token: str, operations: Sequence[SyncOperation]
    ) -> None:
        self._check(server_url)
        device = self._device(token)
        self.pushes += 1
        have = {payload["op_id"] for _, payload in self.log}
        for op in operations:
            if str(op.op_id) not in have:
                self.log.append((device.account_id, op.to_payload()))

    async def pull(
        self, server_url: str, token: str, after: int, limit: int
    ) -> PullPage:
        self._check(server_url)
        device = self._device(token)
        mine = [
            (seq, payload)
            for seq, (account, payload) in enumerate(self.log, start=1)
            if account == device.account_id and seq > after
        ]
        page = mine[:limit]
        return PullPage(
            operations=[SyncOperation.from_payload(p) for _, p in page],
            cursor=page[-1][0] if page else after,
            more=len(mine) > limit,
        )

    async def devices(self, server_url: str, token: str) -> list[DeviceInfo]:
        self._check(server_url)
        me = self._device(token)
        return [
            DeviceInfo(
                device_id=d.device_id,
                name=d.name,
                joined_at=d.joined_at,
                last_seen_at=None,
                revoked=d.revoked,
            )
            for d in self.devices_by_token.values()
            if d.account_id == me.account_id
        ]

    async def revoke_device(self, server_url: str, token: str, device_id: UUID) -> None:
        self._check(server_url)
        self._device(token)
        for d in self.devices_by_token.values():
            if d.device_id == device_id:
                d.revoked = True


@dataclass
class Device:
    """One device: its own data, its own store, the same server."""

    name: str
    server: FakeServer
    user: User
    store: FakeSyncStore = field(default_factory=FakeSyncStore)
    clock: FakeClock = field(default_factory=lambda: FakeClock(NOW))
    token: str = ""

    def __post_init__(self) -> None:
        self.users: dict[str, User] = {str(self.user.id): self.user}
        self.store.rows[(SyncEntity.USER, self.user.id.value)] = {
            "username": self.user.username
        }
        self.store.account_row = (SyncEntity.USER, self.user.id.value)
        self.store.users = self.users

    def uow(self, trigger_relay: bool = False) -> FakeUnitOfWork:
        return FakeUnitOfWork(users_dict=self.users, sync=self.store)

    async def join(self, invite: str | None = None, password: str = "secret") -> Any:
        result = await JoinSyncUseCase(
            self.uow, self.clock, self.server, FakeHasher()
        ).execute(
            JoinSyncInputDTO(
                user_id=str(self.user.id),
                server_url=URL + "/",
                username="wesley",
                password=password,
                device_name=self.name,
                invite=invite,
            )
        )
        self.token = result.token
        return result

    async def sync(self, batch: int = 500) -> Any:
        return await RunSyncUseCase(self.uow, self.clock, self.server).execute(
            RunSyncInputDTO(token=self.token, batch=batch)
        )

    def change(self, entity_id: UUID, **fields: Any) -> None:
        self.clock.set_time(self.clock.now() + timedelta(seconds=1))
        self.store.change(self.clock.now(), TASK, entity_id, **fields)


def _user(name: str = "local") -> User:
    return User.create(username=name, email=f"{name}@example.com", now=NOW)


@pytest.fixture
def server() -> FakeServer:
    return FakeServer()


@pytest.fixture
def mint(server: FakeServer) -> Device:
    return Device("mint", server, _user("mint"))


@pytest.fixture
def phone(server: FakeServer) -> Device:
    return Device("phone", server, _user("phone"))


# ---------------------------------------------------------------------- join


async def test_the_first_device_creates_the_account_with_its_own_id(
    mint: Device, server: FakeServer
) -> None:
    task = uuid4()
    mint.store.rows[(TASK, task)] = {"title": "Pay the bill"}

    result = await mint.join(invite="INVITE-1")

    assert result.created_account
    assert result.account_id == str(mint.user.id)
    assert server.accounts["wesley"][0] == mint.user.id.value
    assert mint.store.adopted == []
    # Every row waits for the first push, the account's own row included
    assert result.pending == 2
    assert {op.entity for op in mint.store.outbox} == {SyncEntity.USER, TASK}
    state = mint.store.sync_state
    assert state is not None
    assert state.server_url == URL
    assert state.device_name == "mint"
    assert str(state.device_id) == result.device_id
    assert state.clock >= mint.store.outbox[-1].hlc
    assert mint.user.password_hash == "hashed:secret"


async def test_the_next_device_becomes_the_account(mint: Device, phone: Device) -> None:
    await mint.join(invite="INVITE-1")
    local, account = phone.user.id, mint.user.id

    result = await phone.join()

    assert not result.created_account
    assert result.account_id == str(account)
    assert phone.store.adopted == [(local, account)]
    assert phone.user.id == account
    assert phone.user.password_hash == "hashed:secret"
    # Its own user row does not go up: the account's comes from the server
    assert all(op.entity != SyncEntity.USER for op in phone.store.outbox)


async def test_a_device_joins_once(mint: Device) -> None:
    await mint.join(invite="INVITE-1")

    with pytest.raises(AlreadyJoinedError, match=URL):
        await mint.join()


@pytest.mark.parametrize("url", ["api.example.com", "ftp://x", "https://", ""])
async def test_the_server_must_be_a_web_address(mint: Device, url: str) -> None:
    use_case = JoinSyncUseCase(mint.uow, mint.clock, mint.server, FakeHasher())

    with pytest.raises(InvalidValueError):
        await use_case.execute(
            JoinSyncInputDTO(
                user_id=str(mint.user.id),
                server_url=url,
                username="u",
                password="p",
                device_name="mint",
            )
        )


async def test_a_device_needs_a_name(mint: Device) -> None:
    use_case = JoinSyncUseCase(mint.uow, mint.clock, mint.server, FakeHasher())

    with pytest.raises(InvalidValueError):
        await use_case.execute(
            JoinSyncInputDTO(
                user_id=str(mint.user.id),
                server_url=URL,
                username="u",
                password="p",
                device_name="  ",
            )
        )


async def test_a_refused_join_leaves_the_device_as_it_was(
    mint: Device, phone: Device
) -> None:
    await mint.join(invite="INVITE-1")

    with pytest.raises(SyncRefusedError):
        await phone.join(password="wrong")
    with pytest.raises(SyncRefusedError):
        await phone.join(invite="USED-OR-UNKNOWN")

    assert phone.store.sync_state is None
    assert phone.store.outbox == []
    assert phone.user.password_hash is None


async def test_joining_needs_the_server(mint: Device, server: FakeServer) -> None:
    server.offline = True

    with pytest.raises(SyncUnavailableError):
        await mint.join(invite="INVITE-1")

    assert mint.store.sync_state is None


# ---------------------------------------------------------------------- sync


async def test_syncing_needs_a_joined_device(mint: Device) -> None:
    with pytest.raises(NotJoinedError):
        await mint.sync()


async def test_two_devices_end_with_the_same_data(mint: Device, phone: Device) -> None:
    on_mint, on_phone = uuid4(), uuid4()
    mint.store.rows[(TASK, on_mint)] = {"title": "From the Mint", "priority": 2}
    phone.store.rows[(TASK, on_phone)] = {"title": "From the phone"}
    await mint.join(invite="INVITE-1")
    await phone.join()

    first = await mint.sync()
    await phone.sync()
    await mint.sync()

    assert first.pushed == 2
    assert first.pending == 0
    assert mint.store.rows[(TASK, on_phone)] == {"title": "From the phone"}
    assert phone.store.rows[(TASK, on_mint)] == {
        "title": "From the Mint",
        "priority": 2,
    }
    assert phone.store.rows[(SyncEntity.USER, mint.user.id.value)] == {
        "username": "mint"
    }


async def test_changes_to_different_fields_both_stay(
    mint: Device, phone: Device
) -> None:
    task = uuid4()
    mint.store.rows[(TASK, task)] = {"title": "Draft", "priority": 1}
    await mint.join(invite="INVITE-1")
    await phone.join()
    await mint.sync()
    await phone.sync()

    mint.change(task, title="Final")
    phone.change(task, priority=3)
    await mint.sync()
    result = await phone.sync()
    await mint.sync()

    assert result.pulled >= 1
    expected = {"title": "Final", "priority": 3}
    assert mint.store.rows[(TASK, task)] == expected
    assert phone.store.rows[(TASK, task)] == expected


async def test_the_same_field_keeps_the_later_change(
    mint: Device, phone: Device
) -> None:
    task = uuid4()
    mint.store.rows[(TASK, task)] = {"title": "Draft"}
    await mint.join(invite="INVITE-1")
    await phone.join()
    await mint.sync()
    await phone.sync()

    phone.change(task, title="Earlier, on the phone")
    mint.clock.set_time(NOW + timedelta(minutes=5))
    mint.change(task, title="Later, on the Mint")
    # The phone pushes last, but its change is older
    await mint.sync()
    await phone.sync()
    last = await mint.sync()

    # The Mint drops the phone's older title when it comes down
    assert last.dropped == 1
    assert mint.store.rows[(TASK, task)]["title"] == "Later, on the Mint"
    assert phone.store.rows[(TASK, task)]["title"] == "Later, on the Mint"


async def test_the_clock_moves_past_what_it_received(
    mint: Device, phone: Device
) -> None:
    task = uuid4()
    mint.store.rows[(TASK, task)] = {"title": "x"}
    mint.clock.set_time(NOW + timedelta(hours=2))
    await mint.join(invite="INVITE-1")
    await mint.sync()
    await phone.join()

    await phone.sync()

    latest = max(Hlc.parse(payload["hlc"]) for _, payload in mint.server.log)
    assert phone.store.sync_state is not None
    # The Mint's clock runs two hours ahead: the phone's moves past it
    assert phone.store.sync_state.clock > latest


async def test_many_changes_go_in_batches(
    mint: Device, phone: Device, server: FakeServer
) -> None:
    for n in range(5):
        mint.store.rows[(TASK, uuid4())] = {"title": f"task {n}"}
    await mint.join(invite="INVITE-1")
    await phone.join()

    pushed = await mint.sync(batch=2)
    pulled = await phone.sync(batch=2)

    assert pushed.pushed == 6  # five tasks and the account
    assert server.pushes == 3
    assert pulled.pulled == 6
    assert pulled.changed == 6
    assert len(phone.store.rows) == 6 + 1  # its own user row stays too


async def test_a_failed_sync_is_kept_and_cleared_by_the_next(
    mint: Device, server: FakeServer
) -> None:
    await mint.join(invite="INVITE-1")
    server.offline = True

    with pytest.raises(SyncUnavailableError):
        await mint.sync()

    status = await GetSyncStatusUseCase(mint.uow, mint.clock).execute()
    assert status.last_error == "The server did not answer."
    assert status.pending == 1

    server.offline = False
    await mint.sync()
    status = await GetSyncStatusUseCase(mint.uow, mint.clock).execute()
    assert status.last_error is None
    assert status.last_sync_at == NOW.isoformat()
    assert status.pending == 0


async def test_a_revoked_device_cannot_sync(mint: Device, phone: Device) -> None:
    await mint.join(invite="INVITE-1")
    await phone.join()
    await RevokeSyncDeviceUseCase(mint.uow, mint.clock, mint.server).execute(
        RevokeSyncDeviceInputDTO(token=mint.token, device="phone")
    )

    with pytest.raises(SyncRefusedError):
        await phone.sync()


# -------------------------------------------------------------------- status


async def test_the_status_of_a_device_that_does_not_sync(
    fake_uow_factory: FakeUowFactory, fake_clock: FakeClock
) -> None:
    status = await GetSyncStatusUseCase(fake_uow_factory, fake_clock).execute()

    assert not status.joined
    assert status.server_url is None


async def test_the_status_of_a_joined_device(mint: Device) -> None:
    joined = await mint.join(invite="INVITE-1")

    status = await GetSyncStatusUseCase(mint.uow, mint.clock).execute()

    assert status.joined
    assert status.server_url == URL
    assert status.device_id == joined.device_id
    assert status.account_id == joined.account_id
    assert status.device_name == "mint"
    assert status.pending == 1
    assert status.last_sync_at is None


# ------------------------------------------------------------------- devices


async def test_the_accounts_devices(mint: Device, phone: Device) -> None:
    await mint.join(invite="INVITE-1")
    await phone.join()

    devices = await ListSyncDevicesUseCase(mint.uow, mint.clock, mint.server).execute(
        SyncTokenInputDTO(token=mint.token)
    )

    assert [(d.name, d.this_device, d.revoked) for d in devices.devices] == [
        ("mint", True, False),
        ("phone", False, False),
    ]
    assert devices.devices[0].joined_at == NOW.isoformat()


async def test_revoking_a_device_by_its_id_prefix(mint: Device, phone: Device) -> None:
    await mint.join(invite="INVITE-1")
    joined = await phone.join()

    revoked = await RevokeSyncDeviceUseCase(mint.uow, mint.clock, mint.server).execute(
        RevokeSyncDeviceInputDTO(token=mint.token, device=joined.device_id[:8])
    )

    assert revoked.name == "phone"
    assert revoked.revoked
    assert not revoked.this_device


async def test_a_device_cannot_revoke_itself(mint: Device) -> None:
    await mint.join(invite="INVITE-1")

    with pytest.raises(InvalidValueError):
        await RevokeSyncDeviceUseCase(mint.uow, mint.clock, mint.server).execute(
            RevokeSyncDeviceInputDTO(token=mint.token, device="MINT")
        )


async def test_revoking_an_unknown_or_ambiguous_device(
    mint: Device, phone: Device, server: FakeServer
) -> None:
    await mint.join(invite="INVITE-1")
    await phone.join()
    for token, device in list(server.devices_by_token.items()):
        server.devices_by_token[token] = replace(
            device, device_id=UUID("abcd" + device.device_id.hex[4:])
        )
    revoke = RevokeSyncDeviceUseCase(mint.uow, mint.clock, mint.server)

    with pytest.raises(EntityNotFound):
        await revoke.execute(RevokeSyncDeviceInputDTO(token=mint.token, device="tv"))
    with pytest.raises(AmbiguousIdentifierError):
        await revoke.execute(RevokeSyncDeviceInputDTO(token=mint.token, device="abcd"))


async def test_listing_devices_needs_a_joined_device(mint: Device) -> None:
    with pytest.raises(NotJoinedError):
        await ListSyncDevicesUseCase(mint.uow, mint.clock, mint.server).execute(
            SyncTokenInputDTO(token="none")
        )
