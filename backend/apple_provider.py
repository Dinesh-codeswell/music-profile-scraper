"""Apple Music provider — Python port of the Navidrome apple-music-plugin patterns.

Uses the free iTunes Search/Lookup APIs (no key) plus scraping of music.apple.com
artist pages (JSON-LD) for biography, high-res image, and similar artists. Ported
directly from apple-music-plugin-main (Go): country fallback, placeholder
biography/image detection, image size rewriting, and similar-artist markers.
"""
from __future__ import annotations

import html
import json
import re
import threading
from typing import Any, Optional
from urllib.parse import quote

import httpx

from .models import (
    AlbumEntry,
    ArtistProfile,
    Availability,
    Candidate,
    Image,
    PrefillField,
    RelatedArtist,
    ResolveResponse,
    TopTrack,
)

ITUNES_SEARCH = "https://itunes.apple.com/search"
ITUNES_LOOKUP = "https://itunes.apple.com/lookup"
APPLE_BASE = "https://music.apple.com"
COUNTRIES = ["us", "in", "gb", "de", "br", "au"]  # Global storefronts with early regional fallback
PLACEHOLDER_IMAGE_URL = "https://music.apple.com/assets/meta/apple-music.png"

_LOCK = threading.Lock()
_HTTP: Optional[httpx.Client] = None

# --- Ported helpers (from helpers.go / artist.go) ---------------------------------

_IMAGE_SIZE_RE = re.compile(r"/\d+x\d+[a-z]*\.")
_JSON_LD_OPEN = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>', re.IGNORECASE)
_APPLE_MUSIC_RE = re.compile(r"Apple\s+Music")
_OG_IMAGE = '<meta property="og:image" content="'
_SIMILAR_MARKERS = [
    'aria-label="Similar Artists"',
    'aria-label="Artistas semelhantes"',
    'aria-label="Ähnliche Künstler"',
    'aria-label="Artistes similaires"',
    'aria-label="Artistas similares"',
]
_LOCKUP_TITLE = re.compile(r'data-testid="ellipse-lockup__title"[^>]*>([^<]+)<')


def _http() -> httpx.Client:
    global _HTTP
    if _HTTP is None:
        _HTTP = httpx.Client(
            timeout=15.0,
            headers={"User-Agent": "ArtistImportStudio/1.0 (EPK import studio)"},
            follow_redirects=True,
        )
    return _HTTP


def normalize_name(name: str) -> str:
    return name.strip().lower()


def normalize_text(s: str) -> str:
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    lines = s.split("\n")
    return "\n".join(" ".join(line.split()) for line in lines).strip()


def rewrite_image_size(image_url: str, size: int) -> str:
    return _IMAGE_SIZE_RE.sub(f"/{size}x{size}bb.", image_url)


def build_image_list(base_url: str) -> list[dict[str, Any]]:
    return [
        {"url": rewrite_image_size(base_url, size), "width": size, "height": size}
        for size in (1500, 600, 300)
    ]


def is_placeholder_biography(text: str) -> bool:
    if not text:
        return False
    first_sentence = text.split(". ", 1)[0]
    return bool(_APPLE_MUSIC_RE.search(first_sentence))


def is_placeholder_image(url: str) -> bool:
    return not url or url == PLACEHOLDER_IMAGE_URL or "music.apple.com/assets" in url


