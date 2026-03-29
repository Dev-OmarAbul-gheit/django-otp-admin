# tests/test_utils.py
#
# Unit tests for django_otp_admin.utils
#
# Run with:  pytest --ds=tests.settings

import pytest
from unittest.mock import patch, MagicMock
from django.core.cache import cache

from django_otp_admin.utils import (
    generate_otp,
    is_valid_otp,
    can_request_otp,
)


@pytest.fixture(autouse=True)
def clear_cache():
    """Wipe the cache before every test so keys don't bleed across tests."""
    cache.clear()
    yield
    cache.clear()


class TestGenerateOtp:
    def test_returns_six_digit_string(self):
        code = generate_otp("admin@example.com")
        assert len(code) == 6
        assert code.isdigit()

    def test_stores_code_in_cache(self):
        code = generate_otp("admin@example.com")
        stored = cache.get("admin_otp:admin@example.com")
        assert stored == code

    def test_new_call_overwrites_previous_otp(self):
        first  = generate_otp("admin@example.com")
        second = generate_otp("admin@example.com")
        assert cache.get("admin_otp:admin@example.com") == second
        # codes are random so they are very likely different
        # (1-in-900000 chance of false failure — acceptable for a unit test)


class TestIsValidOtp:
    def test_valid_code_returns_true(self):
        code = generate_otp("admin@example.com")
        assert is_valid_otp("admin@example.com", code) is True

    def test_valid_code_is_deleted_after_use(self):
        code = generate_otp("admin@example.com")
        is_valid_otp("admin@example.com", code)
        assert cache.get("admin_otp:admin@example.com") is None

    def test_wrong_code_returns_false(self):
        generate_otp("admin@example.com")
        assert is_valid_otp("admin@example.com", "000000") is False

    def test_expired_code_returns_false(self):
        # Key was never set — simulates expiry
        assert is_valid_otp("admin@example.com", "123456") is False

    def test_replay_attack_blocked(self):
        code = generate_otp("admin@example.com")
        assert is_valid_otp("admin@example.com", code) is True
        # Second use of the same code must fail
        assert is_valid_otp("admin@example.com", code) is False


class TestCanRequestOtp:
    def test_first_request_allowed(self):
        assert can_request_otp("admin@example.com") is True

    def test_second_immediate_request_blocked(self):
        can_request_otp("admin@example.com")
        assert can_request_otp("admin@example.com") is False

    def test_different_emails_are_independent(self):
        can_request_otp("user1@example.com")
        assert can_request_otp("user2@example.com") is True
