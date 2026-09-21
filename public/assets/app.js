"use strict";

/* ---------- state ---------- */
let provider = "spotify";
let current = null; // current ArtistProfile
let profileRaw = null;

/* ---------- helpers ---------- */
const $ = (id) => document.getElementById(id);
const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );

function fmt(n) {
  if (n == null) return "—";
  if (n >= 1e9) return (n / 1e9).toFixed(1) + "B";
  if (n >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(1) + "K";
  return String(n);
}

function fmtDuration(ms) {
  if (!ms) return "";
  const m = Math.floor(ms / 60000), s = Math.floor((ms % 60000) / 1000);
  return `${m}:${String(s).padStart(2, "0")}`;
}

async function api(url, opts = {}) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    let detail = {};
    try { detail = (await res.json()).detail || {}; } catch { /* ignore */ }
    throw new Error(detail.message || detail.code || `HTTP ${res.status}`);
  }
  return res.json();
}

/* ---------- provider tabs ---------- */
document.querySelectorAll(".provider-tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    provider = tab.dataset.provider;
    document.querySelectorAll(".provider-tab").forEach((t) => t.classList.toggle("active", t === tab));
    updateHint();
    loadEngineNote();
  });
});

function updateHint() {
  if (provider === "fused") {
    $("hint").innerHTML = '<b>⚡ Fused Mode:</b> Paste a Spotify link, Apple Music link, or artist name. We automatically cross-enrich genres from Apple Music with audience reach &amp; audio previews from Spotify.';
  } else if (provider === "spotify") {
    $("hint").innerHTML = 'Paste e.g. <code>https://open.spotify.com/artist/4tZwfgrHOc3mvqYlEYSvVi</code> or an artist name. Genres are not exposed by Spotify — use the ⚡ Fused or Apple pill for genre.';
  } else {
    $("hint").innerHTML = 'Paste e.g. <code>https://music.apple.com/us/artist/dermot-kennedy/1082836810</code>, a bare iTunes artist id, or an artist name.';
  }
}

async function loadEngineNote() {
  try {
    const data = await api("/api/providers");
    const p = data.providers[provider];
    $("engine-note").textContent = p ? `${p.engine}` : "";
  } catch { /* noop */ }
}

/* ---------- fetch flow ---------- */
$("fetch-btn").addEventListener("click", doFetch);
$("query").addEventListener("keydown", (e) => { if (e.key === "Enter") doFetch(); });
$("clear-btn").addEventListener("click", () => { $("query").value = ""; });

async function doFetch() {
  const query = $("query").value.trim();
  if (!query) return;
  setBusy(true);
  hideError();
  $("candidates").hidden = true;
  $("candidates").innerHTML = "";
  try {
    const resolved = await api("/api/import/resolve", {
      method: "POST",
      body: JSON.stringify({ provider, query }),
    });
    if (!resolved.resolved) {
      if (resolved.candidates && resolved.candidates.length > 1) {
        renderCandidates(resolved.candidates, resolved.provider);
        setBusy(false);
        return;
      }
      throw new Error(`No artist found for "${query}"`);
    }
    await fetchProfile(resolved.id, resolved.name, resolved.url, resolved.provider);
  } catch (err) {
    showError(err.message);
  }
  setBusy(false);
}

function renderCandidates(candidates, candidateProvider) {
  const box = $("candidates");
  box.innerHTML = "<p class='muted small'>Multiple matches — pick one:</p>";
  candidates.forEach((c) => {
    const row = document.createElement("div");
    row.className = "candidate-row";
    const img = c.image_url ? `<img src="${esc(c.image_url)}" alt="" onerror="this.style.visibility='hidden'" />` : "<img alt='' />";
    row.innerHTML = `${img}<div><div class="candidate-name">${esc(c.name)}</div>
      <div class="candidate-meta">${esc([c.genre, c.country].filter(Boolean).join(" · ") || "—")}</div></div>`;
    row.addEventListener("click", async () => {
      box.hidden = true;
      setBusy(true);
      try { await fetchProfile(c.id, c.name, c.url, candidateProvider); } catch (err) { showError(err.message); }
      setBusy(false);
    });
  box.scrollIntoView({ behavior: "smooth", block: "nearest" });
    box.appendChild(row);
  });
  box.hidden = false;
}

