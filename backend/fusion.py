"""Cross-platform Profile Fusion Engine (Spotify + Apple Music).

Synthesizes public streaming metadata across Spotify and Apple Music into a
unified, high-fidelity artist identity:
- Spotify delivers: Monthly listeners, world rank, top cities ("Where They Listen"),
  30s audio previews, tour dates, and external social links.
- Apple Music delivers: Curated iTunes genre taxonomy (missing from Spotify's public payload),
  storefront region hints, release years, and high-res master artwork.
"""
from __future__ import annotations

import copy
import logging
from typing import Optional

from . import apple_provider, spotify_provider
from .models import ArtistProfile, PrefillField, RelatedArtist

logger = logging.getLogger(__name__)


def find_matching_id(query_name: str, target_provider: str) -> Optional[str]:
    """Search target provider for an artist matching the given name."""
    clean_name = query_name.strip()
    if not clean_name:
        return None

    mod = apple_provider if target_provider == "apple" else spotify_provider
    try:
        res = mod.resolve(clean_name)
    except Exception as exc:
        logger.warning("Failed resolving %s on %s: %s", clean_name, target_provider, exc)
        return None

    if res.resolved and res.id:
        return res.id

    if res.candidates:
        # Check exact name match first (case-insensitive)
        target_lower = clean_name.lower()
        for cand in res.candidates:
            if cand.name.lower() == target_lower:
                return cand.id
        # Fallback to the top candidate
        return res.candidates[0].id

    return None


def fuse_profiles(
    primary: ArtistProfile,
    secondary_id: Optional[str] = None,
) -> ArtistProfile:
    """
    Cross-enrich the primary profile with data from the secondary streaming provider.
    If secondary_id is not provided, automatically resolves the artist on the other platform.
    """
    fused_profile = copy.deepcopy(primary)
    other_provider = "apple" if primary.provider == "spotify" else "spotify"
    other_mod = apple_provider if other_provider == "apple" else spotify_provider

    matched_id = secondary_id or find_matching_id(primary.name, other_provider)
    if not matched_id:
        # Return profile with unfulfilled fusion note
        fused_profile.fused = False
        fused_profile.fused_providers = [primary.provider]
        fused_profile.fusion_sources = {"primary": primary.provider}
        return fused_profile

    try:
        other_profile = other_mod.fetch_artist(matched_id)
    except Exception as exc:
        logger.warning("Failed fetching %s artist %s for fusion: %s", other_provider, matched_id, exc)
        fused_profile.fused = False
        fused_profile.fused_providers = [primary.provider]
        return fused_profile

    fused_profile.fused = True
    fused_profile.fused_providers = [primary.provider, other_provider]
    sources = dict(fused_profile.fusion_sources or {})
    sources["primary"] = primary.provider
    sources["secondary"] = other_provider

    # 1. Genres: Apple provides clean primaryGenreName; Spotify public payloads lack genres
    if not fused_profile.genres and other_profile.genres:
        fused_profile.genres = list(other_profile.genres)
        sources["genres"] = other_provider
        fused_profile.availability.genre = True
    elif fused_profile.genres:
        sources["genres"] = primary.provider

    # 2. Region / Storefront hint: Apple's storefront or Spotify's top cities
    if not fused_profile.region_hint and other_profile.region_hint:
        fused_profile.region_hint = other_profile.region_hint
        sources["region_hint"] = other_provider
        fused_profile.availability.region_hint = True
    elif fused_profile.region_hint:
        sources["region_hint"] = primary.provider

    # 3. Audience Metrics: Monthly listeners, rank, followers (primarily Spotify)
    if not fused_profile.stats and other_profile.stats:
        fused_profile.stats = dict(other_profile.stats)
        sources["stats"] = other_provider
        fused_profile.availability.stats = True
    elif fused_profile.stats:
        sources["stats"] = primary.provider

    # 4. Where They Listen: Spotify top listening cities
    if not fused_profile.top_cities and other_profile.top_cities:
        fused_profile.top_cities = list(other_profile.top_cities)
        sources["top_cities"] = other_provider
    elif fused_profile.top_cities:
        sources["top_cities"] = primary.provider

    # 5. Events / Tours: Spotify concerts
    if not fused_profile.events and other_profile.events:
        fused_profile.events = list(other_profile.events)
        sources["events"] = other_provider
        fused_profile.availability.events = True
    elif fused_profile.events:
        sources["events"] = primary.provider

    # 6. External Links & Socials
    existing_links = set(fused_profile.external_links)
    for link in other_profile.external_links:
        if link not in existing_links:
            fused_profile.external_links.append(link)
            existing_links.add(link)
    # Also add the other provider's artist page if not already in external links
    if other_profile.url and other_profile.url not in existing_links:
        fused_profile.external_links.append(other_profile.url)

    # 7. Discography release years: cross-populate year from Apple if missing in Spotify
    if fused_profile.albums and other_profile.albums:
        year_by_album: dict[str, int] = {}
        for a in other_profile.albums:
            if a.year:
                year_by_album[a.name.strip().lower()] = a.year
        for a in fused_profile.albums:
            if not a.year and a.name.strip().lower() in year_by_album:
                a.year = year_by_album[a.name.strip().lower()]

    # 8. Related Artists: Merge and deduplicate
    rel_names = {r.name.lower() for r in fused_profile.related_artists}
    for r in other_profile.related_artists:
        if r.name.lower() not in rel_names:
            fused_profile.related_artists.append(r)
            rel_names.add(r.name.lower())

    # 9. Biography fallback
    if not fused_profile.biography and other_profile.biography:
        fused_profile.biography = other_profile.biography
        fused_profile.biography_source = f"{other_provider} (fused)"
        fused_profile.availability.biography = True

    # 10. Re-evaluate EPK Pre-fill Fields
    # Update Genre prefill
    genre_str = ", ".join(fused_profile.genres) if fused_profile.genres else None
    _update_or_add_prefill(
        fused_profile.prefilled,
        question="Q1 — Genre",
        target="Onboarding Q1 / EPK genre tags",
        value=genre_str,
        available=bool(genre_str),
        note=f"Cross-platform match from {sources.get('genres', 'fused source')}." if genre_str else None,
    )

    # Update Location prefill
    if fused_profile.region_hint:
        _update_or_add_prefill(
            fused_profile.prefilled,
            question="Q0a — Location",
            target="Region/location confirmation",
            value=fused_profile.region_hint,
            available=True,
            note=f"Matched storefront region from {sources.get('region_hint', 'fused source')}.",
        )

    # Update Stats prefill
    if fused_profile.stats:
        _update_or_add_prefill(
            fused_profile.prefilled,
            question="EPK stats",
            target="EPK credibility card",
            value=f"{fused_profile.stats.get('monthly_listeners', 0):,} monthly listeners",
            available=True,
            note=f"Live audience numbers from {sources.get('stats', 'Spotify')}.",
        )

    fused_profile.fusion_sources = sources
    return fused_profile


def _update_or_add_prefill(
    prefilled: list[PrefillField],
    question: str,
    target: str,
    value: Optional[str],
    available: bool,
    note: Optional[str],
) -> None:
    """Helper to update an existing prefill field in-place or append if missing."""
    for field in prefilled:
        if field.question == question:
            field.value = value
            field.available = available
            if note:
                field.note = note
            return
    prefilled.append(
        PrefillField(
            question=question,
            target=target,
            value=value,
            available=available,
            note=note,
        )
    )
