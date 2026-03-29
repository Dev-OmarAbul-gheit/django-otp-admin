# django_otp_admin/forms.py
#
# Forms used by the two-step OTP admin login flow:
#
#   AdminEmailForm  — Step 1: collect the admin's email address.
#   AdminOTPForm    — Step 2: collect and validate the 6-digit OTP code.
#
# Both forms are intentionally minimal — validation logic that requires
# database or cache access lives in the site views, not here.

from django import forms
from django.utils.translation import gettext_lazy as _


class AdminEmailForm(forms.Form):
    """
    Step 1 form — collects the admin's email address.

    Intentionally contains no user-lookup logic so that the view can
    control the exact error message shown (preventing user enumeration).

    Fields:
        email: A standard email field with browser autocomplete enabled.
    """

    email = forms.EmailField(
        label=_("Email Address"),
        # EmailInput renders as <input type="email">, triggering native
        # browser validation and the correct mobile keyboard.
        widget=forms.EmailInput(
            attrs={
                "autofocus": True,           # focus the field on page load
                "autocomplete": "email",     # allow password managers to fill
                "placeholder": "you@example.com",
            }
        ),
    )


class AdminOTPForm(forms.Form):
    """
    Step 2 form — collects and performs format validation of the
    6-digit one-time password sent to the admin's email.

    Only format validation is done here (digits-only, correct length).
    Checking the code against the Redis-stored value is the responsibility
    of the view so that cache/timing logic stays in one place.

    Fields:
        otp_code: A 6-character numeric string.
    """

    otp_code = forms.CharField(
        label=_("Verification Code"),
        min_length=6,
        max_length=6,
        # TextInput (not NumberInput) is used deliberately:
        # NumberInput strips leading zeros and disables paste on some
        # browsers, both of which would silently break valid OTP codes.
        widget=forms.TextInput(
            attrs={
                "autofocus": True,                # focus the field on page load
                "autocomplete": "one-time-code",  # triggers OTP autofill on iOS/Android
                "inputmode": "numeric",           # numeric keyboard on mobile without NumberInput downsides
                "pattern": "[0-9]{6}",            # HTML5 client-side hint (not a security control)
                "placeholder": "000000",
            }
        ),
    )

    def clean_otp_code(self):
        """
        Validate that the submitted code contains exactly 6 digits.

        strip() handles accidental whitespace from copy-paste.
        isdigit() rejects any non-numeric characters that slipped past
        the HTML pattern attribute (which is only a browser hint, not
        enforced server-side).

        Returns:
            str: The cleaned 6-digit string.

        Raises:
            ValidationError: If the code contains non-numeric characters.
        """
        code = self.cleaned_data["otp_code"].strip()

        if not code.isdigit():
            raise forms.ValidationError(
                _("Enter the 6-digit code from your email.")
            )

        return code
