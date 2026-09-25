from .auth.login import LoginUseCase
from .auth.register import RegisterUserUseCase
from .context import (
    CreateContextUseCase,
    DeleteContextUseCase,
    ListContextsUseCase,
    SwitchContextUseCase,
    UpdateContextUseCase,
)
from .task.complete import CompleteTaskUseCase
from .task.create import CreateTaskUseCase
from .task.delete import DeleteTaskUseCase
from .task.get import GetTaskUseCase
from .task.list import ListTasksUseCase
from .task.update import UpdateTaskUseCase
from .user.get_current import GetCurrentUserUseCase
from .user.update_prefs import UpdateUserPreferencesUseCase

__all__ = [
    "CompleteTaskUseCase",
    "CreateContextUseCase",
    "CreateTaskUseCase",
    "DeleteContextUseCase",
    "DeleteTaskUseCase",
    "GetCurrentUserUseCase",
    "GetTaskUseCase",
    "ListContextsUseCase",
    "ListTasksUseCase",
    "LoginUseCase",
    "RegisterUserUseCase",
    "SwitchContextUseCase",
    "UpdateContextUseCase",
    "UpdateTaskUseCase",
    "UpdateUserPreferencesUseCase",
]
