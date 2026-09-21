"use strict";

/* ============================================================
   CSV FILTER STUDIO — Standalone Module
   Account integrity, spam filtering, and cohort extraction
   ============================================================ */

const $ = (id) => document.getElementById(id);
const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );

let filterFile = null;
let filterResults = null;
let currentFilterTab = "kept";

function isAllowedFile(name) {
  const lower = name.toLowerCase();
  return lower.endsWith(".csv") || lower.endsWith(".xlsx") || lower.endsWith(".xls");
}

function formatFileSize(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

// Upload zone interactions
const uploadZone = $("upload-zone");
const fileInput = $("csv-file-input");
const browseBtn = $("upload-browse-btn");
const removeFileBtn = $("remove-file-btn");
const runFilterBtn = $("run-filter-btn");

if (uploadZone && fileInput) {
  if (browseBtn) {
    browseBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      fileInput.click();
    });
  }

  uploadZone.addEventListener("click", () => fileInput.click());

  uploadZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    uploadZone.classList.add("dragover");
  });

  uploadZone.addEventListener("dragleave", () => {
    uploadZone.classList.remove("dragover");
  });

  uploadZone.addEventListener("drop", (e) => {
    e.preventDefault();
    uploadZone.classList.remove("dragover");
    const files = e.dataTransfer.files;
    if (files.length && isAllowedFile(files[0].name)) {
      handleFileSelect(files[0]);
    }
  });

  fileInput.addEventListener("change", (e) => {
    if (e.target.files.length) {
      handleFileSelect(e.target.files[0]);
    }
  });
}

function handleFileSelect(file) {
  filterFile = file;
  $("file-name-display").textContent = file.name;
  $("file-size-display").textContent = formatFileSize(file.size);
  $("file-info").hidden = false;
  $("filter-options").hidden = false;
  $("run-filter-btn").disabled = false;
  $("filter-results").hidden = true;
  $("filter-progress").hidden = true;
  if (uploadZone) uploadZone.style.display = "none";
}

if (removeFileBtn) {
  removeFileBtn.addEventListener("click", () => {
    filterFile = null;
    if (fileInput) fileInput.value = "";
    $("file-info").hidden = true;
    $("filter-options").hidden = true;
    $("filter-results").hidden = true;
    $("filter-progress").hidden = true;
    if (uploadZone) uploadZone.style.display = "";
  });
}

if (runFilterBtn) {
  runFilterBtn.addEventListener("click", runFilter);
}

async function runFilter() {
  if (!filterFile) return;

  const scrapeEnabled = $("scrape-toggle")?.checked ?? true;
  runFilterBtn.disabled = true;
  runFilterBtn.textContent = "Processing...";
  $("filter-progress").hidden = false;
  $("filter-results").hidden = true;
  $("filter-status").textContent = "";

  const scrapeProg = $("scrape-progress");
  const fill = $("progress-fill");
  const text = $("progress-text");
  const startTime = Date.now();

  if (scrapeEnabled && scrapeProg) {
    scrapeProg.hidden = false;
    $("scrape-count").textContent = "0";
    $("scrape-total").textContent = "...";
    $("scrape-rate").textContent = "";
  } else if (scrapeProg) {
    scrapeProg.hidden = true;
  }

  fill.style.width = "5%";
  text.textContent = "Uploading file...";

  const formData = new FormData();
  formData.append("file", filterFile);
  formData.append("scrape", String(scrapeEnabled));

  const dateStart = $("date-start")?.value;
  const dateEnd = $("date-end")?.value;
  if (dateStart) formData.append("date_start", dateStart);
  if (dateEnd) formData.append("date_end", dateEnd);

  try {
    const endpoint = scrapeEnabled ? "/api/filter/upload-scrape-stream" : "/api/filter/upload";
    const response = await fetch(endpoint, { method: "POST", body: formData });

    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: { message: "Unknown error" } }));
      throw new Error(err.detail?.message || `HTTP ${response.status}`);
    }

    if (!scrapeEnabled) {
      filterResults = await response.json();
      fill.style.width = "100%";
      text.textContent = "Complete!";
      setTimeout(() => {
        $("filter-progress").hidden = true;
        renderFilterResults(filterResults);
      }, 400);
      runFilterBtn.disabled = false;
      runFilterBtn.textContent = "Run Filter Pipeline";
      return;
    }

    // SSE stream: read line by line
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let currentEvent = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop(); // keep incomplete line in buffer

      for (const line of lines) {
        if (line.startsWith("event: ")) {
          currentEvent = line.slice(7).trim();
        } else if (line.startsWith("data: ")) {
          const jsonStr = line.slice(6);
          try {
            const payload = JSON.parse(jsonStr);
            handleSSEEvent(currentEvent, payload, startTime, fill, text);
          } catch { /* skip malformed */ }
          currentEvent = "";
        }
      }
    }
  } catch (err) {
    fill.style.width = "0%";
    text.textContent = "";
    $("filter-progress").hidden = true;
    $("filter-status").textContent = "Error: " + err.message;
    $("filter-status").style.color = "#dc2626";
  }

  runFilterBtn.disabled = false;
  runFilterBtn.textContent = "Run Filter Pipeline";
}

