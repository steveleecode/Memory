from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, cast

import httpx

from app.core.settings import Settings


class GoogleAuthorizationError(RuntimeError):
    pass


class GoogleRateLimitError(RuntimeError):
    pass


class GoogleTransientError(RuntimeError):
    pass


class GooglePermanentError(RuntimeError):
    pass


@dataclass(frozen=True)
class TokenResponse:
    access_token: str
    refresh_token: str | None
    expires_in: int | None
    scope: str


class GoogleDriveClient(Protocol):
    async def exchange_code(self, code: str, code_verifier: str) -> TokenResponse: ...

    async def refresh_access_token(self, refresh_token: str) -> TokenResponse: ...

    async def revoke_token(self, token: str) -> None: ...

    async def userinfo(self, access_token: str) -> dict[str, Any]: ...

    async def start_page_token(self, access_token: str) -> str: ...

    def list_files(self, access_token: str) -> AsyncIterator[dict[str, Any]]: ...

    def list_changes(
        self,
        access_token: str,
        page_token: str,
    ) -> AsyncIterator[tuple[dict[str, Any], str | None, str | None]]: ...

    async def download_file(self, access_token: str, file_id: str) -> bytes: ...

    async def export_file(self, access_token: str, file_id: str, mime_type: str) -> bytes: ...


class HttpGoogleDriveClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def exchange_code(self, code: str, code_verifier: str) -> TokenResponse:
        return await self._token(
            {
                "code": code,
                "client_id": self.settings.google_oauth_client_id,
                "client_secret": self.settings.google_oauth_client_secret,
                "redirect_uri": self.settings.google_oauth_redirect_url,
                "grant_type": "authorization_code",
                "code_verifier": code_verifier,
            }
        )

    async def refresh_access_token(self, refresh_token: str) -> TokenResponse:
        return await self._token(
            {
                "refresh_token": refresh_token,
                "client_id": self.settings.google_oauth_client_id,
                "client_secret": self.settings.google_oauth_client_secret,
                "grant_type": "refresh_token",
            }
        )

    async def revoke_token(self, token: str) -> None:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                "https://oauth2.googleapis.com/revoke",
                params={"token": token},
            )
        if response.status_code not in {200, 400}:
            _raise_google_error(response)

    async def userinfo(self, access_token: str) -> dict[str, Any]:
        return await self._get_json(
            "https://openidconnect.googleapis.com/v1/userinfo",
            access_token,
        )

    async def start_page_token(self, access_token: str) -> str:
        payload = await self._get_json(
            "https://www.googleapis.com/drive/v3/changes/startPageToken",
            access_token,
            params={"supportsAllDrives": "true"},
        )
        token = payload.get("startPageToken")
        if not isinstance(token, str):
            raise GooglePermanentError("Google did not return a Drive changes cursor")
        return token

    async def list_files(self, access_token: str) -> AsyncIterator[dict[str, Any]]:
        page_token: str | None = None
        fields = (
            "nextPageToken,files(id,name,mimeType,parents,createdTime,modifiedTime,size,"
            "md5Checksum,webViewLink,trashed,ownedByMe,shared,version,headRevisionId,owners(emailAddress))"
        )
        while True:
            payload = await self._get_json(
                "https://www.googleapis.com/drive/v3/files",
                access_token,
                params={
                    "fields": fields,
                    "pageSize": "1000",
                    "q": "trashed = false",
                    "supportsAllDrives": "true",
                    "includeItemsFromAllDrives": "true",
                    **({"pageToken": page_token} if page_token else {}),
                },
            )
            for item in _list(payload.get("files")):
                yield item
            page_token = _optional_string(payload.get("nextPageToken"))
            if page_token is None:
                break

    async def list_changes(
        self,
        access_token: str,
        page_token: str,
    ) -> AsyncIterator[tuple[dict[str, Any], str | None, str | None]]:
        token = page_token
        fields = (
            "nextPageToken,newStartPageToken,changes(removed,fileId,file(id,name,mimeType,"
            "parents,createdTime,modifiedTime,size,md5Checksum,webViewLink,trashed,ownedByMe,"
            "shared,version,headRevisionId,owners(emailAddress)))"
        )
        while True:
            payload = await self._get_json(
                "https://www.googleapis.com/drive/v3/changes",
                access_token,
                params={
                    "pageToken": token,
                    "fields": fields,
                    "pageSize": "1000",
                    "supportsAllDrives": "true",
                    "includeItemsFromAllDrives": "true",
                },
            )
            next_page = _optional_string(payload.get("nextPageToken"))
            new_start = _optional_string(payload.get("newStartPageToken"))
            for item in _list(payload.get("changes")):
                yield item, next_page, new_start
            if next_page is None:
                break
            token = next_page

    async def download_file(self, access_token: str, file_id: str) -> bytes:
        return await self._get_bytes(
            f"https://www.googleapis.com/drive/v3/files/{file_id}",
            access_token,
            params={"alt": "media", "supportsAllDrives": "true"},
        )

    async def export_file(self, access_token: str, file_id: str, mime_type: str) -> bytes:
        return await self._get_bytes(
            f"https://www.googleapis.com/drive/v3/files/{file_id}/export",
            access_token,
            params={"mimeType": mime_type},
        )

    async def _token(self, data: Mapping[str, object]) -> TokenResponse:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post("https://oauth2.googleapis.com/token", data=data)
        if response.status_code >= 400:
            _raise_google_error(response)
        payload = response.json()
        return TokenResponse(
            access_token=str(payload["access_token"]),
            refresh_token=_optional_string(payload.get("refresh_token")),
            expires_in=int(payload["expires_in"]) if payload.get("expires_in") else None,
            scope=str(payload.get("scope") or ""),
        )

    async def _get_json(
        self,
        url: str,
        access_token: str,
        *,
        params: Mapping[str, object] | None = None,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                url,
                headers=_auth(access_token),
                params=cast(Any, params),
            )
        if response.status_code >= 400:
            _raise_google_error(response)
        payload = response.json()
        if not isinstance(payload, dict):
            raise GooglePermanentError("Google returned an invalid JSON object")
        return payload

    async def _get_bytes(
        self,
        url: str,
        access_token: str,
        *,
        params: Mapping[str, object] | None = None,
    ) -> bytes:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(
                url,
                headers=_auth(access_token),
                params=cast(Any, params),
            )
        if response.status_code >= 400:
            _raise_google_error(response)
        return response.content


def _auth(access_token: str) -> dict[str, str]:
    return {"authorization": f"Bearer {access_token}"}


def _raise_google_error(response: httpx.Response) -> None:
    if response.status_code in {401, 403}:
        raise GoogleAuthorizationError("Google authorization is invalid or has been revoked")
    if response.status_code in {429, 500, 502, 503, 504}:
        if response.status_code == 429:
            raise GoogleRateLimitError("Google Drive rate limit exceeded")
        raise GoogleTransientError(f"Google Drive temporary error: HTTP {response.status_code}")
    raise GooglePermanentError(f"Google Drive request failed: HTTP {response.status_code}")


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
