# decky-solver-auth — SolveMart Solver Auth & Admin API

## Working agreement
- Act as a senior FastAPI engineer + DevOps engineer. The owner is a Senior DevOps Engineer (k8s/k3s, Docker, GitHub Actions) and comfortable with Django/Spring Boot, newer to FastAPI/React/Tailwind.
- Be concise: give the solution or the necessary point, no filler.
- If a request doesn't fit production best practice, propose the standard approach and ASK before applying. If it already fits, just do it.
- Flag design decisions and trade-offs before building anything with security or schema impact.
- Deployment (k3s manifests, kustomize, GitHub Actions workflow, Ingress, ConfigMap) is the owner's domain. Never assume those files; ask to see them.
- Code must pass the pipeline gates (SonarQube etc.). Target 80% test coverage (zero tests exist yet).

## Stack
FastAPI, async SQLAlchemy 2.0 + asyncpg, PostgreSQL, Alembic, Pydantic v2 / pydantic-settings, argon2 (passlib), JWT (python-jose), Mailjet (email), AWS S3 (boto3), google-auth. Docker multi-stage (venv, non-root user). Runs on k3s (EC2), 2 replicas.

## Layout
app/{core,db,models,schemas,api/v1/endpoints,services}, alembic/, tests/ (empty)
- core: config.py (Settings), security.py, cookies.py, exception_handlers.py
- api/deps.py: get_current_user (rejects BANNED), get_current_admin, ensure_not_suspended
- services: email.py, otp_service.py, session_service.py (issue_login_session), storage.py (S3), google_auth.py, activity_log_service.py
- endpoints: auth.py, registration.py, profile.py, admin.py (all routers prefixed /auth, mounted at /api/v1)

## Database
- users: id, email (unique), google_id (unique, nullable), full_name, hashed_password (nullable for Google-only), phone_number (unique, nullable), role, account_status, status_reason, status_changed_at, previous_status (status before suspend/ban, restored on activate), created_at, updated_at
- otps: user_id, code_hash (argon2), purpose, expires_at, is_used, attempts
- solver_profiles: user_id (unique), profile_image_key, contact_address, shop_address?, state, nationality, category, description?, skills[]?, latitude, longitude, radius_km, working_experience, availability?, pricing_guidance?, response_time?, bank_name?, acct_num?, acct_name?
- kyc_documents: user_id (unique), id_document_key, selfie_key, review_status, reviewed_by, reviewed_at, rejection_reason
- refresh_tokens: user_id, family_id, token_hash (SHA-256), is_revoked, expires_at
- activity_logs: actor_id, target_user_id, action, description, created_at

Enum rules (important):
- All native Postgres enums store the Python member NAMES in UPPERCASE (user_role, account_status, otp_purpose, kyc_review_status, activity_action).
- account_status contains stray lowercase 'suspended'/'banned' (from my early mistake). They are unused and harmless. Postgres can't drop enum values.
- BEFORE writing any enum-extending migration, run: SELECT unnest(enum_range(NULL::<enum>)); and match the casing.
- Alembic doesn't detect new enum values in autogenerate: write those migrations by hand with ALTER TYPE ... ADD VALUE IF NOT EXISTS.
- All datetime columns are now TIMESTAMP WITH TIME ZONE. Always use datetime.now(timezone.utc). Never use utcnow() or naive datetimes.

Migration head: f4e6f0a54670. History includes one empty no-op migration (4192475b1cfa). It's harmless and live, so leave it.
Rule: run `alembic upgrade head` immediately after every `alembic revision`. Check the DB name in DATABASE_URL (live DB is decky_auth_db).

## Account status state machine
pending_email_verification → (OTP verified) → profile_incomplete → (complete-registration) → pending_review → admin approve → active | admin reject → rejected → (solver edits profile/files) → pending_review
active/rejected/pending_review → suspended (read-only: profile PATCH endpoints return 403 with reason) or banned (login blocked, get_current_user rejects, refresh tokens revoked) → admin activate → active
Admins skip KYC: create-admin → verify-email → active.
Google solvers skip OTP: land on profile_incomplete.

