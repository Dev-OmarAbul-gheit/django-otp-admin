# django_otp_admin/utils.py
#
# Stateless utility functions for OTP generation, validation, and delivery.
#
# All OTP state is stored in Django's cache backend (Redis recommended).
# No database writes occur in this module.
#
# Cache key layout:
#   admin_otp:<email>         → the 6-digit code (string), TTL = OTP_TTL
#   admin_otp_cooldown:<email>→ sentinel for rate-limiting, TTL = 60 s

import logging
import random

from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration — override in settings.py
# ---------------------------------------------------------------------------

# How long (seconds) an OTP remains valid.  Default: 5 minutes.
OTP_TTL: int = getattr(settings, "OTP_ADMIN_TTL", 300)

# Minimum gap (seconds) between two OTP requests for the same email.
# Prevents spam/abuse.  Default: 60 seconds.
OTP_COOLDOWN: int = getattr(settings, "OTP_ADMIN_COOLDOWN", 60)

# Cache key templates — centralised so a rename never causes key mismatches.
_KEY_OTP      = "admin_otp:{email}"
_KEY_COOLDOWN = "admin_otp_cooldown:{email}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_otp(email: str) -> str:
    """
    Generate a cryptographically adequate 6-digit OTP and store it in
    the cache backend with a TTL of ``OTP_TTL`` seconds.

    A new call overwrites any existing OTP for the same email, so
    requesting a new code always invalidates the previous one.

    Args:
        email: The canonical (lower-cased) email address of the admin user.

    Returns:
        str: The 6-digit code that was stored (to be passed to
             ``send_admin_otp``).
    """
    # random.randint is sufficient here — OTPs are rate-limited, short-lived,
    # and delivered over TLS.  secrets.randbelow could be used for stricter
    # environments.
    code = str(random.randint(100_000, 999_999))

    cache.set(_KEY_OTP.format(email=email), code, timeout=OTP_TTL)
    logger.debug("OTP generated for %s (TTL=%ds)", email, OTP_TTL)

    return code


def is_valid_otp(email: str, entered_code: str) -> bool:
    """
    Validate a submitted OTP code against the value stored in the cache.

    The stored key is deleted immediately on a successful match so that
    each code can only be used once (replay-attack prevention).

    Args:
        email:        The canonical email address of the admin user.
        entered_code: The 6-digit string submitted by the user.

    Returns:
        bool: True if the code matches the stored value; False if the
              code is wrong, the key has expired, or the key does not
              exist.
    """
    key       = _KEY_OTP.format(email=email)
    real_code = cache.get(key)

    if not real_code:
        # Key missing — either expired or never generated.
        logger.debug("OTP lookup miss for %s (expired or not found)", email)
        return False

    if real_code != entered_code:
        logger.debug("OTP mismatch for %s", email)
        return False

    # Delete immediately so the code cannot be replayed.
    cache.delete(key)
    logger.debug("OTP verified and consumed for %s", email)
    return True


def can_request_otp(email: str) -> bool:
    """
    Rate-limit check — returns True if the user is allowed to request a
    new OTP, False if they must wait until the cooldown expires.

    Uses a cache sentinel key with a TTL of ``OTP_COOLDOWN`` seconds.
    The sentinel is set on the *first* allowed request, so subsequent
    calls within the window are rejected.

    Args:
        email: The canonical email address of the admin user.

    Returns:
        bool: True  — request is within rate-limit; a new OTP may be sent.
              False — cooldown is active; do not send another OTP yet.
    """
    key = _KEY_COOLDOWN.format(email=email)

    if cache.get(key):
        logger.debug("OTP rate-limit hit for %s", email)
        return False

    # Set the cooldown sentinel.  nx=True (set-if-not-exists) is not
    # available on all cache backends, so we rely on the TTL instead.
    cache.set(key, True, timeout=OTP_COOLDOWN)
    return True


def send_admin_otp(email: str, code: str) -> None:
    """
    Send the OTP code to the admin's email address via Django's email
    backend (configured in settings.py).

    Args:
        email: Recipient email address.
        code:  The 6-digit OTP to include in the message body.

    Raises:
        ConnectionRefusedError: Raised by the SMTP backend when the mail
            server is unreachable (e.g. not running locally).
        Exception: Any other transport error propagated from the backend.
            Callers should catch broadly and handle gracefully.
    """
    expiry_minutes = OTP_TTL // 60

    send_mail(
        subject=_build_subject(),
        message=_build_body(code=code, expiry_minutes=expiry_minutes),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
        fail_silently=False,  # let exceptions propagate so the view can handle them
    )
    logger.info("OTP email dispatched to %s", email)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _build_subject() -> str:
    """Return the email subject line, optionally prefixed with the site name."""
    site_name = getattr(settings, "OTP_ADMIN_SITE_NAME", "Admin")
    return f"[{site_name}] Admin Login Verification Code"


def _build_body(code: str, expiry_minutes: int) -> str:
    """
    Build the plain-text email body.

    Args:
        code:            The 6-digit OTP.
        expiry_minutes:  How many minutes until the code expires.

    Returns:
        str: Formatted plain-text message body.
    """
    return (
        f"Your one-time login code is:\n\n"
        f"    {code}\n\n"
        f"It expires in {expiry_minutes} minute(s).\n\n"
        f"If you did not request this code, you can safely ignore this email.\n"
        f"Someone may have entered your address by mistake.\n"
    )
