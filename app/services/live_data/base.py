import re
from typing import Any

import httpx


class ProviderError(Exception):
    """Sanitized upstream request or response-validation error."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        provider_status: str | None = None,
        failure_kind: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.provider_status = provider_status
        self.failure_kind = failure_kind


class LiveProvider:
    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 8.0,
    ) -> None:
        self.client = client
        self.timeout_seconds = timeout_seconds

    async def request_json(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, str | int] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        try:
            if self.client is not None:
                response = await self.client.request(
                    method,
                    url,
                    params=params,
                    json=json,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
            else:
                async with httpx.AsyncClient(
                    timeout=self.timeout_seconds,
                ) as client:
                    response = await client.request(
                        method,
                        url,
                        params=params,
                        json=json,
                        headers=headers,
                    )
            if len(response.content) > 5_000_000:
                raise ProviderError("The external provider response exceeded the size limit.")
            response.raise_for_status()
            payload = response.json()
        except ProviderError:
            raise
        except httpx.HTTPStatusError as exc:
            raise ProviderError(
                "The external provider returned an HTTP error.",
                status_code=exc.response.status_code,
                provider_status=self._provider_status(exc.response),
                failure_kind="http",
            ) from None
        except httpx.TimeoutException:
            raise ProviderError(
                "The external provider request timed out.",
                failure_kind="timeout",
            ) from None
        except httpx.NetworkError:
            raise ProviderError(
                "The external provider could not be reached.",
                failure_kind="network",
            ) from None
        except (httpx.HTTPError, ValueError):
            raise ProviderError("The external provider request failed or returned invalid JSON.") from None
        if not isinstance(payload, (dict, list)):
            raise ProviderError("The external provider returned an unsupported response.")
        return payload

    @staticmethod
    def _provider_status(response: httpx.Response) -> str | None:
        try:
            payload = response.json()
        except ValueError:
            return None
        error = payload.get("error") if isinstance(payload, dict) else None
        provider_status = error.get("status") if isinstance(error, dict) else None
        if isinstance(provider_status, str) and re.fullmatch(r"[A-Z][A-Z_]{1,63}", provider_status):
            return provider_status
        return None
