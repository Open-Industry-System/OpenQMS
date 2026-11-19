"""Server-owned investigation actions for publication and shared review."""
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import RequestScope
from app.services.iqc_investigation_associations import (
    AssociationChanged,
    AssociationSnapshot,
    LinkedInvestigation,
    read_linked_investigations,
)


class InvestigationAction(StrEnum):
    CHECK_EXISTING = "check_existing"
    SUPPLEMENT_EXISTING = "supplement_existing"
    CONSIDER_NEW = "consider_new"


@dataclass(frozen=True)
class InvestigationHint:
    action: InvestigationAction
    investigations: tuple[LinkedInvestigation, ...] = ()
    checked_modules: tuple[str, ...] = ()


def validate_investigation_action(
    action: InvestigationAction, confirmed: AssociationSnapshot | None,
) -> None:
    """Validate a structured action using only a current, server-verified receipt.

    The caller resolves and checks the receipt's task, run, epoch, scope and
    current association version before passing its snapshot.
    """
    if not isinstance(action, InvestigationAction):
        raise ValueError("Invalid investigation action")
    if action is InvestigationAction.CONSIDER_NEW and not (confirmed and confirmed.may_consider_new):
        raise ValueError("New investigation requires a current and complete linked-investigation check")
    if action is InvestigationAction.SUPPLEMENT_EXISTING and not (
        confirmed and confirmed.investigations and not confirmed.ambiguous
    ):
        raise ValueError("Supplementing requires a visible and unambiguous linked investigation")


def review_investigation_hint(
    recorded: InvestigationAction,
    *,
    is_current: bool,
    visible: AssociationSnapshot | None,
) -> InvestigationHint:
    """Compute a response-only hint from the current reader's authorized snapshot."""
    if visible is None:
        return InvestigationHint(InvestigationAction.CHECK_EXISTING)
    if visible.ambiguous:
        return InvestigationHint(
            InvestigationAction.CHECK_EXISTING, visible.investigations, visible.allowed_modules,
        )
    if visible.investigations:
        return InvestigationHint(
            InvestigationAction.SUPPLEMENT_EXISTING, visible.investigations, visible.allowed_modules,
        )
    if is_current and recorded is InvestigationAction.CONSIDER_NEW and visible.may_consider_new:
        return InvestigationHint(
            InvestigationAction.CONSIDER_NEW, checked_modules=visible.allowed_modules,
        )
    return InvestigationHint(InvestigationAction.CHECK_EXISTING)


async def read_review_investigation_hint(
    db: AsyncSession,
    scope: RequestScope,
    *,
    recorded: InvestigationAction,
    is_current: bool,
    inspection_ids: tuple[UUID, ...],
    factory_id: UUID,
    allowed_product_lines: frozenset[str | None] | None = None,
) -> InvestigationHint:
    """Read current links only after the caller authorizes the card and its sources.

    Inputs identify the current reader's accessible inspection family and any
    reader-side bound on product lines. The original run's permissions do not
    carry over to the new lookup.
    """
    try:
        async with db.begin_nested():
            visible = await read_linked_investigations(
                db, scope, inspection_ids, factory_id=factory_id,
                allowed_product_lines=allowed_product_lines,
            )
    except (AssociationChanged, PermissionError, LookupError, SQLAlchemyError):
        visible = None
    return review_investigation_hint(recorded, is_current=is_current, visible=visible)
