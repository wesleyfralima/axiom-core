"""The sync server's use cases, on a store in memory — and a device's use
cases talking to them through a transport in the same process."""

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from a_core import EntityNotFound
from a_core.exceptions import ValidationException
from b_domain.exceptions.sync import (
    DeviceNotAllowedError,
    SyncConflictError,
    WrongCredentialsError,
)
from b_domain.ports.password_hasher import PasswordHasher
from b_domain.ports.sync_server_store import SyncServerStore
from b_domain.ports.sync_transport import (
    DeviceAccess,
    DeviceInfo,
    PullPage,
    SyncTransport,
)
from b_domain.value_objects.sync import Hlc, SyncEntity, SyncOperation
from b_domain.value_objects.sync_server import SyncAccount, SyncDevice, secret_hash
from c_application.dtos.sync_dtos import (
    JoinSyncInputDTO,
    RevokeSyncDeviceInputDTO,
    RunSyncInputDTO,
)
from c_application.dtos.sync_server_dtos import (
    CreateSyncAccountInputDTO,
    PullInputDTO,
    PushInputDTO,
    RegisterSyncDeviceInputDTO,
    RevokeServerDeviceInputDTO,
    ServerTokenInputDTO,
)
from c_application.use_cases.sync import (
    JoinSyncUseCase,
    RevokeSyncDeviceUseCase,
    RunSyncUseCase,
)
from c_application.use_cases.sync_server import (
    MAX_BATCH,
    AcceptPushUseCase,
    CreateInviteUseCase,
    CreateSyncAccountUseCase,
    ListServerDevicesUseCase,
    RegisterSyncDeviceUseCase,
    RevokeServerDeviceUseCase,
    ServePullUseCase,
)
from tests.a_unit.c_application.use_cases.test_sync_uc import Device, FakeServer, _user
from tests.conftest import FakeClock

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 26, 12, tzinfo=UTC)
PASSWORD = "long enough"


class FakeHasher(PasswordHasher):
    def hash(self, password: str) -> str:
        return f"hashed:{password}"

    def verify(self, plain_password: str, hashed_password: str) -> bool:
        return hashed_password == f"hashed:{plain_password}"


@dataclass
class MemoryServerStore(SyncServerStore):
    invites: dict[str, bool] = field(default_factory=dict)
    accounts: dict[UUID, SyncAccount] = field(default_factory=dict)
    by_id: dict[UUID, SyncDevice] = field(default_factory=dict)
    log: list[tuple[UUID, SyncOperation]] = field(default_factory=list)
    lose_the_race: bool = False

    async def add_invite(self, code_hash: str, now: datetime) -> None:
        self.invites[code_hash] = False

    async def invite_is_open(self, code_hash: str) -> bool:
        return self.invites.get(code_hash) is False

    async def create_account(self, account: SyncAccount, invite_hash: str) -> bool:
        if self.lose_the_race or self.invites.get(invite_hash) is not False:
            return False
        self.invites[invite_hash] = True
        self.accounts[account.account_id] = account
        return True

    async def account_by_username(self, username: str) -> SyncAccount | None:
        return next(
            (
                a
                for a in self.accounts.values()
                if a.username.lower() == username.lower()
            ),
            None,
        )

    async def account_exists(self, account_id: UUID) -> bool:
        return account_id in self.accounts

    async def add_device(self, device: SyncDevice) -> None:
        self.by_id[device.device_id] = device

    async def device(self, device_id: UUID) -> SyncDevice | None:
        return self.by_id.get(device_id)

    async def device_by_token(self, token_hash: str) -> SyncDevice | None:
        return next(
            (d for d in self.by_id.values() if d.token_hash == token_hash), None
        )

    async def devices(self, account_id: UUID) -> list[SyncDevice]:
        return [d for d in self.by_id.values() if d.account_id == account_id]

    async def revoke_device(self, device_id: UUID, now: datetime) -> None:
        self.by_id[device_id] = replace(self.by_id[device_id], revoked_at=now)

    async def seen(self, device_id: UUID, now: datetime) -> None:
        self.by_id[device_id] = replace(self.by_id[device_id], last_seen_at=now)

    async def append(
        self, account_id: UUID, operations: Sequence[SyncOperation], now: datetime
    ) -> int:
        have = {op.op_id for _, op in self.log}
        new = [op for op in operations if op.op_id not in have]
        self.log.extend((account_id, op) for op in new)
        return len(new)

    async def after(
        self, account_id: UUID, sequence: int, limit: int
    ) -> tuple[list[tuple[int, SyncOperation]], bool]:
        mine = [
            (seq, op)
            for seq, (owner, op) in enumerate(self.log, start=1)
            if owner == account_id and seq > sequence
        ]
        return mine[:limit], len(mine) > limit


