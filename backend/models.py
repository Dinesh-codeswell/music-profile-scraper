"""Unified data models shared across providers and the API."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class Image(BaseModel):
    url: str
    width: Optional[int] = None
    height: Optional[int] = None


class TopTrack(BaseModel):
    name: str
    album: Optional[str] = None
    preview_url: Optional[str] = None
    explicit: bool = False
    play_count: Optional[int] = None
    duration_ms: Optional[int] = None
    image_url: Optional[str] = None


class AlbumEntry(BaseModel):
    name: str
    type: Optional[str] = None  # "album" | "single" | Apple collectionType
    year: Optional[int] = None  # Apple only (from releaseDate); Spotify path: None
    image_url: Optional[str] = None


class RelatedArtist(BaseModel):
    name: str
    id: Optional[str] = None
    url: Optional[str] = None
    image_url: Optional[str] = None


class TopCity(BaseModel):
    city: str
    country: Optional[str] = None
    region: Optional[str] = None
    listeners: Optional[int] = None


class PinnedItem(BaseModel):
    name: Optional[str] = None
    comment: Optional[str] = None
    image_url: Optional[str] = None


class EventEntry(BaseModel):
    title: str
    city: Optional[str] = None
    start_date: Optional[str] = None


class Availability(BaseModel):
    genre: bool = False
    biography: bool = False
    image: bool = False
    top_tracks: bool = False
    albums: bool = False
    related_artists: bool = False
    events: bool = False
    external_links: bool = False
    stats: bool = False
    region_hint: bool = False


class PrefillField(BaseModel):
    question: str  # e.g. "Q1 — Genre"
    target: str  # e.g. "Onboarding Q1 / EPK genre tags"
    value: Optional[str] = None
    available: bool = False
    note: Optional[str] = None


class ArtistProfile(BaseModel):
    provider: str  # "spotify" | "apple"
    id: str
    url: str
    name: str
    image_url: Optional[str] = None
    images: list[Image] = []
    genres: list[str] = []
    region_hint: Optional[str] = None
    biography: Optional[str] = None
    biography_source: Optional[str] = None
    stats: dict[str, Any] = {}
    top_tracks: list[TopTrack] = []
    albums: list[AlbumEntry] = []
    related_artists: list[RelatedArtist] = []
    top_cities: list[TopCity] = []
    banner_images: list[Image] = []
    gallery_images: list[Image] = []
    is_verified: bool = False
    pinned_item: Optional[PinnedItem] = None
    appears_on_count: int = 0
    featuring_count: int = 0
    compilations: list[AlbumEntry] = []
    copyright: Optional[str] = None
    brand_colors: dict[str, str] = {}
    events: list[EventEntry] = []
    external_links: list[str] = []
    availability: Availability = Availability()
    prefilled: list[PrefillField] = []
    raw: dict[str, Any] = {}
    fetched_at: str = ""
    cache_hit: bool = False
    fused: bool = False
    fused_providers: list[str] = []
    fusion_sources: dict[str, str] = {}


class Candidate(BaseModel):
    id: str
    name: str
    genre: Optional[str] = None
    country: Optional[str] = None
    image_url: Optional[str] = None
    url: Optional[str] = None


class ResolveRequest(BaseModel):
    provider: str  # "spotify" | "apple"
    query: str  # URL / URI / ID / artist name


class ResolveResponse(BaseModel):
    provider: str
    resolved: bool = False
    id: Optional[str] = None
    name: Optional[str] = None
    url: Optional[str] = None
    candidates: list[Candidate] = []


class ApplyRequest(BaseModel):
    provider: str
    id: str
    confirmed_fields: list[str] = []  # subset of field keys; empty = all available


class ApplyResponse(BaseModel):
    provider: str
    id: str
    applied: dict[str, Any]  # what would be written to onboarding/EPK
    north_star_impact: dict[str, Any]  # which North Star criteria the import satisfies
