// Airvoyage front-end: airport swap, live refresh, sorting, status and airline filter chips.
(function () {
  "use strict";

  // Swap From/To in any search form
  document.querySelectorAll("[data-swap]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var f = btn.closest("form"), a = f.elements.source, b = f.elements.destination, t = a.value;
      a.value = b.value; b.value = t;
    });
  });

  // Concession pill radio selector interaction
  document.querySelectorAll(".cb-pill input[type='radio']").forEach(function (radio) {
    radio.addEventListener("change", function () {
      var container = radio.closest(".cb-options");
      if (container) {
        container.querySelectorAll(".cb-pill").forEach(function (pill) {
          pill.classList.remove("active");
        });
      }
      var parentPill = radio.closest(".cb-pill");
      if (parentPill) {
        parentPill.classList.add("active");
      }
    });
  });

  var root = document.getElementById("results");
  if (!root) return;

  var list = document.getElementById("flight-list");
  var errorBox = document.getElementById("api-error");
  var stamp = document.getElementById("last-updated");
  var refreshBtn = document.getElementById("refresh-btn");
  var autoBox = document.getElementById("auto-refresh");
  var chips = document.getElementById("status-chips");
  var airlineChips = document.getElementById("airline-chips");
  var sortButtons = document.querySelectorAll(".sort-btn");
  var stopButtons = document.querySelectorAll("[data-stop-filter]");
  var scopeButtons = document.querySelectorAll("[data-scope-filter]");
  var interval = Math.max(30, parseInt(root.dataset.interval, 10) || 60) * 1000;
  var timer = null, busy = false, activeStatus = "", activeAirline = "", activeStops = "all", activeScope = "all", currentSort = "price";

  stopButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      stopButtons.forEach(function (b) { b.classList.remove("active"); });
      btn.classList.add("active");
      activeStops = btn.dataset.stopFilter;
      applyFilter();
    });
  });

  scopeButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      scopeButtons.forEach(function (b) { b.classList.remove("active"); });
      btn.classList.add("active");
      activeScope = btn.dataset.scopeFilter;
      activeAirline = ""; // reset specific airline filter if scope changes
      applyFilter();
      buildAirlineChips();
    });
  });

  function buildChips() {
    if (!chips) return;
    var counts = {};
    list.querySelectorAll(".flight-card").forEach(function (c) {
      var s = c.dataset.status || "Unknown";
      counts[s] = (counts[s] || 0) + 1;
    });
    chips.innerHTML = "";
    var allBtn = document.createElement("button");
    allBtn.type = "button";
    allBtn.className = "chip" + (!activeStatus ? " on" : "");
    allBtn.textContent = "All (" + list.querySelectorAll(".flight-card").length + ")";
    allBtn.addEventListener("click", function () {
      activeStatus = "";
      applyFilter();
      buildChips();
    });
    chips.appendChild(allBtn);

    Object.keys(counts).sort().forEach(function (s) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "chip" + (s === activeStatus ? " on" : "");
      b.textContent = s + " (" + counts[s] + ")";
      b.addEventListener("click", function () {
        activeStatus = activeStatus === s ? "" : s;
        applyFilter();
        buildChips();
      });
      chips.appendChild(b);
    });

    buildAirlineChips();
    applyFilter();
    sortFlights();
  }

  function buildAirlineChips() {
    if (!airlineChips) return;
    var airlines = {};
    list.querySelectorAll(".flight-card").forEach(function (c) {
      var scopeMatch = (activeScope === "all") || (c.dataset.scope === activeScope);
      if (scopeMatch) {
        var a = c.dataset.airline || "Other";
        airlines[a] = (airlines[a] || 0) + 1;
      }
    });
    airlineChips.innerHTML = "";
    Object.keys(airlines).sort().forEach(function (a) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "chip" + (a === activeAirline ? " on" : "");
      b.textContent = a + " (" + airlines[a] + ")";
      b.addEventListener("click", function () {
        activeAirline = activeAirline === a ? "" : a;
        applyFilter();
        buildAirlineChips();
      });
      airlineChips.appendChild(b);
    });
  }

  function applyFilter() {
    list.querySelectorAll(".flight-card").forEach(function (c) {
      var statusMatch = !activeStatus || c.dataset.status === activeStatus;
      var airlineMatch = !activeAirline || c.dataset.airline === activeAirline;
      var stopsMatch = (activeStops === "all") || (c.dataset.stops === activeStops);
      var scopeMatch = (activeScope === "all") || (c.dataset.scope === activeScope);
      c.hidden = !(statusMatch && airlineMatch && stopsMatch && scopeMatch);
    });
  }

  function sortFlights() {
    var cards = Array.from(list.querySelectorAll(".flight-card"));
    cards.sort(function (a, b) {
      if (currentSort === "price") {
        return (parseInt(a.dataset.price, 10) || 0) - (parseInt(b.dataset.price, 10) || 0);
      }
      if (currentSort === "duration") {
        return (parseInt(a.dataset.duration, 10) || 0) - (parseInt(b.dataset.duration, 10) || 0);
      }
      if (currentSort === "dep") {
        return (a.dataset.dep || "").localeCompare(b.dataset.dep || "");
      }
      return 0;
    });
    cards.forEach(function (card) {
      list.appendChild(card);
    });
  }

  sortButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      sortButtons.forEach(function (b) { b.classList.remove("active"); });
      btn.classList.add("active");
      currentSort = btn.dataset.sort;
      sortFlights();
    });
  });

  function showError(msg) {
    if (errorBox) {
      errorBox.textContent = msg;
      errorBox.hidden = false;
    }
  }

  function refresh(force) {
    if (busy) return;
    busy = true;
    if (refreshBtn) {
      refreshBtn.disabled = true;
      refreshBtn.textContent = "Refreshing…";
    }
    fetch(root.dataset.api + "?" + root.dataset.query + (force ? "&force=1" : ""), {
      headers: { "X-Requested-With": "fetch" }
    })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
      .then(function (res) {
        if (!res.ok) {
          showError(res.body.error || "Unable to retrieve live flight information. Please try again in a few moments.");
          return;
        }
        if (errorBox) errorBox.hidden = true;
        list.innerHTML = res.body.html;
        if (stamp) stamp.textContent = res.body.last_updated;
        buildChips();
      })
      .catch(function () {
        showError("Unable to retrieve live flight information. Please try again in a few moments.");
      })
      .finally(function () {
        busy = false;
        if (refreshBtn) {
          refreshBtn.textContent = "↻ Refresh";
          setTimeout(function () { refreshBtn.disabled = false; }, 2000);
        }
      });
  }

  if (refreshBtn) {
    refreshBtn.addEventListener("click", function () { refresh(true); });
  }

  function schedule() {
    clearInterval(timer);
    if (autoBox && autoBox.checked) {
      timer = setInterval(function () {
        if (!document.hidden) refresh(false);
      }, interval);
    }
  }

  if (autoBox) {
    autoBox.addEventListener("change", schedule);
  }

  buildChips();
})();
