import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.api.v1.endpoints import registration as registration_module
from app.core.categories import CATEGORIES, CATEGORY_ALIASES, normalize, resolve_category
from app.core.limiter import limiter
from app.db.session import get_db
from app.main import app
from app.models.user import AccountStatus, UserRole
from app.services.storage import FileValidationError

CSRF = {"X-CSRF-Token": "tok"}
COOKIES = {"csrf_token": "tok"}

# The dropdown the customer wizard showed on dev.deckymart.com, in order.
WIZARD = [
    "Vulcanizer", "Auto Electrician", "Auto Mechanic", "Plumber", "Home Cabinet", "House Electrician",
    "Laundry Service", "Tilers Service", "Event Planning", "Air-Conditioner Repair", "Fashion Designer",
    "Hair Stylist", "Fridge Repair", "POP Service", "Washing Machine Repair Service",
]


# ---------- the list and the matching ----------

def test_official_list_matches_the_wizard_dropdown():
    assert [c.name for c in CATEGORIES] == WIZARD
    assert len({c.slug for c in CATEGORIES}) == len({c.name for c in CATEGORIES}) == 15


def test_aliases_point_at_real_slugs():
    assert set(CATEGORY_ALIASES.values()) <= {c.slug for c in CATEGORIES}


@pytest.mark.parametrize(
    "text,slug",
    [
        ("Plumber", "plumber"), ("plumber ", "plumber"), ("  PLUMBER", "plumber"),
        ("auto electrician", "auto-electrician"), ("Auto-Electrician", "auto-electrician"),
        ("auto_electrician", "auto-electrician"), ("Automobile Electrician", "auto-electrician"),
        ("Air-Conditioner Repair", "air-conditioner-repair"), ("air conditioner repair", "air-conditioner-repair"),
        ("POP service", "pop-service"),
    ],
)
def test_resolve_category(text, slug):
    assert resolve_category(text).slug == slug


@pytest.mark.parametrize("text", [None, "", "  ", "Plumbing", "Electrician", "Astronaut", "Logo Design"])
def test_resolve_category_unknown(text):
    assert resolve_category(text) is None


def test_every_official_name_and_slug_resolves_to_itself():
    for c in CATEGORIES:
        assert resolve_category(c.name) == c
        assert resolve_category(c.slug) == c


def test_normalize():
    assert normalize("  Air-Conditioner_Repair ") == "air conditioner repair"


# ---------- fixtures ----------

@pytest.fixture
def db():
    limiter.enabled = False  # the limiter's Redis isn't available in unit tests
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()

    async def fake_db():
        yield db

    app.dependency_overrides[get_db] = fake_db
    yield db
    app.dependency_overrides.clear()


def _user(status=AccountStatus.ACTIVE):
    return SimpleNamespace(id=uuid.uuid4(), account_status=status, full_name="Jane", phone_number=None)


# ---------- public endpoints ----------

def test_all_categories_for_registration_public_and_cacheable(db):
    resp = TestClient(app).get("/api/v1/auth/categories/all")
    assert resp.status_code == 200
    assert [i["name"] for i in resp.json()["items"]] == WIZARD
    assert resp.json()["items"][3] == {"slug": "plumber", "name": "Plumber"}
    assert "max-age" in resp.headers["cache-control"]


def _labels(db, labels):
    result = MagicMock()
    result.scalars.return_value.all.return_value = labels
    db.execute.return_value = result


def test_available_folds_legacy_text_dedupes_and_keeps_dropdown_order(db):
    _labels(db, ["plumber ", "Plumber", "Automobile Electrician", "Vulcanizer", "Astronaut", "Logo Design"])
    resp = TestClient(app).get("/api/v1/auth/categories")
    assert resp.status_code == 200
    assert [i["name"] for i in resp.json()["items"]] == ["Vulcanizer", "Auto Electrician", "Plumber"]


def test_available_is_empty_when_no_active_solver(db):
    _labels(db, [])
    assert TestClient(app).get("/api/v1/auth/categories").json() == {"items": []}