async function fetchProfile(id, name, url, activeProvider) {
  const effProv = activeProvider || provider;
  const isFused = provider === "fused";
  const endpoint = isFused
    ? `/api/import/fusion/${effProv === "fused" ? "spotify" : effProv}/${encodeURIComponent(id)}`
    : `/api/import/${effProv}/${encodeURIComponent(id)}`;

  const data = await api(endpoint);
  current = data;
  profileRaw = data;
  render(data, { name, url });
  $("results").scrollIntoView({ behavior: "smooth", block: "start" });
}

/* ---------- refresh / raw / apply / fusion ---------- */
$("refresh-btn").addEventListener("click", async () => {
  if (!current) return;
  setBusy(true);
  try {
    const data = await api("/api/import/refresh", {
      method: "POST",
      body: JSON.stringify({ provider: current.provider, query: current.id }),
    });
    current = data;
    profileRaw = data;
    render(data, { name: data.name, url: data.url });
  } catch (err) { showError(err.message); }
  setBusy(false);
});

$("fuse-btn").addEventListener("click", async () => {
  if (!current) return;
  setBusy(true);
  try {
    const data = await api(`/api/import/fusion/${current.provider}/${encodeURIComponent(current.id)}`);
    current = data;
    profileRaw = data;
    render(data, { name: data.name, url: data.url });
  } catch (err) { showError(err.message); }
  setBusy(false);
});

$("toggle-raw").addEventListener("click", () => {
  $("raw-panel").hidden = !$("raw-panel").hidden;
  $("toggle-raw").textContent = $("raw-panel").hidden ? "Raw JSON" : "Hide JSON";
});

$("apply-btn").addEventListener("click", async () => {
  try {
    const out = await api("/api/import/apply", {
      method: "POST",
      body: JSON.stringify({ provider: current.provider, id: current.id, confirmed_fields: [] }),
    });
    $("apply-output").textContent = JSON.stringify(out, null, 2);
    $("apply-output").hidden = false;
  } catch (err) { showError(err.message); }
});

const devPrevBtn = $("device-preview-btn");
if (devPrevBtn) {
  devPrevBtn.addEventListener("click", () => {
    if (window.DevicePreview && current.id) {
      DevicePreview.open({
        defaultTarget: "link",
        provider: current.provider,
        id: current.id,
      });
    }
  });
}

