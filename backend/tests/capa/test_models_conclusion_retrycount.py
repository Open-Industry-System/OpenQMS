from app.models.capa import CapaRootCauseVerification, CAPAEightD


def test_verification_has_conclusion_column():
    assert "conclusion" in CapaRootCauseVerification.__table__.columns
    col = CapaRootCauseVerification.__table__.columns["conclusion"]
    assert col.nullable is False


def test_verification_has_method_check_constraint():
    consts = [c.name for c in CapaRootCauseVerification.__table__.constraints if hasattr(c, "name")]
    assert "chk_verification_method" in consts


def test_verification_has_conclusion_check_constraint():
    consts = [c.name for c in CapaRootCauseVerification.__table__.constraints if hasattr(c, "name")]
    assert "chk_verification_conclusion" in consts


def test_eightd_has_d4_retry_count():
    assert "d4_retry_count" in CAPAEightD.__table__.columns
    col = CAPAEightD.__table__.columns["d4_retry_count"]
    assert col.nullable is False
