"""Website builder: sanitization (XSS), page lifecycle, public serving, privilege gate, AI assist."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.session import make_session_token
from app.modules.content import service
from app.modules.content.sanitize import sanitize_css, sanitize_html
from app.modules.identity.models import Person, Role, User, UserRoleAssignment


def _user_with_role(db, org, role_key: str, email: str):
    person = Person(org_id=org.id, name=email, email=email, email_verified=True)
    db.add(person)
    db.flush()
    user = User(org_id=org.id, person_id=person.id)
    db.add(user)
    db.flush()
    role = db.scalar(select(Role).where(Role.org_id == org.id, Role.key == role_key))
    db.add(UserRoleAssignment(org_id=org.id, user_id=user.id, role_id=role.id))
    db.commit()
    return {"Authorization": f"Bearer {make_session_token(user_id=user.id, org_id=org.id)}"}


# --- Sanitizer (the security core) ------------------------------------------ #

@pytest.mark.parametrize("payload", [
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    '<a href="javascript:alert(1)">x</a>',
    '<div onclick="alert(1)">d</div>',
    '<iframe src="//evil"></iframe>',
    '<p style="background:url(javascript:alert(1))">x</p>',
    '<svg/onload=alert(1)>',
])
def test_sanitize_html_neutralizes_xss(payload):
    out = sanitize_html(payload)
    low = out.lower()
    assert "<script" not in low and "onerror" not in low and "onclick" not in low
    assert "javascript:" not in low and "onload" not in low and "<iframe" not in low
    assert "<svg" not in low


def test_sanitize_html_keeps_safe_markup():
    out = sanitize_html('<p>Hello <strong>world</strong> <a href="https://ok.org">link</a></p>')
    assert "<strong>world</strong>" in out and 'href="https://ok.org"' in out


@pytest.mark.parametrize("css", [
    "@import url(evil.css); .a{color:red}",
    ".a{background:url(javascript:alert(1))}",
    ".a{color:red} </style><script>alert(1)</script>",
    ".a{behavior:url(x.htc)}",
])
def test_sanitize_css_rejects_dangerous(css):
    assert sanitize_css(css, scope_id="1") == ""


def test_sanitize_css_scopes_selectors():
    out = sanitize_css("body { margin: 0 } .hero { color: red }", scope_id="9")
    assert "#page-9" in out
    assert "body {" not in out  # body rewritten to the scope root


# --- Page lifecycle + public serving ---------------------------------------- #

def test_create_edit_publish_and_public_serving(client, admin_headers):
    pid = client.post("/api/admin/pages", headers=admin_headers,
                      json={"slug": "our-work", "title": "Our Work"}).json()["id"]
    client.patch(f"/api/admin/pages/{pid}", headers=admin_headers, json={
        "blocks": [{"type": "heading", "level": 1, "text": "Our Work"},
                   {"type": "paragraph", "html": "<p>We do <strong>good</strong> things.</p>"}],
        "show_in_nav": True})
    # Not served publicly until published.
    assert client.get("/api/public/pages/our-work").status_code == 404
    assert client.post(f"/api/admin/pages/{pid}/publish", headers=admin_headers).status_code == 200

    page = client.get("/api/public/pages/our-work").json()
    assert page["title"] == "Our Work"
    assert any(b.get("html") == "<p>We do <strong>good</strong> things.</p>" for b in page["blocks"])
    nav = client.get("/api/public/site-nav").json()
    assert any(n["slug"] == "our-work" for n in nav)


def test_seeded_pages_are_published_and_in_nav(client):
    # The demo pages seeded at bootstrap serve publicly and populate the nav out of the box.
    nav = client.get("/api/public/site-nav").json()
    slugs = {n["slug"] for n in nav}
    assert {"our-story", "get-involved"} <= slugs
    page = client.get("/api/public/pages/our-story").json()
    assert page["title"] == "Our story" and page["blocks"]


def test_reserved_slug_rejected(client, admin_headers):
    r = client.post("/api/admin/pages", headers=admin_headers,
                    json={"slug": "login", "title": "x"})
    assert r.status_code == 400 and "reserved" in r.json()["detail"].lower()


def test_html_block_is_sanitized_end_to_end(client, admin_headers):
    pid = client.post("/api/admin/pages", headers=admin_headers,
                      json={"slug": "promo", "title": "Promo"}).json()["id"]
    client.patch(f"/api/admin/pages/{pid}", headers=admin_headers, json={
        "blocks": [{"type": "html", "html": "<script>alert(1)</script><b>Sale!</b>"}]})
    client.post(f"/api/admin/pages/{pid}/publish", headers=admin_headers)
    page = client.get("/api/public/pages/promo").json()
    served = str(page["blocks"])
    assert "<script" not in served and "alert(1)" not in served and "<b>Sale!</b>" in served


def test_public_serves_only_published_snapshot_not_draft(client, admin_headers):
    pid = client.post("/api/admin/pages", headers=admin_headers,
                      json={"slug": "news", "title": "News"}).json()["id"]
    client.patch(f"/api/admin/pages/{pid}", headers=admin_headers,
                 json={"blocks": [{"type": "paragraph", "html": "<p>v1</p>"}]})
    client.post(f"/api/admin/pages/{pid}/publish", headers=admin_headers)
    # Edit the draft AFTER publishing — public must still show v1 until re-published.
    client.patch(f"/api/admin/pages/{pid}", headers=admin_headers,
                 json={"blocks": [{"type": "paragraph", "html": "<p>v2 draft</p>"}]})
    page = client.get("/api/public/pages/news").json()
    assert "v1" in str(page["blocks"]) and "v2 draft" not in str(page["blocks"])


# --- Privilege gate --------------------------------------------------------- #

def test_privileged_blocks_require_site_develop(client, db, org, admin_headers):
    editor = _user_with_role(db, org, "site_editor", "editor@x.org")  # has edit+publish, NOT develop
    pid = client.post("/api/admin/pages", headers=editor,
                      json={"slug": "e1", "title": "E1"}).json()["id"]
    # A plain paragraph is fine for a site_editor.
    assert client.patch(f"/api/admin/pages/{pid}", headers=editor,
                        json={"blocks": [{"type": "paragraph", "html": "<p>ok</p>"}]}).status_code == 200
    # A raw html block OR custom CSS requires site.develop → 403 for the editor.
    assert client.patch(f"/api/admin/pages/{pid}", headers=editor,
                        json={"blocks": [{"type": "html", "html": "<b>x</b>"}]}).status_code == 403
    assert client.patch(f"/api/admin/pages/{pid}", headers=editor,
                        json={"custom_css": ".x{color:red}"}).status_code == 403
    # org_admin has site.develop → allowed.
    assert client.patch(f"/api/admin/pages/{pid}", headers=admin_headers,
                        json={"custom_css": ".x{color:red}"}).status_code == 200


def test_pages_are_org_scoped(db, org):
    from app.modules.org.models import Organization
    other = Organization(name="Other", slug="other-org")
    db.add(other)
    db.flush()
    page = service.create_page(db, org_id=org.id, slug="team", title="Team", actor_user_id=1)
    db.commit()
    with pytest.raises(service.ContentError):
        service.get_page(db, org_id=other.id, page_id=page.id)


# --- AI assist -------------------------------------------------------------- #

def test_ai_assist_returns_deterministic_copy_without_key(client, admin_headers):
    r1 = client.post("/api/admin/pages/assist", headers=admin_headers,
                     json={"prompt": "a welcoming intro for our food pantry"})
    r2 = client.post("/api/admin/pages/assist", headers=admin_headers,
                     json={"prompt": "a welcoming intro for our food pantry"})
    assert r1.status_code == 200 and r1.json()["provider"] == "dev"
    assert r1.json()["text"] and r1.json()["text"] == r2.json()["text"]  # deterministic
