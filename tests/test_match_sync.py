import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_admin, get_current_user
from app.api.v1.endpoints import admin as admin_module
from app.api.v1.endpoints import profile as profile_module
from app.core.config import settings
from app.core.limiter import limiter
from app.db.session import get_db
from app.main import app
from app.models.user import AccountStatus, UserRole
from app.services import match_sync

T0 = datetime(2026, 11, 9, 10, 0, tzinfo=timezone.utc)
SID = uuid.uuid4()
CSRF = {"X-CSRF-Token": "tok"}
COOKIES = {"csrf_token": "tok"}
EXPECTED_KEYS = {
    "verified", "display_name", "profile_image_url", "category", "state", "phone",
    "latitude", "longitude", "radius_km", "source_updated_at",
}


def _user(status=AccountStatus.ACTIVE, **kw):
    base = dict(
        id=SID, role=UserRole.SOLVER, account_status=status, full_name="Jane Solver", email="jane@example.com",
        phone_number="0800000000", updated_at=T0, status_changed_at=T0 - timedelta(hours=1),
    )
    return SimpleNamespace(**{**base, **kw})


def _profile(**kw):
    base = dict(
        profile_image_key="solver/abc.png", category="Plumber", state="Lagos", latitude=6.5, longitude=3.3,
        radius_km=15, updated_at=T0 - timedelta(minutes=5), acct_num="0123456789", contact_address="1 Secret St",
    )
    return SimpleNamespace(**{**base, **kw})


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(settings, "MATCH_SERVICE_URL", "http://match.internal:8000/")
    monkeypatch.setattr(settings, "MATCH_INTERNAL_API_KEY", "shared-key")


# ---------- payload ----------

def test_payload_has_only_the_agreed_fields_and_no_other_private_data():
    payload = match_sync.build_payload(_user(), _profile())
    assert set(payload) == EXPECTED_KEYS
    assert payload["phone"] == "0800000000"  # the one private field we send on purpose
    text = str(payload)
    for private in ("jane@example.com", "0123456789", "1 Secret St"):  # email, bank account, address stay home
        assert private not in text


def test_a_solver_without_a_phone_sends_none():
    assert match_sync.build_payload(_user(phone_number=None), _profile())["phone"] is None


@pytest.mark.parametrize("status", list(AccountStatus))
def test_only_active_is_verified(status):
    assert match_sync.build_payload(_user(status), _profile())["verified"] is (status == AccountStatus.ACTIVE)


@pytest.mark.parametrize(
    "text,slug", [("Plumber", "plumber"), ("plumber ", "plumber"), ("Automobile Electrician", "auto-electrician"),
                  ("Auto Mobile", None), ("", None)],
)
def test_category_is_the_official_slug_or_none(text, slug):
    assert match_sync.build_payload(_user(), _profile(category=text))["category"] == slug


def test_version_stamp_is_the_latest_change_and_timezone_aware():
    payload = match_sync.build_payload(_user(), _profile(updated_at=T0 + timedelta(minutes=3)))
    assert payload["source_updated_at"] == (T0 + timedelta(minutes=3)).isoformat()
    assert payload["source_updated_at"].endswith("+00:00")


def test_missing_status_changed_at_is_fine():
    assert match_sync.build_payload(_user(status_changed_at=None), _profile())["source_updated_at"]


# ---------- sending ----------

class _Recorder:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        outcome = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture
def wire(monkeypatch, configured):
    def make(*outcomes):
        rec = _Recorder(*outcomes)
        real = httpx.AsyncClient
        monkeypatch.setattr(match_sync.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(rec), **kw))
        monkeypatch.setattr(match_sync.asyncio, "sleep", AsyncMock())  # no real waiting between retries
        return rec

    return make


OK = httpx.Response(200, json={"applied": True, "category_matched": True})


async def test_put_sends_key_and_goes_to_the_internal_url(wire):
    rec = wire(OK)
    assert await match_sync.put_to_match(SID, {"verified": True}) is True
    (req,) = rec.requests
    assert req.method == "PUT"
    assert str(req.url) == f"http://match.internal:8000/api/v1/internal/solvers/{SID}"
    assert req.headers["x-internal-key"] == "shared-key"


