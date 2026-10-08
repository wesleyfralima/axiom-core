from .auth.login import LoginUseCase
from .auth.register import RegisterUserUseCase
from .context import (
    CreateContextUseCase,
    DeleteContextUseCase,
    ListContextsUseCase,
    SwitchContextUseCase,
    UpdateContextUseCase,
)
from .task.add_subtasks import AddSubtasksUseCase
from .task.archive import ArchiveTaskUseCase
from .task.cancel import CancelTaskUseCase
from .task.complete import CompleteTaskUseCase
from .task.create import CreateTaskUseCase
from .task.delete import DeleteTaskUseCase
from .task.get import GetTaskUseCase
from .task.history import GetTaskHistoryUseCase
from .task.list import ListTasksUseCase
from .task.reopen import ReopenTaskUseCase
from .task.report import ReportUseCase
from .task.restore import RestoreTaskUseCase
from .task.snooze import SnoozeTaskUseCase
from .task.timer import PauseTaskUseCase, StartTaskUseCase
from .task.today import TodayUseCase
from .task.undo import UndoPreviewUseCase, UndoUseCase
from .task.update import UpdateTaskUseCase
from .user.get_current import GetCurrentUserUseCase
from .user.update_prefs import UpdateUserPreferencesUseCase

__all__ = [
    "AddSubtasksUseCase",
    "ArchiveTaskUseCase",
    "CancelTaskUseCase",
    "CompleteTaskUseCase",
    "CreateContextUseCase",
    "CreateTaskUseCase",
    "DeleteContextUseCase",
    "DeleteTaskUseCase",
    "GetCurrentUserUseCase",
    "GetTaskHistoryUseCase",
    "GetTaskUseCase",
    "ListContextsUseCase",
    "ListTasksUseCase",
    "LoginUseCase",
    "PauseTaskUseCase",
    "RegisterUserUseCase",
    "ReopenTaskUseCase",
    "ReportUseCase",
    "RestoreTaskUseCase",
    "SnoozeTaskUseCase",
    "StartTaskUseCase",
    "SwitchContextUseCase",
    "TodayUseCase",
    "UndoPreviewUseCase",
    "UndoUseCase",
    "UpdateContextUseCase",
    "UpdateTaskUseCase",
    "UpdateUserPreferencesUseCase",
]
