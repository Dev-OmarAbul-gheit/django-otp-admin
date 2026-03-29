# django_otp_admin/apps.py
#
# AppConfig for django-otp-admin.
#
# Add to INSTALLED_APPS *after* django.contrib.admin:
#
#   INSTALLED_APPS = [
#       "unfold",                    # if used — must be before django.contrib.admin
#       "django.contrib.admin",
#       ...
#       "django_otp_admin",          # after django.contrib.admin
#   ]

from django.apps import AppConfig


class DjangoOtpAdminConfig(AppConfig):
    """
    AppConfig for the django-otp-admin package.

    Deliberately performs no work in ready() — the model mirror is
    triggered lazily from OTPAdminSite.get_urls() instead, which is
    the only reliable hook that fires after autodiscover() has fully
    populated admin.site._registry.
    """

    name         = "django_otp_admin"
    verbose_name = "OTP Admin"

    def ready(self):
        """
        Called by Django once all apps are loaded.

        No mirroring is done here because at this point autodiscover()
        may not have run yet for all apps, leaving admin.site._registry
        partially populated.  The mirror runs in get_urls() instead.
        """
        pass
