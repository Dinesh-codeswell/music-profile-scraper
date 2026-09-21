"""Model Context Protocol (MCP) Server for AI Coding Assistants & Music Agents.

Enables agents in Antigravity, Cursor, Claude Desktop, etc. to query real-time
streaming metadata, audio previews, cross-platform fusion, and tour routing
without needing Spotify or Apple developer API keys.

Implements JSON-RPC 2.0 over standard I/O (stdio).
"""
from __future__ import annotations

import json
import sys
import traceback
from typing import Any, Callable, Optional

from . import apple_provider, fusion, geo, spotify_provider

SERVER_NAME = "artist-import-studio"
SERVER_VERSION = "1.0.0"
PROTOCOL_VERSION = "2024-11-05"

# Tool Definitions
TOOLS = [
    {
        "name": "resolve_artist",
        "description": "Resolve an artist name, Spotify link, or Apple Music link into platform IDs and candidate matches.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Artist name (e.g. 'Dermot Kennedy') or streaming profile link",
                },
                "provider": {
                    "type": "string",
                    "enum": ["spotify", "apple", "fused"],
                    "default": "fused",
                    "description": "Streaming provider to query (default: 'fused')",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_artist_profile",
        "description": "Extract full streaming profile including monthly listeners, world rank, bio, press imagery, and genres.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "artist_id": {
                    "type": "string",
                    "description": "Spotify artist ID (22 chars) or Apple Music numeric artist ID",
                },
                "provider": {
                    "type": "string",
                    "enum": ["spotify", "apple"],
                    "default": "spotify",
                    "description": "Primary streaming provider",
                },
                "fuse": {
                    "type": "boolean",
                    "default": True,
                    "description": "Whether to cross-enrich data across both Spotify & Apple Music",
                },
            },
            "required": ["artist_id"],
        },
    },
    {
        "name": "get_top_tracks",
        "description": "Retrieve top streaming songs with playable 30-second MP3 audio preview URLs and play counts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "artist_id": {
                    "type": "string",
                    "description": "Artist ID on Spotify or Apple Music",
                },
                "provider": {
                    "type": "string",
                    "enum": ["spotify", "apple"],
                    "default": "spotify",
                },
            },
            "required": ["artist_id"],
        },
    },
    {
        "name": "get_tour_routing",
        "description": "Analyze audience geographic concentration vs scheduled concerts to detect high-potential unserved markets ('Tour Deserts').",
        "inputSchema": {
            "type": "object",
            "properties": {
                "artist_id": {
                    "type": "string",
                    "description": "Artist Spotify ID",
                },
            },
            "required": ["artist_id"],
        },
    },
    {
        "name": "generate_epk",
        "description": "Generate an executive Electronic Press Kit (EPK) and One-Sheet summary for booking and press.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "artist_id": {
                    "type": "string",
                    "description": "Artist Spotify or Apple Music ID",
                },
                "provider": {
                    "type": "string",
                    "enum": ["spotify", "apple"],
                    "default": "spotify",
                },
            },
            "required": ["artist_id"],
        },
    },
]


def _extract_id(args: dict[str, Any], prov: str = "spotify") -> str:
    """Safely extract artist ID from various possible argument keys, auto-resolving names/URLs if needed."""
    val = (
        args.get("artist_id")
        or args.get("id")
        or args.get("query")
        or args.get("artist_query")
        or args.get("name")
        or ""
    ).strip()
    if not val:
        raise ValueError("Missing 'artist_id' or 'query' in tool arguments")
    if "open.spotify.com" in val or "music.apple.com" in val or (" " in val and not val.isalnum()):
        mod = apple_provider if (prov == "apple" or "music.apple.com" in val) else spotify_provider
        res = mod.resolve(val)
        if res.resolved and res.id:
            return res.id
        if res.candidates:
            return res.candidates[0].id
    return val


def handle_resolve_artist(args: dict[str, Any]) -> dict[str, Any]:
    query = (
        args.get("query")
        or args.get("artist_query")
        or args.get("artist_id")
        or args.get("name")
        or ""
    ).strip()
    if not query:
        raise ValueError("Missing 'query' in resolve_artist arguments")
    prov = args.get("provider", "fused").lower()

    if prov == "fused":
        is_apple = "music.apple.com" in query.lower() or (query.isdigit() and len(query) > 5)
        primary = "apple" if is_apple else "spotify"
        mod = apple_provider if primary == "apple" else spotify_provider
        res = mod.resolve(query)
        if not res.resolved and not res.candidates:
            alt_mod = spotify_provider if primary == "apple" else apple_provider
            res = alt_mod.resolve(query)
        return res.model_dump()

    mod = apple_provider if prov == "apple" else spotify_provider
    return mod.resolve(query).model_dump()