## Endpoints (/api/v1/auth)
Public/auth: POST /register, /verify-email (auto-login), /resend-verification-code, /login, /google (solver-only), /refresh (rotating + reuse detection), /logout, /forgot-password (enumeration-safe), /reset-password (revokes all sessions); GET /user
Registration: POST /complete-registration (multipart: text fields + profile_image, id_document, selfie; requires status profile_incomplete)
Profile (solver): GET /profile, PATCH /profile (JSON, resets status → pending_review and stale KYC rejection), PATCH /profile/files (multipart, deletes old S3 objects after commit)
Admin (get_current_admin): POST /admin/create-admin, POST /admin/login (rejects non-admin), GET /admin/solvers (page/limit/status filter, default pending_review), GET /admin/overview (total_solvers, pending_kyc, active_solvers + this-week deltas), GET /admin/activity-log (paginated), GET /user/{id}, PATCH /user/{id}/review (approve|reject, email), PATCH /user/{id}/suspend, /ban (reason required), /activate (undo suspend/ban)
All admin actions write an activity_logs row in the same transaction.

## Key decisions
- Auth = httpOnly cookies only (access_token 15m path /; refresh_token 7d path /api/v1/auth). No Bearer headers. Frontend must send credentials: "include".
- Cookie attrs are env-driven: COOKIE_SECURE, COOKIE_SAMESITE, COOKIE_DOMAIN. clear_auth_cookies must reuse the exact same attrs as set_auth_cookies (otherwise browsers ignore the delete).
  - Prod: Secure=True, SameSite=none (frontend devs test from localhost), Domain=.deckymart.com
  - Local: Secure=False, SameSite=lax, Domain= (EMPTY, or the cookie is dropped on localhost)
- CORS: explicit allowlist from FRONTEND_ORIGINS (comma-separated: localhost:3000, localhost:5173, app.deckymart.com, admin.deckymart.com), allow_credentials=True.
- Files: server-side upload to S3. profile_image is public-read (bucket policy on profile-images/ only); id_document/selfie private, presigned GET (15m), admin-only. Caps: 5MB / 5MB / 15MB, JPG/PNG only. Ingress proxy-body-size is 30m.
- Hashing: argon2 for passwords/OTPs; SHA-256 for refresh tokens (fast lookup, high entropy).
- Google: frontend gets an ID token (Google Identity Services) → POST /auth/google → backend verifies via google-auth against GOOGLE_CLIENT_ID (public, no secret). Existing solver email → auto-link; admin/customer email → 403; banned → 403. Google-only accounts get a specific message on /login and /register. A Google user can set a password via forgot/reset (no "old password" field exists).
- Global exception handlers: validation handler strips raw `input` (fixed a crash on binary bodies); catch-all logs traceback and returns a generic 500.
- Location = lat/lng floats + radius_km (no PostGIS yet).