async def test_server_errors_are_retried_then_succeed(wire):
    rec = wire(httpx.Response(503), httpx.Response(502), OK)
    assert await match_sync.put_to_match(SID, {"verified": True}) is True
    assert len(rec.requests) == 3


async def test_network_errors_are_retried_then_give_up(wire):
    rec = wire(httpx.ConnectError("down"))
    assert await match_sync.put_to_match(SID, {"verified": True}) is False
    assert len(rec.requests) == 3


async def test_rate_limit_is_retried(wire):
    rec = wire(httpx.Response(429), OK)
    assert await match_sync.put_to_match(SID, {"verified": True}) is True
    assert len(rec.requests) == 2


@pytest.mark.parametrize("code", [401, 403, 404, 422, 503 - 100])
async def test_other_client_errors_are_not_retried(wire, code):
    rec = wire(httpx.Response(code, text="no"))
    assert await match_sync.put_to_match(SID, {"verified": True}) is False
    assert len(rec.requests) == 1


# ---------- push_solver_to_match ----------

def _fake_session(user, profile):
    result = MagicMock()
    result.scalar_one_or_none.return_value = profile
    db = MagicMock()
    db.get = AsyncMock(return_value=user)
    db.execute = AsyncMock(return_value=result)

    class _Ctx:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *a):
            return False

    return lambda: _Ctx()


async def test_push_does_nothing_when_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "MATCH_SERVICE_URL", "")
    monkeypatch.setattr(match_sync, "AsyncSessionLocal", MagicMock(side_effect=AssertionError("must not open the DB")))
    assert await match_sync.push_solver_to_match(SID) is False


@pytest.mark.parametrize("url,key", [("http://x", ""), ("", "k")])
def test_sync_needs_both_settings(monkeypatch, url, key):
    monkeypatch.setattr(settings, "MATCH_SERVICE_URL", url)
    monkeypatch.setattr(settings, "MATCH_INTERNAL_API_KEY", key)
    assert match_sync.sync_enabled() is False


async def test_push_loads_fresh_data_and_sends(wire, monkeypatch):
    rec = wire(OK)
    monkeypatch.setattr(match_sync, "AsyncSessionLocal", _fake_session(_user(), _profile()))
    assert await match_sync.push_solver_to_match(SID) is True
    import json

    assert json.loads(rec.requests[0].content)["verified"] is True


@pytest.mark.parametrize("user,profile", [(None, _profile()), (_user(role=UserRole.CUSTOMER), _profile()), (_user(), None)])
async def test_push_skips_missing_non_solver_and_profileless_users(wire, monkeypatch, user, profile):
    rec = wire(OK)
    monkeypatch.setattr(match_sync, "AsyncSessionLocal", _fake_session(user, profile))
    assert await match_sync.push_solver_to_match(SID) is False
    assert rec.requests == []


async def test_push_never_raises(wire, monkeypatch):
    wire(OK)
    monkeypatch.setattr(match_sync, "AsyncSessionLocal", MagicMock(side_effect=RuntimeError("db exploded")))
    assert await match_sync.push_solver_to_match(SID) is False


# ---------- the hooks: a push is scheduled after each status-changing action ----------

@pytest.fixture
def api(monkeypatch):
    limiter.enabled = False
    pushed = AsyncMock()
    monkeypatch.setattr(admin_module, "push_solver_to_match", pushed)
    monkeypatch.setattr(profile_module, "push_solver_to_match", pushed)
    monkeypatch.setattr(admin_module, "send_review_result_email", lambda *a, **k: None)
    monkeypatch.setattr(admin_module, "send_account_status_email", lambda *a, **k: None)

    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()

    async def fake_db():
        yield db

    admin = SimpleNamespace(id=uuid.uuid4(), role=UserRole.ADMIN, full_name="Admin", email="a@example.com")
    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_current_admin] = lambda: admin
    client = TestClient(app, cookies=COOKIES)
    client.db, client.pushed = db, pushed
    yield client
    app.dependency_overrides.clear()


