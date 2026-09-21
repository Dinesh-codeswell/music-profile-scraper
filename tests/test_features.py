"""Comprehensive test suite for Artist Import Studio features.
Tests fusion, geographic routing, EPK, embed player, oEmbed, and CLI.
"""
import unittest
from fastapi.testclient import TestClient

from backend.app import app
from backend.models import ArtistProfile, TopCity, TopTrack, EventEntry
from backend import fusion, geo


class TestArtistImportStudioFeatures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_geo_routing_logic(self):
        """Test geographic clustering and tour opportunity calculation."""
        mock_profile = ArtistProfile(
            provider="spotify",
            id="test123",
            name="Indie Artist",
            url="https://open.spotify.com/artist/test123",
            top_cities=[
                TopCity(city="London", country="GB", listeners=85000),
                TopCity(city="Berlin", country="DE", listeners=60000),
                TopCity(city="Paris", country="FR", listeners=65000),
            ],
            events=[
                EventEntry(title="Live in London", city="London"),
            ]
        )
        analysis = geo.analyze_tour_opportunities(mock_profile)
        self.assertEqual(analysis["artist_name"], "Indie Artist")
        self.assertGreaterEqual(len(analysis["cities"]), 2)
        # Berlin is >900km from London, so it must be identified as an unserved tour opportunity
        opp_cities = [o["city"] for o in analysis["opportunities"]]
        self.assertIn("Berlin", opp_cities)

    def test_epk_api_endpoint(self):
        """Test /api/epk/{provider}/{id} returns structured press kit data."""
        # Using known Spotify test ID
        resp = self.client.get("/api/epk/spotify/0tC995Rfn9k2l7nqgCZsV7")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("highlights", data)
        self.assertIn("featured_tracks", data)
        self.assertIn("press_bio", data)
        self.assertEqual(data["highlights"]["name"], "Prateek Kuhad")

    def test_embed_widget_route(self):
        """Test /embed/{provider}/{id} serves the lightweight player HTML."""
        resp = self.client.get("/embed/spotify/0tC995Rfn9k2l7nqgCZsV7")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers["content-type"])
        self.assertIn("widget-container", resp.text)
        self.assertIn("Artist Player Embed", resp.text)

    def test_oembed_endpoint(self):
        """Test standard /api/oembed response format."""
        resp = self.client.get("/api/oembed?url=http://localhost:8000/epk/spotify/0tC995Rfn9k2l7nqgCZsV7")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["version"], "1.0")
        self.assertEqual(data["type"], "rich")
        self.assertEqual(data["provider_name"], "Artist Import Studio")
        self.assertIn("<iframe", data["html"])

    def test_tour_analysis_api(self):
        """Test /api/geo/tour-analysis/{provider}/{id} endpoint."""
        resp = self.client.get("/api/geo/tour-analysis/spotify/0tC995Rfn9k2l7nqgCZsV7")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["artist_name"], "Prateek Kuhad")
        self.assertIn("cities", data)
        self.assertIn("opportunities", data)

    def test_cross_platform_fusion(self):
        """Test fusion merges Spotify reach with Apple genre taxonomy."""
        mock_spotify = ArtistProfile(
            provider="spotify",
            id="sp1",
            name="Coldplay",
            url="https://open.spotify.com/artist/sp1",
            stats={"monthly_listeners": 90000000},
            genres=[],  # Spotify public scraper provides no genres
        )
        fused = fusion.fuse_profiles(mock_spotify)
        self.assertTrue(fused.fused)
        self.assertIn("spotify", fused.fused_providers)
        self.assertIn("apple", fused.fused_providers)
        # Should have retrieved Apple's genre classification
        self.assertGreater(len(fused.genres), 0)

    def test_homepage_dedicated_to_scraper(self):
        """Test homepage is dedicated strictly to the scraper and contains no CSV filter section."""
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Artist Import Studio", resp.text)
        self.assertNotIn("CSV Filter Studio", resp.text)
        self.assertNotIn('id="filter"', resp.text)

    def test_standalone_filter_page(self):
        """Test /filter and /csv-filter route to standalone filter.html module."""
        resp = self.client.get("/filter")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("CSV Filter Studio", resp.text)
        self.assertIn("filter.js", resp.text)

        resp_alias = self.client.get("/csv-filter")
        self.assertEqual(resp_alias.status_code, 200)
        self.assertIn("CSV Filter Studio", resp_alias.text)

    def test_filter_static_assets(self):
        """Test standalone filter.js is served properly without legacy branding."""
        resp = self.client.get("/assets/filter.js")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("runFilter", resp.text)
        self.assertNotIn("Songdew", resp.text)


    def test_smart_link_routes(self):
        """Test /link and /smart-link serve the mobile-first smart link landing page."""
        resp = self.client.get("/link/spotify/0tC995Rfn9k2l7nqgCZsV7")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers["content-type"])
        self.assertIn("Artist Smart Link", resp.text)
        self.assertIn("preview-module", resp.text)
        self.assertIn("tour-section", resp.text)

        resp_alias = self.client.get("/smart-link/spotify/0tC995Rfn9k2l7nqgCZsV7")
        self.assertEqual(resp_alias.status_code, 200)
        self.assertIn("Artist Smart Link", resp_alias.text)

    def test_device_preview_simulator_assets_and_integration(self):
        """Test device preview simulator CSS and JS are served, and pages contain device simulation controls."""
        resp_css = self.client.get("/assets/device-preview.css")
        self.assertEqual(resp_css.status_code, 200)
        self.assertIn("devprev-modal", resp_css.text)
        self.assertIn("bezel-mobile", resp_css.text)

        resp_js = self.client.get("/assets/device-preview.js")
        self.assertEqual(resp_js.status_code, 200)
        self.assertIn("DevicePreview", resp_js.text)
        self.assertIn("iPhone 15", resp_js.text)
        self.assertIn("iPad Air", resp_js.text)
        self.assertIn("MacBook", resp_js.text)

        resp_link = self.client.get("/link/spotify/0tC995Rfn9k2l7nqgCZsV7")
        self.assertEqual(resp_link.status_code, 200)
        self.assertIn('id="device-btn"', resp_link.text)
        self.assertIn("device-preview.js", resp_link.text)
        self.assertIn("viewport-fit=cover", resp_link.text)

        resp_epk = self.client.get("/epk/spotify/0tC995Rfn9k2l7nqgCZsV7")
        self.assertEqual(resp_epk.status_code, 200)
        self.assertIn('id="epk-device-btn"', resp_epk.text)
        self.assertIn("device-preview.js", resp_epk.text)

        resp_home = self.client.get("/")
        self.assertEqual(resp_home.status_code, 200)
        self.assertIn('id="device-preview-btn"', resp_home.text)
        self.assertIn("device-preview.js", resp_home.text)


if __name__ == "__main__":
    unittest.main()