def parse_json_ld(html: str) -> Optional[dict[str, Any]]:
    """Scan all JSON-LD blocks; prefer a MusicGroup/MusicArtist node."""
    best: Optional[dict[str, Any]] = None
    for m in _JSON_LD_OPEN.finditer(html):
        start = m.end()
        end = html.find("</script>", start)
        if end == -1:
            break
        block = html[start:end].strip()
        try:
            data = json.loads(block)
        except (ValueError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        node_type = str(data.get("@type", ""))
        if "MusicGroup" in node_type or "MusicArtist" in node_type:
            return data
        if best is None and data.get("name"):
            best = data
    return best


def parse_open_graph_image(html: str) -> str:
    idx = html.find(_OG_IMAGE)
    if idx == -1:
        return ""
    idx += len(_OG_IMAGE)
    end = html.find('"', idx)
    if end == -1:
        return ""
    return html[idx:end]


def parse_similar_artists(html: str) -> list[str]:
    section_start = -1
    for marker in _SIMILAR_MARKERS:
        idx = html.find(marker)
        if idx != -1:
            section_start = idx
            break
    if section_start == -1:
        return []

    section_end = min(section_start + 60000, len(html))
    section = html[section_start:section_end]
    boundary = section.find('data-testid="section-container"', 100)
    if boundary != -1:
        section = section[: boundary + 100]

    artists: list[str] = []
    seen: set[str] = set()
    for m in _LOCKUP_TITLE.findall(section):
        name = html.unescape(m.strip())
        if name and name not in seen:
            seen.add(name)
            artists.append(name)
    return artists


def parse_artist_page(html: str) -> dict[str, Any]:
    page: dict[str, Any] = {"biography": "", "image_url": "", "similar_artists": []}

    ld = parse_json_ld(html)
    if ld is not None:
        page["biography"] = normalize_text(ld.get("description") or "")
        page["image_url"] = (ld.get("image") or "").strip()

    if is_placeholder_biography(page["biography"]):
        page["biography"] = ""
    if is_placeholder_image(page["image_url"]):
        page["image_url"] = ""

    if not page["image_url"]:
        og = parse_open_graph_image(html)
        if not is_placeholder_image(og):
            page["image_url"] = og

    page["similar_artists"] = parse_similar_artists(html)
    return page


# --- iTunes API calls -------------------------------------------------------------


def itunes_search_artists(term: str, country: str = "us") -> list[dict[str, Any]]:
    url = f"{ITUNES_SEARCH}?term={quote(term)}&entity=musicArtist&limit=6&country={country}"
    resp = _http().get(url)
    resp.raise_for_status()
    return (resp.json().get("results") or []) if resp.status_code == 200 else []


def find_best_artist_match(query: str, results: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    normalized = normalize_name(query)
    first: Optional[dict[str, Any]] = None
    for r in results:
        if r.get("wrapperType") != "artist":
            continue
        if first is None:
            first = r
        if normalize_name(str(r.get("artistName", ""))) == normalized:
            return r
    return first


def itunes_lookup_top_songs(artist_id: int, limit: int = 10) -> list[dict[str, Any]]:
    url = f"{ITUNES_LOOKUP}?id={artist_id}&entity=song&sort=popular&limit={limit}"
    resp = _http().get(url)
    resp.raise_for_status()
    return (resp.json().get("results") or []) if resp.status_code == 200 else []


def itunes_lookup_albums(artist_id: int, limit: int = 10) -> list[dict[str, Any]]:
    url = f"{ITUNES_LOOKUP}?id={artist_id}&entity=album&limit={limit}"
    resp = _http().get(url)
    resp.raise_for_status()
    return (resp.json().get("results") or []) if resp.status_code == 200 else []


# --- Public API -------------------------------------------------------------------


def resolve(query: str) -> ResolveResponse:
    """Resolve an Apple Music URL/ID (single hit) or a name (candidates)."""
    query = query.strip()

    # Apple Music URL or bare numeric id
    m = re.search(r"music\.apple\.com/.+?/artist/[-a-z0-9]+/(\d+)", query, re.IGNORECASE)
    if m:
        return ResolveResponse(
            provider="apple",
            resolved=True,
            id=m.group(1),
            name=None,
            url=f"{APPLE_BASE}/us/artist/-/{m.group(1)}",
        )
    if query.isdigit():
        return ResolveResponse(
            provider="apple",
            resolved=True,
            id=query,
            name=None,
            url=f"{APPLE_BASE}/us/artist/-/{query}",
        )

    # Name search -> candidates (first country that returns results wins)
    candidates: list[Candidate] = []
    for country in COUNTRIES:
        try:
            results = itunes_search_artists(query, country)
        except Exception:
            continue
        if not results:
            continue
        for r in results:
            if r.get("wrapperType") != "artist":
                continue
            art_id = str(r.get("artistId", ""))
            if not art_id:
                continue
            candidates.append(
                Candidate(
                    id=art_id,
                    name=str(r.get("artistName", "")),
                    genre=str(r.get("primaryGenreName") or "") or None,
                    country=str(r.get("country") or "") or None,
                    image_url=str(r.get("artworkUrl100") or "") or None,
                    url=str(r.get("artistLinkUrl") or "") or None,
                )
            )
        if candidates:
            break  # first storefront with matches wins

    if not candidates:
        return ResolveResponse(provider="apple", resolved=False, candidates=[])
    if len(candidates) == 1:
        c = candidates[0]
        return ResolveResponse(
            provider="apple", resolved=True, id=c.id, name=c.name, url=c.url
        )
    return ResolveResponse(provider="apple", resolved=False, candidates=candidates)


def fetch_artist(artist_id: str, *, include_raw: bool = True) -> ArtistProfile:
    """Fetch the full artist profile from Apple Music / iTunes."""
    artist_id_int = int(artist_id)

    # 1) Identify the artist via iTunes search (name, genre, country, artwork)
    artist_info: dict[str, Any] = {}
    for country in COUNTRIES:
        try:
            results = itunes_search_artists_by_id(artist_id_int, country)
        except Exception:
            continue
        match = find_best_artist_match_by_id(artist_id_int, results)
        if match is not None:
            artist_info = match
            break

    if not artist_info:
        raise ValueError(f"Apple Music artist {artist_id} not found")

    name = str(artist_info.get("artistName") or "")
    genre = str(artist_info.get("primaryGenreName") or "") or None
    country = str(artist_info.get("country") or "") or None
    artwork100 = str(artist_info.get("artworkUrl100") or "") or None
    artist_link = str(artist_info.get("artistLinkUrl") or "") or None
    # Storefront is embedded in the artistLinkUrl: music.apple.com/<cc>/artist/...
    link_cc = re.search(r"music\.apple\.com/([a-z]{2})/artist/", artist_link or "", re.IGNORECASE)
    if not country and link_cc:
        country = link_cc.group(1)
    profile_url = artist_link or f"{APPLE_BASE}/{(country or 'us').lower()}/artist/-/{artist_id_int}"

    # 2) Artist page scrape (bio, hi-res image, similar artists) with country fallback
    page: dict[str, Any] = {"biography": "", "image_url": "", "similar_artists": []}
    for country_code in COUNTRIES:
        url = f"{APPLE_BASE}/{country_code}/artist/-/{artist_id_int}"
        try:
            resp = _http().get(url)
            if resp.status_code != 200:
                continue
            parsed = parse_artist_page(resp.text)
        except Exception:
            continue
        # keep first partial result, keep going until we have the requested fields
        if not page["biography"] and parsed["biography"]:
            page["biography"] = parsed["biography"]
        if not page["image_url"] and parsed["image_url"]:
            page["image_url"] = parsed["image_url"]
        if not page["similar_artists"] and parsed["similar_artists"]:
            page["similar_artists"] = parsed["similar_artists"]
        if page["biography"] and page["image_url"] and page["similar_artists"]:
            break

    # 3) Top songs + albums
    top_songs: list[dict[str, Any]] = []
    albums: list[dict[str, Any]] = []
    try:
        top_songs = itunes_lookup_top_songs(artist_id_int)
    except Exception:
        pass
    try:
        albums = itunes_lookup_albums(artist_id_int)
    except Exception:
        pass

    image_base = page["image_url"] or artwork100
    images = build_image_list(image_base) if image_base else []
    image_url = images[0]["url"] if images else None

    tracks: list[TopTrack] = []
    for r in top_songs:
        if r.get("wrapperType") != "track" or not r.get("trackName"):
            continue
        art = r.get("artworkUrl100")
        tracks.append(
            TopTrack(
                name=str(r.get("trackName")),
                album=str(r.get("collectionName") or "") or None,
                preview_url=str(r.get("previewUrl") or "") or None,
                explicit=bool(r.get("trackExplicitness") == "explicit"),
                play_count=None,
                duration_ms=r.get("trackTimeMillis"),
                image_url=rewrite_image_size(art, 300) if art else None,
            )
        )

    album_entries: list[AlbumEntry] = []
    for r in albums:
        if r.get("wrapperType") != "collection" or not r.get("collectionName"):
            continue
        year = None
        rd = r.get("releaseDate")
        if isinstance(rd, str) and len(rd) >= 4:
            try:
                year = int(rd[:4])
            except ValueError:
                year = None
        art = r.get("artworkUrl100")
        album_entries.append(
            AlbumEntry(
                name=str(r.get("collectionName")),
                type=str(r.get("collectionType") or "album").lower(),
                year=year,
                image_url=rewrite_image_size(art, 300) if art else None,
            )
        )

    related_artists = [
        RelatedArtist(name=n) for n in page["similar_artists"][:8]
    ]

    availability = Availability(
        genre=bool(genre),
        biography=bool(page["biography"]),
        image=bool(image_url),
        top_tracks=bool(tracks),
        albums=bool(album_entries),
        related_artists=bool(related_artists),
        events=False,  # not available from Apple Music/iTunes
        external_links=False,  # page URL only
        stats=False,
        region_hint=bool(country),
    )

    prefilled: list[PrefillField] = [
        PrefillField(
            question="Q1 — Genre",
            target="Onboarding Q1 / EPK genre tags",
            value=genre,
            available=bool(genre),
            note="primaryGenreName from iTunes Lookup/Search.",
        ),
        PrefillField(
            question="Q3 — Influencing artists",
            target="Onboarding Q3 (≤5)",
            value=", ".join(page["similar_artists"][:5]) or None,
            available=bool(related_artists),
            note="Similar artists from the Apple Music artist page.",
        ),
        PrefillField(
            question="Q8 — Bio",
            target="EPK Story (draft, editable)",
            value=(page["biography"][:200] + "…") if len(page["biography"]) > 200 else page["biography"] or None,
            available=bool(page["biography"]),
            note="Placeholder promo bios filtered out.",
        ),
        PrefillField(
            question="Profile pic",
            target="EPK Profile Pic (North Star #2)",
            value=image_url,
            available=bool(image_url),
            note="1500px image, rehosted after download.",
        ),
        PrefillField(
            question="EPK Music",
            target="EPK Music section",
            value=f"{len(tracks)} top songs" if tracks else None,
            available=bool(tracks),
            note="Top songs with 30s previews where available.",
        ),
        PrefillField(
            question="Q0a — Location",
            target="Region/location confirmation",
            value=country,
            available=bool(country),
            note="Storefront match — suggest-only confirmation.",
        ),
    ]

    raw: dict[str, Any] = {}
    if include_raw:
        raw = {
            "artist_info": artist_info,
            "page_fields": {"biography_chars": len(page["biography"]), "similar_artists": page["similar_artists"]},
            "top_songs_count": len(top_songs),
            "albums_count": len(albums),
        }

    return ArtistProfile(
        provider="apple",
        id=artist_id,
        url=profile_url,
        name=name or (f"Artist {artist_id}"),
        image_url=image_url,
        images=[Image(**i) for i in images],
        genres=[genre] if genre else [],
        region_hint=country,
        biography=page["biography"] or None,
        biography_source="apple" if page["biography"] else None,
        stats={},
        top_tracks=tracks,
        albums=album_entries,
        related_artists=related_artists,
        events=[],
        external_links=[],
        availability=availability,
        prefilled=prefilled,
        raw=raw,
    )


def itunes_search_artists_by_id(artist_id: int, country: str = "us") -> list[dict[str, Any]]:
    """Lookup an artist by ID via the iTunes Lookup API."""
    url = f"{ITUNES_LOOKUP}?id={artist_id}&country={country}"
    resp = _http().get(url)
    resp.raise_for_status()
    return (resp.json().get("results") or []) if resp.status_code == 200 else []


def find_best_artist_match_by_id(
    artist_id: int, results: list[dict[str, Any]]
) -> Optional[dict[str, Any]]:
    for r in results:
        if r.get("wrapperType") == "artist" and str(r.get("artistId", "")) == str(artist_id):
            return r
    return None