## Config / deployment facts
- Settings fields (all required unless noted): PROJECT_NAME, ENVIRONMENT, LOG_LEVEL (default INFO), DATABASE_URL, REDIS_URL, JWT_SECRET_KEY, JWT_ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_DAYS, REGISTRATION_TOKEN_EXPIRE_MINUTES (unused), CUSTOMER_TOKEN_SIGNING_KEY (verify-only, signs the customer service's cust_access tokens), RESEND_API_KEY/RESEND_SENDER_EMAIL, AWS_ACCESS_KEY_ID/SECRET_ACCESS_KEY/REGION/S3_BUCKET, AWS_S3_PUBLIC_BASE_URL, OTP_EXPIRE_MINUTES, OTP_MAX_ATTEMPTS, OTP_RESEND_COOLDOWN_SECONDS, MAX_PROFILE_IMAGE_SIZE_MB, MAX_ID_DOCUMENT_SIZE_MB, MAX_SELFIE_SIZE_MB, MAX_POST_IMAGE_SIZE_MB, MAX_POST_VIDEO_SIZE_MB, MAX_POST_MEDIA_ITEMS, FRONTEND_ORIGINS, COOKIE_DOMAIN, COOKIE_SECURE, COOKIE_SAMESITE, GOOGLE_CLIENT_ID
- LESSON (bit us twice): any new required Settings field must be added to the live ConfigMap/Secret BEFORE deploy, or pods crash-loop on pydantic ValidationError.
- Email provider is Resend (not Mailjet — migrated). `app/services/email.py` calls Resend's REST API directly via `requests`, no SDK dependency.
- Deployment moved out of this repo: manifests used to live in this repo's `k8s/` (kustomize), deployed via `.github/workflows/deploy.yml` calling a reusable workflow in `DeckyMart/deploy-workflows`. That path is now disabled (`deploy.yml` renamed to `deploy.yml.disabled`, reversible) and `k8s/` is deleted. Manifests now live in the separate `DeckyMart/deployment` repo, under `solver-auth/` (flat YAML files: namespace, configmap, deployment, service, ingress — no kustomize), applied by `.github/workflows/solver-auth-pipeline.yaml` in that repo via a `detect.py` script that only applies changed/unhealthy manifests. That pipeline also syncs GitHub Actions secrets (DATABASE_URL, JWT_SECRET_KEY, RESEND_API_KEY, AWS keys, REDIS_URL, CUSTOMER_TOKEN_SIGNING_KEY) into the `solver-auth-secrets` k8s Secret on every run — keep that list in sync with Settings or the same crash-loop lesson above applies. Non-secret config lives in that repo's `solver-auth/configmap.yaml` now, not a ConfigMap in this repo.
- TLS cert for api.deckymart.com is auto-created by cert-manager's ingress-shim from the Ingress's `cert-manager.io/cluster-issuer` annotation alone — don't add a separate explicit `Certificate` resource pointing at the same secretName, cert-manager won't let two Certificates own one secret and the second one just sits at READY=False.
- Domains: api.deckymart.com (live), app.deckymart.com, admin.deckymart.com (DNS A record still needed). TLS via cert-manager/Let's Encrypt.
- Don't bake `alembic upgrade head` into the container CMD. Use a k8s Job/initContainer.

## Security: CSRF + rate limiting (built)
- CSRF: double-submit cookie. `app/core/csrf.py` issues `csrf_token` (non-httpOnly) and checks it against the `X-CSRF-Token` header on every write endpoint across auth, profile, admin, posts, comments, reactions, and notifications. `GET /api/v1/csrf` mints the cookie for actors who never hit our own `/login` (i.e. customers, authenticated via `get_current_actor`) — solver/admin get it automatically at login.
- Rate limiting: slowapi + Redis (`app/core/limiter.py`, `REDIS_URL` in Settings — needed since 2 replicas make in-memory limits wrong). Limits: login/admin-login 5/min; register, resend-code, forgot-password 3/hr; reset-password 5/hr; verify-email 10/hr; post creation 10/hr; comments 30/hr; reactions 60/min.
- Gotcha: slowapi's `@limiter.limit(...)` needs a `response: Response` param on the decorated endpoint, or it 500s on any *successful* (non-exception) response trying to inject rate-limit headers — easy to miss since 401/429 failure paths never hit that code.

## Known gaps / backlog (priority order)
1. SECURITY: /auth/google links to an existing solver account even if it is still pending_email_verification with a password someone else set (account pre-hijack). Fix: on linking an unverified account, null its password and move it to profile_incomplete.
2. activate_solver always sets ACTIVE, so a solver suspended before KYC approval would bypass review. Store/restore the prior status or re-check KYC.
3. acct_num stored plaintext → app-level Fernet encryption (key from env/secret; KMS later).
4. Zero tests (pytest, pytest-asyncio, httpx; 80% coverage target); no SonarQube step confirmed in pipeline.
5. File content-type is client-declared only (add magic-byte check); boto3 put_object blocks the event loop (use threadpool/aioboto3 at scale).
6. Email enumeration remains on /register, /verify-email, /resend-verification-code (owner chose to harden only /forgot-password).
7. Google OAuth consent screen is still in Testing mode, so Publish before real users.
8. Dead code: registration-token remnants (REGISTRATION_TOKEN_EXPIRE_MINUTES), EMAIL_VERIFIED/PROFILE_INCOMPLETE enum notes, stray lowercase enum values.
9. Customer registration flow: customer-kyc-auth exists and is integrated (comments/reactions resolve customer identity via their cust_access JWT, shared-secret HS256 verify-only — see CUSTOMER_TOKEN_SIGNING_KEY above). Still shared-secret, not yet migrated to their planned RS256/JWKS. Customer display name/avatar on comments is a snapshot taken at comment-creation time (from the JWT), not live — no lookup endpoint exists on their side to refresh it later.

## Frontend contract notes (React, separate devs)
- Always credentials: "include" / withCredentials: true.
- Google button must be on BOTH login and register pages (Google-only users have no password).
- Route by account_status: profile_incomplete → finish registration; pending_review → under review; active → dashboard; suspended → dashboard + banner (reason from GET /profile); banned → 403 with reason.
- Image URLs: profile_image_url is permanent; id_document_url/selfie_url (admin only) expire in 15 min. Never cache them.