@dataclass
class Server:
    store: MemoryServerStore = field(default_factory=MemoryServerStore)
    clock: FakeClock = field(default_factory=lambda: FakeClock(NOW))

    async def invite(self) -> str:
        return (await CreateInviteUseCase(self.store, self.clock).execute()).code

    async def account(
        self, invite: str, username: str = "wesley", account_id: UUID | None = None
    ) -> str:
        created = await CreateSyncAccountUseCase(
            self.store, self.clock, FakeHasher()
        ).execute(
            CreateSyncAccountInputDTO(
                invite=invite,
                account_id=str(account_id or uuid4()),
                username=username,
                email="w@example.com",
                password=PASSWORD,
            )
        )
        return created.account_id

    async def device(
        self,
        name: str = "mint",
        device_id: UUID | None = None,
        username: str = "wesley",
    ) -> tuple[UUID, str]:
        device = device_id or uuid4()
        access = await RegisterSyncDeviceUseCase(
            self.store, self.clock, FakeHasher()
        ).execute(
            RegisterSyncDeviceInputDTO(
                username=username,
                password=PASSWORD,
                device_id=str(device),
                device_name=name,
            )
        )
        return device, access.token

    async def push(self, token: str, operations: list[SyncOperation]) -> Any:
        return await AcceptPushUseCase(self.store, self.clock).execute(
            PushInputDTO(token=token, operations=[op.to_payload() for op in operations])
        )

    async def pull(self, token: str, after: int = 0, limit: int = 500) -> Any:
        return await ServePullUseCase(self.store, self.clock).execute(
            PullInputDTO(token=token, after=after, limit=limit)
        )


def _ops(device: UUID, n: int, ms: int | None = None) -> list[SyncOperation]:
    wall = ms if ms is not None else int(NOW.timestamp() * 1000)
    return [
        SyncOperation(
            entity=SyncEntity.TASK,
            entity_id=uuid4(),
            field="title",
            value=f"task {i}",
            hlc=Hlc(wall_ms=wall, counter=i, device_id=device.hex),
        )
        for i in range(n)
    ]


@pytest.fixture
def server() -> Server:
    return Server()


# ---------------------------------------------------------------- accounts


async def test_an_invite_is_kept_only_as_a_hash(server: Server) -> None:
    code = await server.invite()

    assert len(code) >= 16
    assert list(server.store.invites) == [secret_hash(code)]


async def test_an_account_uses_its_invite_up(server: Server) -> None:
    code = await server.invite()
    account_id = uuid4()

    created = await server.account(code, account_id=account_id)

    assert created == str(account_id)
    stored = server.store.accounts[account_id]
    assert stored.password_hash == f"hashed:{PASSWORD}"
    with pytest.raises(WrongCredentialsError):
        await server.account(code, username="other")


async def test_an_unknown_invite_creates_nothing(server: Server) -> None:
    with pytest.raises(WrongCredentialsError):
        await server.account("made-up")
    assert server.store.accounts == {}


async def test_an_invite_used_meanwhile_creates_nothing(server: Server) -> None:
    code = await server.invite()
    server.store.lose_the_race = True

    with pytest.raises(WrongCredentialsError):
        await server.account(code)


async def test_a_username_or_id_is_taken_once(server: Server) -> None:
    taken = uuid4()
    await server.account(await server.invite(), username="Wesley", account_id=taken)

    with pytest.raises(SyncConflictError, match="taken"):
        await server.account(await server.invite(), username="wesley")
    with pytest.raises(SyncConflictError, match="ID"):
        await server.account(await server.invite(), username="other", account_id=taken)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"username": "ab"}, "username"),
        ({"username": "with space"}, "username"),
        ({"email": "nope"}, "e-mail"),
        ({"password": "short"}, "password"),
        ({"account_id": "not-a-uuid"}, "account ID"),
    ],
)
async def test_an_account_needs_valid_fields(
    server: Server, change: dict[str, str], message: str
) -> None:
    fields = {
        "invite": await server.invite(),
        "account_id": str(uuid4()),
        "username": "wesley",
        "email": "w@example.com",
        "password": PASSWORD,
    } | change

    with pytest.raises(ValidationException, match=message):
        await CreateSyncAccountUseCase(
            server.store, server.clock, FakeHasher()
        ).execute(CreateSyncAccountInputDTO(**fields))


