"""Streaming Import Test Dashboard — FastAPI backend.

Endpoints:
  GET  /api/health
  GET  /api/providers                      capability matrix (for the UI)
  POST /api/import/resolve                 query -> id or disambiguation candidates
  GET  /api/import/{provider}/{id}         full scraped profile (cached 24h)
  POST /api/import/refresh                 force re-scrape (bypass cache)
  POST /api/import/apply                   test-mode: what would be written to onboarding/EPK

Serves the static frontend from ../frontend.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from spotify_scraper.errors import (
    NetworkError as SpotifyNetworkError,
    NotFoundError as SpotifyNotFoundError,
    ParsingError as SpotifyParsingError,
    URLError as SpotifyURLError,
)

from . import apple_provider, fusion, geo, spotify_provider
from .cache import TTLCache
from .models import ApplyRequest, ApplyResponse, ArtistProfile, ResolveRequest, ResolveResponse
from .filter_api import router as filter_router

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(
    title="Artist Import Studio",
    description="Streaming profile ingestion, cross-platform fusion (Spotify + Apple Music), "
    "and Electronic Press Kit (EPK) generator.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(filter_router)

_cache = TTLCache(ttl_positive=86400, ttl_negative=7200)

_PROVIDERS = {
    "spotify": {
        "label": "Spotify",
        "engine": "spotifyscraper (anonymous, no API key)",
        "capabilities": {
            "genre": False,
            "biography": True,
            "image": True,
            "top_tracks": True,
            "albums": True,
            "related_artists": True,
            "events": True,
            "external_links": True,
            "stats": True,
            "region_hint": False,
        },
        "note": "Genres removed from Spotify's public payloads (repo CHANGELOG); no location.",
    },
    "apple": {
        "label": "Apple Music",
        "engine": "iTunes Search/Lookup (free, no key) + music.apple.com page scrape (ported from Go plugin)",
        "capabilities": {
            "genre": True,
            "biography": True,
            "image": True,
            "top_tracks": True,
            "albums": True,
            "related_artists": True,
            "events": False,
            "external_links": False,
            "stats": False,
            "region_hint": True,
        },
        "note": "Genre via primaryGenreName; region hint from storefront match; no concerts/stats.",
    },
    "fused": {
        "label": "⚡ Fused (Spotify + Apple)",
        "engine": "Dual-Provider Real-Time Fusion",
        "capabilities": {
            "genre": True,
            "biography": True,
            "image": True,
            "top_tracks": True,
            "albums": True,
            "related_artists": True,
            "events": True,
            "external_links": True,
            "stats": True,
            "region_hint": True,
        },
        "note": "Cross-platform synthesis: Apple Music genres & storefronts merged with Spotify listeners, top cities & audio previews.",
    },
}


def _provider_module(provider: str):
    if provider == "spotify":
        return spotify_provider
    if provider == "apple":
        return apple_provider
    raise HTTPException(status_code=400, detail={"code": "INVALID_PROVIDER", "message": f"Unknown provider: {provider}"})


def _cache_key(provider: str, obj_id: str) -> str:
    return f"{provider}:profile:{obj_id}"


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "time": dt.datetime.now(dt.timezone.utc).isoformat(),
        "cache": _cache.stats(),
    }


@app.get("/api/providers")
def providers() -> dict[str, Any]:
    return {"providers": _PROVIDERS}


@app.post("/api/import/resolve")
def resolve(req: ResolveRequest) -> ResolveResponse:
    prov = req.provider.lower().strip()
    if prov == "fused":
        is_apple = "music.apple.com" in req.query.lower() or (req.query.isdigit() and len(req.query) > 5)
        primary = "apple" if is_apple else "spotify"
        mod = apple_provider if primary == "apple" else spotify_provider
        try:
            result = mod.resolve(req.query)
            if not result.resolved and not result.candidates:
                alt_mod = spotify_provider if primary == "apple" else apple_provider
                alt_res = alt_mod.resolve(req.query)
                if alt_res.resolved or alt_res.candidates:
                    result = alt_res
                    primary = "spotify" if primary == "apple" else "apple"
            result.provider = primary
            return result
        except Exception as exc:
            raise HTTPException(status_code=502, detail={"code": "PROVIDER_ERROR", "message": str(exc)}) from exc

    mod = _provider_module(prov)
    try:
        result = mod.resolve(req.query)
    except Exception as exc:  # noqa: BLE001 — map any provider error to a typed failure
        raise HTTPException(status_code=502, detail={"code": "PROVIDER_ERROR", "message": str(exc)}) from exc
    return result


@app.get("/api/import/{provider}/{obj_id}")
def fetch(provider: str, obj_id: str) -> ArtistProfile:
    mod = _provider_module(provider.lower().strip())

    key = _cache_key(provider, obj_id)
    cached = _cache.get(key)
    if cached is not None:
        if _cache.is_negative(cached):
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": f"{provider}: artist {obj_id} not found (negative cache)"})
        profile = cached
        profile.cache_hit = True
        return profile

    try:
        profile = mod.fetch_artist(obj_id)
    except Exception as exc:  # noqa: BLE001
        raise _provider_http_error(exc, provider, obj_id, set_negative_key=key) from exc

    profile.fetched_at = dt.datetime.now(dt.timezone.utc).isoformat()
    _cache.set(key, profile)
    return profile


@app.get("/api/import/fusion/{provider}/{obj_id}")
def fetch_fused(provider: str, obj_id: str) -> ArtistProfile:
    """Fetch profile and cross-enrich with the other streaming provider."""
    primary_profile = fetch(provider, obj_id)
    key = f"fused:{provider}:{obj_id}"
    cached = _cache.get(key)
    if cached is not None:
        cached.cache_hit = True
        return cached

    try:
        fused = fusion.fuse_profiles(primary_profile)
    except Exception as exc:
        raise HTTPException(status_code=502, detail={"code": "FUSION_ERROR", "message": str(exc)}) from exc

    fused.fetched_at = dt.datetime.now(dt.timezone.utc).isoformat()
    _cache.set(key, fused)
    return fused


@app.get("/api/epk/{provider}/{obj_id}")
def epk_data(provider: str, obj_id: str, fuse: bool = True) -> dict[str, Any]:
    """Return high-fidelity Electronic Press Kit (EPK) structured payload."""
    if fuse:
        try:
            profile = fetch_fused(provider, obj_id)
        except Exception:
            profile = fetch(provider, obj_id)
    else:
        profile = fetch(provider, obj_id)

    stats = profile.stats or {}
    monthly_listeners = stats.get("monthly_listeners")
    followers = stats.get("followers")
    world_rank = stats.get("world_rank")
    top_city = profile.top_cities[0].city if profile.top_cities else None

    parts = [profile.name]
    if profile.genres:
        parts.append(f"is a {profile.genres[0]} artist")
    else:
        parts.append("is an independent recording artist")
    if profile.region_hint:
        parts.append(f"based in or connected to {profile.region_hint.upper()}")
    summary = " ".join(parts) + "."
    if monthly_listeners:
        summary += f" Currently reaching over {monthly_listeners:,} monthly listeners"
        if top_city:
            summary += f", with a strong audience base in {top_city}."
        else:
            summary += " worldwide."

    return {
        "artist": profile.model_dump(),
        "highlights": {
            "name": profile.name,
            "provider": profile.provider,
            "id": profile.id,
            "genres": profile.genres,
            "primary_genre": profile.genres[0] if profile.genres else "Independent",
            "region": profile.region_hint,
            "monthly_listeners": monthly_listeners,
            "followers": followers,
            "world_rank": world_rank,
            "top_city": top_city,
            "is_verified": profile.is_verified,
            "fused": profile.fused,
            "fused_providers": profile.fused_providers,
            "fusion_sources": profile.fusion_sources,
        },
        "one_sheet_summary": summary,
        "press_bio": profile.biography or f"{profile.name} is a recording artist streaming across global platforms.",
        "featured_tracks": [t.model_dump() for t in profile.top_tracks[:10]],
        "discography": [a.model_dump() for a in profile.albums[:12]],
        "top_cities": [c.model_dump() for c in profile.top_cities],
        "tour_dates": [e.model_dump() for e in profile.events],
        "press_assets": {
            "avatar": profile.image_url,
            "images": [img.model_dump() for img in profile.images],
            "banner_images": [img.model_dump() for img in profile.banner_images],
            "gallery_images": [img.model_dump() for img in profile.gallery_images],
        },
        "contact": {
            "external_links": profile.external_links,
            "streaming_url": profile.url,
            "booking_email": "booking@artist-press.com",
        },
    }


@app.post("/api/import/refresh")
def refresh(req: ResolveRequest) -> ArtistProfile:
    """Force a fresh scrape for an already-resolved id (bypasses cache)."""
    mod = _provider_module(req.provider.lower().strip())
    obj_id = req.query
    _cache.delete(_cache_key(req.provider, obj_id))
    _cache.delete(f"fused:{req.provider}:{obj_id}")
    try:
        profile = mod.fetch_artist(obj_id)
    except Exception as exc:  # noqa: BLE001
        raise _provider_http_error(exc, req.provider, obj_id) from exc
    profile.fetched_at = dt.datetime.now(dt.timezone.utc).isoformat()
    _cache.set(_cache_key(req.provider, obj_id), profile)
    return profile


@app.post("/api/import/apply")
def apply(req: ApplyRequest) -> ApplyResponse:
    """Test-mode apply: shows what would be written to onboarding/EPK. No real writes."""
    mod = _provider_module(req.provider.lower().strip())

    # Reuse cache if present, else fetch
    cached = _cache.get(_cache_key(req.provider, req.id))
    if cached is not None and not _cache.is_negative(cached):
        profile = cached
    else:
        try:
            profile = mod.fetch_artist(req.id)
        except Exception as exc:  # noqa: BLE001
            raise _provider_http_error(exc, req.provider, req.id) from exc

    allowed = {"Q1 — Genre", "Q3 — Influencing artists", "Q8 — Bio", "Profile pic",
               "EPK Music", "Q10 — Performances", "Q12 — Contact links", "EPK stats",
               "Q0a — Location"}
    wanted = set(req.confirmed_fields)
    chosen = [f for f in profile.prefilled if f.available and (not wanted or f.question in wanted)]

    applied: dict[str, Any] = {}
    for f in chosen:
        applied[f.question] = {
            "target": f.target,
            "value": f.value,
            "note": f.note,
        }

    has_pic = any(f.question == "Profile pic" and f.available for f in chosen)
    has_story = any(f.question == "Q8 — Bio" and f.available for f in chosen)
    has_content = any(f.question == "EPK Music" and f.available for f in chosen)

    north_star = {
        "1_profile_info": "Real name present (already captured at signup)",
        "2_pic_or_banner": has_pic,
        "3_story": has_story,
        "4_content": has_content,
        "meets_all": bool(has_pic and has_story and has_content),
        "comment": "Import alone satisfies criteria 2–4 when pic + bio + tracks are confirmed.",
    }

    return ApplyResponse(provider=req.provider, id=req.id, applied=applied, north_star_impact=north_star)


def _provider_http_error(exc: Exception, provider: str, obj_id: str, set_negative_key: Optional[str] = None):
    """Map provider exceptions to typed HTTP errors."""
    code = "PROVIDER_ERROR"
    status = 502
    message = str(exc) or exc.__class__.__name__
    if isinstance(exc, SpotifyURLError):
        code, status = "INVALID_INPUT", 400
        message = f"Invalid Spotify reference: {obj_id}"
    elif isinstance(exc, SpotifyNotFoundError):
        code, status = "NOT_FOUND", 404
        message = f"spotify: artist {obj_id} not found"
        if set_negative_key:
            _cache.set_negative(set_negative_key)
    elif isinstance(exc, SpotifyNetworkError) or "timed out" in message.lower() or "timeout" in message.lower():
        code = "TIMEOUT" if "timeout" in message.lower() else "NETWORK"
        status = 504 if code == "TIMEOUT" else 502
    elif isinstance(exc, SpotifyParsingError):
        code, status = "PARSE", 502
    elif "rate" in message.lower():
        code, status = "RATE_LIMITED", 429
    elif "not found" in message.lower():
        code, status = "NOT_FOUND", 404
    return HTTPException(status_code=status, detail={"code": code, "message": message})


@app.get("/api/geo/tour-analysis/{provider}/{obj_id}")
def tour_analysis(provider: str, obj_id: str) -> dict[str, Any]:
    """Return geographic audience heatmap and unserved tour opportunity analysis."""
    try:
        profile = fetch_fused(provider, obj_id)
    except Exception:
        profile = fetch(provider, obj_id)
    return geo.analyze_tour_opportunities(profile)


@app.get("/api/oembed")
def oembed_endpoint(url: str, format: str = "json", maxwidth: int = 480, maxheight: int = 160) -> dict[str, Any]:
    """Standard oEmbed endpoint for publishing platforms and CMS embeds."""
    # Example URL: http://domain/epk/spotify/4tZwfgrHOc3mvqYlEYSvVi or /embed/...
    parts = url.split("?")[0].rstrip("/").split("/")
    obj_id = parts[-1] if parts else ""
    provider = parts[-2] if len(parts) >= 2 and parts[-2] in ("spotify", "apple", "fused") else "spotify"

    try:
        profile = fetch(provider, obj_id)
        artist_name = profile.name
    except Exception:
        artist_name = "Artist Preview"

    embed_src = f"/embed/{provider}/{obj_id}"
    html = f'<iframe src="{embed_src}" width="{maxwidth}" height="{maxheight}" frameborder="0" allow="autoplay; encrypted-media"></iframe>'

    return {
        "version": "1.0",
        "type": "rich",
        "provider_name": "Artist Import Studio",
        "provider_url": "/",
        "title": f"{artist_name} — Streaming Preview & EPK",
        "author_name": artist_name,
        "width": maxwidth,
        "height": maxheight,
        "html": html,
    }


# --- Static frontend, EPK & Embed routes -------------------------------------------

if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR), name="assets")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "index.html")

    @app.get("/epk", include_in_schema=False)
    @app.get("/epk/{provider}/{obj_id}", include_in_schema=False)
    def epk_page(provider: Optional[str] = None, obj_id: Optional[str] = None) -> FileResponse:
        epk_file = FRONTEND_DIR / "epk.html"
        if epk_file.exists():
            return FileResponse(epk_file)
        return FileResponse(FRONTEND_DIR / "index.html")

    @app.get("/embed", include_in_schema=False)
    @app.get("/embed/{provider}/{obj_id}", include_in_schema=False)
    def embed_page(provider: Optional[str] = None, obj_id: Optional[str] = None) -> FileResponse:
        embed_file = FRONTEND_DIR / "embed.html"
        if embed_file.exists():
            return FileResponse(embed_file)
        return FileResponse(FRONTEND_DIR / "index.html")

    @app.get("/filter", include_in_schema=False)
    @app.get("/csv-filter", include_in_schema=False)
    @app.get("/filter-studio", include_in_schema=False)
    def filter_page() -> FileResponse:
        filter_file = FRONTEND_DIR / "filter.html"
        if filter_file.exists():
            return FileResponse(filter_file)
        return FileResponse(FRONTEND_DIR / "index.html")
else:
    @app.get("/", include_in_schema=False)
    def index() -> dict[str, str]:
        return {"message": "frontend/ not found; API is available under /api"}
