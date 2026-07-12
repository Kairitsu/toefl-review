"""Flask integration tests via test_client (isolated SQLite per test)."""

from app import hash_password, set_setting


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


def test_health_ok(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.get_json()
    assert body["ok"] is True
    assert "time" in body


def test_security_headers_include_csp(client):
    response = client.get("/api/health")
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"
    csp = response.headers.get("Content-Security-Policy", "")
    assert "script-src 'self' 'unsafe-inline'" in csp
    assert "style-src 'self' 'unsafe-inline'" in csp
    assert "connect-src 'self'" in csp
    assert "object-src 'none'" in csp
    assert "base-uri 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "img-src 'self' data:" in csp
    assert "font-src 'self'" in csp

    # HTML shell also carries CSP (same after_request)
    index = client.get("/")
    assert index.status_code == 200
    assert "Content-Security-Policy" in index.headers


# ---------------------------------------------------------------------------
# Question CRUD
# ---------------------------------------------------------------------------


def test_question_crud(client, sample_reading_choice):
    # Create
    create = client.post("/api/questions", json=sample_reading_choice)
    assert create.status_code == 201, create.get_json()
    created = create.get_json()
    qid = created["id"]
    assert created["type"] == "reading_choice"
    assert created["data"]["correctAnswer"] == "B"

    # List
    listing = client.get("/api/questions")
    assert listing.status_code == 200
    items = listing.get_json()["items"]
    assert any(item["id"] == qid for item in items)

    # Get one
    detail = client.get(f"/api/questions/{qid}")
    assert detail.status_code == 200
    assert detail.get_json()["prompt"] == sample_reading_choice["prompt"]

    # Update
    updated_payload = {
        **sample_reading_choice,
        "prompt": "Updated prompt?",
        "data": {
            **sample_reading_choice["data"],
            "correctAnswer": "C",
        },
    }
    update = client.put(f"/api/questions/{qid}", json=updated_payload)
    assert update.status_code == 200, update.get_json()
    assert update.get_json()["prompt"] == "Updated prompt?"
    assert update.get_json()["data"]["correctAnswer"] == "C"

    # Delete
    delete = client.delete(f"/api/questions/{qid}")
    assert delete.status_code == 200
    assert delete.get_json()["ok"] is True

    # Gone
    missing = client.get(f"/api/questions/{qid}")
    assert missing.status_code == 404


def test_create_build_and_complete_words(
    client, sample_build_sentence, sample_complete_words
):
    build = client.post("/api/questions", json=sample_build_sentence)
    assert build.status_code == 201, build.get_json()
    assert build.get_json()["type"] == "build_sentence"

    complete = client.post("/api/questions", json=sample_complete_words)
    assert complete.status_code == 201, complete.get_json()
    body = complete.get_json()
    assert body["type"] == "complete_words"
    # Underscores should be converted to markers after normalize
    passage = body["data"]["passageText"]
    assert "[[" in passage
    assert len(body["data"]["blanks"]) == 2


def test_create_invalid_question_returns_400(client):
    response = client.post(
        "/api/questions",
        json={"type": "reading_choice", "article": "", "prompt": "", "data": {}},
    )
    assert response.status_code == 400
    body = response.get_json()
    assert "validation" in body


# ---------------------------------------------------------------------------
# Auth flow
# ---------------------------------------------------------------------------


def test_auth_required_when_configured(client, app_mod, sample_reading_choice):
    """
    After username/password are configured:
    - unauthenticated requests to protected APIs return 401
    - login with correct credentials succeeds
    - subsequent requests work
    """
    # Seed credentials directly in the isolated DB (avoids needing an open session)
    with app_mod.get_db() as db:
        set_setting(db, "auth_username", "tester")
        set_setting(db, "auth_password_hash", hash_password("s3cret-pass"))
        db.commit()

    # Fresh client has no session cookie → should be blocked
    anon = app_mod.app.test_client()
    blocked = anon.get("/api/questions")
    assert blocked.status_code == 401
    body = blocked.get_json()
    assert body.get("authRequired") is True

    # Health stays public
    health = anon.get("/api/health")
    assert health.status_code == 200

    # Wrong password
    bad_login = anon.post(
        "/api/auth/login",
        json={"username": "tester", "password": "wrong"},
    )
    assert bad_login.status_code == 401

    # Good login
    good_login = anon.post(
        "/api/auth/login",
        json={"username": "tester", "password": "s3cret-pass"},
    )
    assert good_login.status_code == 200
    assert good_login.get_json()["ok"] is True
    assert good_login.get_json()["username"] == "tester"

    # Now protected routes work
    listing = anon.get("/api/questions")
    assert listing.status_code == 200

    created = anon.post("/api/questions", json=sample_reading_choice)
    assert created.status_code == 201, created.get_json()


def test_auth_open_when_not_configured(client, sample_reading_choice):
    """With no credentials stored, the API stays open (personal-use default)."""
    status = client.get("/api/auth/status")
    assert status.status_code == 200
    assert status.get_json()["authRequired"] is False

    listing = client.get("/api/questions")
    assert listing.status_code == 200

    created = client.post("/api/questions", json=sample_reading_choice)
    assert created.status_code == 201
