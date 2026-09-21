"""Compatibility shim: expose Spotify artist extended fields.

The vendored ``spotifyscraper`` source (``SpotifyScraper-master/``) has been
patched to parse banner images, gallery, verification, pinned item, appears-on
counts, compilations, copyright, and brand colours from the pathfinder
GraphQL response — but deployments (Vercel) install the library from **PyPI**,
which does not ship those fields. This shim patches the artist parser
**in-process at import time** so the rest of the backend can always read
these fields identically locally and on deployed servers.

It is idempotent and self-detecting: if the installed library already exposes
the fields (patched local editable install), it is a no-op.
"""
from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from spotify_scraper.api import parse_entities
from spotify_scraper.models.artist import Artist
from spotify_scraper.models.base import ModelBase
from spotify_scraper.models.common import Image


@dataclass(frozen=True, slots=True)
class TopCity(ModelBase):
    """Top listening city, mirroring ``spotify_scraper.models.common.TopCity``."""

    city: str
    country: str | None = None
    region: str | None = None
    listeners: int | None = None


# The full set of fields the shim may add
_EXTRA_FIELDS = {
    "top_cities": "tuple", "banner_images": "tuple", "gallery_images": "tuple",
    "is_verified": "bool", "pinned_item_name": "str", "pinned_item_comment": "str",
    "pinned_item_image": "str", "appears_on_count": "int", "featuring_count": "int",
    "compilations": "tuple", "copyright": "str", "brand_colors": "dict",
}


def _extract_images(sources: Any) -> tuple[Image, ...]:
    if not isinstance(sources, Sequence):
        return ()
    return tuple(
        Image(url=str(s["url"]), width=s.get("maxWidth", s.get("width")), height=s.get("maxHeight", s.get("height")))
        for s in sources if isinstance(s, Mapping) and "url" in s
    )


def _extract_extended(union: Mapping[str, Any]) -> dict[str, Any]:
    """Extract all extended fields from the raw GraphQL union."""
    result: dict[str, Any] = {}

    # top_cities
    stats = union.get("stats") if isinstance(union, Mapping) else None
    if isinstance(stats, Mapping):
        node = stats.get("topCities")
        if isinstance(node, Mapping):
            cities = []
            for item in (node.get("items") or []):
                if isinstance(item, Mapping) and item.get("city"):
                    cities.append(TopCity(
                        city=str(item["city"]), country=item.get("country"),
                        region=item.get("region"), listeners=item.get("numberOfListeners"),
                    ))
            result["top_cities"] = tuple(cities)

    # banner_images
    hi = union.get("headerImage") if isinstance(union, Mapping) else None
    if isinstance(hi, Mapping):
        data = hi.get("data")
        if isinstance(data, Mapping):
            imgs = _extract_images(data.get("sources"))
            if imgs:
                result["banner_images"] = imgs
    if "banner_images" not in result:
        vi = union.get("visualIdentity") if isinstance(union, Mapping) else None
        if isinstance(vi, Mapping):
            wfbi = vi.get("wideFullBleedImage")
            if isinstance(wfbi, Mapping):
                result["banner_images"] = _extract_images(wfbi.get("sources"))

    # gallery_images
    visuals = union.get("visuals") if isinstance(union, Mapping) else None
    if isinstance(visuals, Mapping):
        gallery = visuals.get("gallery")
        if isinstance(gallery, Mapping):
            images = []
            for item in (gallery.get("items") or []):
                if isinstance(item, Mapping):
                    images.extend(_extract_images(item.get("sources")))
            result["gallery_images"] = tuple(images)

    # is_verified
    rep = union.get("onPlatformReputationTrait") if isinstance(union, Mapping) else None
    if isinstance(rep, Mapping):
        verif = rep.get("verification")
        if isinstance(verif, Mapping):
            result["is_verified"] = bool(verif.get("isVerified", False))

    # pinned item
    profile = union.get("profile") if isinstance(union, Mapping) else None
    if isinstance(profile, Mapping):
        pinned = profile.get("pinnedItem")
        if isinstance(pinned, Mapping):
            result["pinned_item_comment"] = pinned.get("comment")
            item_v2 = pinned.get("itemV2")
            if isinstance(item_v2, Mapping):
                data = item_v2.get("data")
                if isinstance(data, Mapping):
                    result["pinned_item_name"] = data.get("name")
            bg = pinned.get("backgroundImageV2")
            if isinstance(bg, Mapping):
                data = bg.get("data")
                if isinstance(data, Mapping):
                    sources = data.get("sources")
                    if isinstance(sources, Sequence) and sources:
                        first = sources[0]
                        if isinstance(first, Mapping) and "url" in first:
                            result["pinned_item_image"] = str(first["url"])

    # appears_on / featuring counts
    rc = union.get("relatedContent") if isinstance(union, Mapping) else None
    if isinstance(rc, Mapping):
        for key, field_name in [("appearsOn", "appears_on_count"), ("featuringV2", "featuring_count")]:
            node = rc.get(key)
            if isinstance(node, Mapping):
                result[field_name] = node.get("totalCount", 0)

    # compilations
    disc = union.get("discography") if isinstance(union, Mapping) else None
    if isinstance(disc, Mapping):
        comp = disc.get("compilations")
        if isinstance(comp, Mapping):
            items = comp.get("items", [])
            releases = []
            for item in items:
                if isinstance(item, Mapping):
                    rels = item.get("releases", {}).get("items", []) if isinstance(item.get("releases"), Mapping) else []
                    for rel in rels:
                        if isinstance(rel, Mapping) and rel.get("uri"):
                            name = rel.get("name", "")
                            rid = rel.get("id", "")
                            ruri = rel.get("uri", "")
                            images_data = rel.get("coverArt", {}).get("sources", []) if isinstance(rel.get("coverArt"), Mapping) else []
                            images = _extract_images(images_data)
                            releases.append({"id": rid, "uri": ruri, "name": name, "images": images})
            result["compilations"] = tuple(
                type("AlbumRef", (), {"id": r["id"], "uri": r["uri"], "name": r["name"], "images": r["images"]})()
                for r in releases
            )

    # copyright
    if isinstance(disc, Mapping):
        latest = disc.get("latest")
        if isinstance(latest, Mapping):
            cp = latest.get("copyright")
            if isinstance(cp, Mapping):
                items = cp.get("items", [])
                if isinstance(items, Sequence) and items:
                    first = items[0]
                    if isinstance(first, Mapping) and first.get("text"):
                        result["copyright"] = str(first["text"])

    # brand_colors
    vi = union.get("visualIdentity") if isinstance(union, Mapping) else None
    if isinstance(vi, Mapping):
        wfbi = vi.get("wideFullBleedImage")
        if isinstance(wfbi, Mapping):
            color_set = wfbi.get("extractedColorSet")
            if isinstance(color_set, Mapping):
                colors = {}
                for key, val in color_set.items():
                    if isinstance(val, str):
                        colors[key] = val
                    elif isinstance(val, Mapping) and "hex" in val:
                        colors[key] = str(val["hex"])
                    elif isinstance(val, dict):
                        for sub_val in val.values():
                            if isinstance(sub_val, Mapping) and "hex" in sub_val:
                                colors[key] = str(sub_sub.get("hex", ""))
                                break
                result["brand_colors"] = colors

    return result


