from __future__ import annotations

from typing import Final

T7_ACCEPTED_INDEX_MISMATCH: Final[tuple[str, ...]] = (
    "6cbe81664153a2b59eb9755448763aee",
    "37ad86ef-7ed2-449a-b0dc-04575d30bf63",
    "2ec5dc1c-3b92-4e6e-958f-71a718cf775f",
    "dabe011ef7d9ecc92ba865301bc69141b0ec02e9bb06ed535ee09a21cbdeaae6",
    "839a32d9cc0ba1e06f7536161663e63227d2a7e4c702d627d25b28f57c4b59e8",
    "refs/heads/oc2-fixture",
    "1e54222fa8613b4e27f99e416774805d63a9645c",
    "0ea64553e9d6f8beb55298a67bd2a5e1249ba6ed",
    "sha1",
    "4e79e8547e6a1a6276894c2c58124bc1e5a1e4419a376f3c841c939031bf8b03",
    "9b0bc8972181c62d93aa33bb55594e05482307c80ab127a524bb106039184e98",
    "68ef7fa18bd9e5324cbadd0294a6f81dadd9e2f35b5c68ef2e20bdb22e32c2ea",
    "de8497cc42589e0e5a377442c351797572b914c1f87cc3c7a493dbf5518f3fb2",
    "1e54222fa8613b4e27f99e416774805d63a9645c",
    "0ea64553e9d6f8beb55298a67bd2a5e1249ba6ed",
    "9b0bc8972181c62d93aa33bb55594e05482307c80ab127a524bb106039184e98",
    "read-only-inspected",
)


def is_accepted_t7_index_fingerprint(fingerprint: tuple[str, ...]) -> bool:
    """Match only the complete pinned historical T7 index-mismatch evidence tuple."""
    return fingerprint == T7_ACCEPTED_INDEX_MISMATCH
