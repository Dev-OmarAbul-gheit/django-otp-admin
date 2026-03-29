# Changelog

All notable changes to `django-otp-admin` will be documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.0] — Unreleased

### Added
- `OTPAdminSite` — drop-in replacement for Django's default `AdminSite`
- Two-step email OTP login flow (`/admin/login/` → `/admin/verify-otp/`)
- Redis-backed OTP storage via Django's cache framework (no extra DB table)
- Automatic mirroring of all models registered on `admin.site`
- Optional [Unfold](https://github.com/unfoldadmin/django-unfold) UI support (graceful fallback to plain Django admin)
- Rate-limiting: one OTP request per email per 60 seconds (`OTP_ADMIN_COOLDOWN`)
- Configurable OTP TTL (`OTP_ADMIN_TTL`, default 300 s)
- `@never_cache` on login views to prevent browser caching
- Replay-attack prevention: OTP keys are deleted on first successful use
- Session-fixation prevention via Django's `login()` session key rotation
- User enumeration protection: generic error message for unknown emails
- Graceful mail-server error handling with user-facing fallback message
- Matching HTML templates styled to the Unfold purple palette
- Full docstrings and inline comments throughout
- Unit tests for all utility functions
