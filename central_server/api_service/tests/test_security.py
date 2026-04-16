"""Tests for security-critical settings validation and authentication logic."""
import hmac
import sys
import types
import unittest
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Helpers to build isolated Settings instances without touching real env vars
# ---------------------------------------------------------------------------

def _make_settings(**overrides):
    """Return a fresh Settings instance with the given field values.

    We patch os.getenv so that the module-level calls inside settings.py
    resolve to the values we supply, and we bypass pydantic's usual env-file
    loading to keep tests self-contained.
    """
    # Import here so the module is guaranteed to be importable in test context.
    from central_server.api_service.core.settings import Settings, _FORBIDDEN_PASSWORDS, _FORBIDDEN_SECRET_KEYS, _SECRET_KEY_MIN_LENGTH

    defaults = {
        "SECRET_KEY": "a" * 32,           # valid by default
        "LIFELOG_PASSWORD": "StrongPass1!",  # valid by default
        "LIFELOG_USERNAME": "admin",
        "POSTGRES_PASSWORD": "",
        "RABBITMQ_PASS": "",
        "GEMINI_API_KEY": "",
        "ALLOWED_ORIGINS_STR": "",
    }
    defaults.update(overrides)

    # Construct directly, bypassing env-var loading
    return Settings.model_construct(**defaults)


class TestValidateSecurity(unittest.TestCase):
    """Unit tests for Settings.validate_security()."""

    def test_valid_config_does_not_raise(self):
        s = _make_settings(SECRET_KEY="x" * 32, LIFELOG_PASSWORD="StrongPass1!")
        # Should not raise or call sys.exit
        s.validate_security()

    def test_empty_secret_key_exits(self):
        s = _make_settings(SECRET_KEY="")
        with self.assertRaises(SystemExit):
            s.validate_security()

    def test_placeholder_secret_key_exits(self):
        s = _make_settings(SECRET_KEY="your-super-secret-key-that-is-long-and-random")
        with self.assertRaises(SystemExit):
            s.validate_security()

    def test_short_secret_key_exits(self):
        s = _make_settings(SECRET_KEY="short")
        with self.assertRaises(SystemExit):
            s.validate_security()

    def test_secret_key_exactly_at_minimum_length_is_valid(self):
        from central_server.api_service.core.settings import _SECRET_KEY_MIN_LENGTH
        s = _make_settings(SECRET_KEY="a" * _SECRET_KEY_MIN_LENGTH, LIFELOG_PASSWORD="StrongPass1!")
        s.validate_security()  # should not raise

    def test_empty_password_exits(self):
        s = _make_settings(SECRET_KEY="a" * 32, LIFELOG_PASSWORD="")
        with self.assertRaises(SystemExit):
            s.validate_security()

    def test_known_bad_password_admin123_exits(self):
        s = _make_settings(SECRET_KEY="a" * 32, LIFELOG_PASSWORD="admin123")
        with self.assertRaises(SystemExit):
            s.validate_security()

    def test_known_bad_password_password_exits(self):
        s = _make_settings(SECRET_KEY="a" * 32, LIFELOG_PASSWORD="password")
        with self.assertRaises(SystemExit):
            s.validate_security()

    def test_multiple_errors_all_logged_before_exit(self):
        """When both SECRET_KEY and LIFELOG_PASSWORD are bad, the app still exits."""
        s = _make_settings(SECRET_KEY="", LIFELOG_PASSWORD="admin123")
        with self.assertRaises(SystemExit):
            s.validate_security()


