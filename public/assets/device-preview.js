/**
 * Multi-Device Live Preview Studio
 * Provides 1:1 hardware and viewport simulation across Mobile, Tablet, iPad, Laptop, and Desktop.
 * Accurately triggers native CSS @media queries by embedding real iframe viewports.
 */

(function (root, factory) {
  if (typeof define === "function" && define.amd) {
    define([], factory);
  } else if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.DevicePreview = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {

  const DEVICES = {
    "mobile": { name: "iPhone 15 / Galaxy", width: 393, height: 852, type: "mobile", icon: "📱", label: "Mobile" },
    "compact": { name: "iPhone SE / Mini", width: 375, height: 667, type: "mobile", icon: "📱", label: "Compact" },
    "ipad": { name: "iPad Air 10.9\"", width: 820, height: 1180, type: "tablet", icon: "📲", label: "iPad" },
    "tablet": { name: "iPad Mini / Tablet", width: 768, height: 1024, type: "tablet", icon: "📲", label: "Tablet" },
    "laptop": { name: "MacBook 13\" / Laptop", width: 1280, height: 800, type: "laptop", icon: "💻", label: "Laptop" },
    "desktop": { name: "Desktop Display", width: 1440, height: 900, type: "desktop", icon: "🖥️", label: "Desktop" },
    "fluid": { name: "Responsive Fluid", width: 0, height: 0, type: "fluid", icon: "↔️", label: "Fluid" },
  };

  const state = {
    activeDeviceKey: "mobile",
    isLandscape: false,
    scaleMode: "auto", // "auto" | "1" | "0.75" | "0.5"
    bezelOn: true,
    target: "link", // "link" | "epk" | "embed"
    provider: "spotify",
    id: "0tC995Rfn9k2l7nqgCZsV7",
    isOpen: false,
  };

  let dom = null;

  function ensureModal() {
    if (dom) return dom;

    const modal = document.createElement("div");
    modal.id = "devprev-modal";
    modal.className = "devprev-modal";
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-label", "Multi-Device Viewport Preview Studio");

    modal.innerHTML = `
      <header class="devprev-header">
        <div class="devprev-left-group">
          <span class="devprev-title-badge">📱 Device Simulator</span>
          
          <!-- Page Target Selector -->
          <div class="devprev-targets" id="devprev-targets">
            <button class="devprev-target-btn active" data-target="link">🔗 Smart Link</button>
            <button class="devprev-target-btn" data-target="epk">📄 Public EPK</button>
            <button class="devprev-target-btn" data-target="embed">🎵 Player Embed</button>
          </div>

          <!-- Device Presets -->
          <div class="devprev-devices" id="devprev-devices">
            ${Object.entries(DEVICES).map(([k, d]) => `
              <button class="devprev-device-btn ${k === 'mobile' ? 'active' : ''}" data-device="${k}" title="${d.name} (${d.width ? d.width + '×' + d.height + ' px' : 'Fluid'})">
                <span>${d.icon}</span> <span>${d.label}</span>
              </button>
            `).join("")}
          </div>
        </div>

        <div class="devprev-right-group">
          <!-- Orientation Toggle -->
          <button id="devprev-rotate-btn" class="devprev-btn" title="Rotate Orientation (Portrait ↔ Landscape)">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg>
            <span id="devprev-orient-label">Rotate</span>
          </button>

          <!-- Scaling Dropdown -->
          <select id="devprev-scale-select" class="devprev-scale-select" title="Display Zoom Level">
            <option value="auto" selected>Fit Screen (Auto)</option>
            <option value="1">100% (Native)</option>
            <option value="0.75">75% Zoom</option>
            <option value="0.5">50% Zoom</option>
          </select>

          <!-- Bezel Toggle -->
          <button id="devprev-bezel-btn" class="devprev-btn" title="Toggle Hardware Frame / Frameless Viewport">
            <span id="devprev-bezel-label">Bezel: ON</span>
          </button>

          <!-- Close Modal -->
          <button id="devprev-close-btn" class="devprev-close-btn" title="Close Preview (Esc)">
            ✕ Close
          </button>
        </div>
      </header>

      <!-- Status Bar with Dimension Specs -->
      <div class="devprev-status-bar">
        <div>
          <span class="devprev-status-badge" id="devprev-info-badge">iPhone 15 · 393 × 852 px</span>
          <span style="margin: 0 8px; opacity:0.4">|</span>
          <span id="devprev-scale-badge">Scale: Auto</span>
          <span style="margin: 0 8px; opacity:0.4">|</span>
          <span style="color:#10b981; font-weight:800">● 1:1 Live Browser Engine</span>
        </div>
        <div class="devprev-external-links">
          <button id="devprev-copy-url">📋 Copy Target URL</button>
          <a id="devprev-newtab" href="#" target="_blank" rel="noopener">↗ Open in Tab</a>
        </div>
      </div>

      <!-- Viewport Stage / Canvas -->
      <div class="devprev-stage" id="devprev-stage">
        <div class="devprev-device-wrap" id="devprev-device-wrap">
          <div class="devprev-frame bezel-mobile" id="devprev-frame">
            <!-- Hardware Accents -->
            <div class="devprev-notch"></div>
            <div class="devprev-home-bar"></div>
            
            <!-- Frame Window with Real Iframe -->
            <div class="devprev-iframe-wrap" id="devprev-iframe-wrap">
              <iframe id="devprev-iframe" class="devprev-iframe" allow="autoplay; clipboard-write"></iframe>
            </div>

            <!-- Laptop Base Element -->
            <div class="devprev-laptop-base" style="display:none">
              <div class="devprev-laptop-notch"></div>
            </div>

            <!-- Desktop Stand Elements -->
            <div class="devprev-desktop-stand" style="display:none"></div>
            <div class="devprev-desktop-base" style="display:none"></div>
          </div>
        </div>
      </div>
    `;

    document.body.appendChild(modal);

    // Cache elements
    dom = {
      modal,
      targets: modal.querySelector("#devprev-targets"),
      devices: modal.querySelector("#devprev-devices"),
      rotateBtn: modal.querySelector("#devprev-rotate-btn"),
      orientLabel: modal.querySelector("#devprev-orient-label"),
      scaleSelect: modal.querySelector("#devprev-scale-select"),
      bezelBtn: modal.querySelector("#devprev-bezel-btn"),
      bezelLabel: modal.querySelector("#devprev-bezel-label"),
      closeBtn: modal.querySelector("#devprev-close-btn"),
      infoBadge: modal.querySelector("#devprev-info-badge"),
      scaleBadge: modal.querySelector("#devprev-scale-badge"),
      copyUrlBtn: modal.querySelector("#devprev-copy-url"),
      newTabLink: modal.querySelector("#devprev-newtab"),
      stage: modal.querySelector("#devprev-stage"),
      deviceWrap: modal.querySelector("#devprev-device-wrap"),
      frame: modal.querySelector("#devprev-frame"),
      iframeWrap: modal.querySelector("#devprev-iframe-wrap"),
      iframe: modal.querySelector("#devprev-iframe"),
    };

    // Attach Event Listeners
    dom.closeBtn.addEventListener("click", close);

    // Target Switcher
    dom.targets.addEventListener("click", (e) => {
      const btn = e.target.closest(".devprev-target-btn");
      if (!btn) return;
      dom.targets.querySelectorAll(".devprev-target-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      state.target = btn.dataset.target;
      updateIframeUrl();
    });

    // Device Preset Switcher
    dom.devices.addEventListener("click", (e) => {
      const btn = e.target.closest(".devprev-device-btn");
      if (!btn) return;
      dom.devices.querySelectorAll(".devprev-device-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      state.activeDeviceKey = btn.dataset.device;
      state.isLandscape = false; // reset orientation on device change
      renderViewport();
    });

    // Rotate Orientation
    dom.rotateBtn.addEventListener("click", () => {
      if (state.activeDeviceKey === "fluid") return;
      state.isLandscape = !state.isLandscape;
      renderViewport();
    });

    // Scale Select
    dom.scaleSelect.addEventListener("change", (e) => {
      state.scaleMode = e.target.value;
      applyScaling();
    });

    // Bezel Toggle
    dom.bezelBtn.addEventListener("click", () => {
      state.bezelOn = !state.bezelOn;
      dom.bezelLabel.textContent = `Bezel: ${state.bezelOn ? "ON" : "OFF"}`;
      dom.bezelBtn.classList.toggle("active", state.bezelOn);
      renderViewport();
    });

    // Copy Target URL
    dom.copyUrlBtn.addEventListener("click", () => {
      const currentUrl = dom.iframe.src;
      navigator.clipboard.writeText(currentUrl).then(() => {
        const orig = dom.copyUrlBtn.textContent;
        dom.copyUrlBtn.textContent = "✓ Copied!";
        setTimeout(() => { dom.copyUrlBtn.textContent = orig; }, 1500);
      });
    });

    // Keyboard navigation (Esc to close, R to rotate)
    window.addEventListener("keydown", (e) => {
      if (!state.isOpen) return;
      if (e.key === "Escape") {
        close();
      }
      if ((e.key === "r" || e.key === "R") && !e.ctrlKey && !e.metaKey && e.target.tagName !== "INPUT") {
        state.isLandscape = !state.isLandscape;
        renderViewport();
      }
    });

    // Window resize handler for Auto Fit scaling
    window.addEventListener("resize", () => {
      if (state.isOpen && state.scaleMode === "auto") {
        applyScaling();
      }
    });

    return dom;
  }

  function getTargetUrl() {
    const prov = encodeURIComponent(state.provider);
    const id = encodeURIComponent(state.id);
    if (state.target === "epk") return `/epk/${prov}/${id}`;
    if (state.target === "embed") return `/embed/${prov}/${id}`;
    return `/link/${prov}/${id}`;
  }

  function updateIframeUrl() {
    const url = getTargetUrl();
    if (dom.iframe.src !== window.location.origin + url && dom.iframe.getAttribute("src") !== url) {
      dom.iframe.src = url;
    }
    dom.newTabLink.href = url;
  }

  function renderViewport() {
    ensureModal();
    const dev = DEVICES[state.activeDeviceKey];
    if (!dev) return;

    let w = dev.width;
    let h = dev.height;

    // Handle landscape orientation
    if (state.isLandscape && dev.type !== "fluid") {
      const tmp = w;
      w = h;
      h = tmp;
    }

    // Set frame classes
    dom.frame.className = "devprev-frame";
    if (state.bezelOn && dev.type !== "fluid") {
      dom.frame.classList.add(`bezel-${dev.type}`);
    } else {
      dom.frame.classList.add("bezel-none");
    }

    // Set hardware accent visibility
    const laptopBase = dom.frame.querySelector(".devprev-laptop-base");
    const deskStand = dom.frame.querySelector(".devprev-desktop-stand");
    const deskBase = dom.frame.querySelector(".devprev-desktop-base");

    if (laptopBase) laptopBase.style.display = (state.bezelOn && dev.type === "laptop") ? "block" : "none";
    if (deskStand) deskStand.style.display = (state.bezelOn && dev.type === "desktop") ? "block" : "none";
    if (deskBase) deskBase.style.display = (state.bezelOn && dev.type === "desktop") ? "block" : "none";

    // Set container and iframe dimensions
    if (dev.type === "fluid") {
      dom.iframeWrap.style.width = "100%";
      dom.iframeWrap.style.height = "100%";
      dom.frame.style.width = "100%";
      dom.frame.style.height = "calc(100vh - 160px)";
      dom.deviceWrap.style.width = "100%";
      dom.deviceWrap.style.height = "100%";
      dom.deviceWrap.style.transform = "none";
      dom.infoBadge.textContent = "Fluid Responsive (100% Screen)";
      dom.rotateBtn.style.opacity = "0.4";
      dom.rotateBtn.style.pointerEvents = "none";
    } else {
      dom.iframeWrap.style.width = `${w}px`;
      dom.iframeWrap.style.height = `${h}px`;
      dom.frame.style.width = `${w}px`;
      dom.frame.style.height = `${h}px`;
      dom.rotateBtn.style.opacity = "1";
      dom.rotateBtn.style.pointerEvents = "auto";
      const orientText = state.isLandscape ? "Landscape" : "Portrait";
      dom.infoBadge.textContent = `${dev.name} · ${w} × ${h} px (${orientText})`;
      applyScaling(w, h);
    }

    dom.orientLabel.textContent = state.isLandscape ? "Landscape ⟳" : "Portrait ⟳";
  }

  function applyScaling(widthOverride, heightOverride) {
    ensureModal();
    const dev = DEVICES[state.activeDeviceKey];
    if (dev.type === "fluid") return;

    let w = widthOverride || dev.width;
    let h = heightOverride || dev.height;
    if (state.isLandscape && dev.type !== "fluid" && !widthOverride) {
      const tmp = w; w = h; h = tmp;
    }

    // Account for bezel thickness in outer dimension
    const bezelPad = state.bezelOn ? (dev.type === "tablet" ? 36 : (dev.type === "mobile" ? 28 : 24)) : 4;
    const totalW = w + bezelPad;
    const totalH = h + bezelPad + (state.bezelOn && dev.type === "laptop" ? 20 : 0);

    let scale = 1;
    if (state.scaleMode === "auto") {
      const stageW = dom.stage.clientWidth - 48;
      const stageH = dom.stage.clientHeight - 48;
      const scaleX = stageW / totalW;
      const scaleY = stageH / totalH;
      scale = Math.min(1, scaleX, scaleY);
      scale = Math.max(0.25, Math.floor(scale * 100) / 100);
      dom.scaleBadge.textContent = `Scale: ${Math.round(scale * 100)}% (Auto Fit)`;
    } else {
      scale = parseFloat(state.scaleMode) || 1;
      dom.scaleBadge.textContent = `Scale: ${Math.round(scale * 100)}%`;
    }

    // Apply scaling
    dom.deviceWrap.style.width = `${Math.round(totalW * scale)}px`;
    dom.deviceWrap.style.height = `${Math.round(totalH * scale)}px`;
    dom.deviceWrap.style.transform = `scale(${scale})`;
    dom.deviceWrap.style.transformOrigin = "top center";
  }

  function open(options = {}) {
    ensureModal();
    if (options.defaultTarget) state.target = options.defaultTarget;
    if (options.provider) state.provider = options.provider;
    if (options.id) state.id = options.id;
    if (options.device && DEVICES[options.device]) state.activeDeviceKey = options.device;

    // Sync active target button
    dom.targets.querySelectorAll(".devprev-target-btn").forEach(b => {
      b.classList.toggle("active", b.dataset.target === state.target);
    });

    // Sync active device button
    dom.devices.querySelectorAll(".devprev-device-btn").forEach(b => {
      b.classList.toggle("active", b.dataset.device === state.activeDeviceKey);
    });

    updateIframeUrl();
    renderViewport();

    dom.modal.classList.add("active");
    state.isOpen = true;
    document.body.style.overflow = "hidden";
  }

  function close() {
    if (!dom) return;
    dom.modal.classList.remove("active");
    state.isOpen = false;
    document.body.style.overflow = "";
    // Clean iframe to free audio memory
    setTimeout(() => {
      if (!state.isOpen) dom.iframe.src = "about:blank";
    }, 200);
  }

  return {
    open,
    close,
    setTarget: (t) => { state.target = t; updateIframeUrl(); },
    setDevice: (d) => { state.activeDeviceKey = d; renderViewport(); },
    getState: () => ({ ...state }),
  };
});