function handleSSEEvent(event, payload, startTime, fill, text) {
  const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);

  switch (event) {
    case "phase":
      if (payload.phase === "scraping") {
        fill.style.width = "15%";
        text.textContent = `Scraping ${payload.total || "?"} artist profiles...`;
      } else if (payload.phase === "filtering") {
        fill.style.width = "85%";
        text.textContent = "Running multi-tier filter rules...";
      } else if (payload.phase === "done") {
        fill.style.width = "100%";
        text.textContent = `Complete in ${elapsed}s`;
      }
      break;

    case "progress": {
      const pct = 15 + (payload.completed / payload.total) * 65;
      fill.style.width = pct + "%";
      text.textContent = `Scraping profiles: ${payload.completed}/${payload.total} (${payload.found} found) — ${elapsed}s`;
      if ($("scrape-progress")) {
        $("scrape-count").textContent = payload.found;
        $("scrape-total").textContent = payload.total;
        $("scrape-rate").textContent = payload.elapsed ? `— ${payload.elapsed}s` : "";
      }
      break;
    }

    case "done":
      filterResults = payload;
      fill.style.width = "100%";
      text.textContent = `Complete in ${elapsed}s — ${payload.scrape_stats?.profiles_found || 0} profiles verified`;
      if ($("scrape-progress")) {
        const ss = payload.scrape_stats || {};
        $("scrape-count").textContent = ss.profiles_found || 0;
        $("scrape-total").textContent = ss.slugs_scraped || 0;
        $("scrape-rate").textContent = ss.elapsed_seconds ? `— ${ss.elapsed_seconds}s` : "";
      }
      setTimeout(() => {
        $("filter-progress").hidden = true;
        renderFilterResults(filterResults);
      }, 600);
      break;

    case "error":
      fill.style.width = "0%";
      text.textContent = "";
      $("filter-progress").hidden = true;
      $("filter-status").textContent = "Error: " + (payload.message || "Unknown");
      $("filter-status").style.color = "#dc2626";
      break;
  }
}

function renderFilterResults(data) {
  $("filter-results").hidden = false;

  // Summary stats
  $("stat-total").textContent = Number(data.total_records || 0).toLocaleString();
  $("stat-kept").textContent = Number(data.kept_count || 0).toLocaleString();
  $("stat-removed").textContent = Number(data.removed_count || 0).toLocaleString();
  $("stat-c1").textContent = Number(data.cohort1_count || 0).toLocaleString();
  $("stat-c2").textContent = Number(data.cohort2_count || 0).toLocaleString();

  // Removal reasons
  const reasonsList = $("reasons-list");
  const reasons = data.removal_reasons || {};
  const maxCount = Math.max(...Object.values(reasons), 1);
  reasonsList.innerHTML = Object.entries(reasons)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 15)
    .map(([reason, count]) => {
      const pct = (count / maxCount) * 100;
      return `<div class="reason-row">
        <span class="reason-count">${count}</span>
        <div class="reason-bar" style="width:${pct}%"></div>
        <span class="reason-label">${esc(reason)}</span>
      </div>`;
    }).join("");

  // Tab counts
  $("tab-kept-count").textContent = data.kept_count;
  $("tab-removed-count").textContent = data.removed_count;

  // Default tab
  currentFilterTab = "kept";
  renderFilterTable(data);

  // Tab switching
  document.querySelectorAll(".results-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      currentFilterTab = tab.dataset.tab;
      document.querySelectorAll(".results-tab").forEach((t) => t.classList.toggle("active", t === tab));
      renderFilterTable(data);
    });
  });

  // Download buttons
  const csvBtn = $("download-csv-btn");
  const jsonBtn = $("download-json-btn");
  if (csvBtn) csvBtn.onclick = () => downloadFilter("csv");
  if (jsonBtn) jsonBtn.onclick = () => downloadFilter("json");
}

function renderFilterTable(data) {
  const items = currentFilterTab === "kept" ? data.kept : data.removed;
  const thead = $("results-thead");
  const tbody = $("results-tbody");

  if (currentFilterTab === "kept") {
    thead.innerHTML = "<tr><th>Email</th><th>Name</th><th>Slug</th><th>Country</th><th>Cohort</th></tr>";
    tbody.innerHTML = items.map((r) =>
      `<tr><td>${esc(r.email || "")}</td><td>${esc(r.name || "")}</td><td>${esc(r.slug || "")}</td><td>${esc(r.country || "")}</td><td>${r.cohort === 1 ? "Activation" : r.cohort === 2 ? "Completion" : "—"}</td></tr>`
    ).join("");
  } else {
    thead.innerHTML = "<tr><th>Email</th><th>Name</th><th>Slug</th><th>Country</th><th>Reason</th></tr>";
    tbody.innerHTML = items.map((r) =>
      `<tr><td>${esc(r.email || "")}</td><td>${esc(r.name || "")}</td><td>${esc(r.slug || "")}</td><td>${esc(r.country || "")}</td><td>${esc(r.reason || "")}</td></tr>`
    ).join("");
  }
}

async function downloadFilter(format) {
  if (!filterFile) return;

  const scrapeEnabled = $("scrape-toggle")?.checked ?? false;
  const formData = new FormData();
  formData.append("file", filterFile);
  formData.append("format", format);
  formData.append("scrape", String(scrapeEnabled));

  const dateStart = $("date-start")?.value;
  const dateEnd = $("date-end")?.value;
  if (dateStart) formData.append("date_start", dateStart);
  if (dateEnd) formData.append("date_end", dateEnd);

  try {
    const response = await fetch("/api/filter/download", {
      method: "POST",
      body: formData,
    });

    if (!response.ok) throw new Error("Download failed");

    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `filtered_results.${format}`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch (err) {
    alert("Download failed: " + err.message);
  }
}
