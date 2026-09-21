"""Headless CLI tool for Artist Import Studio.

Usage:
  python -m backend.cli search "Prateek Kuhad"
  python -m backend.cli info 0tC995Rfn9k2l7nqgCZsV7
  python -m backend.cli tour 0tC995Rfn9k2l7nqgCZsV7
  python -m backend.cli epk 0tC995Rfn9k2l7nqgCZsV7
  python -m backend.cli mcp
"""
from __future__ import annotations

import argparse
import json
import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from . import apple_provider, fusion, geo, spotify_provider


def cmd_search(args: argparse.Namespace):
    query = args.query
    prov = args.provider.lower()
    mod = apple_provider if prov == "apple" else spotify_provider
    res = mod.resolve(query)
    print(f"\n🔍 Search Results for '{query}' [{prov}]:")
    if res.resolved:
        print(f"  ✓ Exact Match: {res.name} (ID: {res.id}) -> {res.url}")
    elif res.candidates:
        print(f"  Found {len(res.candidates)} candidate(s):")
        for i, c in enumerate(res.candidates, 1):
            meta = " · ".join(filter(None, [getattr(c, "genre", None), getattr(c, "country", None)]))
            meta_str = f" | {meta}" if meta else ""
            print(f"  {i}. {c.name} (ID: {c.id}){meta_str}")
    else:
        print("  ✗ No artists found.")


def cmd_info(args: argparse.Namespace):
    artist_id = args.id
    prov = args.provider.lower()
    mod = apple_provider if prov == "apple" else spotify_provider
    profile = mod.fetch_artist(artist_id)

    if not args.no_fuse:
        profile = fusion.fuse_profiles(profile)

    print(f"\n🎵 Artist Profile: {profile.name}")
    print(f"   Provider:        {profile.provider.upper()} (ID: {profile.id})")
    print(f"   Cross-Fused:     {'Yes ⚡' if profile.fused else 'No'}")
    if profile.genres:
        print(f"   Genres:          {', '.join(profile.genres)}")
    if profile.stats:
        listeners = profile.stats.get("monthly_listeners")
        followers = profile.stats.get("followers")
        rank = profile.stats.get("world_rank")
        if listeners:
            print(f"   Monthly Streams: {listeners:,}")
        if rank:
            print(f"   World Rank:      #{rank:,}")
        if followers:
            print(f"   Followers:       {followers:,}")
    if profile.top_cities:
        print(f"   Top Audience:    {profile.top_cities[0].city} ({profile.top_cities[0].listeners:,} listeners)")
    print(f"   Tracks Available:{len(profile.top_tracks)}")
    print(f"   Albums/Singles:  {len(profile.albums)}")
    print(f"   Tour Events:     {len(profile.events)}")
    if profile.url:
        print(f"   Streaming URL:   {profile.url}")


def cmd_tour(args: argparse.Namespace):
    artist_id = args.id
    profile = spotify_provider.fetch_artist(artist_id)
    analysis = geo.analyze_tour_opportunities(profile)

    print(f"\n🗺️ Tour & Geographic Intelligence for {analysis['artist_name']}:")
    print(f"   💡 {analysis['insight_headline']}")
    print(f"   {analysis['insight_detail']}\n")

    print("   📍 Audience Hubs ('Where They Listen'):")
    for c in analysis["cities"]:
        print(f"      • {c['city']} ({c['listeners']:,} listeners)")

    print("\n   🎯 High-Potential Tour Opportunities (Unserved):")
    if analysis["opportunities"]:
        for opp in analysis["opportunities"]:
            print(f"      ★ {opp['city']}: {opp['listeners']:,} listeners | Rec: {opp['recommended_capacity']}")
    else:
        print("      No major unserved tour gaps detected.")


def cmd_epk(args: argparse.Namespace):
    artist_id = args.id
    prov = args.provider.lower()
    mod = apple_provider if prov == "apple" else spotify_provider
    profile = mod.fetch_artist(artist_id)
    profile = fusion.fuse_profiles(profile)

    print(f"\n📄 Electronic Press Kit Summary: {profile.name}")
    print(f"   Link: http://127.0.0.1:8000/epk/{prov}/{artist_id}")
    if profile.biography:
        snippet = profile.biography[:180] + "..." if len(profile.biography) > 180 else profile.biography
        print(f"\n   Bio: \"{snippet}\"")
    print("\n   Top Tracks:")
    for t in profile.top_tracks[:5]:
        preview = " [30s audio ready]" if t.preview_url else ""
        print(f"      • {t.name} ({t.album or 'Single'}){preview}")


def main():
    parser = argparse.ArgumentParser(
        prog="artist-studio",
        description="Artist Import Studio — Headless CLI & Music Intelligence",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # Search
    p_search = sub.add_parser("search", help="Search artist across streaming services")
    p_search.add_argument("query", help="Artist name or URL")
    p_search.add_argument("--provider", default="spotify", choices=["spotify", "apple"])

    # Info
    p_info = sub.add_parser("info", help="Get artist profile with cross-platform fusion")
    p_info.add_argument("id", help="Artist ID")
    p_info.add_argument("--provider", default="spotify", choices=["spotify", "apple"])
    p_info.add_argument("--no-fuse", action="store_true", help="Disable dual-provider fusion")

    # Tour
    p_tour = sub.add_parser("tour", help="Run geographic tour routing & opportunity analysis")
    p_tour.add_argument("id", help="Spotify Artist ID")

    # EPK
    p_epk = sub.add_parser("epk", help="Generate EPK summary")
    p_epk.add_argument("id", help="Artist ID")
    p_epk.add_argument("--provider", default="spotify", choices=["spotify", "apple"])

    # MCP
    sub.add_parser("mcp", help="Launch Model Context Protocol (MCP) stdio server for AI agents")

    args = parser.parse_args()

    if args.command == "search":
        cmd_search(args)
    elif args.command == "info":
        cmd_info(args)
    elif args.command == "tour":
        cmd_tour(args)
    elif args.command == "epk":
        cmd_epk(args)
    elif args.command == "mcp":
        from .mcp_server import run_stdio_server
        run_stdio_server()


if __name__ == "__main__":
    main()
