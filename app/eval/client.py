"""EvalHub client wrapper — thin abstraction over the eval-hub-sdk.

Provides:
 - submit_eval()    — submit a job from YAML config or inline params
 - poll_eval()      — wait for completion and return structured results
 - check_gate()     — single call for CI: submit + wait + pass/fail
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import httpx
import yaml


class EvalHubClient:
    """Lightweight wrapper around the EvalHub REST API."""

    def __init__(
        self,
        base_url: str | None = None,
        tenant: str | None = None,
        token: str | None = None,
        timeout: float = 30.0,
        verify_ssl: bool | None = None,
    ):
        self.base_url = (base_url or os.environ.get("EVALHUB_URL", "")).rstrip("/")
        self.tenant = tenant or os.environ.get("EVALHUB_TENANT", "redhat-ods-applications")
        self.token = token or os.environ.get("EVALHUB_TOKEN", "")
        if verify_ssl is None:
            verify_ssl = os.environ.get("EVALHUB_SSL_VERIFY", "true").lower() not in (
                "false",
                "0",
                "no",
            )
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            verify=verify_ssl,
        )

    @property
    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "X-Tenant": self.tenant,
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def submit_eval(
        self,
        config_path: str | Path | None = None,
        *,
        name: str = "",
        model_url: str = "",
        model_name: str = "",
        benchmarks: list[dict[str, Any]] | None = None,
    ) -> str:
        """Submit an evaluation job.

        Args:
            config_path: Path to a YAML config (preferred).
            name: Job name (if not using config).
            model_url: Model endpoint URL.
            model_name: Model name.
            benchmarks: List of benchmark dicts.

        Returns:
            Job ID string.
        """
        if config_path:
            with open(config_path) as f:
                body = yaml.safe_load(f)
        else:
            body = {
                "name": name,
                "model": {"url": model_url, "name": model_name},
                "benchmarks": benchmarks or [],
            }

        resp = self._client.post(
            "/api/v1/evaluations/jobs",
            json=body,
            headers=self._headers,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("id", data.get("job_id", ""))

    def get_status(self, job_id: str) -> dict[str, Any]:
        """Get job status."""
        resp = self._client.get(
            f"/api/v1/evaluations/jobs/{job_id}",
            headers=self._headers,
        )
        resp.raise_for_status()
        return resp.json()

    def poll_eval(
        self,
        job_id: str,
        timeout: float = 1800,
        poll_interval: float = 10,
    ) -> dict[str, Any]:
        """Poll until job completes or times out.

        Returns:
            Final job status dict.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = self.get_status(job_id)
            state = result.get("status", result.get("state", ""))
            if state in ("completed", "failed", "cancelled", "error"):
                return result
            time.sleep(poll_interval)

        return {"status": "timeout", "job_id": job_id}

    def check_gate(
        self,
        config_path: str | Path | None = None,
        *,
        timeout: float = 1800,
        **submit_kwargs: Any,
    ) -> tuple[bool, dict[str, Any]]:
        """CI gate: submit, wait, return (passed, result).

        Returns:
            Tuple of (passed: bool, result: dict).
        """
        job_id = self.submit_eval(config_path, **submit_kwargs)
        result = self.poll_eval(job_id, timeout=timeout)
        status = result.get("status", result.get("state", ""))
        passed = status == "completed" and result.get("pass", result.get("result", "")) in (
            True,
            "true",
            "pass",
            "passed",
        )
        return passed, result

    def list_collections(self) -> list[dict[str, Any]]:
        """List available evaluation collections."""
        resp = self._client.get(
            "/api/v1/evaluations/collections",
            headers=self._headers,
        )
        resp.raise_for_status()
        return resp.json()

    def list_providers(self) -> list[dict[str, Any]]:
        """List available evaluation providers."""
        resp = self._client.get(
            "/api/v1/evaluations/providers",
            headers=self._headers,
        )
        resp.raise_for_status()
        return resp.json()

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def __enter__(self) -> EvalHubClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
