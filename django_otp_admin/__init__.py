# django_otp_admin/__init__.py
#
# Public API surface for django-otp-admin.
#
# Consumers should import from here rather than from sub-modules so that
# internal refactors never break their import paths:
#
#   from django_otp_admin import OTPAdminSite, otp_admin_site

# Intentionally empty at module level to avoid importing Django internals
# before django.setup() has been called (which would raise AppRegistryNotReady).
#
# Safe import points:
#   - urls.py         (always imported after django.setup())
#   - admin.py        (imported during autodiscover, after setup)
#   - Inside methods  (called at request time)
#
# Example:
#   # urls.py
#   from django_otp_admin.site import otp_admin_site
#   path("admin/", otp_admin_site.urls),

__version__ = "1.0.2"
__all__ = ["__version__"]
