/* Shared sidebar. Each page sets `NAV_BASE` (relative path to docs/ root)
   and `NAV_CURRENT` (this page's key, or "" for none) before loading this script. */
(function () {
  var base = typeof NAV_BASE !== "undefined" ? NAV_BASE : "";
  var current = typeof NAV_CURRENT !== "undefined" ? NAV_CURRENT : "";

  var ADDONS = [
    { slug: "bone-renamer", title: "Bone Renamer", cat: "Rigging", small: true },
    { slug: "bweight", title: "Bweight", cat: "Paint" },
    { slug: "cyclic-animation-baker", title: "Cyclic Animation Baker", cat: "Animation" },
    { slug: "gizmo-plus", title: "Gizmo Plus", cat: "3D View" },
    { slug: "guard-edit-mode", title: "Guard Edit Mode", cat: "System", small: true },
    { slug: "hdri-maker", title: "HDRi Maker", cat: "3D View" },
    { slug: "open-console-startup", title: "Open Console on Startup", cat: "System", small: true },
    { slug: "screenshot-nodes", title: "ScreenshotNodes", cat: "Node" },
    { slug: "symmetrize-plus", title: "Symmetrize Plus", cat: "Mesh" },
    { slug: "target-please", title: "Tracking Camera Rig", cat: "Camera" },
    { slug: "translate-shapekeys", title: "translateShapekeysToEnglish", cat: "Rigging", small: true },
    { slug: "world-space-brush", title: "World-Space Brush", cat: "Paint" }
  ];

  window.BP_ADDONS = ADDONS;

  function esc(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function render() {
    var html = "";
    html += '<h4>Guide</h4><ul>';
    html += '<li><a href="' + base + 'index.html" class="' + (current === "home" ? "active" : "") + '">Getting Started</a></li>';
    html += '<li><a href="' + base + 'index.html#installation" class="' + (current === "installation" ? "active" : "") + '">Installation</a></li>';
    html += '</ul>';

    function addonItem(a) {
      var active = current === a.slug ? "active" : "";
      return '<li><a href="' + base + 'addons/' + a.slug + '/index.html" class="' + active + '">' +
        '<span>' + esc(a.title) + '</span><span class="cat">' + esc(a.cat) + '</span>' +
        '</a></li>';
    }

    var mainAddons = ADDONS.filter(function (a) { return !a.small; });
    var smallAddons = ADDONS.filter(function (a) { return a.small; });
    var smallHasActive = smallAddons.some(function (a) { return a.slug === current; });

    html += '<h4>Add-ons</h4><ul>';
    mainAddons.forEach(function (a) { html += addonItem(a); });
    html += '</ul>';

    html += '<details class="sidebar-collapsible"' + (smallHasActive ? " open" : "") + '>' +
      '<summary>Smaller Add-ons</summary><ul>';
    smallAddons.forEach(function (a) { html += addonItem(a); });
    html += '</ul></details>';

    var mount = document.getElementById("sidebar-mount");
    if (mount) mount.innerHTML = html;
  }

  // ---- Icons ----------------------------------------------------------
  var ICON_SEARCH = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>';
  var ICON_SUN = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"></circle><line x1="12" y1="2" x2="12" y2="4"></line><line x1="12" y1="20" x2="12" y2="22"></line><line x1="4.9" y1="4.9" x2="6.3" y2="6.3"></line><line x1="17.7" y1="17.7" x2="19.1" y2="19.1"></line><line x1="2" y1="12" x2="4" y2="12"></line><line x1="20" y1="12" x2="22" y2="12"></line><line x1="4.9" y1="19.1" x2="6.3" y2="17.7"></line><line x1="17.7" y1="6.3" x2="19.1" y2="4.9"></line></svg>';
  var ICON_MOON = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg>';
  var ICON_MONITOR = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2"></rect><line x1="8" y1="21" x2="16" y2="21"></line><line x1="12" y1="17" x2="12" y2="21"></line></svg>';
  var ICON_GLOBE = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path></svg>';
  var ICON_CHEV = '<svg class="chev" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>';
  var ICON_DOC = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>';
  var ICON_CLOSE = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>';

  // ---- Theme toggle -----------------------------------------------------
  var THEME_KEY = "bp-theme";

  function getStoredTheme() {
    try { return localStorage.getItem(THEME_KEY) || "auto"; } catch (e) { return "auto"; }
  }

  function applyTheme(theme) {
    if (theme === "light" || theme === "dark") {
      document.documentElement.setAttribute("data-theme", theme);
    } else {
      document.documentElement.removeAttribute("data-theme");
    }
  }

  function setTheme(theme) {
    try { localStorage.setItem(THEME_KEY, theme); } catch (e) {}
    applyTheme(theme);
    updateThemeUI(theme);
  }

  function themeIcon(theme) {
    return theme === "light" ? ICON_SUN : theme === "dark" ? ICON_MOON : ICON_MONITOR;
  }
  function themeLabel(theme) {
    return theme === "light" ? "Light" : theme === "dark" ? "Dark" : "Auto";
  }

  function updateThemeUI(theme) {
    var toggle = document.getElementById("theme-toggle");
    if (!toggle) return;
    toggle.innerHTML = themeIcon(theme) + '<span>' + themeLabel(theme) + '</span>' + ICON_CHEV;
    var menu = document.getElementById("theme-menu");
    if (menu) {
      Array.prototype.forEach.call(menu.querySelectorAll("button"), function (b) {
        b.classList.toggle("active", b.getAttribute("data-theme-choice") === theme);
      });
    }
  }

  function closeAllDropdowns(except) {
    Array.prototype.forEach.call(document.querySelectorAll(".dropdown.open"), function (d) {
      if (d !== except) d.classList.remove("open");
    });
  }

  // ---- Header (search trigger + dropdowns) ------------------------------
  function renderHeader() {
    var topbar = document.querySelector(".topbar");
    var topLinks = document.querySelector(".topbar .top-links");
    if (!topbar || !topLinks) return;

    // Search trigger, inserted between the brand and the top-links.
    var searchWrap = document.createElement("div");
    searchWrap.className = "search-wrap";
    searchWrap.innerHTML =
      '<button class="search-trigger" id="search-trigger" aria-label="Search">' +
        ICON_SEARCH +
        '<span class="st-label">Search</span>' +
        '<kbd>Ctrl K</kbd>' +
      '</button>';
    topbar.insertBefore(searchWrap, topLinks);

    // Theme dropdown.
    var themeDropdown = document.createElement("div");
    themeDropdown.className = "dropdown";
    themeDropdown.id = "theme-dropdown";
    themeDropdown.innerHTML =
      '<button class="dropdown-toggle" id="theme-toggle" aria-label="Toggle theme"></button>' +
      '<div class="dropdown-menu" id="theme-menu">' +
        '<button data-theme-choice="light">' + ICON_SUN + ' <span style="margin-left:.4rem">Light</span></button>' +
        '<button data-theme-choice="dark">' + ICON_MOON + ' <span style="margin-left:.4rem">Dark</span></button>' +
        '<button data-theme-choice="auto">' + ICON_MONITOR + ' <span style="margin-left:.4rem">Auto</span></button>' +
      '</div>';
    topLinks.appendChild(themeDropdown);

    // Language dropdown (English only for now).
    var langDropdown = document.createElement("div");
    langDropdown.className = "dropdown";
    langDropdown.id = "lang-dropdown";
    langDropdown.innerHTML =
      '<button class="dropdown-toggle" id="lang-toggle" aria-label="Language">' + ICON_GLOBE + ' <span>English</span>' + ICON_CHEV + '</button>' +
      '<div class="dropdown-menu"><button class="active">English</button></div>';
    topLinks.appendChild(langDropdown);

    updateThemeUI(getStoredTheme());

    themeDropdown.querySelector(".dropdown-toggle").addEventListener("click", function (e) {
      e.stopPropagation();
      closeAllDropdowns(themeDropdown);
      themeDropdown.classList.toggle("open");
    });
    Array.prototype.forEach.call(themeDropdown.querySelectorAll("[data-theme-choice]"), function (b) {
      b.addEventListener("click", function () {
        setTheme(b.getAttribute("data-theme-choice"));
        themeDropdown.classList.remove("open");
      });
    });

    langDropdown.querySelector(".dropdown-toggle").addEventListener("click", function (e) {
      e.stopPropagation();
      closeAllDropdowns(langDropdown);
      langDropdown.classList.toggle("open");
    });
    langDropdown.querySelector(".dropdown-menu button").addEventListener("click", function () {
      langDropdown.classList.remove("open");
    });

    document.addEventListener("click", function () { closeAllDropdowns(); });

    document.getElementById("search-trigger").addEventListener("click", openSearch);
  }

  // ---- Search modal -------------------------------------------------------
  var searchIndexLoaded = false;
  var searchOverlay, searchInput, searchResults;

  function loadSearchIndex(cb) {
    if (window.BP_SEARCH_INDEX) { searchIndexLoaded = true; return cb(); }
    var s = document.createElement("script");
    s.src = base + "assets/search-index.js";
    s.onload = function () { searchIndexLoaded = true; cb(); };
    document.head.appendChild(s);
  }

  function esc2(s) { return esc(String(s)); }

  function highlight(text, q) {
    if (!q) return esc2(text);
    var idx = text.toLowerCase().indexOf(q.toLowerCase());
    if (idx === -1) return esc2(text);
    return esc2(text.slice(0, idx)) + "<mark>" + esc2(text.slice(idx, idx + q.length)) + "</mark>" + esc2(text.slice(idx + q.length));
  }

  function buildSearchModal() {
    searchOverlay = document.createElement("div");
    searchOverlay.className = "search-overlay";
    searchOverlay.id = "search-overlay";
    searchOverlay.innerHTML =
      '<div class="search-modal">' +
        '<div class="search-input-wrap">' +
          ICON_SEARCH +
          '<input type="text" id="search-input" placeholder="Search add-ons and docs..." autocomplete="off">' +
          '<button class="search-close" id="search-close" aria-label="Close">' + ICON_CLOSE + '</button>' +
        '</div>' +
        '<div class="search-results" id="search-results"></div>' +
      '</div>';
    document.body.appendChild(searchOverlay);

    searchInput = document.getElementById("search-input");
    searchResults = document.getElementById("search-results");

    searchOverlay.addEventListener("click", function (e) {
      if (e.target === searchOverlay) closeSearch();
    });
    document.getElementById("search-close").addEventListener("click", closeSearch);
    searchInput.addEventListener("input", function () { runSearch(searchInput.value); });
  }

  function runSearch(query) {
    query = query.trim();
    if (!query) {
      searchResults.innerHTML = '<div class="search-meta">Type to search add-ons, features, and usage notes.</div>';
      return;
    }
    var q = query.toLowerCase();
    var pages = window.BP_SEARCH_INDEX || [];
    var matches = [];

    pages.forEach(function (page) {
      var pageHit = page.title.toLowerCase().indexOf(q) !== -1 || (page.desc || "").toLowerCase().indexOf(q) !== -1;
      var sectionHits = (page.sections || []).filter(function (s) {
        return s.title.toLowerCase().indexOf(q) !== -1 || (s.snippet || "").toLowerCase().indexOf(q) !== -1;
      });
      if (pageHit || sectionHits.length) {
        matches.push({ page: page, sections: sectionHits.slice(0, 3) });
      }
    });

    if (!matches.length) {
      searchResults.innerHTML = '<div class="search-empty">No results for &ldquo;' + esc2(query) + '&rdquo;</div>';
      return;
    }

    var html = '<div class="search-meta">' + matches.length + ' result' + (matches.length === 1 ? "" : "s") + ' for ' + esc2(query) + '</div>';
    matches.slice(0, 12).forEach(function (m) {
      html += '<div class="search-group">';
      html += '<a class="search-group-title" href="' + base + m.page.url + '">' + ICON_DOC + '<span>' + highlight(m.page.title, query) + '</span></a>';
      if (m.sections.length) {
        html += '<div class="search-sub">';
        m.sections.forEach(function (s) {
          html += '<a class="search-item" href="' + base + s.url + '">' +
            '<div class="si-title">' + highlight(s.title, query) + '</div>' +
            (s.snippet ? '<div class="si-snippet">' + highlight(s.snippet, query) + '</div>' : '') +
            '</a>';
        });
        html += '</div>';
      }
      html += '</div>';
    });
    searchResults.innerHTML = html;
  }

  function openSearch() {
    if (!searchOverlay) buildSearchModal();
    loadSearchIndex(function () {
      searchOverlay.classList.add("open");
      searchInput.value = "";
      runSearch("");
      setTimeout(function () { searchInput.focus(); }, 0);
    });
  }

  function closeSearch() {
    if (searchOverlay) searchOverlay.classList.remove("open");
  }

  function isSearchOpen() {
    return searchOverlay && searchOverlay.classList.contains("open");
  }

  document.addEventListener("keydown", function (e) {
    var mod = e.ctrlKey || e.metaKey;
    if (mod && (e.key === "k" || e.key === "K")) {
      e.preventDefault();
      isSearchOpen() ? closeSearch() : openSearch();
      return;
    }
    if (e.key === "Escape" && isSearchOpen()) {
      closeSearch();
      return;
    }
    if (e.key === "/" && !isSearchOpen()) {
      var tag = document.activeElement && document.activeElement.tagName;
      if (tag !== "INPUT" && tag !== "TEXTAREA") {
        e.preventDefault();
        openSearch();
      }
    }
  });

  document.addEventListener("DOMContentLoaded", function () {
    render();
    renderHeader();
    var toggle = document.getElementById("nav-toggle");
    var sidebar = document.getElementById("sidebar-mount") ? document.getElementById("sidebar-mount").closest(".sidebar") : null;
    if (toggle && sidebar) {
      toggle.addEventListener("click", function () {
        sidebar.classList.toggle("open");
      });
      sidebar.addEventListener("click", function (e) {
        if (e.target.tagName === "A") sidebar.classList.remove("open");
      });
    }
  });
})();