# ----------------------------------------------------------------- devices


async def test_a_device_gets_a_token_the_server_keeps_hashed(server: Server) -> None:
    await server.account(await server.invite())

    device, token = await server.device()

    stored = server.store.by_id[device]
    assert stored.token_hash == secret_hash(token)
    assert token not in repr(stored)
    assert stored.joined_at == NOW


async def test_a_device_needs_the_right_password(server: Server) -> None:
    await server.account(await server.invite())
    register = RegisterSyncDeviceUseCase(server.store, server.clock, FakeHasher())

    for username, password in (("wesley", "wrong password"), ("nobody", PASSWORD)):
        with pytest.raises(WrongCredentialsError):
            await register.execute(
                RegisterSyncDeviceInputDTO(
                    username=username,
                    password=password,
                    device_id=str(uuid4()),
                    device_name="mint",
                )
            )


async def test_a_device_id_and_name_must_be_valid_and_new(server: Server) -> None:
    await server.account(await server.invite())
    device, _ = await server.device()

    with pytest.raises(SyncConflictError):
        await server.device(device_id=device)
    with pytest.raises(ValidationException):
        await server.device(name=" ")
    with pytest.raises(ValidationException):
        await server.device(name="x" * 65)


async def test_devices_are_listed_and_revoked(server: Server) -> None:
    await server.account(await server.invite())
    _, mint = await server.device("mint")
    phone, phone_token = await server.device("phone")

    revoked = await RevokeServerDeviceUseCase(server.store, server.clock).execute(
        RevokeServerDeviceInputDTO(token=mint, device_id=str(phone))
    )
    again = await RevokeServerDeviceUseCase(server.store, server.clock).execute(
        RevokeServerDeviceInputDTO(token=mint, device_id=str(phone))
    )
    listed = await ListServerDevicesUseCase(server.store, server.clock).execute(
        ServerTokenInputDTO(token=mint)
    )

    assert revoked.revoked and again.revoked
    assert [(d.name, d.revoked) for d in listed] == [("mint", False), ("phone", True)]
    with pytest.raises(DeviceNotAllowedError):
        await server.pull(phone_token)


async def test_a_device_of_another_account_cannot_be_revoked(server: Server) -> None:
    await server.account(await server.invite())
    await server.account(await server.invite(), username="other")
    _, mine = await server.device("mint")
    theirs, _ = await server.device("theirs", username="other")
    revoke = RevokeServerDeviceUseCase(server.store, server.clock)

    for device_id in (str(theirs), str(uuid4())):
        with pytest.raises(EntityNotFound):
            await revoke.execute(
                RevokeServerDeviceInputDTO(token=mine, device_id=device_id)
            )


# -------------------------------------------------------------- push, pull


async def test_pushed_operations_come_back_in_pages(server: Server) -> None:
    await server.account(await server.invite())
    device, token = await server.device()
    ops = _ops(device, 5)

    pushed = await server.push(token, ops)
    again = await server.push(token, ops[:2])
    first = await server.pull(token, limit=3)
    rest = await server.pull(token, after=first.cursor, limit=3)
    nothing = await server.pull(token, after=rest.cursor)

    assert (pushed.received, pushed.accepted) == (5, 5)
    assert (again.received, again.accepted) == (2, 0)
    assert [SyncOperation.from_payload(p) for p in first.operations] == ops[:3]
    assert (first.cursor, first.more) == (3, True)
    assert [SyncOperation.from_payload(p) for p in rest.operations] == ops[3:]
    assert (rest.cursor, rest.more) == (5, False)
    assert (nothing.operations, nothing.cursor, nothing.more) == ([], 5, False)
    assert server.store.by_id[device].last_seen_at == NOW


async def test_an_account_only_sees_its_own_log(server: Server) -> None:
    await server.account(await server.invite())
    await server.account(await server.invite(), username="other")
    mine, my_token = await server.device("mint")
    theirs, their_token = await server.device("theirs", username="other")
    await server.push(their_token, _ops(theirs, 2))
    await server.push(my_token, _ops(mine, 1))

    page = await server.pull(my_token)

    assert len(page.operations) == 1
    assert page.cursor == 3


async def test_a_pull_page_has_limits(server: Server) -> None:
    await server.account(await server.invite())
    device, token = await server.device()
    await server.push(token, _ops(device, 3))

    assert len((await server.pull(token, limit=0)).operations) == 1
    with pytest.raises(ValidationException):
        await server.pull(token, after=-1)


