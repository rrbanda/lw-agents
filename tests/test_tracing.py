"""Unit tests for app.tracing — MLflow tracing bootstrap and graceful degradation.

These tests exercise the tracing module WITHOUT requiring a live MLflow server
or the optional tracing dependencies. All external calls are mocked.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _mock_tracing_modules() -> dict:
    """Build a dict of mocked mlflow + opentelemetry modules for sys.modules patching.

    Important: sub-module mocks must be reachable as attributes of
    their parent mock so that ``import mlflow; mlflow.litellm.autolog()``
    and ``import mlflow.litellm; mlflow.litellm.autolog()`` both hit the
    same mock object.
    """
    mock_litellm = MagicMock()
    mock_config = MagicMock()
    mock_entities = MagicMock()

    mock_mlflow = MagicMock()
    mock_mlflow.set_experiment.return_value = MagicMock(experiment_id="0")
    mock_mlflow.litellm = mock_litellm
    mock_mlflow.config = mock_config
    mock_mlflow.entities = mock_entities

    mock_otel_trace = MagicMock()
    mock_exporter_mod = MagicMock(OTLPSpanExporter=MagicMock())
    mock_provider_cls = MagicMock()
    mock_processor_cls = MagicMock()

    return {
        "mlflow": mock_mlflow,
        "mlflow.litellm": mock_litellm,
        "mlflow.config": mock_config,
        "mlflow.entities": mock_entities,
        "opentelemetry": MagicMock(),
        "opentelemetry.trace": mock_otel_trace,
        "opentelemetry.exporter": MagicMock(),
        "opentelemetry.exporter.otlp": MagicMock(),
        "opentelemetry.exporter.otlp.proto": MagicMock(),
        "opentelemetry.exporter.otlp.proto.http": MagicMock(),
        "opentelemetry.exporter.otlp.proto.http.trace_exporter": mock_exporter_mod,
        "opentelemetry.sdk": MagicMock(),
        "opentelemetry.sdk.trace": MagicMock(TracerProvider=mock_provider_cls),
        "opentelemetry.sdk.trace.export": MagicMock(SimpleSpanProcessor=mock_processor_cls),
    }


@pytest.fixture(autouse=True)
def _reset_tracing_state():
    """Reset the module-level _TRACING_ENABLED flag between tests."""
    import app.tracing as mod

    original = mod._TRACING_ENABLED
    yield
    mod._TRACING_ENABLED = original


class TestEnableTracingDisabledByDefault:
    """When MLFLOW_TRACKING_URI is not set, tracing should be a no-op."""

    def test_noop_when_env_unset(self, monkeypatch):
        monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
        from app.tracing import enable_tracing, is_tracing_enabled

        enable_tracing()
        assert is_tracing_enabled() is False

    def test_noop_when_env_empty(self, monkeypatch):
        monkeypatch.setenv("MLFLOW_TRACKING_URI", "")
        from app.tracing import enable_tracing, is_tracing_enabled

        enable_tracing()
        assert is_tracing_enabled() is False


class TestEnableTracingGracefulDegradation:
    """When URI is set but something goes wrong, the agent should still start."""

    def test_unreachable_server_degrades(self, monkeypatch):
        """Agent starts even if MLflow is unreachable."""
        monkeypatch.setenv("MLFLOW_TRACKING_URI", "https://does-not-exist.local:9999")
        monkeypatch.setenv("MLFLOW_HEALTH_CHECK_TIMEOUT", "1")

        import app.tracing as mod

        mod._TRACING_ENABLED = False

        with (
            patch.dict("sys.modules", _mock_tracing_modules()),
            patch("app.tracing._check_mlflow_health") as mock_health,
        ):
            mock_health.side_effect = RuntimeError("MLflow unreachable")
            mod.enable_tracing()

        assert mod._TRACING_ENABLED is False

    def test_missing_mlflow_package_raises(self, monkeypatch):
        """If URI is set but mlflow is not installed, raise clearly."""
        monkeypatch.setenv("MLFLOW_TRACKING_URI", "https://mlflow.local")
        import app.tracing as mod

        mod._TRACING_ENABLED = False

        import builtins
        import sys

        real_import = builtins.__import__

        # Remove mlflow from sys.modules first so the import inside enable_tracing
        # actually hits our mock
        saved = {}
        for key in list(sys.modules):
            if key == "mlflow" or key.startswith("mlflow."):
                saved[key] = sys.modules.pop(key)

        def mock_import(name, *args, **kwargs):
            if name == "mlflow" or name.startswith("mlflow."):
                raise ModuleNotFoundError("No module named 'mlflow'")
            return real_import(name, *args, **kwargs)

        try:
            with patch("builtins.__import__", side_effect=mock_import):
                with pytest.raises(ModuleNotFoundError, match="mlflow is not installed"):
                    mod.enable_tracing()
        finally:
            sys.modules.update(saved)


class TestHealthCheck:
    """Tests for _check_mlflow_health."""

    def test_healthy_server_returns(self):
        """Health check returns immediately when server is healthy."""

        from app.tracing import _check_mlflow_health

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.get", return_value=mock_response):
            _check_mlflow_health("https://mlflow.local", max_wait=2)

    def test_422_is_considered_healthy(self):
        """RHOAI MLflow returns 422 on /v1/traces — that counts as healthy."""
        from app.tracing import _check_mlflow_health

        mock_response = MagicMock()
        mock_response.status_code = 422

        with patch("httpx.get", return_value=mock_response):
            _check_mlflow_health("https://mlflow.local", max_wait=2)

    def test_timeout_raises(self):
        """Health check raises after max_wait seconds."""
        import httpx

        from app.tracing import _check_mlflow_health

        with patch("httpx.get", side_effect=httpx.ConnectError("refused")):
            with pytest.raises(RuntimeError, match="unreachable after"):
                _check_mlflow_health(
                    "https://mlflow.local",
                    max_wait=1,
                    retry_interval=0,
                )


class TestSafeUri:
    """Tests for _safe_uri — credential stripping."""

    def test_strips_credentials(self):
        from app.tracing import _safe_uri

        result = _safe_uri("https://user:pass@mlflow.local:8443/api")
        assert "user" not in result
        assert "pass" not in result
        assert "mlflow.local" in result

    def test_preserves_path(self):
        from app.tracing import _safe_uri

        result = _safe_uri("https://mlflow.local:8443/api/v1")
        assert "/api/v1" in result

    def test_strips_query_params(self):
        from app.tracing import _safe_uri

        result = _safe_uri("https://mlflow.local?token=secret&key=abc")
        assert "secret" not in result
        assert "key" not in result


class TestWrapFuncWithMlflowTrace:
    """Tests for wrap_func_with_mlflow_trace."""

    def test_noop_when_tracing_disabled(self):
        """Returns the function unchanged when tracing is off."""
        import app.tracing as mod

        mod._TRACING_ENABLED = False

        def my_func():
            return 42

        wrapped = mod.wrap_func_with_mlflow_trace(my_func, span_type="tool")
        assert wrapped is my_func

    def test_wraps_when_tracing_enabled(self):
        """Wraps the function when tracing is on."""
        import app.tracing as mod

        mod._TRACING_ENABLED = True

        def my_func():
            return 42

        mock_mlflow = MagicMock()
        mock_mlflow.trace = MagicMock(return_value=lambda f: f)

        with patch.dict("sys.modules", {"mlflow": mock_mlflow, "mlflow.entities": MagicMock()}):
            mod.wrap_func_with_mlflow_trace(my_func, span_type="tool", name="test")
            mock_mlflow.trace.assert_called_once()


class TestIsTracingEnabled:
    """Tests for is_tracing_enabled."""

    def test_false_by_default(self):
        import app.tracing as mod

        mod._TRACING_ENABLED = False
        assert mod.is_tracing_enabled() is False

    def test_true_when_set(self):
        import app.tracing as mod

        mod._TRACING_ENABLED = True
        assert mod.is_tracing_enabled() is True


class TestFullEnableFlow:
    """Test the full enable_tracing flow with mocked dependencies."""

    def test_successful_enable(self, monkeypatch):
        monkeypatch.setenv("MLFLOW_TRACKING_URI", "https://mlflow.test.local")
        monkeypatch.setenv("MLFLOW_EXPERIMENT_NAME", "test-experiment")
        monkeypatch.setenv("MLFLOW_WORKSPACE", "test-workspace")
        monkeypatch.setenv("MLFLOW_TRACKING_TOKEN", "test-token")

        import app.tracing as mod

        mod._TRACING_ENABLED = False

        mods = _mock_tracing_modules()
        mock_mlflow = mods["mlflow"]
        mock_mlflow.set_experiment.return_value = MagicMock(experiment_id="123")
        mock_litellm = mods["mlflow.litellm"]

        with (
            patch("app.tracing._check_mlflow_health"),
            patch.dict("sys.modules", mods),
        ):
            mod.enable_tracing()

        assert mod._TRACING_ENABLED is True
        mock_mlflow.set_tracking_uri.assert_called_once_with("https://mlflow.test.local")
        mock_mlflow.set_experiment.assert_called_once_with("test-experiment")
        mock_litellm.autolog.assert_called_once()
