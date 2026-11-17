"""Opaque seal shared by the verified Guest authority capability."""

from __future__ import annotations

from typing import Protocol


class _GuestAuthorityToken:
    __slots__ = ()


_GUEST_AUTHORITY_TOKEN = _GuestAuthorityToken()


class SealedGuestAuthority(Protocol):
    @property
    def authority_token(self) -> _GuestAuthorityToken: ...


def has_guest_authority_seal(authority: SealedGuestAuthority) -> bool:
    return authority.authority_token is _GUEST_AUTHORITY_TOKEN
