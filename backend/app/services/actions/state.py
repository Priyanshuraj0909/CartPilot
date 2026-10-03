"""Only explicit lifecycle transitions can authorize local execution."""
from app.models.action import Action, ActionStatus

TRANSITIONS = {
    ActionStatus.PENDING: {ActionStatus.VALIDATED, ActionStatus.FAILED},
    ActionStatus.VALIDATED: {ActionStatus.AWAITING_APPROVAL},
    ActionStatus.AWAITING_APPROVAL: {ActionStatus.APPROVED, ActionStatus.REJECTED},
    ActionStatus.APPROVED: {ActionStatus.EXECUTING},
    ActionStatus.EXECUTING: {ActionStatus.EXECUTED, ActionStatus.FAILED},
}


class ActionError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


def transition(action: Action, target: ActionStatus) -> None:
    if target not in TRANSITIONS.get(ActionStatus(action.status), set()):
        raise ActionError(409, f"Cannot transition {action.status} to {target}.")
    action.status = target.value