/* ---------- rendering ---------- */
function render(p) {
  $("results").hidden = false;
  $("toggle-raw").hidden = false;

  // header
  $("avatar").src = p.image_url || "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='140'%3E%3Crect fill='%23f4ede9' width='140' height='140'/%3E%3C/svg%3E";
  $("avatar").onerror = () => { $("avatar").style.opacity = "0.25"; };
  $("artist-name").textContent = p.name;
  const badge = $("provider-badge");
  badge.textContent = p.provider === "apple" ? "Apple Music" : (p.provider === "spotify" ? "Spotify" : p.provider);
  badge.dataset.provider = p.provider;
  badge.removeAttribute("style");
  $("cache-badge").hidden = !p.cache_hit;
  $("artist-id").textContent = p.id;
  $("artist-link").href = p.url;
  $("artist-link").textContent = p.provider === "spotify" ? "open Spotify ↗" : "open Apple Music ↗";
  $("refresh-btn").style.display = "inline-flex";

  // Fused status and Provenance
  const isFused = Boolean(p.fused);
  const fusedBadge = $("fused-badge");
  if (fusedBadge) fusedBadge.hidden = !isFused;
  const provBox = $("fusion-provenance");
  if (provBox) {
    if (isFused && p.fusion_sources) {
      const src = p.fusion_sources;
      provBox.innerHTML = `<b>⚡ Cross-Platform Fused:</b> Genres from <b>${esc(src.genres || 'Apple Music')}</b> · Audience stats &amp; top cities from <b>${esc(src.stats || 'Spotify')}</b>`;
      provBox.hidden = false;
    } else {
      provBox.hidden = true;
    }
  }
  const fuseBtn = $("fuse-btn");
  if (fuseBtn) {
    if (isFused) {
      fuseBtn.style.display = "none";
    } else {
      fuseBtn.style.display = "inline-flex";
      fuseBtn.textContent = `⚡ Fuse with ${p.provider === 'spotify' ? 'Apple Music' : 'Spotify'}`;
    }
  }
  const epkBtn = $("epk-btn");
  if (epkBtn) {
    epkBtn.href = `/epk/${encodeURIComponent(p.provider)}/${encodeURIComponent(p.id)}`;
    epkBtn.style.display = "inline-flex";
  }
  const smartlinkBtn = $("smartlink-btn");
  if (smartlinkBtn) {
    smartlinkBtn.href = `/link/${encodeURIComponent(p.provider)}/${encodeURIComponent(p.id)}`;
    smartlinkBtn.style.display = "inline-flex";
  }
  const devPrevBtnEl = $("device-preview-btn");
  if (devPrevBtnEl) {
    devPrevBtnEl.style.display = "inline-flex";
  }

  $("stats-list").closest(".section").style.display = p.availability.stats ? "" : "none";

  // stat chips
  const chips = $("stat-chips");
  chips.innerHTML = "";
  const stats = [
    ["Followers", p.stats.followers],
    ["Monthly listeners", p.stats.monthly_listeners],
    ["World rank", p.stats.world_rank ? "#" + fmt(p.stats.world_rank) : null],
  ];
  stats.forEach(([label, val]) => {
    if (val == null) return;
    const chip = document.createElement("div");
    chip.className = "stat-chip";
    chip.innerHTML = `<b>${fmt(val)}</b>${esc(label)}`;
    chips.appendChild(chip);
  });

  // genre & region
  $("genre-region").innerHTML = kvRows([
    ["Genre", p.genres.length ? p.genres.join(", ") : "<span class='muted'>Not available on " + p.provider + " — use the other provider tab</span>"],
    ["Region hint", p.region_hint || "<span class='muted'>—</span>"],
    ["Concert-derived cities", p.events.filter((e) => e.city).map((e) => e.city).join(", ") || "<span class='muted'>—</span>"],
  ]);

  // bio
  $("bio-source").textContent = p.biography_source ? p.biography_source : "";
  $("bio").textContent = p.biography || "No curated biography available.";
  $("bio-warning").hidden = true;

  // stats list
  $("stats-list").innerHTML = kvRows(Object.entries(p.stats).map(([k, v]) => [k, fmt(v)]));

  // where they listen (top cities)
  const cities = p.top_cities || [];
  $("cities-count").textContent = cities.length ? `${cities.length} cities` : "";
  $("cities-list").closest(".section").style.display = cities.length ? "" : "none";
  $("cities-list").innerHTML = cities.length
    ? cities.map((c) => {
        const where = [c.city, c.country, c.region].filter(Boolean).join(", ");
        return kvRows([[where, `<b>${fmt(c.listeners)}</b>`]]);
      }).join("")
    : '<span class="muted">Not available on this provider</span>';

  // tracks
  const tcount = $("tracks-count");
  tcount.textContent = p.top_tracks.length ? `${p.top_tracks.length} tracks` : "none";
  $("tracks").innerHTML = p.top_tracks.length
    ? p.top_tracks.map((t) => `
        <div class="track">
          ${t.image_url ? `<img src="${esc(t.image_url)}" alt="" onerror="this.style.visibility='hidden'" />` : "<img alt='' />"}
          <div>
            <div class="track-name">${esc(t.name)}</div>
            <div class="track-meta">${esc(t.album || "")}${t.explicit ? " · <b>E</b>" : ""}${fmtDuration(t.duration_ms) ? " · " + fmtDuration(t.duration_ms) : ""}</div>
          </div>
          <div class="track-play">
            ${t.play_count ? `▶ ${fmt(t.play_count)}` : ""}
            ${t.preview_url ? `<audio controls preload="none" src="${esc(t.preview_url)}"></audio>` : ""}
          </div>
        </div>`).join("")
    : "<span class='muted'>No top tracks returned.</span>";

  // albums
  const acount = $("albums-count");
  acount.textContent = p.albums.length ? `${p.albums.length} releases` : "none";
  $("albums").innerHTML = p.albums.length
    ? p.albums.map((a) => `
        <div class="album">
          ${a.image_url ? `<img src="${esc(a.image_url)}" alt="" onerror="this.style.visibility='hidden'" />` : "<img alt='' />"}
          <div>
            <div class="album-name">${esc(a.name)}</div>
            <div class="album-meta">${esc([a.type, a.year].filter(Boolean).join(" · ") || "—")}</div>
          </div>
        </div>`).join("")
    : "<span class='muted'>No releases returned.</span>";

  // related
  const rcount = $("related-count");
  rcount.textContent = p.related_artists.length ? `${p.related_artists.length} artists` : "none";
  $("related").innerHTML = p.related_artists.length
    ? p.related_artists.map((r) => {
        const rawName = String(r.name || "").replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"');
        const words = rawName.trim().split(/\s+/);
        const initials = words.length >= 2 ? (words[0][0] + words[words.length - 1][0]).toUpperCase() : rawName.slice(0, 2).toUpperCase();
        const imgBlock = r.image_url
          ? `<img src="${esc(r.image_url)}" alt="${esc(rawName)}" onerror="this.parentElement.innerHTML='<span class=\\'related-avatar-fallback\\'>${esc(initials)}</span>'" />`
          : `<span class="related-avatar-fallback">${esc(initials || "♫")}</span>`;
        return `
          <div class="related-item">
            <div class="related-avatar-box">${imgBlock}</div>
            <div class="related-name">${esc(rawName)}</div>
          </div>`;
      }).join("")
    : "<span class='muted'>No similar artists found.</span>";

  // events
  const ecount = $("events-count");
  ecount.textContent = p.events.length ? `${p.events.length} events` : "none";
  $("events").innerHTML = p.events.length
    ? p.events.map((e) => `
        <div class="event">
          <div class="event-title">${esc(e.title)}</div>
          <div class="event-meta">${esc([e.city, e.start_date].filter(Boolean).join(" · ") || "—")}</div>
        </div>`).join("")
    : p.provider === "apple"
      ? "<span class='muted'>Not available on Apple Music — use the Spotify tab.</span>"
      : "<span class='muted'>No upcoming concerts found.</span>";

  // links
  $("links").innerHTML = p.external_links.length
    ? p.external_links.map((l) => `<a href="${esc(l)}" target="_blank" rel="noopener">${esc(l)}</a>`).join("")
    : "<span class='muted'>No external links on this provider.</span>";

  // banner
  const banners = p.banner_images || [];
  const bannerSec = $("banner-section");
  if (banners.length) {
    bannerSec.style.display = "";
    const best = banners.reduce((a, b) => (a.width || 0) > (b.width || 0) ? a : b, banners[0]);
    $("banner-preview").innerHTML = `<img src="${esc(best.url)}" alt="Profile banner" onerror="this.parentElement.style.display='none'" />`;
  } else {
    bannerSec.style.display = "none";
  }

  // gallery
  const gallery = p.gallery_images || [];
  const galSec = $("gallery-section");
  if (gallery.length) {
    galSec.style.display = "";
    $("gallery-count").textContent = `${gallery.length} photos`;
    $("gallery-grid").innerHTML = gallery.map((g) => `<img src="${esc(g.url)}" alt="Gallery" onerror="this.style.display='none'" />`).join("");
  } else {
    galSec.style.display = "none";
  }

  // credibility & collaboration
  const credRows = [];
  if (p.is_verified) credRows.push(["Verified", "<span style='color:var(--color-shop-violet)'>✓ Spotify Verified</span>"]);
  if (p.appears_on_count) credRows.push(["Appears On", fmt(p.appears_on_count) + " releases"]);
  if (p.featuring_count) credRows.push(["Featuring", fmt(p.featuring_count) + " collaborations"]);
  $("cred-collab").innerHTML = credRows.length ? kvRows(credRows) : '<span class="muted">—</span>';

  // pinned item
  const pinned = p.pinned_item;
  const pinSec = $("pinned-section");
  if (pinned && (pinned.name || pinned.comment)) {
    pinSec.style.display = "";
    $("pinned-item").innerHTML = `${pinned.image_url ? `<img src="${esc(pinned.image_url)}" alt="" onerror="this.style.display='none'" />` : ""}<div class="pin-info"><div class="pin-name">${esc(pinned.name || "—")}</div><div class="pin-comment">${esc(pinned.comment || "")}</div></div>`;
  } else {
    pinSec.style.display = "none";
  }

  // copyright
  const cpSec = $("copyright-section");
  if (p.copyright) {
    cpSec.style.display = "";
    $("copyright-text").textContent = p.copyright;
  } else {
    cpSec.style.display = "none";
  }

  // pre-fill preview
  renderPrefill(p.prefilled);

  // raw
  $("raw").textContent = JSON.stringify(p.raw ?? {}, null, 2);
  $("apply-output").hidden = true;

  // Fan Map & Tour Routing
  renderFanMapAndTour(p);
}