def test_available_only_counts_active_solvers(db):
    _labels(db, [])
    TestClient(app).get("/api/v1/auth/categories")
    stmt = db.execute.await_args.args[0]
    compiled = stmt.compile()
    sql = str(compiled)
    assert "users.account_status =" in sql and "users.role =" in sql and "DISTINCT" in sql
    assert AccountStatus.ACTIVE in compiled.params.values()
    assert UserRole.SOLVER in compiled.params.values()


# ---------- registration / profile validation ----------

def _registration_form(category):
    return {
        "phone_number": "08012345678", "contact_address": "1 Test St", "state": "Lagos", "nationality": "Nigerian",
        "category": category, "working_experience": "5 years", "latitude": "6.5", "longitude": "3.3", "radius_km": "10",
    }


def _files():
    return {k: (f"{k}.png", b"x", "image/png") for k in ("profile_image", "id_document", "selfie")}


@pytest.fixture
def uploads(monkeypatch):
    calls = []

    async def fake_upload(*args, **kwargs):
        calls.append(args)
        raise FileValidationError("stop here")  # proves the request got past the category check

    monkeypatch.setattr(registration_module, "validate_and_upload", fake_upload)
    return calls


def test_registration_rejects_unknown_category_before_uploading_anything(db, uploads):
    app.dependency_overrides[get_current_user] = lambda: _user(AccountStatus.PROFILE_INCOMPLETE)
    resp = TestClient(app, cookies=COOKIES).post(
        "/api/v1/auth/complete-registration", data=_registration_form("Astronaut"), files=_files(), headers=CSRF
    )
    assert resp.status_code == 400
    assert "Unknown category" in resp.json()["detail"]
    assert uploads == []  # nothing was sent to S3


def test_registration_accepts_a_legacy_spelling_and_moves_on(db, uploads):
    app.dependency_overrides[get_current_user] = lambda: _user(AccountStatus.PROFILE_INCOMPLETE)
    resp = TestClient(app, cookies=COOKIES).post(
        "/api/v1/auth/complete-registration",
        data=_registration_form("automobile electrician"), files=_files(), headers=CSRF,
    )
    assert resp.status_code == 400 and resp.json()["detail"] == "stop here"  # got to the upload step
    assert len(uploads) == 1


def _profile_db(db, profile):
    first, second = MagicMock(), MagicMock()
    first.scalar_one_or_none.return_value = profile
    second.scalar_one_or_none.return_value = None  # no KYC row
    db.execute.side_effect = [first, second]


def test_profile_update_rejects_unknown_category(db):
    app.dependency_overrides[get_current_user] = lambda: _user()
    profile = SimpleNamespace(category="Plumber")
    _profile_db(db, profile)
    resp = TestClient(app, cookies=COOKIES).patch("/api/v1/auth/profile", json={"category": "Astronaut"}, headers=CSRF)
    assert resp.status_code == 400
    assert profile.category == "Plumber"
    db.commit.assert_not_called()


def test_profile_update_stores_the_official_name(db):
    user = _user()
    app.dependency_overrides[get_current_user] = lambda: user
    profile = SimpleNamespace(category="Vulcanizer")
    _profile_db(db, profile)
    resp = TestClient(app, cookies=COOKIES).patch("/api/v1/auth/profile", json={"category": "air conditioner repair"}, headers=CSRF)
    assert resp.status_code == 200
    assert profile.category == "Air-Conditioner Repair"
    db.commit.assert_awaited_once()


def test_profile_update_without_category_leaves_it_alone(db):
    app.dependency_overrides[get_current_user] = lambda: _user()
    profile = SimpleNamespace(category="Plumber", state="Lagos")
    _profile_db(db, profile)
    resp = TestClient(app, cookies=COOKIES).patch("/api/v1/auth/profile", json={"state": "Abuja"}, headers=CSRF)
    assert resp.status_code == 200
    assert (profile.category, profile.state) == ("Plumber", "Abuja")


def test_profile_category_cannot_be_cleared(db):
    app.dependency_overrides[get_current_user] = lambda: _user()
    _profile_db(db, SimpleNamespace(category="Plumber"))
    resp = TestClient(app, cookies=COOKIES).patch("/api/v1/auth/profile", json={"category": None}, headers=CSRF)
    assert resp.status_code == 400
