"""GOFI instance content (Phase D): the three programs, the two puppy qualifications, the Puppy
Raiser application that emails the applicant on a decision, a certified raiser enrollment, a
qualification-gated puppy-sitter sheet, and a live donation campaign — all from seed."""

from __future__ import annotations

import pytest
from conftest import inbox, relay
from sqlalchemy import func, select

from app.modules.donations.models import CampaignStatus, DonationCampaign
from app.modules.forms.models import FormDefinition, FormSubmission
from app.modules.org.models import Program
from app.modules.people.models import ProgramEnrollment, QualificationType
from app.modules.scheduling.models import ShiftRole


@pytest.fixture(autouse=True)
def gofi(db, org):
    """GOFI org content is opt-in (settings.seed_org_content); seed it explicitly for these
    tests so the generic suite keeps its minimal seed."""
    from app.seed import _seed_gofi_programs
    _seed_gofi_programs(db, org.id, include_demo=True)
    db.commit()
    return org


def test_gofi_programs_and_qualifications_seeded(db, org):
    programs = {p.key for p in db.scalars(select(Program).where(Program.org_id == org.id))}
    assert {"service_dog", "facility_dog", "crisis_response_dog"} <= programs
    quals = {q.key for q in db.scalars(select(QualificationType).where(
        QualificationType.org_id == org.id))}
    assert {"puppy_raiser_certified", "puppy_sitter_certified"} <= quals
    assert db.scalar(select(FormDefinition).where(
        FormDefinition.org_id == org.id,
        FormDefinition.key == "puppy_raiser_application")) is not None


def test_demo_raiser_enrolled_and_sitter_slots_gated(db, org):
    enr = db.scalar(select(ProgramEnrollment).where(
        ProgramEnrollment.org_id == org.id, ProgramEnrollment.role == "puppy_raiser"))
    assert enr is not None and enr.status == "active"
    # The seeded puppy-sitter respite shifts require the sitter qualification.
    sitter_qual = db.scalar(select(QualificationType).where(
        QualificationType.org_id == org.id, QualificationType.key == "puppy_sitter_certified"))
    gated = db.scalar(select(func.count()).select_from(ShiftRole).where(
        ShiftRole.org_id == org.id,
        ShiftRole.required_qualification_type_id == sitter_qual.id))
    assert gated >= 1


def test_donation_campaign_is_public_and_live(db, org, client):
    c = db.scalar(select(DonationCampaign).where(
        DonationCampaign.org_id == org.id, DonationCampaign.slug == "raise-a-service-dog"))
    assert c is not None and c.status == CampaignStatus.active and c.is_public
    # Reachable on the public campaign endpoint the /donate page consumes.
    assert client.get("/api/campaigns/raise-a-service-dog").status_code == 200


def test_puppy_raiser_application_approval_emails_the_applicant(client, db, org, admin_headers):
    r = client.post("/api/forms/puppy_raiser_application/submissions", json={"answers": {
        "full_name": "Casey Applicant", "email": "casey@example.org", "town": "Walpole",
        "home_type": "House with a yard", "availability": "Yes"}})
    assert r.status_code == 201
    iid = db.get(FormSubmission, r.json()["id"]).workflow_instance_id
    client.post(f"/api/instances/{iid}/transitions/start_review", headers=admin_headers, json={})
    client.post(f"/api/instances/{iid}/transitions/approve", headers=admin_headers, json={})
    relay(db)  # workflow.notify -> email.send
    relay(db)  # email.send -> dev inbox
    msgs = inbox(db, org.id)
    assert any(m.to_email == "casey@example.org" and "approved" in m.body_text.lower()
               for m in msgs)