let leafletMap = null;

async function renderFanMapAndTour(p) {
  const mapSec = $("geo-tour-section");
  if (!mapSec) return;

  if ((!p.top_cities || !p.top_cities.length) && (!p.events || !p.events.length)) {
    mapSec.style.display = "none";
    return;
  }
  mapSec.style.display = "block";

  try {
    const data = await api(`/api/geo/tour-analysis/${encodeURIComponent(p.provider)}/${encodeURIComponent(p.id)}`);
    
    // Tour insight banner
    const banner = $("tour-insight-banner");
    if (banner && data.insight_headline) {
      $("tour-insight-title").textContent = data.insight_headline;
      $("tour-insight-desc").textContent = data.insight_detail;
      banner.style.display = "flex";
    }

    // Render opportunities cards
    const oppsBox = $("tour-opportunities-box");
    if (oppsBox && data.opportunities && data.opportunities.length) {
      oppsBox.innerHTML = `
        <h4 style="font-size:13px; font-weight:700; margin:12px 0 8px; color:#0f172a">🎯 Identified Tour Opportunity Markets:</h4>
        <div class="tour-opps-grid">
          ${data.opportunities.slice(0, 4).map(opp => `
            <div class="tour-opp-card">
              <div style="display:flex; justify-content:space-between; align-items:center">
                <b>${esc(opp.city)}${opp.country ? ', ' + esc(opp.country) : ''}</b>
                <span class="tour-opp-tag">${esc(opp.opportunity_score)} Opportunity</span>
              </div>
              <div style="color:var(--color-shop-violet); font-weight:600; margin:4px 0">${fmt(opp.listeners)} monthly listeners</div>
              <div style="color:#64748b; font-size:11px">${esc(opp.recommended_capacity)}</div>
            </div>
          `).join('')}
        </div>
      `;
    } else if (oppsBox) {
      oppsBox.innerHTML = '<p class="small muted" style="margin-top:6px">No unserved tour markets detected — concerts cover audience concentrations.</p>';
    }

    // Leaflet Map
    if (typeof L !== "undefined") {
      const mapDiv = $("fan-map");
      if (leafletMap) {
        leafletMap.remove();
        leafletMap = null;
      }
      mapDiv.innerHTML = "";

      const firstCity = (data.cities || []).find(c => c.lat != null && c.lon != null);
      const defaultCenter = firstCity ? [firstCity.lat, firstCity.lon] : [20, 0];
      const defaultZoom = firstCity ? 4 : 2;

      leafletMap = L.map(mapDiv, { scrollWheelZoom: false }).setView(defaultCenter, defaultZoom);

      L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png", {
        attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
        maxZoom: 18,
      }).addTo(leafletMap);

      const bounds = [];

      // Plot Audience Cities (pulsing violet circle markers)
      (data.cities || []).forEach(c => {
        if (c.lat != null && c.lon != null) {
          const latlng = [c.lat, c.lon];
          bounds.push(latlng);
          const radius = Math.max(12, Math.min(30, Math.sqrt(c.listeners || 1000) / 16));

          const circle = L.circleMarker(latlng, {
            radius: radius,
            color: "#8c52ff",
            weight: 2,
            fillColor: "#8c52ff",
            fillOpacity: 0.35,
          }).addTo(leafletMap);

          circle.bindPopup(`
            <div style="font-family:sans-serif; font-size:12px; line-height:1.4">
              <b style="font-size:13px">${esc(c.city)}</b><br>
              <span style="color:#8c52ff; font-weight:600">${fmt(c.listeners)} Monthly Listeners</span><br>
              <span style="color:#64748b">Audience Concentration</span>
            </div>
          `);
        }
      });

      // Plot Scheduled Concerts (Green circle pins)
      (data.events || []).forEach(ev => {
        if (ev.lat != null && ev.lon != null) {
          const latlng = [ev.lat, ev.lon];
          bounds.push(latlng);

          const marker = L.circleMarker(latlng, {
            radius: 8,
            color: "#10b981",
            weight: 3,
            fillColor: "#ffffff",
            fillOpacity: 1,
          }).addTo(leafletMap);

          marker.bindPopup(`
            <div style="font-family:sans-serif; font-size:12px; line-height:1.4">
              <span style="background:#dcfce7; color:#15803d; font-size:10px; font-weight:700; padding:2px 6px; border-radius:4px">CONCERT DATE</span><br>
              <b style="font-size:13px">${esc(ev.title)}</b><br>
              <span>${esc(ev.city || 'Venue')}</span><br>
              <span style="color:#64748b">${esc(ev.start_date || 'Upcoming')}</span>
            </div>
          `);
        }
      });

      if (bounds.length > 1) {
        leafletMap.fitBounds(bounds, { padding: [30, 30], maxZoom: 6 });
      }

      setTimeout(() => { if (leafletMap) leafletMap.invalidateSize(); }, 350);
    }
  } catch (err) {
    console.warn("Tour routing error:", err);
  }
}

