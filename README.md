# django-otp-admin

A drop-in Django admin site that replaces the default username/password login with a **two-step email OTP flow**.  
All OTP state is stored in Redis via Django's cache framework — no extra database table required.  
Works with plain Django admin and optionally with [Unfold](https://github.com/unfoldadmin/django-unfold).

---

## Login flow

```
/admin/
  │
  ▼
GET  /admin/login/       →  Enter email address
POST /admin/login/       →  OTP sent to email
  │
  ▼
GET  /admin/verify-otp/  →  Enter 6-digit code
POST /admin/verify-otp/  →  Code verified
  │
  ▼
login(request, user)     →  Normal Django admin session ✅
```

---

## Features

- 🔐 **Two-step login** — email address then OTP code
- ⚡ **Redis-backed** — OTPs stored with automatic TTL expiry, no DB migrations
- 🔄 **Auto-mirroring** — all models registered on `admin.site` appear automatically
- 🎨 **Unfold-compatible** — inherits Unfold's admin site when installed, falls back gracefully
- 🛡️ **Security-first**:
  - Replay-attack prevention (OTP keys deleted on first use)
  - Session-fixation prevention (Django's `login()` rotates session key)
  - User enumeration protection (generic error for unknown emails)
  - Rate-limiting (one OTP request per email per 60 seconds)
- 📧 **Graceful mail errors** — mail server failures show a friendly message instead of a 500

---

## Requirements

| Dependency    | Version  |
|---------------|----------|
| Python        | ≥ 3.6    |
| Django        | ≥ 2.2    |
| django-redis  | ≥ 4.9    |
| django-unfold | optional |

---

## Installation

```bash
pip install django-otp-admin

# With Unfold support
pip install django-otp-admin[unfold]
```

---

## Quick start

### 1. `settings.py`

```python
INSTALLED_APPS = [
    "unfold",                        # optional — must precede django.contrib.admin
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "django_otp_admin",              # after django.contrib.admin
    # ... your apps
]

# Redis cache (required for OTP storage)
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://127.0.0.1:6379/1",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    }
}

# Email backend
EMAIL_BACKEND   = "django.core.mail.backends.smtp.EmailBackend"
DEFAULT_FROM_EMAIL = "no-reply@yourdomain.com"
```

### 2. `urls.py`

```python
from django_otp_admin.site import otp_admin_site   # replaces: from django.contrib import admin

urlpatterns = [
    path("admin/", otp_admin_site.urls),            # replaces: admin.site.urls
    # ...
]
```

### 3. `yourapp/admin.py`

No changes needed. Standard `@admin.register()` works as-is:

```python
from django.contrib import admin
from .models import MyModel

@admin.register(MyModel)              # no site= argument required
class MyModelAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
```

The package mirrors everything from `admin.site` automatically, including Django's built-in `User`, `Group`, and any third-party models.

If you need a model to appear **only** on this site (not on `admin.site`), use the explicit form:

```python
from django_otp_admin.site import otp_admin_site

@admin.register(MyModel, site=otp_admin_site)
class MyModelAdmin(admin.ModelAdmin):
    ...
```

---

## Configuration

All settings are optional. Override in `settings.py`:

| Setting                 | Type  | Default    | Description                                      |
|-------------------------|-------|------------|--------------------------------------------------|
| `OTP_ADMIN_TTL`         | `int` | `300`      | OTP lifetime in seconds                          |
| `OTP_ADMIN_COOLDOWN`    | `int` | `60`       | Min seconds between OTP requests per email       |
| `OTP_ADMIN_SITE_NAME`   | `str` | `"Admin"`  | Prefix used in the OTP email subject line        |

Example:

```python
OTP_ADMIN_TTL       = 600    # 10 minutes
OTP_ADMIN_COOLDOWN  = 120    # 2 minutes between requests
OTP_ADMIN_SITE_NAME = "Acme Corp"
```

---

## INSTALLED_APPS order

The order matters:

```python
INSTALLED_APPS = [
    "unfold",                  # 1. Unfold must precede django.contrib.admin
    "django.contrib.admin",    # 2. Django admin
    ...
    "django_otp_admin",        # 3. This package — after django.contrib.admin
    "yourapp",                 # 4. Your apps — last
]
```

---

## Running the tests

```bash
pip install -e ".[dev]"
pytest --ds=tests.settings
```

---

## Security notes

| Concern                 | Mitigation                                                                 |
|-------------------------|----------------------------------------------------------------------------|
| Replay attacks          | OTP key is deleted from Redis immediately after the first successful use   |
| Session fixation        | Django's `login()` rotates the session key on authentication               |
| User enumeration        | Unknown emails receive the same generic response as known emails           |
| OTP brute-force         | Codes expire after `OTP_ADMIN_TTL` seconds; rate-limited per email         |
| Mail server downtime    | Caught and surfaced as a user-friendly message; no 500 errors              |

---

## Project structure

```
django_otp_admin/
├── __init__.py          # version, public API surface
├── apps.py              # AppConfig
├── site.py              # OTPAdminSite — the main class + singleton
├── forms.py             # AdminEmailForm, AdminOTPForm
├── utils.py             # generate_otp, is_valid_otp, send_admin_otp
└── templates/
    └── admin/
        ├── email_login.html
        └── otp_verify.html
```

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-change`
3. Make your changes with tests
4. Run the test suite: `pytest --ds=tests.settings`
5. Open a pull request

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

---

## License

[MIT](LICENSE)
