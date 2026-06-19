"""HTTP client for Enterprise Team Server API (v2.1.5-T4)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import httpx


class ServerModeError(Exception):
    """Raised when server-mode CLI prerequisites are missing or invalid."""


def load_bearer_token(*, token_stdin: bool = False) -> str:
    if token_stdin:
        token = os.read(0, 8192).decode("utf-8").strip()
        if not token:
            raise ServerModeError("token-stdin provided no bearer token")
        return token
    token = os.environ.get("SAFECODE_ENTERPRISE_TOKEN", "").strip()
    if not token:
        raise ServerModeError(
            "server mode requires SAFECODE_ENTERPRISE_TOKEN or --token-stdin"
        )
    return token


def reject_raw_token_argv(argv: list[str]) -> None:
    for arg in argv:
        if arg.startswith("eyJ") and arg.count(".") >= 2:
            raise ServerModeError("raw bearer tokens are not accepted as CLI arguments")


@dataclass(frozen=True)
class EnterpriseApiClient:
    base_url: str
    tenant_id: str
    bearer_token: str
    transport: httpx.BaseTransport | None = None

    def _headers(self, *, idempotency_key: str | None = None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.bearer_token}",
            "X-Tenant-Id": self.tenant_id,
        }
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    def start_run(
        self,
        *,
        task_type: str,
        input_ref: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        url = self.base_url.rstrip("/") + "/v2/runs"
        response = httpx.post(
            url,
            headers=self._headers(idempotency_key=idempotency_key),
            json={"task_type": task_type, "input_ref": input_ref},
            transport=self.transport,
        )
        if response.status_code >= 400:
            raise ServerModeError(
                f"start run failed with status {response.status_code}: {response.text[:256]}"
            )
        return response.json()

    def get_run(self, *, run_id: str) -> dict[str, Any]:
        response = httpx.get(
            urljoin(self.base_url.rstrip("/") + "/", f"v2/runs/{run_id}"),
            headers=self._headers(),
            params={"tenant_id": self.tenant_id},
            transport=self.transport,
        )
        response.raise_for_status()
        return response.json()

    @classmethod
    def from_test_client(cls, client: Any, *, tenant_id: str, bearer_token: str = "test-token") -> EnterpriseApiClient:
        return cls(
            base_url="http://testserver",
            tenant_id=tenant_id,
            bearer_token=bearer_token,
            transport=client._transport,
        )