// Embed Modal handlers
const embedBtn = $("embed-btn");
const embedModal = $("embed-modal");
const closeEmbedBtn = $("close-embed-modal");
const embedThemeSelect = $("embed-theme-select");
const embedHeightSelect = $("embed-height-select");
const embedIframePreview = $("embed-iframe-preview");
const embedCodeText = $("embed-code-text");
const copyEmbedCodeBtn = $("copy-embed-code-btn");

function updateEmbedSnippet() {
  if (!current) return;
  const theme = embedThemeSelect.value;
  const height = embedHeightSelect.value;
  const embedUrl = `${window.location.origin}/embed/${encodeURIComponent(current.provider)}/${encodeURIComponent(current.id)}?theme=${theme}`;
  const iframeHtml = `<iframe src="${embedUrl}" width="100%" height="${height}" frameborder="0" allow="autoplay; encrypted-media"></iframe>`;
  
  embedIframePreview.src = embedUrl;
  embedIframePreview.height = height;
  embedCodeText.value = iframeHtml;
}

if (embedBtn && embedModal) {
  embedBtn.addEventListener("click", () => {
    if (!current) return;
    updateEmbedSnippet();
    embedModal.hidden = false;
  });

  closeEmbedBtn.addEventListener("click", () => {
    embedModal.hidden = true;
    embedIframePreview.src = "";
  });

  embedModal.addEventListener("click", (e) => {
    if (e.target === embedModal) {
      embedModal.hidden = true;
      embedIframePreview.src = "";
    }
  });

  embedThemeSelect.addEventListener("change", updateEmbedSnippet);
  embedHeightSelect.addEventListener("change", updateEmbedSnippet);

  copyEmbedCodeBtn.addEventListener("click", () => {
    navigator.clipboard.writeText(embedCodeText.value);
    const origText = copyEmbedCodeBtn.textContent;
    copyEmbedCodeBtn.textContent = "✓ Copied to Clipboard!";
    setTimeout(() => { copyEmbedCodeBtn.textContent = origText; }, 2200);
  });
}