def handle_get_artist_profile(args: dict[str, Any]) -> dict[str, Any]:
    prov = args.get("provider", "spotify").lower()
    artist_id = _extract_id(args, prov)
    should_fuse = args.get("fuse", True)

    mod = apple_provider if prov == "apple" else spotify_provider
    profile = mod.fetch_artist(artist_id)
    if should_fuse:
        profile = fusion.fuse_profiles(profile)

    return {
        "name": profile.name,
        "provider": profile.provider,
        "id": profile.id,
        "genres": profile.genres,
        "monthly_listeners": profile.stats.get("monthly_listeners"),
        "world_rank": profile.stats.get("world_rank"),
        "followers": profile.stats.get("followers"),
        "region_hint": profile.region_hint,
        "fused": profile.fused,
        "fusion_sources": profile.fusion_sources,
        "biography": profile.biography,
        "top_cities": [c.model_dump() for c in profile.top_cities],
        "events_count": len(profile.events),
        "tracks_count": len(profile.top_tracks),
    }


def handle_get_top_tracks(args: dict[str, Any]) -> list[dict[str, Any]]:
    prov = args.get("provider", "spotify").lower()
    artist_id = _extract_id(args, prov)
    mod = apple_provider if prov == "apple" else spotify_provider
    profile = mod.fetch_artist(artist_id)
    return [
        {
            "name": t.name,
            "album": t.album,
            "preview_url": t.preview_url,
            "duration_ms": t.duration_ms,
            "play_count": t.play_count,
            "explicit": t.explicit,
        }
        for t in profile.top_tracks
    ]


def handle_get_tour_routing(args: dict[str, Any]) -> dict[str, Any]:
    artist_id = _extract_id(args, "spotify")
    profile = spotify_provider.fetch_artist(artist_id)
    return geo.analyze_tour_opportunities(profile)


def handle_generate_epk(args: dict[str, Any]) -> dict[str, Any]:
    prov = args.get("provider", "spotify").lower()
    artist_id = _extract_id(args, prov)
    mod = apple_provider if prov == "apple" else spotify_provider
    profile = mod.fetch_artist(artist_id)
    profile = fusion.fuse_profiles(profile)

    stats = profile.stats or {}
    listeners = stats.get("monthly_listeners")
    top_city = profile.top_cities[0].city if profile.top_cities else "Global"

    summary = f"{profile.name} is a {profile.genres[0] if profile.genres else 'recording'} artist"
    if listeners:
        summary += f" currently commanding {listeners:,} monthly listeners, with key audience traction in {top_city}."
    else:
        summary += "."

    return {
        "artist_name": profile.name,
        "primary_genre": profile.genres[0] if profile.genres else "Independent",
        "monthly_listeners": listeners,
        "summary": summary,
        "press_bio": profile.biography,
        "top_tracks": [t.name for t in profile.top_tracks[:5]],
        "top_cities": [f"{c.city} ({c.listeners:,} listeners)" for c in profile.top_cities if c.listeners],
        "upcoming_shows": [f"{e.start_date or 'TBA'} - {e.title} ({e.city})" for e in profile.events],
        "epk_url": f"http://127.0.0.1:8000/epk/{prov}/{artist_id}",
    }


TOOL_HANDLERS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "resolve_artist": handle_resolve_artist,
    "get_artist_profile": handle_get_artist_profile,
    "get_top_tracks": handle_get_top_tracks,
    "get_tour_routing": handle_get_tour_routing,
    "generate_epk": handle_generate_epk,
}


def run_stdio_server():
    """Run the JSON-RPC stdio event loop."""
    sys.stderr.write(f"[{SERVER_NAME}] MCP stdio server initialized (v{SERVER_VERSION})\n")
    sys.stderr.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue

        msg_id = req.get("id")
        method = req.get("method")

        # 1. Initialize
        if method == "initialize":
            resp = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": SERVER_NAME,
                        "version": SERVER_VERSION,
                    },
                },
            }
            _send(resp)

        # 2. Initialized Notification
        elif method == "notifications/initialized":
            pass

        # 3. Ping
        elif method == "ping":
            _send({"jsonrpc": "2.0", "id": msg_id, "result": {}})

        # 4. Tools List
        elif method == "tools/list":
            _send({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": TOOLS},
            })

        # 5. Tools Call
        elif method == "tools/call":
            params = req.get("params", {})
            name = params.get("name")
            arguments = params.get("arguments", {})

            handler = TOOL_HANDLERS.get(name)
            if not handler:
                _send({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32601, "message": f"Unknown tool: {name}"},
                })
                continue

            try:
                result_data = handler(arguments)
                text_content = json.dumps(result_data, indent=2)
                _send({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": text_content}],
                    },
                })
            except Exception as exc:
                sys.stderr.write(f"Tool error in {name}: {traceback.format_exc()}\n")
                sys.stderr.flush()
                _send({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32000, "message": str(exc)},
                })

        # Unknown method
        else:
            if msg_id is not None:
                _send({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                })


def _send(data: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(data) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    run_stdio_server()
