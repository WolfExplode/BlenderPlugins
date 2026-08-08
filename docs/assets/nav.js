/* Shared sidebar. Each page sets `NAV_BASE` (relative path to docs/ root)
   and `NAV_CURRENT` (this page's key, or "" for none) before loading this script. */
(function () {
  var base = typeof NAV_BASE !== "undefined" ? NAV_BASE : "";
  var current = typeof NAV_CURRENT !== "undefined" ? NAV_CURRENT : "";

  var ADDONS = [
    { slug: "bone-renamer", title: "Bone Renamer", cat: "Rigging" },
    { slug: "bweight", title: "Bweight", cat: "Paint" },
    { slug: "cyclic-animation-baker", title: "Cyclic Animation Baker", cat: "Animation" },
    { slug: "geo-nodes-io", title: "Import Export Geo Nodes", cat: "Node" },
    { slug: "gizmo-plus", title: "Gizmo Plus", cat: "3D View" },
    { slug: "guard-edit-mode", title: "Guard Edit Mode", cat: "System" },
    { slug: "hdri-maker", title: "HDRi Maker", cat: "3D View" },
    { slug: "open-console-startup", title: "Open Console on Startup", cat: "System" },
    { slug: "screenshot-nodes", title: "ScreenshotNodes", cat: "Node" },
    { slug: "symmetrize-plus", title: "Symmetrize Plus", cat: "Mesh" },
    { slug: "target-please", title: "Target, Please!", cat: "Object" },
    { slug: "translate-shapekeys", title: "translateShapekeysToEnglish", cat: "Rigging" },
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

    html += '<h4>Add-ons</h4><ul>';
    ADDONS.forEach(function (a) {
      var active = current === a.slug ? "active" : "";
      html += '<li><a href="' + base + 'addons/' + a.slug + '/index.html" class="' + active + '">' +
        '<span>' + esc(a.title) + '</span><span class="cat">' + esc(a.cat) + '</span>' +
        '</a></li>';
    });
    html += '</ul>';

    var mount = document.getElementById("sidebar-mount");
    if (mount) mount.innerHTML = html;
  }

  document.addEventListener("DOMContentLoaded", function () {
    render();
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