def _results(db, *values):
    outs = []
    for v in values:
        r = MagicMock()
        r.scalar_one_or_none.return_value = v
        outs.append(r)
    db.execute.side_effect = outs


def test_approve_schedules_a_push_after_commit(api):
    target = SimpleNamespace(id=SID, email="s@example.com", full_name="S", account_status=AccountStatus.PENDING_REVIEW)
    kyc = SimpleNamespace()
    _results(api.db, target, kyc)
    resp = api.patch(f"/api/v1/auth/user/{SID}/review", json={"action": "approve"}, headers=CSRF)
    assert resp.status_code == 200, resp.text
    assert target.account_status == AccountStatus.ACTIVE
    api.pushed.assert_awaited_once_with(SID)


def test_reject_also_pushes(api):
    target = SimpleNamespace(id=SID, email="s@example.com", full_name="S", account_status=AccountStatus.PENDING_REVIEW)
    _results(api.db, target, SimpleNamespace())
    resp = api.patch(f"/api/v1/auth/user/{SID}/review", json={"action": "reject", "rejection_reason": "blurry"}, headers=CSRF)
    assert resp.status_code == 200, resp.text
    api.pushed.assert_awaited_once_with(SID)


@pytest.mark.parametrize("action,new_status", [("suspend", AccountStatus.SUSPENDED), ("ban", AccountStatus.BANNED)])
def test_suspend_and_ban_push(api, action, new_status):
    target = SimpleNamespace(
        id=SID, role=UserRole.SOLVER, email="s@example.com", full_name="S", account_status=AccountStatus.ACTIVE,
        previous_status=None, status_reason=None, status_changed_at=None,
    )
    _results(api.db, target, None)  # user lookup, then the refresh-token revoke UPDATE
    resp = api.patch(f"/api/v1/auth/user/{SID}/{action}", json={"reason": "breach of terms of service"}, headers=CSRF)
    assert resp.status_code == 200, resp.text
    assert target.account_status == new_status
    api.pushed.assert_awaited_once_with(SID)


def test_failed_admin_action_does_not_push(api):
    _results(api.db, None)  # user not found
    resp = api.patch(f"/api/v1/auth/user/{SID}/suspend", json={"reason": "breach of terms of service"}, headers=CSRF)
    assert resp.status_code == 404
    api.pushed.assert_not_awaited()


def test_activate_pushes(api):
    target = SimpleNamespace(
        id=SID, role=UserRole.SOLVER, email="s@example.com", full_name="S", account_status=AccountStatus.SUSPENDED,
        previous_status=AccountStatus.ACTIVE, status_reason="x", status_changed_at=None,
    )
    _results(api.db, target)
    resp = api.patch(f"/api/v1/auth/user/{SID}/activate", headers=CSRF)
    assert resp.status_code == 200, resp.text
    api.pushed.assert_awaited_once_with(SID)


def test_profile_edit_pushes_the_pending_review_state(api):
    user = SimpleNamespace(id=SID, account_status=AccountStatus.ACTIVE, full_name="S", phone_number=None)
    app.dependency_overrides[get_current_user] = lambda: user
    profile = SimpleNamespace(state="Lagos")
    _results(api.db, profile, None)  # profile, no KYC row
    resp = api.patch("/api/v1/auth/profile", json={"state": "Abuja"}, headers=CSRF)
    assert resp.status_code == 200, resp.text
    assert user.account_status == AccountStatus.PENDING_REVIEW
    api.pushed.assert_awaited_once_with(SID)


def test_rejected_profile_edit_does_not_push(api):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=SID, account_status=AccountStatus.ACTIVE)
    _results(api.db, SimpleNamespace(category="Plumber"), None)
    resp = api.patch("/api/v1/auth/profile", json={"category": "Astronaut"}, headers=CSRF)
    assert resp.status_code == 400
    api.pushed.assert_not_awaited()