function kvRows(rows) {
  return rows.map(([k, v]) => `<span class="k">${esc(k)}</span><span class="v">${v}</span>`).join("");
}

function renderPrefill(fields) {
  const box = $("prefill-table");
  box.innerHTML = fields.length
    ? fields.map((f) => `
        <div class="prefill-row">
          <div>
            <div class="prefill-q">${esc(f.question)}</div>
            <div class="prefill-target">${esc(f.target)}</div>
          </div>
          <div class="prefill-val">${esc(f.value || "—")}</div>
          <span class="prefill-status ${f.available ? "ok" : "na"}">${f.available ? "✓ auto-fill" : "✗ n/a"}</span>
        </div>`).join("")
    : "<span class='muted'>No pre-fill candidates.</span>";
  $("apply-btn").hidden = false;
}

/* ---------- busy / error ---------- */
function setBusy(on) {
  const btn = $("fetch-btn");
  btn.disabled = on;
  btn.classList.toggle("loading", on);
  btn.setAttribute("aria-busy", String(on));
}

function showError(msg) {
  const el = $("error");
  el.textContent = msg;
  el.hidden = false;
}

function hideError() {
  $("error").hidden = true;
}

/* ---------- hero floating constellation ---------- */
const HERO_ARTISTS = [
  { provider: "spotify", id: "4YRxDV8wJFPHPTeXepOstw" }, // Arijit Singh
  { provider: "spotify", id: "6M2wZ9GZgrQXHCFfjv46we" }, // Dua Lipa
  { provider: "spotify", id: "6eUKZXaKkcviH0Ku9w2n3V" }, // Ed Sheeran
  { provider: "apple", id: "484568188" }, // Arijit Singh
  { provider: "apple", id: "159260351" }, // Taylor Swift
  { provider: "apple", id: "376564133" }, // Dermot Kennedy
];