def _needs_patching() -> bool:
    """Check if the installed library is missing the extended fields."""
    field_names = {f.name for f in dataclasses.fields(Artist)}
    return not _EXTRA_FIELDS.keys() <= field_names


_patched = False


def patch_artist_top_cities() -> None:
    """Wrap ``parse_artist_gql`` so Artist results carry extended fields."""
    global _patched
    if _patched:
        return
    if not _needs_patching():
        _patched = True
        return

    original = parse_entities.parse_artist_gql

    def _wrapped(union: Mapping[str, Any]) -> Artist:
        artist = original(union)
        if not _needs_patching():
            return artist
        extended = _extract_extended(union)
        return type("_PatchedArtist", (Artist,), {
            "__slots__": (),
            "top_cities": extended.get("top_cities", ()),
            "banner_images": extended.get("banner_images", ()),
            "gallery_images": extended.get("gallery_images", ()),
            "is_verified": extended.get("is_verified", False),
            "pinned_item_name": extended.get("pinned_item_name"),
            "pinned_item_comment": extended.get("pinned_item_comment"),
            "pinned_item_image": extended.get("pinned_item_image"),
            "appears_on_count": extended.get("appears_on_count", 0),
            "featuring_count": extended.get("featuring_count", 0),
            "compilations": extended.get("compilations", ()),
            "copyright": extended.get("copyright"),
            "brand_colors": extended.get("brand_colors", {}),
        })(
            id=artist.id, uri=artist.uri, name=artist.name, images=artist.images,
            biography=artist.biography, followers=artist.followers,
            monthly_listeners=artist.monthly_listeners, world_rank=artist.world_rank,
            top_tracks=artist.top_tracks, albums=artist.albums, singles=artist.singles,
            external_links=artist.external_links, share_url=artist.share_url,
        )

    parse_entities.parse_artist_gql = _wrapped
    _patched = True
