# Deployment Verification — Checklist and Status

**Status: UNVERIFIED.** No production deployment has been exercised. Everything in this
document is either a local static/code check (already automated and passing) or a step that
**must be run against the real environment** before production security may be claimed.

The API's own startup gate refuses to boot in `APP_ENV=production` when the JWT secret is
missing, short or a known placeholder, when CORS is empty or wildcarded, or when MQTT broker
credentials are absent without an explicit anonymous opt-in. Passing that gate locally does not
verify the deployment.

---

## 1. Local checks (automated, run before every deploy)

```bash
cd backend

# Static PASS/FAIL/REVIEW checklist. Exit code 1 on any FAIL.
# Requires the PRODUCTION environment variables to be loaded; against a
# development .env it intentionally reports FAILs.
python scripts/verify_production_config.py

# The same checks, pinned by tests (including MQTT, TLS, ingestion bounds,
# public URL and a git scan for tracked secret files).
python -m pytest tests/test_production_config.py tests/test_security_hardening.py -v
```

Checks implemented:

| Check | Where |
|---|---|
| `APP_ENV` is production-like | `scripts/verify_production_config.py` |
| JWT secret present, ≥ 32 chars, not a known placeholder | `app/core/config.py::validate_security`, `verify_production_config.py` |
| CORS allowlist explicit, no wildcard, HTTPS origins reviewed | `app/core/config.py::resolve_cors`, `verify_production_config.py` |
| Login, registration and device activation rate limits enabled | `app/core/rate_limit.py`, `verify_production_config.py` |
| MQTT username/password required; anonymous explicitly rejected | `app/core/config.py::validate_security`, `verify_production_config.py` |
| TLS required for any non-loopback broker | `verify_production_config.py` |
| `PUBLIC_BASE_URL` is an HTTPS origin before QR codes are printed | `verify_production_config.py` |
| Ingestion upper bounds finite (TDS ≤ 50 000 ppm, NTU ≤ 4 000, index ≤ 100) | `app/services/mqtt_service.py`, `verify_production_config.py` |
| No real `.env` / `config.h` tracked by git | `verify_production_config.py` (`git ls-files`) |
| Token lifetime ≤ 480 min | `verify_production_config.py` |

## 2. Real-environment checklist (still to be executed)

Record the date, environment name and operator beside each item. Do not mark an item done
because the configuration *looks* correct — observe the behaviour.

| # | Check | How to verify | Status |
|---|---|---|---|
| 1 | Secret manager supplies `JWT_SECRET_KEY` and `MQTT_PASSWORD`; neither is in git, logs, error pages or the OpenAPI schema | Search the deployed logs and `docker inspect`/process environment; open `/docs` | ☐ Not run |
| 2 | API boots with `APP_ENV=production` and exits non-zero when the secret or MQTT credentials are removed | Start with a deliberately broken env in a disposable container | ☐ Not run |
| 3 | `alembic upgrade head` applied; `alembic current` = `head` | Run against the production database | ☐ Not run |
| 4 | CORS allows only the real frontend origin and returns no `Access-Control-Allow-Origin` for an arbitrary origin | Real browser + `curl -H "Origin: https://evil.example"` | ☐ Not run |
| 5 | Login → authenticated authority call → product-user 403 → unauthenticated 401 | Real host, real tokens | ☐ Not run |
| 6 | Login, registration and device activation return **429 + Retry-After** after their configured limits | Scripted requests against the real host | ☐ Not run |
| 7 | MQTT broker refuses anonymous connections and enforces ACLs (devices publish only their own station topic; backend only subscribes) | `mosquitto_sub` without credentials must fail; a second device must not publish another station's topic | ☐ Not run |
| 8 | Broker TLS certificate validates for `MQTT_BROKER_HOST` when the broker is remote | Subscriber logs must show a verified TLS connection; a wrong CA must fail | ☐ Not run |
| 9 | Ingestion bounds reject implausible payloads on the live broker | Publish TDS > 50 000 / NTU > 4 000 and confirm rejection in logs, no row inserted | ☐ Not run |
| 10 | QR codes encode the real `PUBLIC_BASE_URL` and resolve from a phone off the developer network | Generate one station QR and scan it | ☐ Not run |
| 11 | No password, token, JWT secret or broker password appears in logs or API errors | Grep the deployed logs; trigger 401/422/500 responses | ☐ Not run |
| 12 | Seeded demo credentials are rotated or removed before real users exist | Login with the seeded authority account must fail after rotation | ☐ Not run |
| 13 | Notification e-mail delivery (if SMTP configured) works and never includes secrets | Trigger a real alert for a test account | ☐ Not run |
| 14 | Backups/restore of PostgreSQL verified before data is treated as authoritative | Restore into a disposable database | ☐ Not run |

## 3. Broker configuration reference

`mosquitto.conf` (minimum for a non-anonymous broker):

```conf
allow_anonymous false
password_file /etc/mosquitto/passwd
acl_file      /etc/mosquitto/acl

listener 8883
cafile   /etc/mosquitto/certs/ca.crt
certfile /etc/mosquitto/certs/server.crt
keyfile  /etc/mosquitto/certs/server.key
```

`acl` (per-station publishing, backend read-only):

```conf
user hydrasense-backend
topic read hydrasense/stations/+/telemetry

user device-ark-001
topic write hydrasense/stations/ARK-001/telemetry
```

Create credentials with `mosquitto_passwd -c /etc/mosquitto/passwd hydrasense-backend`.
Set the same username/password in `backend/.env` as `MQTT_USERNAME` / `MQTT_PASSWORD`, set
`MQTT_USE_TLS=true`, and point `MQTT_CA_CERT_PATH` at the CA bundle when it is not in the system
trust store. The firmware's `config.h` holds the device-side credentials and is git-ignored.

## 4. What remains unverified

- Real reverse-proxy behaviour (TLS termination, forwarded headers, HSTS).
- Real frontend build served from the production origin against the production API.
- Real broker ACL enforcement and TLS certificate validation.
- Real rate-limit behaviour under concurrent workers.
- Any claim that production is "secure": it is **not** until every box above is observed.