async def test_a_push_is_refused_when(server: Server) -> None:
    await server.account(await server.invite())
    device, token = await server.device()
    ahead = int((NOW + timedelta(days=2)).timestamp() * 1000)

    with pytest.raises(DeviceNotAllowedError):
        await server.push("unknown token", _ops(device, 1))
    with pytest.raises(ValidationException, match="another device"):
        await server.push(token, _ops(uuid4(), 1))
    with pytest.raises(ValidationException, match="ahead"):
        await server.push(token, _ops(device, 1, ms=ahead))
    with pytest.raises(ValidationException, match="up to"):
        await server.push(token, _ops(device, MAX_BATCH + 1))
    with pytest.raises(ValidationException):
        await AcceptPushUseCase(server.store, server.clock).execute(
            PushInputDTO(token=token, operations=[{"op_id": "nope"}])
        )
    assert server.store.log == []


# ------------------------------------------- a device's use cases, end to end


@dataclass
class InProcessTransport(SyncTransport):
    """The device's transport, calling the server's use cases directly."""

    server: Server

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
        await CreateSyncAccountUseCase(
            self.server.store, self.server.clock, FakeHasher()
        ).execute(
            CreateSyncAccountInputDTO(
                invite=invite,
                account_id=str(account_id),
                username=username,
                email=email,
                password=password,
            )
        )

    async def register_device(
        self,
        server_url: str,
        *,
        username: str,
        password: str,
        device_id: UUID,
        device_name: str,
    ) -> DeviceAccess:
        access = await RegisterSyncDeviceUseCase(
            self.server.store, self.server.clock, FakeHasher()
        ).execute(
            RegisterSyncDeviceInputDTO(
                username=username,
                password=password,
                device_id=str(device_id),
                device_name=device_name,
            )
        )
        return DeviceAccess(account_id=UUID(access.account_id), token=access.token)

    async def push(
        self, server_url: str, token: str, operations: Sequence[SyncOperation]
    ) -> None:
        await self.server.push(token, list(operations))

    async def pull(
        self, server_url: str, token: str, after: int, limit: int
    ) -> PullPage:
        page = await self.server.pull(token, after, limit)
        return PullPage(
            operations=[SyncOperation.from_payload(p) for p in page.operations],
            cursor=page.cursor,
            more=page.more,
        )

    async def devices(self, server_url: str, token: str) -> list[DeviceInfo]:
        listed = await ListServerDevicesUseCase(
            self.server.store, self.server.clock
        ).execute(ServerTokenInputDTO(token=token))
        return [
            DeviceInfo(
                device_id=UUID(d.device_id),
                name=d.name,
                joined_at=datetime.fromisoformat(d.joined_at),
                last_seen_at=None,
                revoked=d.revoked,
            )
            for d in listed
        ]

    async def revoke_device(self, server_url: str, token: str, device_id: UUID) -> None:
        await RevokeServerDeviceUseCase(self.server.store, self.server.clock).execute(
            RevokeServerDeviceInputDTO(token=token, device_id=str(device_id))
        )


async def test_the_devices_side_talks_to_the_servers_side(server: Server) -> None:
    transport = InProcessTransport(server)
    mint, phone = (Device(n, FakeServer(), _user(n)) for n in ("mint", "phone"))
    task = uuid4()
    mint.store.rows[(SyncEntity.TASK, task)] = {"title": "Across"}
    invite = await server.invite()

    tokens: dict[str, str] = {}
    for device, code in ((mint, invite), (phone, None)):
        joined = await JoinSyncUseCase(
            device.uow, device.clock, transport, FakeHasher()
        ).execute(
            JoinSyncInputDTO(
                user_id=str(device.user.id),
                server_url="https://example.com",
                username="wesley",
                password=PASSWORD,
                device_name=device.name,
                invite=code,
            )
        )
        tokens[device.name] = joined.token
    for device in (mint, phone, mint):
        await RunSyncUseCase(device.uow, device.clock, transport).execute(
            RunSyncInputDTO(token=tokens[device.name])
        )
    await RevokeSyncDeviceUseCase(mint.uow, mint.clock, transport).execute(
        RevokeSyncDeviceInputDTO(token=tokens["mint"], device="phone")
    )

    assert phone.store.rows[(SyncEntity.TASK, task)] == {"title": "Across"}
    assert server.store.accounts[mint.user.id.value].username == "wesley"
    with pytest.raises(DeviceNotAllowedError):
        await RunSyncUseCase(phone.uow, phone.clock, transport).execute(
            RunSyncInputDTO(token=tokens["phone"])
        )
