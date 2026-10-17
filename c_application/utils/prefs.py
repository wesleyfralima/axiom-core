from dataclasses import replace

from b_domain.entities.user import User, UserPrefs
from b_domain.ports.unit_of_work import UnitOfWork


def prefs_of(uow: UnitOfWork, user: User | None) -> UserPrefs:
    """The user's preferences for this command (the defaults without a user).

    The command's zone (``uow.timezone``, an interface's ``--tz``) wins over
    the stored one, never saved: a time typed is a wall-clock time there,
    and "today" is its day. Reading them to change them is
    ``user.preferences``.
    """
    prefs: UserPrefs = user.preferences if user else UserPrefs()
    if uow.timezone and uow.timezone != prefs.timezone:
        return replace(prefs, timezone=uow.timezone)
    return prefs