class TestAuthenticateUser(unittest.TestCase):
    """Unit tests for the authenticate_user function."""

    def _call(self, username: str, password: str) -> bool:
        from central_server.api_service.auth import authenticate_user
        return authenticate_user(username, password)

    def _patch_settings(self, username="admin", password="StrongPass1!"):
        """Context manager: temporarily override settings credentials."""
        return patch(
            "central_server.api_service.auth.settings",
            LIFELOG_USERNAME=username,
            LIFELOG_PASSWORD=password,
            SECRET_KEY="a" * 32,
            API_V1_STR="/api/v1",
            ALGORITHM="HS256",
            ACCESS_TOKEN_EXPIRE_MINUTES=30,
        )

    def test_correct_credentials_returns_true(self):
        with self._patch_settings():
            self.assertTrue(self._call("admin", "StrongPass1!"))

    def test_wrong_password_returns_false(self):
        with self._patch_settings():
            self.assertFalse(self._call("admin", "wrongpassword"))

    def test_wrong_username_returns_false(self):
        with self._patch_settings():
            self.assertFalse(self._call("hacker", "StrongPass1!"))

    def test_both_wrong_returns_false(self):
        with self._patch_settings():
            self.assertFalse(self._call("hacker", "wrongpassword"))

    def test_empty_credentials_return_false(self):
        with self._patch_settings():
            self.assertFalse(self._call("", ""))

    def test_uses_constant_time_comparison(self):
        """Verify authenticate_user delegates to hmac.compare_digest (timing-safe)."""
        import central_server.api_service.auth as auth_module
        with patch.object(hmac, "compare_digest", wraps=hmac.compare_digest) as mock_cd:
            with self._patch_settings():
                auth_module.authenticate_user("admin", "StrongPass1!")
            self.assertGreaterEqual(mock_cd.call_count, 2,
                msg="Both username and password must be compared via hmac.compare_digest")


class TestIngestionAuth(unittest.TestCase):
    """Unit tests for the ingestion service token verification logic.

    The ingestion service depends on ``aio_pika`` which may not be installed in
    all test environments (it's only needed at runtime, not for the auth logic).
    We stub it out so we can exercise the security code in isolation.
    """

    def _load_ingestion_module(self):
        """Load ingestion main.py with unavailable deps stubbed out."""
        import importlib.util
        import os

        # Stub modules that are only needed at runtime, not for auth logic
        aio_pika_stub = types.ModuleType("aio_pika")
        aio_pika_stub.connect_robust = None
        aio_pika_stub.Message = None
        aio_pika_stub.DeliveryMode = types.SimpleNamespace(PERSISTENT=2)
        aio_pika_exceptions_stub = types.ModuleType("aio_pika.exceptions")
        aio_pika_exceptions_stub.AMQPException = Exception

        stub_models = types.ModuleType("models")
        stub_models.LogEvent = object
        stub_models.LogPayload = object

        ingestion_main_path = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..", "ingestion_service", "main.py")
        )
        spec = importlib.util.spec_from_file_location("_ingestion_main_test", ingestion_main_path)
        mod = importlib.util.module_from_spec(spec)
        extra_stubs = {
            "aio_pika": aio_pika_stub,
            "aio_pika.exceptions": aio_pika_exceptions_stub,
            "models": stub_models,
        }
        with patch.dict(sys.modules, extra_stubs):
            spec.loader.exec_module(mod)
        return mod

    def test_valid_token_accepted(self):
        from fastapi.security import HTTPAuthorizationCredentials

        mod = self._load_ingestion_module()
        token = "supersecrettoken"
        with patch.object(mod, "_INGESTION_AUTH_TOKEN", token):
            creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
            mod._verify_ingestion_token(creds)  # should not raise

    def test_invalid_token_raises_401(self):
        from fastapi import HTTPException
        from fastapi.security import HTTPAuthorizationCredentials

        mod = self._load_ingestion_module()
        with patch.object(mod, "_INGESTION_AUTH_TOKEN", "correcttoken"):
            creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="wrongtoken")
            with self.assertRaises(HTTPException) as ctx:
                mod._verify_ingestion_token(creds)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_empty_server_token_raises_503(self):
        from fastapi import HTTPException
        from fastapi.security import HTTPAuthorizationCredentials

        mod = self._load_ingestion_module()
        with patch.object(mod, "_INGESTION_AUTH_TOKEN", ""):
            creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="anytoken")
            with self.assertRaises(HTTPException) as ctx:
                mod._verify_ingestion_token(creds)
        self.assertEqual(ctx.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()