async function loadHeroCards() {
  const box = $("constellation");
  const results = await Promise.allSettled(
    HERO_ARTISTS.map((a) => api(`/api/import/${a.provider}/${encodeURIComponent(a.id)}`))
  );
  let idx = 0;
  results.forEach((r) => {
    if (r.status !== "fulfilled" || !r.value.image_url) return;
    const p = r.value;
    const card = document.createElement("div");
    card.className = `hero-card pos${(idx % 6) + 1}`;
    card.dataset.provider = p.provider;
    card.dataset.url = p.url;
    card.dataset.name = p.name;
    const caption =
      p.provider === "spotify"
        ? `♪ ${fmt(p.stats.monthly_listeners || 0)} listeners`
        : `Apple Music · ${p.genres[0] || "—"}`;
    card.innerHTML = `
      <div class="hero-card-img"><img src="${esc(p.image_url)}" alt="${esc(p.name)}" loading="lazy" onerror="this.closest('.hero-card').style.display='none'"/></div>
      <div class="hero-card-name">${esc(p.name)}</div>
      <div class="hero-card-meta">${esc(caption)}</div>`;
    card.title = `Import ${p.name}`;
    card.addEventListener("click", () => loadFromHero(card));
    box.appendChild(card);
    idx++;
  });
  if (box.children.length > 0) box.classList.add("loaded");
}

function loadFromHero(card) {
  provider = card.dataset.provider;
  document.querySelectorAll(".provider-tab").forEach((t) => t.classList.toggle("active", t.dataset.provider === provider));
  $("query").value = card.dataset.url;
  updateHint();
  loadEngineNote();
  doFetch();
}

/* ---------- deep-link test URL: ?q=spotify:<query> | ?q=apple:<query> ---------- */
function applyDeepLink() {
  const params = new URLSearchParams(location.search);
  const q = params.get("q");
  if (!q) return;
  const colon = q.indexOf(":");
  const prov = colon === -1 ? null : q.slice(0, colon);
  const rest = colon === -1 ? q : q.slice(colon + 1);
  if (prov !== "spotify" && prov !== "apple") return;
  provider = prov;
  document.querySelectorAll(".provider-tab").forEach((t) => t.classList.toggle("active", t.dataset.provider === prov));
  $("query").value = rest;
  updateHint();
  loadEngineNote();
  setTimeout(doFetch, 150);
}

/* ---------- init ---------- */
updateHint();
loadEngineNote();
loadHeroCards();
applyDeepLink();

