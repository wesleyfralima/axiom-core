"""What the sync server keeps besides the log: accounts, devices, invites.

Secrets (a device's token, an invite code) are handed out once and kept only
as a hash (``secret_hash``): a copy of the server's database does not let
anyone sync.
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from a_core import ValueObject


def new_secret(nbytes: int = 32) -> str:
    """A new random secret, URL-safe (a token, an invite code)."""
    return secrets.token_urlsafe(nbytes)


def secret_hash(secret: str) -> str:
    """What the server keeps of a secret (SHA-256, hex): a token is random
    and long, so a fast hash is enough — unlike a password."""
    return hashlib.sha256(secret.strip().encode()).hexdigest()


@dataclass(frozen=True, kw_only=True)
class SyncAccount(ValueObject):
    """An account on the server: the same user on every device.

    Attributes:
        account_id (UUID): The account (the user's ID on the devices).
        username (str): To sign a device in.
        email (str): The owner's e-mail.
        password_hash (str): The password, hashed (bcrypt).
        created_at (datetime): When it was created.
    """

    account_id: UUID
    username: str
    email: str
    password_hash: str
    created_at: datetime


@dataclass(frozen=True, kw_only=True)
class SyncDevice(ValueObject):
    """A device signed in to an account.

    Attributes:
        device_id (UUID): The device (it chose the ID when joining).
        account_id (UUID): Its account.
        name (str): What the owner calls it.
        token_hash (str): Its token, hashed.
        joined_at (datetime): When it joined.
        last_seen_at (datetime | None): When it last pushed or pulled.
        revoked_at (datetime | None): When it was revoked, if it was.
    """

    device_id: UUID
    account_id: UUID
    name: str
    token_hash: str
    joined_at: datetime
    last_seen_at: datetime | None = None
    revoked_at: datetime | None = None
