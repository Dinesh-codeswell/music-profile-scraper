"""Spotify provider — wraps the local spotifyscraper library (anonymous, no API key).

Read-only public data only: artist profile, images, biography, stats, top tracks,
albums/singles, related artists, upcoming concerts, external links. Genres are NOT
available from Spotify's public payloads (see repo CHANGELOG).
"""
from __future__ import annotations

import dataclasses
import threading
from typing import Any, Optional

from spotify_scraper import SpotifyClient
from spotify_scraper.errors import NotFoundError, SpotifyScraperError, URLError

# Ensure artist.top_cities is readable whether the installed spotifyscraper
# ships the field (patched local editable install) or not (PyPI on Vercel).
from .spotify_topcities_shim import patch_artist_top_cities

patch_artist_top_cities()

from .models import (
    AlbumEntry,
    ArtistProfile,
    Availability,
    Candidate,
    EventEntry,
    Image,
    PinnedItem,
    PrefillField,
    RelatedArtist,
    ResolveResponse,
    TopCity,
    TopTrack,
)

_LOCK = threading.Lock()
_CLIENT: Optional[SpotifyClient] = None


def _client() -> SpotifyClient:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = SpotifyClient()  # anonymous, per-host rate limits built in
    return _CLIENT


def _to_dict(obj: Any) -> Any:
    """JSON-safe to_dict if the model provides it, else dataclasses.asdict."""
    to_dict = getattr(obj, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    if dataclasses.is_dataclass(obj):
        return dataclasses.asdict(obj)
    return str(obj)


def _looks_like_spotify_ref(query: str) -> bool:
    q = query.strip().lower()
    return (
        q.startswith("https://open.spotify.com/")
        or q.startswith("http://open.spotify.com/")
        or q.startswith("spotify:artist:")
        or (len(q) == 22 and q.isalnum())
    )


def resolve(query: str) -> ResolveResponse:
    """Resolve a Spotify URL/URI/ID (single hit) or a name (candidates)."""
    query = query.strip()
    with _LOCK:
        client = _client()
        # Direct reference?
        if _looks_like_spotify_ref(query):
            try:
                artist = client.get_artist(query)
                return ResolveResponse(
                    provider="spotify",
                    resolved=True,
                    id=artist.id,
                    name=artist.name,
                    url=artist.url,
                )
            except (NotFoundError, URLError, SpotifyScraperError):
                return ResolveResponse(provider="spotify", resolved=False, candidates=[])

        # Name search -> candidates
        try:
            results = client.search(query, types=("artist",), limit=6)
        except SpotifyScraperError:
            return ResolveResponse(provider="spotify", resolved=False, candidates=[])
        candidates: list[Candidate] = []
        for a in results.artists:
            image_url = a.images[0].url if a.images else None
            candidates.append(
                Candidate(id=a.id, name=a.name, image_url=image_url, url=a.url)
            )
        if not candidates:
            return ResolveResponse(provider="spotify", resolved=False, candidates=[])
        if len(candidates) == 1:
            c = candidates[0]
            return ResolveResponse(
                provider="spotify", resolved=True, id=c.id, name=c.name, url=c.url
            )
        return ResolveResponse(provider="spotify", resolved=False, candidates=candidates)


def fetch_artist(artist_id: str, *, include_raw: bool = True) -> ArtistProfile:
    """Fetch the full artist profile from Spotify."""
    with _LOCK:
        client = _client()
        artist = client.get_artist(artist_id)

        related: list[Any] = []
        events: list[Any] = []
        try:
            related = list(client.get_related_artists(artist_id))
        except SpotifyScraperError:
            pass
        try:
            events = list(client.get_artist_events(artist_id))
        except SpotifyScraperError:
            pass

    images = [Image(url=i.url, width=i.width, height=i.height) for i in artist.images]
    image_url = max(images, key=lambda i: i.width or 0).url if images else None

    top_tracks = [
        TopTrack(
            name=t.name,
            album=t.album.name if t.album else None,
            preview_url=t.preview_url,
            explicit=bool(t.explicit),
            play_count=t.play_count,
            duration_ms=t.duration_ms,
            image_url=t.images[0].url if t.images else None,
        )
        for t in artist.top_tracks
    ]

    albums: list[AlbumEntry] = []
    albums += [
        AlbumEntry(name=a.name, type="album", image_url=a.images[0].url if a.images else None)
        for a in artist.albums
    ]
    albums += [
        AlbumEntry(name=a.name, type="single", image_url=a.images[0].url if a.images else None)
        for a in artist.singles
    ]

    related_artists = [
        RelatedArtist(
            name=r.name,
            id=r.id,
            url=r.url,
            image_url=r.images[0].url if r.images else None,
        )
        for r in related[:8]
    ]

    event_entries = [
        EventEntry(title=e.title, city=e.city, start_date=e.start_date) for e in events[:10]
    ]

    top_cities = [
        TopCity(city=c.city, country=c.country, region=c.region, listeners=c.listeners)
        for c in getattr(artist, "top_cities", ())
    ]

    banner_images = [
        Image(url=i.url, width=i.width, height=i.height)
        for i in getattr(artist, "banner_images", ())
    ]

    gallery_images = [
        Image(url=i.url, width=i.width, height=i.height)
        for i in getattr(artist, "gallery_images", ())
    ]

    is_verified = getattr(artist, "is_verified", False)

    pinned_item = None
    pin_name = getattr(artist, "pinned_item_name", None)
    pin_comment = getattr(artist, "pinned_item_comment", None)
    pin_image = getattr(artist, "pinned_item_image", None)
    if pin_name or pin_comment:
        pinned_item = PinnedItem(name=pin_name, comment=pin_comment, image_url=pin_image)

    appears_on_count = getattr(artist, "appears_on_count", 0)
    featuring_count = getattr(artist, "featuring_count", 0)

    compilations = [
        AlbumEntry(name=c.name, type="compilation", image_url=c.images[0].url if c.images else None)
        for c in getattr(artist, "compilations", ())
    ]

    copyright_text = getattr(artist, "copyright", None)
    brand_colors = getattr(artist, "brand_colors", {})

    external_links = list(artist.external_links)

    stats: dict[str, Any] = {}
    if artist.followers is not None:
        stats["followers"] = artist.followers
    if artist.monthly_listeners is not None:
        stats["monthly_listeners"] = artist.monthly_listeners
    if artist.world_rank is not None:
        stats["world_rank"] = artist.world_rank

    availability = Availability(
        genre=False,  # Spotify does not expose genres (verified in library source)
        biography=bool(artist.biography),
        image=bool(image_url),
        top_tracks=bool(top_tracks),
        albums=bool(albums),
        related_artists=bool(related_artists),
        events=bool(event_entries),
        external_links=bool(external_links),
        stats=bool(stats),
        region_hint=False,
    )

    prefilled: list[PrefillField] = [
        PrefillField(
            question="Q1 — Genre",
            target="Onboarding Q1 / EPK genre tags",
            available=False,
            note="Spotify does not expose genres; import from Apple Music or pick manually.",
        ),
        PrefillField(
            question="Q3 — Influencing artists",
            target="Onboarding Q3 (≤5)",
            value=", ".join(r.name for r in related_artists[:5]) or None,
            available=bool(related_artists),
            note="From Spotify related artists." if related_artists else "None found.",
        ),
        PrefillField(
            question="Q8 — Bio",
            target="EPK Story (draft, editable)",
            value=(artist.biography[:200] + "…") if artist.biography and len(artist.biography) > 200 else artist.biography,
            available=bool(artist.biography),
            note="Drafted into the bio builder; artist confirms before save.",
        ),
        PrefillField(
            question="Profile pic",
            target="EPK Profile Pic (North Star #2)",
            value=image_url,
            available=bool(image_url),
            note="Downloaded + rehosted; confirmed by artist.",
        ),
        PrefillField(
            question="EPK Music",
            target="EPK Music section",
            value=f"{len(top_tracks)} top tracks" if top_tracks else None,
            available=bool(top_tracks),
            note="Top tracks with 30s previews.",
        ),
        PrefillField(
            question="Q10 — Performances",
            target="EPK Live Performances / upcoming shows",
            value=", ".join(f"{e.city or e.title}" for e in event_entries[:5]) or None,
            available=bool(event_entries),
            note="From upcoming concerts (city + date).",
        ),
        PrefillField(
            question="Q12 — Contact links",
            target="EPK Business Enquiries (validated)",
            value=", ".join(external_links[:5]) or None,
            available=bool(external_links),
            note="External links from the artist profile.",
        ),
        PrefillField(
            question="EPK stats",
            target="EPK credibility strip (display-only)",
            value=", ".join(f"{k}={v}" for k, v in stats.items()) or None,
            available=bool(stats),
            note="Followers / monthly listeners / world rank, with as-of timestamp.",
        ),
        PrefillField(
            question="EPK Banner",
            target="EPK Banner Image (North Star visual)",
            value=banner_images[0].url if banner_images else None,
            available=bool(banner_images),
            note=f"{len(banner_images)} banner images found." if banner_images else "No banner image.",
        ),
        PrefillField(
            question="EPK Gallery",
            target="EPK Photo Gallery",
            value=f"{len(gallery_images)} photos" if gallery_images else None,
            available=bool(gallery_images),
            note="Artist-uploaded gallery photos.",
        ),
        PrefillField(
            question="Verified Badge",
            target="EPK credibility indicator",
            value="Verified" if is_verified else None,
            available=is_verified,
            note="Spotify artist verification status.",
        ),
    ]

    raw: dict[str, Any] = {}
    if include_raw:
        raw = {
            "artist": _to_dict(artist),
            "related_artist_names": [r.name for r in related],
            "events": [_to_dict(e) for e in events],
        }

    return ArtistProfile(
        provider="spotify",
        id=artist.id,
        url=artist.url or f"https://open.spotify.com/artist/{artist.id}",
        name=artist.name,
        image_url=image_url,
        images=images,
        biography=artist.biography,
        biography_source="spotify" if artist.biography else None,
        stats=stats,
        top_tracks=top_tracks,
        albums=albums,
        related_artists=related_artists,
        top_cities=top_cities,
        banner_images=banner_images,
        gallery_images=gallery_images,
        is_verified=is_verified,
        pinned_item=pinned_item,
        appears_on_count=appears_on_count,
        featuring_count=featuring_count,
        compilations=compilations,
        copyright=copyright_text,
        brand_colors=brand_colors,
        events=event_entries,
        external_links=external_links,
        availability=availability,
        prefilled=prefilled,
        raw=raw,
    )
