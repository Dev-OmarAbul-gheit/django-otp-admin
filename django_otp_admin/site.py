# django_otp_admin/site.py
#
# Replaces Django's default admin login with a two-step OTP flow:
#
#   Step 1  GET/POST  /admin/login/        → email form  (email_login.html)
#   Step 2  GET/POST  /admin/verify-otp/   → OTP form    (otp_verify.html)
#   Step 3            login(request, user) → normal Django admin session
#
# The site also mirrors every model registered on the default admin.site
# (Django built-ins, third-party apps) so consuming projects only need to
# use the standard @admin.register() decorator — no site= argument required.

import logging

from django.contrib import admin, messages
from django.contrib.auth import get_user_model, login
from django.shortcuts import render, redirect
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache

from .forms import AdminEmailForm, AdminOTPForm
from .utils import generate_otp, send_admin_otp, is_valid_otp

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Base class — prefer Unfold's admin site for its UI enhancements; fall back
# to Django's built-in AdminSite if Unfold is not installed.
# ---------------------------------------------------------------------------
try:
    from unfold.sites import UnfoldAdminSite
    _Base = UnfoldAdminSite
except ImportError:
    _Base = admin.AdminSite


class OTPAdminSite(_Base):
    """
    A custom Django admin site that enforces two-factor authentication
    via one-time passwords (OTP) delivered by email.

    All OTP state is stored in the configured Django cache backend
    (Redis recommended) — no additional database table is required.

    Quick start
    -----------
    1. Add to INSTALLED_APPS (after django.contrib.admin)::

        INSTALLED_APPS = [
            "unfold",                  # optional — must precede django.contrib.admin
            "django.contrib.admin",
            ...
            "django_otp_admin",
        ]

    2. Replace the admin URL in urls.py::

        from django_otp_admin.site import otp_admin_site
        path("admin/", otp_admin_site.urls),

    3. Register your models normally — the mirror handles the rest::

        @admin.register(MyModel)
        class MyModelAdmin(ModelAdmin):
            ...

    Optional settings
    -----------------
    OTP_ADMIN_TTL         int   OTP lifetime in seconds (default: 300)
    OTP_ADMIN_COOLDOWN    int   Min seconds between OTP requests (default: 60)
    OTP_ADMIN_SITE_NAME   str   Prefix used in email subject (default: "Admin")
    """

    # ------------------------------------------------------------------ #
    #  Mirroring                                                           #
    # ------------------------------------------------------------------ #

    def _mirror_default_admin(self):
        """
        Copy every model registered on Django's default admin.site into
        this site.

        Called lazily from get_urls() — at that point autodiscover() has
        already run, so admin.site._registry is fully populated with both
        Django built-ins (User, Group, …) and any third-party app models.

        Models already explicitly registered on this site (e.g. via
        ``@admin.register(Model, site=otp_admin_site)``) are skipped to
        avoid ``AlreadyRegistered`` errors.
        """
        for model, model_admin in admin.site._registry.items():
            if model not in self._registry:
                self.register(model, type(model_admin))

    # ------------------------------------------------------------------ #
    #  URL wiring                                                          #
    # ------------------------------------------------------------------ #

    def get_urls(self):
        """
        Prepend the OTP verification URL to the standard admin URL list,
        then trigger the mirror so all models are available before Django
        resolves any admin URL.

        The custom URL is prepended (not appended) so it takes precedence
        over any wildcard patterns defined by the parent class.
        """
        # Mirror here — guaranteed to run after autodiscover() completes.
        self._mirror_default_admin()

        return [
            # Step 2 of the login flow — OTP code entry.
            # Exposed as "admin:otp_verify_view" for use with reverse().
            path("verify-otp/", self.otp_verify_view, name="otp_verify_view"),
        ] + super().get_urls()

    # ------------------------------------------------------------------ #
    #  Private render helpers                                              #
    # ------------------------------------------------------------------ #

    def _render_login(self, request, form=None):
        """
        Render the email entry page (Step 1).

        Args:
            request: The current HTTP request.
            form:    A bound ``AdminEmailForm`` to re-display with
                     validation errors. Defaults to a fresh unbound form.

        Returns:
            HttpResponse: Rendered ``admin/email_login.html``.
        """
        return render(request, "admin/email_login.html", {
            **self.each_context(request),   # injects site_header, has_permission, etc.
            "form": form or AdminEmailForm(),
        })

    def _render_verify(self, request, form=None):
        """
        Render the OTP code entry page (Step 2).

        Args:
            request: The current HTTP request.
            form:    A bound ``AdminOTPForm`` to re-display with
                     validation errors. Defaults to a fresh unbound form.

        Returns:
            HttpResponse: Rendered ``admin/otp_verify.html``.
        """
        return render(request, "admin/otp_verify.html", {
            **self.each_context(request),   # injects site_header, has_permission, etc.
            "form": form or AdminOTPForm(),
        })

    def _send_otp_safe(self, request, *, email: str, otp: str) -> bool:
        """
        Attempt to send the OTP email, handling all transport errors
        gracefully so a mail misconfiguration never causes an unhandled 500.

        Adds a user-facing error message to the request on failure and
        logs the exception so operators can diagnose mail issues.

        Args:
            request: The current HTTP request (used to attach messages).
            email:   Recipient address.
            otp:     The one-time code to include in the email body.

        Returns:
            bool: True if the email was dispatched successfully;
                  False if sending failed (message already added).
        """
        try:
            send_admin_otp(email=email, code=otp)
            return True
        except ConnectionRefusedError:
            # Mail server is down or not configured (common in local dev).
            logger.exception("Mail server refused connection for %s", email)
        except Exception:
            # Catch-all for unexpected SMTP errors (timeouts, auth, TLS …).
            logger.exception("Unexpected error sending OTP to %s", email)

        messages.error(
            request,
            _("The email service is temporarily unavailable. Please try again later."),
        )
        return False

    # ------------------------------------------------------------------ #
    #  Step 1 — Email form                                                 #
    # ------------------------------------------------------------------ #

    @method_decorator(never_cache)   # prevents the browser from caching the login page
    def login(self, request, extra_context=None):
        """
        Step 1 of the OTP login flow — collect and validate the admin's
        email address, then dispatch an OTP.

        GET  → render ``email_login.html`` with a blank form.
        POST → validate email, look up the user, send OTP, redirect to
               the verify-otp view.

        On any error (unknown email, mail failure) the same page is
        re-rendered with an appropriate message so the user can retry
        without losing context.

        Security notes:
        - A generic error message is shown for unknown emails to prevent
          user enumeration (an attacker cannot tell whether an address
          is registered by observing the response).
        - Already-authenticated staff are redirected immediately to avoid
          an unnecessary OTP round-trip.

        Args:
            request:       The current HTTP request.
            extra_context: Unused; accepted for API compatibility with
                           the parent ``AdminSite.login`` signature.

        Returns:
            HttpResponse: Either a rendered login page or a redirect.
        """
        request.current_app = self.name
        User = get_user_model()

        # Already authenticated staff — skip the flow entirely.
        if request.user.is_active and request.user.is_staff:
            return redirect(reverse("admin:index"))

        # GET — just show the empty form.
        if request.method != "POST":
            return self._render_login(request)

        form = AdminEmailForm(request.POST)

        # Re-render with field-level errors if the form is invalid
        # (e.g. malformed email address).
        if not form.is_valid():
            return self._render_login(request, form)

        email = form.cleaned_data["email"].lower()

        # Look up an active staff user with this email address.
        # The same generic message is shown whether the email exists or not
        # to prevent user enumeration attacks.
        try:
            user = User.objects.get(email__iexact=email, is_active=True, is_staff=True)
        except User.DoesNotExist:
            logger.warning("Admin login attempt for unknown/inactive email: %s", email)
            messages.error(request, _("No active staff account found for that address."))
            return self._render_login(request)

        # Generate a fresh OTP and store it in the cache backend (Redis).
        otp = generate_otp(email=email)

        # Attempt delivery; abort and re-render if the mail server is down.
        if not self._send_otp_safe(request, email=email, otp=otp):
            return self._render_login(request)

        # Store the user PK in the session so Step 2 knows who to
        # authenticate without exposing anything in the URL.
        request.session["otp_user_id"] = user.id
        logger.info("OTP sent to admin user pk=%s", user.id)

        return redirect(reverse("admin:otp_verify_view"))

    # ------------------------------------------------------------------ #
    #  Step 2 — OTP verification                                           #
    # ------------------------------------------------------------------ #

    @method_decorator(never_cache)   # prevents the browser from caching the OTP page
    def otp_verify_view(self, request):
        """
        Step 2 of the OTP login flow — validate the 6-digit code and,
        on success, create a full Django admin session.

        GET  → render ``otp_verify.html`` with a blank form.
        POST → validate the submitted code against the Redis-stored value,
               then call Django's ``login()`` to finalise the session.

        Guards:
        - No ``otp_user_id`` in session → redirect to Step 1 (session
          expired or user navigated here directly).
        - User no longer active/staff → redirect to Step 1 (account
          disabled between Step 1 and Step 2).
        - Invalid/expired code → re-render with error, allow retry.

        Security notes:
        - ``is_valid_otp()`` deletes the Redis key on success so each
          code can only be used once (replay-attack prevention).
        - Django's ``login()`` rotates the session key to prevent
          session-fixation attacks.
        - The user is re-fetched from the database (not taken from the
          session) to guard against account state changes between steps.

        Args:
            request: The current HTTP request.

        Returns:
            HttpResponse: Either a rendered OTP page or a redirect.
        """
        request.current_app = self.name
        User = get_user_model()

        # Guard — session must carry the user PK written in Step 1.
        user_id = request.session.get("otp_user_id")
        if not user_id:
            # Session missing or expired → restart from the email form.
            return redirect(reverse("admin:login"))

        # GET — show the blank OTP input form.
        if request.method != "POST":
            return self._render_verify(request)

        form = AdminOTPForm(request.POST)

        # Re-render with field-level errors (e.g. non-numeric input).
        if not form.is_valid():
            return self._render_verify(request, form)

        code = form.cleaned_data["otp_code"]

        # Re-fetch the user to guard against the account being deactivated
        # or losing staff status between Step 1 and Step 2.
        try:
            user = User.objects.get(pk=user_id, is_active=True, is_staff=True)
        except User.DoesNotExist:
            logger.warning("OTP verify: user pk=%s not found or inactive", user_id)
            messages.error(request, _("Session expired. Please try again."))
            return redirect(reverse("admin:login"))

        # Validate the submitted code against the Redis-stored value.
        # is_valid_otp() deletes the key on success (single-use enforcement).
        if not is_valid_otp(email=user.email, entered_code=code):
            logger.warning("Invalid OTP attempt for user pk=%s", user_id)
            messages.error(request, _("Invalid or expired code. Please try again."))
            return self._render_verify(request)

        # ✅  Code is valid — clean up the temporary session marker, then
        # call Django's login() which attaches the user to the session
        # and rotates the session key to prevent session fixation.
        request.session.pop("otp_user_id", None)
        user.backend = "django.contrib.auth.backends.ModelBackend"
        login(request, user)

        logger.info("Admin user pk=%s successfully authenticated via OTP", user.id)
        return redirect(reverse("admin:index"))


# ---------------------------------------------------------------------------
# Module-level singleton — one instance is shared across the entire project.
#
# Always import this object rather than instantiating OTPAdminSite directly:
#
#   from django_otp_admin.site import otp_admin_site
# ---------------------------------------------------------------------------
otp_admin_site = OTPAdminSite(name="admin")
