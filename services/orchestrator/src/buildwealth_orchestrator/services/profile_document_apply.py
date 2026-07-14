"""Apply bridge for document-vision suggestions.

Takes the (possibly user-edited) suggestions patch produced by
profile_document_vision and merges it into the financial profile. Only known
sections and fields are honored; list sections append to the current list
with the same label+amount dedupe as the context-candidate bridge; the store
save is a single call carrying document-vision metadata.
"""

from __future__ import annotations

from typing import Any, Mapping

from buildwealth_orchestrator.services.profile_mutation import apply_reviewed_profile_patch

APPLY_METADATA_SOURCE = "profile_document_vision"

def apply_document_suggestions(patch: Mapping[str, Any] | None, profile_store: Any) -> dict[str, Any]:
    """Merge a reviewed suggestions patch into the profile.

    Returns {"applied_sections": [...], "counts": {...}, "skipped_duplicates": n}.
    """
    return apply_reviewed_profile_patch(
        patch,
        profile_store,
        metadata_source=APPLY_METADATA_SOURCE,
    )
