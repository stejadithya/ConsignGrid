"""Copies of the signed consignment agreement (finding 14, D8). Stored in the database like drop-off photos."""

import base64
import binascii

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, NotFoundError
from app.modules.audit.service import record_audit
from app.modules.customers.models import ConsignmentAgreementFile, Reseller
from app.modules.identity.models import User

MAX_BYTES = 5 * 1024 * 1024
TYPES = ("application/pdf", "image/jpeg", "image/png", "image/webp")


def sniff(raw: bytes) -> str | None:
    """The file's real type from its first bytes (the file name and browser claim are not trusted)."""
    if raw.startswith(b"%PDF"):
        return "application/pdf"
    if raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
        return "image/webp"
    return None


def upload(db: Session, actor: User, reseller: Reseller, filename: str, content_base64: str) -> ConsignmentAgreementFile:
    try:
        raw = base64.b64decode(content_base64.split(",")[-1], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise BusinessRuleError("The uploaded file could not be decoded.") from exc
    if not raw:
        raise BusinessRuleError("The file is empty.")
    if len(raw) > MAX_BYTES:
        raise BusinessRuleError("The file is larger than 5 MB.")
    content_type = sniff(raw)
    if content_type is None:
        raise BusinessRuleError("Upload a PDF or a photo (JPG, PNG or WEBP).")
    f = ConsignmentAgreementFile(reseller_id=reseller.id, filename=filename.strip()[:255] or "agreement",
                                 content_type=content_type, size_bytes=len(raw), data=raw, uploaded_by_user_id=actor.id)
    db.add(f)
    db.flush()
    record_audit(db, actor_id=actor.id, action="agreement_file.upload", entity_type="consignment_agreement_file",
                 entity_id=f.id, reseller_id=reseller.id, summary=f"Uploaded agreement copy {f.filename}")
    return f


def list_files(db: Session, reseller_id: int) -> list[ConsignmentAgreementFile]:
    return list(db.execute(select(ConsignmentAgreementFile).where(
        ConsignmentAgreementFile.reseller_id == reseller_id, ConsignmentAgreementFile.is_active.is_(True))
        .order_by(ConsignmentAgreementFile.uploaded_at.desc())).scalars())


def get_file(db: Session, reseller_id: int, file_id: int) -> ConsignmentAgreementFile:
    f = db.get(ConsignmentAgreementFile, file_id)
    if f is None or f.reseller_id != reseller_id or not f.is_active:
        raise NotFoundError("Agreement copy not found")
    return f


def remove(db: Session, actor: User, reseller_id: int, file_id: int) -> None:
    f = get_file(db, reseller_id, file_id)
    f.is_active = False
    db.flush()
    record_audit(db, actor_id=actor.id, action="agreement_file.delete", entity_type="consignment_agreement_file",
                 entity_id=f.id, reseller_id=reseller_id, summary=f"Removed agreement copy {f.filename}")
