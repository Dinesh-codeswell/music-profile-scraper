# Artist Import Studio

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-Protocol%202024--11--05-blueviolet.svg)](https://modelcontextprotocol.io/)
[![Vercel Ready](https://img.shields.io/badge/Vercel-Deployed-black.svg?logo=vercel&logoColor=white)](https://vercel.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

An open-source music intelligence platform, streaming profile ingestion studio, and **Electronic Press Kit (EPK)** generator. Paste a public **Spotify** or **Apple Music** profile link (or artist name), extract rich metadata without any API keys, fuse cross-platform taxonomies, analyze geographic tour routing opportunities, embed audio players into any CMS, and query music intelligence using an AI-native **Model Context Protocol (MCP)** server or headless CLI.

---

## 🌟 Key Capabilities

### 1. Zero-Auth Streaming Scrapers
- **Spotify Public Scraper (`spotifyscraper`)**: Anonymous token bootstrapping from public web-player embed pages. Fetches avatars, header banners, gallery photos, bios, verification, external links, top tracks with 30s previews, full discography, monthly listeners, follower counts, world rank, "Where They Listen" audience cities, and upcoming concerts.
- **Apple Music / iTunes Ingestion**: Free iTunes Lookup API returning accurate `primaryGenreName` without rate limiting, plus localized JSON-LD biographies, 1500px artwork, and regional storefront fallback (`in`, `us`, `gb`).

### 2. ⚡ Cross-Platform Profile Fusion (Idea 2)
- **Problem Solved**: Spotify public payloads lack genre taxonomies; Apple Music lacks listener metrics and concert itineraries.
- **The Fusion Engine (`backend/fusion.py`)**: Merges both platforms with full provenance tracking. Combines Apple's authoritative genres with Spotify's monthly reach, top cities, and tour dates into an integrated profile available under the `⚡ Fused` tab or `/api/import/fusion/{provider}/{id}`.

### 3. 📄 Public EPK & Printable PDF One-Sheet Generator (Idea 1)
- **Interactive Web EPK (`/epk/{provider}/{id}`)**: Executive dark/light press kit featuring hero banners, listener statistics, audio previews, discography grid, and tour stops.
- **Print / PDF One-Sheet**: Built-in `@media print` styling that formats the entire press kit into a single-page or two-page executive print document with a single click (`window.print()`).
- **REST Payload**: Structured JSON endpoint at `/api/epk/{provider}/{id}`.

### 4. 🗺️ Geographic Tour Routing & Fan Heatmap (Idea 3)
- **Interactive Leaflet Fan Map**: Embedded in both the main studio and the public EPK, displaying audience concentrations via CartoDB Voyager tiles (100% free, zero API keys required).
- **Tour Desert & Opportunity Algorithm (`backend/geo.py`)**: Calculates Haversine distances between audience clusters and scheduled concerts. Detects unserved markets with over 50k–200k listeners lacking a show within a 350km radius and provides venue capacity recommendations.
- **REST Payload**: Accessible via `/api/geo/tour-analysis/{provider}/{id}`.

### 5. 🎵 Embeddable Audio Player & oEmbed (Idea 4)
- **Lightweight Player Widget (`/embed/{provider}/{id}`)**: Responsive, self-contained iframe widget with audio controls, 30s preview streams, track progression, and dark/light mode toggles.
- **Interactive Embed Modal**: Built-in modal in the dashboard with live iframe preview and one-click HTML copy snippet.
- **oEmbed Standard Support**: Standard discovery endpoint at `/api/oembed` for automated rich embeds in CMS platforms, Medium, Notion, WordPress, and Discord.

### 6. 🤖 Model Context Protocol (MCP) Server & Headless CLI (Idea 6)
- **Headless CLI (`python -m backend.cli`)**: Fast terminal utility for music analysts and booking agents with subcommands `search`, `info`, `tour`, `epk`, and `mcp`.
- **MCP Server (`backend/mcp_server.py`)**: Standard JSON-RPC 2.0 stdio server enabling Claude Desktop, Cursor, Antigravity, and other AI agents to natively resolve artists, inspect stats, evaluate tour opportunities, and draft press kits.

#### 7. Isolated CSV Filter Studio Module (Standalone at `/filter`)
- **Complete Separation**: Removed entirely from the public homepage, keeping `/` 100% dedicated to artist streaming profile scraping, tour routing, and EPK generation.
- **Dedicated Standalone Interface**: Accessible directly at `/filter` (or `/csv-filter`), with its own optimized layout, multi-tier integrity rules, and real-time SSE progress indicators.
- **Multi-Tier Detection**: Automated spam, bot-farm, gambling keyword, and non-artist business account filtering.
- **Bulk Import Support**: Process user lists in `.csv` or `.xlsx` format with real-time classification reports and downloadable clean datasets.

---

## 🏗️ Project Structure

```
artist-import-studio/
├── backend/                      # FastAPI backend & music intelligence
│   ├── __init__.py
│   ├── app.py                    # API routes, EPK, Embed & /filter endpoints
│   ├── apple_provider.py         # iTunes & Apple Music scraper
│   ├── spotify_provider.py       # Spotify public scraper integration
│   ├── spotify_topcities_shim.py # In-process compatibility patch for top cities
│   ├── fusion.py                 # Cross-platform profile fusion engine
│   ├── geo.py                    # Geographic geocoding & tour routing engine
│   ├── mcp_server.py             # Model Context Protocol (MCP) stdio server
│   ├── cli.py                    # Headless CLI entry point
│   ├── cache.py                  # Thread-safe TTL cache (24h positive / 2h negative)
│   ├── models.py                 # Typed Pydantic models for profiles & responses
│   ├── filter_api.py             # CSV/XLSX filtering endpoints
│   └── filter_engine.py          # Account integrity & bot detection pipeline
├── frontend/                     # Static client single-page dashboard & widgets
│   ├── index.html                # Main studio dashboard (dedicated exclusively to scrapers)
│   ├── filter.html               # Standalone CSV Filter Studio module (/filter)
│   ├── filter.js                 # Standalone CSV Filter logic & SSE streaming
│   ├── epk.html                  # Standalone Public EPK & PDF One-Sheet (/epk)
│   ├── embed.html                # Embeddable mini audio player iframe widget (/embed)
│   ├── app.js                    # Scraper client logic, Leaflet maps & embed modal
│   └── styles.css                # Dark mode styles, map containers & printable media
├── tests/                        # Automated unit tests
│   └── test_features.py          # Comprehensive test suite (Fusion, Geo, Embed, EPK, Filter)
├── public/                       # Branding assets
│   └── favicon.jpg
├── package.json                  # NPM convenience scripts
├── pyproject.toml                # Python packaging & Vercel entrypoint
├── requirements.txt              # Python dependencies
├── vercel.json                   # Vercel serverless function & routing
├── render.yaml                   # Render web service blueprint
└── README.md                     # Project documentation
```

---

## 💻 Headless CLI Usage

The studio includes a powerful terminal interface for scripts, pipelines, and terminal workflows:

```bash
# 1. Search for an artist across Spotify or Apple Music
python -m backend.cli search "Prateek Kuhad"
python -m backend.cli search "Coldplay" --provider apple

# 2. Inspect an artist profile (with automatic cross-platform fusion)
python -m backend.cli info 0tC995Rfn9k2l7nqgCZsV7

# 3. Analyze geographic audience clusters and tour opportunities
python -m backend.cli tour 0tC995Rfn9k2l7nqgCZsV7

# 4. Generate EPK press bio and top track preview summary
python -m backend.cli epk 0tC995Rfn9k2l7nqgCZsV7
```

---

## 🤖 Model Context Protocol (MCP) Setup for AI Agents

Artist Import Studio exposes an MCP stdio server that equips AI assistants (Claude Desktop, Cursor, Antigravity, etc.) with real-time music intelligence tools.

### Available MCP Tools:
1. `resolve_artist`: Resolve artist names, Spotify URLs, or Apple Music URLs into verified entity IDs.
2. `get_artist_profile`: Fetch comprehensive artist intelligence with optional cross-platform fusion.
3. `get_top_tracks`: Fetch popular tracks with 30-second audio stream URLs.
4. `get_tour_routing`: Identify high-potential unserved tour markets ("Tour Deserts") based on fan concentrations vs scheduled tour stops.
5. `generate_epk`: Produce an executive booking summary, press bio, and one-sheet link.

### Adding to Claude Desktop / Cursor Config

Add the following to your `claude_desktop_config.json` or MCP settings file:

```json
{
  "mcpServers": {
    "artist-import-studio": {
      "command": "python",
      "args": ["-m", "backend.mcp_server"],
      "cwd": "C:/songdew-import-studio"
    }
  }
}
```

---

## 🎵 Embed Widget & oEmbed Integration

### IFrame Embed Snippet
Paste this HTML snippet into any website, blog, or CMS:
```html
<iframe 
  src="http://127.0.0.1:8000/embed/spotify/0tC995Rfn9k2l7nqgCZsV7?theme=dark" 
  width="100%" 
  height="160" 
  frameborder="0" 
  allow="autoplay; encrypted-media">
</iframe>
```

### Standard oEmbed Endpoint
CMS platforms (WordPress, Medium, Notion) can resolve rich player embeds automatically:
```
GET /api/oembed?url=http://127.0.0.1:8000/epk/spotify/0tC995Rfn9k2l7nqgCZsV7&format=json
```

---

## 🚀 Quick Start (Local Development)

### 1. Set Up Virtual Environment
```bash
# Create virtual environment
python -m venv .venv

# Activate environment
# On Windows (PowerShell):
.\.venv\Scripts\activate
# On macOS / Linux:
source .venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Start the Development Server
```bash
uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000
```

### 3. Open in Browser
- **Artist Scraper Studio**: [http://127.0.0.1:8000](http://127.0.0.1:8000) (Homepage dedicated exclusively to streaming scrapers)
- **CSV Filter Studio**: [http://127.0.0.1:8000/filter](http://127.0.0.1:8000/filter) (Standalone module accessible directly via URL)
- **Interactive OpenAPI Documentation**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Sample Public EPK**: [http://127.0.0.1:8000/epk/spotify/0tC995Rfn9k2l7nqgCZsV7](http://127.0.0.1:8000/epk/spotify/0tC995Rfn9k2l7nqgCZsV7)
- **Sample Embed Widget**: [http://127.0.0.1:8000/embed/spotify/0tC995Rfn9k2l7nqgCZsV7](http://127.0.0.1:8000/embed/spotify/0tC995Rfn9k2l7nqgCZsV7)

### 4. Run Automated Test Suite
```bash
python -m unittest discover tests
```

---

## 📡 API Reference

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Artist Scraper Studio dashboard (dedicated to public streaming ingestion) |
| `GET` | `/filter` | Standalone CSV Filter Studio module (also `/csv-filter`) |
| `GET` | `/api/health` | Liveness probe and cache statistics |
| `GET` | `/api/providers` | Capability matrix (Spotify, Apple Music, and ⚡ Fused) |
| `POST` | `/api/import/resolve` | Resolves query/URL to artist candidates |
| `GET` | `/api/import/{provider}/{id}` | Fetches full scraped profile (cached 24h) |
| `GET` | `/api/import/fusion/{provider}/{id}` | Cross-platform synthesis (Apple genres + Spotify audience) |
| `GET` | `/api/geo/tour-analysis/{provider}/{id}` | Geographic tour opportunity analysis & fan city coordinates |
| `GET` | `/api/epk/{provider}/{id}` | Structured Electronic Press Kit & One-Sheet payload |
| `GET` | `/epk/{provider}/{id}` | Standalone responsive Public EPK & printable PDF One-Sheet |
| `GET` | `/embed/{provider}/{id}` | Standalone responsive mini audio player widget |
| `GET` | `/api/oembed` | Standard oEmbed JSON provider for CMS rich embeds |
| `POST` | `/api/import/refresh` | Bypasses cache and forces re-scraping |
| `POST` | `/api/import/apply` | Previews onboarding auto-fill and EPK field mapping |
| `POST` | `/api/filter/upload` | Uploads and filters artist CSV/XLSX |
| `POST` | `/api/filter/upload-scrape`| Filters and scrapes profile verification signals |
| `POST` | `/api/filter/download` | Exports filtered records as CSV |
| `GET` | `/api/filter/presets` | Lists available filter configurations |

---

## ☁️ Deployment

### Option A: Deploy to Vercel (Recommended)
This repository includes [`vercel.json`](vercel.json) and [`pyproject.toml`](pyproject.toml) pre-configured for Vercel's Python runtime.

1. Push your project to GitHub.
2. Import your repository at **[vercel.com/new](https://vercel.com/new)**.
3. Vercel automatically deploys the static frontend to its global Edge CDN and the FastAPI backend as Serverless Python Functions.

### Option B: Deploy to Render
The repository includes a [`render.yaml`](render.yaml) blueprint for one-click web service deployment using `uvicorn backend.app:app`.

---

## 📄 License

This project is open-source software licensed under the [MIT License](LICENSE).
