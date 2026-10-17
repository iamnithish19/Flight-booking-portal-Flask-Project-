/**
 * Airvoyage Live Flight Radar & Google Map Tracker
 * High-definition flight path, geodesic curved route, real-time aircraft tracking,
 * and Google Maps tile layer integration.
 */

(function () {
  "use strict";

  // Map Tile URL Templates (FlightAware Radar + Google Maps layers)
  var MAP_LAYERS = {
    flightaware: {
      url: "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
      name: "FlightAware Radar",
      attr: '&copy; <a href="https://carto.com/" target="_blank" rel="noopener">CARTO</a> &copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>',
      subdomains: ["a", "b", "c", "d"],
      isFlightAware: true
    },
    hybrid: {
      url: "https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
      name: "Google Hybrid",
      attr: '&copy; <a href="https://maps.google.com" target="_blank" rel="noopener">Google Maps</a>',
      subdomains: ["mt0", "mt1", "mt2", "mt3"]
    },
    streets: {
      url: "https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}",
      name: "Google Streets",
      attr: '&copy; <a href="https://maps.google.com" target="_blank" rel="noopener">Google Maps</a>',
      subdomains: ["mt0", "mt1", "mt2", "mt3"]
    },
    satellite: {
      url: "https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
      name: "Google Satellite",
      attr: '&copy; <a href="https://maps.google.com" target="_blank" rel="noopener">Google Maps</a>',
      subdomains: ["mt0", "mt1", "mt2", "mt3"]
    },
    terrain: {
      url: "https://mt1.google.com/vt/lyrs=p&x={x}&y={y}&z={z}",
      name: "Google Terrain",
      attr: '&copy; <a href="https://maps.google.com" target="_blank" rel="noopener">Google Maps</a>',
      subdomains: ["mt0", "mt1", "mt2", "mt3"]
    }
  };

  // FlightAware Style Aircraft Marker:
  // Coral Red Airplane Silhouette + Clean White Speech-Bubble Callout (e.g. THY2) with live telemetry
  function createAirplaneSvg(heading, flightNo, timeStr, spdStr, latStr) {
    flightNo = flightNo || "THY2";
    timeStr = timeStr || "14:25 UTC";
    spdStr = spdStr || "840 km/h";
    latStr = latStr || "41.270° N, 28.730° E";

    return (
      '<div class="flightaware-aircraft-wrapper" title="' + flightNo + ' · Live Radar Track">' +
        '<div class="flightaware-speech-bubble">' +
          '<div class="callout-callsign">' + flightNo + '</div>' +
          '<div class="callout-telemetry-box">' +
            '<div class="callout-telemetry-row">' +
              '<span class="callout-metric"><span class="callout-ico">⏱️</span><span class="live-hud-time">' + timeStr + '</span></span>' +
              '<span class="callout-sep">·</span>' +
              '<span class="callout-metric"><span class="callout-ico">💨</span><span class="live-hud-spd">' + spdStr + '</span></span>' +
            '</div>' +
            '<div class="callout-telemetry-coord"><span class="callout-ico">📍</span><span class="live-hud-lat">' + latStr + '</span></div>' +
          '</div>' +
          '<div class="callout-pointer-tail"></div>' +
        '</div>' +
        '<div class="flightaware-plane-icon-box airplane-svg-elem" style="transform: rotate(' + Math.round(heading) + 'deg);">' +
          '<svg class="flightaware-plane-svg" viewBox="0 0 32 32" width="32" height="32">' +
            '<path fill="#ef4444" stroke="#dc2626" stroke-width="0.6" d="M16 2l1.5 3.8v6.2l9.5 6.5v2.5l-9.5-3.2v6l3 2.5v1.8l-4.5-1.4-4.5 1.4v-1.8l3-2.5v-6l-9.5 3.2V21l9.5-6.5V5.8L16 2z"/>' +
          '</svg>' +
        '</div>' +
      '</div>'
    );
  }

  // FlightAware Style Airport Pin: Amber/Yellow Circle Badge with White Air Traffic Control Tower
  function createAirportPin(iata, type, city) {
    iata = iata || "APT";
    city = city || "";
    var isDest = (type === "dest");
    var isLayover = (type === "layover");
    var badgeBg = isLayover ? "#0284c7" : (isDest ? "#f59e0b" : "#eab308");
    var beaconColor = isDest ? "#10b981" : "#06b6d4";

    return (
      '<div class="custom-airport-tower-pin" title="' + iata + (city ? ' · ' + city : '') + '">' +
        '<div class="tower-iata-tag">' + iata + '</div>' +
        '<div class="tower-circle-badge" style="background: ' + badgeBg + ';">' +
          '<svg class="tower-svg-icon" viewBox="0 0 24 24" width="18" height="18">' +
            '<line x1="12" y1="2" x2="12" y2="4.8" stroke="#ffffff" stroke-width="1.8" stroke-linecap="round"/>' +
            '<path d="M7 5h10l1.8 4.2H5.2L7 5z" fill="#ffffff"/>' +
            '<path d="M8.2 6.4h7.6l0.9 1.6H7.3l0.9-1.6z" fill="' + badgeBg + '"/>' +
            '<path d="M9.8 9.5h4.4l-0.7 7.2h-3l-0.7-7.2z" fill="#ffffff"/>' +
            '<path d="M7.8 17h8.4l1.6 4.2H6.2l1.6-4.2z" fill="#ffffff"/>' +
          '</svg>' +
          '<div class="tower-pin-stem"></div>' +
        '</div>' +
        '<div class="tower-ground-beacon" style="background: ' + beaconColor + ';"></div>' +
      '</div>'
    );
  }

  // Main Radar Map Controller Class
  function FlightRadarController(containerId, telemetry) {
    this.containerId = containerId;
    this.data = telemetry;
    this.map = null;
    this.currentTileLayer = null;
    this.tileLayers = {};
    this.traveledLine = null;
    this.remainingLine = null;
    this.fullRouteLine = null;
    this.waypointMarkers = [];
    this.airplaneMarker = null;
    this.originMarker = null;
    this.destMarker = null;
    this.layoverMarker = null;
    this.tracerTimer = null;
    this.isTracingActive = true;
    this.init();
  }

  FlightRadarController.prototype.init = function () {
    var container = document.getElementById(this.containerId);
    if (!container || !window.L) return;

    // Clean up existing map instance and timer if already initialized
    if (window._flightRadarInstances && window._flightRadarInstances[this.containerId]) {
      var oldInst = window._flightRadarInstances[this.containerId];
      if (oldInst._traceTimer) clearInterval(oldInst._traceTimer);
      if (oldInst.tracerTimer) clearInterval(oldInst.tracerTimer);
    }
    if (container._flight_map_instance) {
      try { container._flight_map_instance.remove(); } catch (e) {}
      container._flight_map_instance = null;
    }
    container._leaflet_id = null;

    if (!this.data || !this.data.origin || !this.data.destination) return;

    var origin = this.data.origin;
    var dest = this.data.destination;

    // Center between origin and dest initially
    var midLat = ((origin.lat || 0) + (dest.lat || 0)) / 2;
    var midLon = ((origin.lon || 0) + (dest.lon || 0)) / 2;

    this.map = L.map(this.containerId, {
      center: [midLat, midLon],
      zoom: 5,
      zoomControl: true,
      attributionControl: true
    });
    container._flight_map_instance = this.map;

    // Setup map tile layers
    var self = this;
    for (var key in MAP_LAYERS) {
      if (MAP_LAYERS.hasOwnProperty(key)) {
        var layerDef = MAP_LAYERS[key];
        self.tileLayers[key] = L.tileLayer(layerDef.url, {
          maxZoom: 19,
          attribution: layerDef.attr,
          subdomains: layerDef.subdomains || ["a", "b", "c", "d"]
        });
      }
    }

    // Default to Google Maps Satellite Hybrid
    this.setLayer("hybrid");

    // Draw route lines & purple waypoints
    this.drawRoute();

    // Place yellow airport control tower pins
    this.placeAirportMarkers();

    // Place live red airplane & white callout bubble
    this.placeAirplaneMarker();

    // Auto-fit route
    this.fitRoute();

    // Wire up scrubber if present
    this.bindScrubber();

    // Start airplane movement on purple trace line with time, speed, latitude & longitude
    this.startTraceMovement();
  };

  FlightRadarController.prototype.setLayer = function (layerKey) {
    if (!this.tileLayers[layerKey] || !this.map) return;
    if (this.currentTileLayer) {
      this.map.removeLayer(this.currentTileLayer);
    }
    this.currentTileLayer = this.tileLayers[layerKey];
    this.currentTileLayer.addTo(this.map);

    var container = document.getElementById(this.containerId);
    if (container) {
      if (layerKey === "flightaware") {
        container.classList.add("flightaware-radar-tiles");
      } else {
        container.classList.remove("flightaware-radar-tiles");
      }
    }
  };

  FlightRadarController.prototype.drawRoute = function () {
    if (!this.map || !this.data) return;

    // Ambient glowing violet halo
    if (this.data.full_route && this.data.full_route.length) {
      L.polyline(this.data.full_route, {
        color: "rgba(139, 92, 246, 0.25)",
        weight: 8,
        lineCap: "round",
        lineJoin: "round"
      }).addTo(this.map);

      // Base violet/purple great-circle arc (#7c3aed)
      this.fullRouteLine = L.polyline(this.data.full_route, {
        color: "#7c3aed",
        weight: 3.5,
        opacity: 0.85,
        lineCap: "round",
        lineJoin: "round"
      }).addTo(this.map);
    }

    // Traveled path (vibrant solid purple #8b5cf6)
    if (this.data.traveled_path && this.data.traveled_path.length > 1) {
      this.traveledLine = L.polyline(this.data.traveled_path, {
        color: "#8b5cf6",
        weight: 4,
        opacity: 1.0,
        lineCap: "round"
      }).addTo(this.map);
    }

    // Remaining path (dashed purple trail)
    if (this.data.remaining_path && this.data.remaining_path.length > 1) {
      this.remainingLine = L.polyline(this.data.remaining_path, {
        color: "#a78bfa",
        weight: 3,
        dashArray: "5, 7",
        opacity: 0.75,
        className: "radar-streaming-dash"
      }).addTo(this.map);
    }

    // Waypoint dots along the curve matching FlightAware template
    if (this.data.full_route && this.data.full_route.length > 4) {
      this.waypointMarkers = [];
      var pts = this.data.full_route;
      var step = Math.max(2, Math.floor(pts.length / 14));
      for (var i = step; i < pts.length - step; i += step) {
        var wp = L.circleMarker(pts[i], {
          radius: 3.2,
          fillColor: "#a855f7",
          fillOpacity: 0.95,
          color: "#6d28d9",
          weight: 1
        }).addTo(this.map);
        this.waypointMarkers.push(wp);
      }
    }
  };

  FlightRadarController.prototype.placeAirportMarkers = function () {
    var self = this;
    var orig = this.data.origin;
    var dest = this.data.destination;

    // Origin Marker (Yellow Tower Pin)
    var origIcon = L.divIcon({
      className: "origin-icon-wrapper",
      html: createAirportPin(orig.iata, "origin", orig.city),
      iconSize: [44, 48],
      iconAnchor: [22, 46]
    });
    var origStatus = (this.data.progress_percent > 0) ? "Departed" : (this.data.phase || "At Gate");
    this.originMarker = L.marker([orig.lat, orig.lon], { icon: origIcon, zIndexOffset: 800 }).addTo(this.map);
    this.originMarker.bindPopup(
      '<div class="map-popup-header">🛫 ' + orig.city + ' (' + orig.iata + ')</div>' +
      '<div class="map-popup-sub">' + (orig.name || "") + '</div>' +
      '<div class="map-popup-grid">' +
        '<span>Terminal:</span><strong>T' + (orig.terminal || "1") + (orig.gate && orig.gate !== "—" ? ' · Gate ' + orig.gate : '') + '</strong>' +
        '<span>Scheduled:</span><strong>' + (orig.scheduled || "—") + '</strong>' +
        '<span>Status:</span><strong style="color: #34d399;">' + origStatus + '</strong>' +
      '</div>'
    );

    // Destination Marker (Yellow Tower Pin)
    var destIcon = L.divIcon({
      className: "dest-icon-wrapper",
      html: createAirportPin(dest.iata, "dest", dest.city),
      iconSize: [44, 48],
      iconAnchor: [22, 46]
    });
    this.destMarker = L.marker([dest.lat, dest.lon], { icon: destIcon, zIndexOffset: 800 }).addTo(this.map);
    this.destMarker.bindPopup(
      '<div class="map-popup-header">🛬 ' + dest.city + ' (' + dest.iata + ')</div>' +
      '<div class="map-popup-sub">' + (dest.name || "") + '</div>' +
      '<div class="map-popup-grid">' +
        '<span>Terminal:</span><strong>T' + (dest.terminal || "2") + (dest.gate && dest.gate !== "—" ? ' · Gate ' + dest.gate : '') + '</strong>' +
        '<span>Scheduled:</span><strong>' + (dest.scheduled || "—") + '</strong>' +
        '<span>Distance:</span><strong>' + self.data.total_distance_km + ' km</strong>' +
      '</div>'
    );

    // Connecting Layover Marker
    if (this.data.is_connecting && this.data.layover) {
      var lay = this.data.layover;
      var layIcon = L.divIcon({
        className: "layover-icon-wrapper",
        html: createAirportPin(lay.iata, "layover", lay.city),
        iconSize: [44, 48],
        iconAnchor: [22, 46]
      });
      this.layoverMarker = L.marker([lay.lat, lay.lon], { icon: layIcon, zIndexOffset: 800 }).addTo(this.map);
      this.layoverMarker.bindPopup(
        '<div class="map-popup-header">🔄 Transit Layover: ' + lay.city + ' (' + lay.iata + ')</div>' +
        '<div class="map-popup-sub">' + (lay.name || "") + '</div>'
      );
    }
  };

  FlightRadarController.prototype.computeSimulatedTime = function (fraction) {
    var orig = this.data.origin || {};
    var dest = this.data.destination || {};
    var depStr = orig.actual || orig.scheduled;
    var arrStr = dest.actual || dest.scheduled;

    function parseToMinutes(s) {
      if (!s) return null;
      if (s.indexOf("T") !== -1) {
        var tPart = s.split("T")[1];
        var p = tPart.split(":");
        return parseInt(p[0], 10) * 60 + parseInt(p[1], 10);
      }
      if (s.indexOf(":") !== -1) {
        var p2 = s.split(":");
        return parseInt(p2[0], 10) * 60 + parseInt(p2[1], 10);
      }
      return null;
    }

    var depMin = parseToMinutes(depStr);
    var arrMin = parseToMinutes(arrStr);
    if (depMin === null) depMin = 8 * 60 + 15;
    if (arrMin === null) arrMin = depMin + 140;
    if (arrMin < depMin) arrMin += 24 * 60;

    var curMin = Math.round(depMin + fraction * (arrMin - depMin)) % (24 * 60);
    var h = Math.floor(curMin / 60);
    var m = curMin % 60;
    var h12 = h % 12 || 12;
    var ampm = h >= 12 ? "PM" : "AM";
    return (h12 < 10 ? "0" : "") + h12 + ":" + (m < 10 ? "0" : "") + m + " " + ampm;
  };

  FlightRadarController.prototype.computeSimulatedSpeed = function (fraction) {
    if (fraction <= 0 || fraction >= 1) return 0;
    if (fraction < 0.15) {
      return Math.round(350 + 490 * (fraction / 0.15));
    }
    if (fraction > 0.85) {
      return Math.round(300 + 540 * ((1 - fraction) / 0.15));
    }
    return Math.round(840 + Math.sin(fraction * 32) * 16);
  };

  FlightRadarController.prototype.placeAirplaneMarker = function () {
    var plane = this.data.current_location;
    var heading = plane.heading || 0;
    var flightNo = this.data.flight_number || "AV101";
    var latDir = plane.lat >= 0 ? "N" : "S";
    var lonDir = plane.lon >= 0 ? "E" : "W";
    var latStr = Math.abs(plane.lat).toFixed(3) + "° " + latDir + ", " + Math.abs(plane.lon).toFixed(3) + "° " + lonDir;
    var spdStr = (this.data.speed_kmh || 840) + " km/h";
    var timeStr = this.computeSimulatedTime((this.data.progress_percent || 0) / 100.0);

    var planeIcon = L.divIcon({
      className: "airplane-marker-wrapper",
      html: createAirplaneSvg(heading, flightNo, timeStr, spdStr, latStr),
      iconSize: [44, 44],
      iconAnchor: [22, 22]
    });

    this.airplaneMarker = L.marker([plane.lat, plane.lon], { icon: planeIcon, zIndexOffset: 1000 }).addTo(this.map);
    this.airplaneMarker.bindPopup(
      '<div class="map-popup-header">✈️ ' + this.data.airline_name + ' ' + this.data.flight_number + '</div>' +
      '<div class="map-popup-sub">' + this.data.aircraft + ' · <span style="color: #38bdf8;">' + this.data.phase + '</span></div>' +
      '<div class="map-popup-grid">' +
        '<span>Altitude:</span><strong>' + (this.data.altitude_ft ? this.data.altitude_ft.toLocaleString() + ' ft' : 'On Ground') + '</strong>' +
        '<span>Speed:</span><strong>' + this.data.speed_kmh + ' km/h (' + this.data.speed_knots + ' kts)</strong>' +
        '<span>Heading:</span><strong>' + Math.round(this.data.heading_degrees) + '°</strong>' +
        '<span>Coordinates:</span><strong>' + plane.lat.toFixed(4) + ', ' + plane.lon.toFixed(4) + '</strong>' +
        '<span>Progress:</span><strong>' + this.data.progress_percent + '% (' + this.data.traveled_km + ' / ' + this.data.total_distance_km + ' km)</strong>' +
      '</div>'
    );
  };

  FlightRadarController.prototype.recenterAirplane = function () {
    if (!this.map || !this.data || !this.data.current_location) return;
    var p = this.data.current_location;
    this.map.flyTo([p.lat, p.lon], Math.max(this.map.getZoom(), 7), { duration: 1.2 });
  };

  FlightRadarController.prototype.fitRoute = function () {
    if (!this.map || !this.data) return;
    var bounds = L.latLngBounds([
      [this.data.origin.lat, this.data.origin.lon],
      [this.data.destination.lat, this.data.destination.lon]
    ]);
    if (this.data.current_location) {
      bounds.extend([this.data.current_location.lat, this.data.current_location.lon]);
    }
    this.map.fitBounds(bounds, { padding: [50, 50] });
  };

  FlightRadarController.prototype.startTraceMovement = function () {
    var self = this;
    if (this._traceTimer) clearInterval(this._traceTimer);
    this.isTracingActive = true;
    this.flightProgress = (typeof this.data.progress_percent === "number" && this.data.progress_percent > 0 && this.data.progress_percent < 100) ? (this.data.progress_percent / 100.0) : 0.0;

    this._traceTimer = setInterval(function () {
      if (!self.isTracingActive || !self.data || !self.data.full_route) return;

      self.flightProgress += 0.0035;
      if (self.flightProgress > 1.0) {
        self.flightProgress = 0.0;
      }

      self.simulateProgress(self.flightProgress);
    }, 45);
  };

  FlightRadarController.prototype.bindScrubber = function () {
    var scrubber = document.getElementById(this.containerId + "-scrubber");
    if (!scrubber) return;
    var self = this;
    scrubber.value = (this.data.progress_percent || 0);

    scrubber.addEventListener("mousedown", function () { scrubber._userDragging = true; });
    scrubber.addEventListener("touchstart", function () { scrubber._userDragging = true; });

    scrubber.addEventListener("input", function (e) {
      var pct = parseFloat(e.target.value);
      self.flightProgress = pct / 100.0;
      self.simulateProgress(self.flightProgress);
    });

    scrubber.addEventListener("change", function () { scrubber._userDragging = false; });
    scrubber.addEventListener("mouseup", function () { scrubber._userDragging = false; });
    scrubber.addEventListener("touchend", function () { scrubber._userDragging = false; });
  };

  FlightRadarController.prototype.simulateProgress = function (fraction) {
    if (!this.data || !this.data.full_route) return;
    fraction = Math.max(0, Math.min(1, fraction));
    var route = this.data.full_route;
    var idxFloat = fraction * (route.length - 1);
    var idx = Math.floor(idxFloat);
    var nextIdx = Math.min(route.length - 1, idx + 1);
    var subF = idxFloat - idx;

    var curLat = route[idx][0] + (route[nextIdx][0] - route[idx][0]) * subF;
    var curLon = route[idx][1] + (route[nextIdx][1] - route[idx][1]) * subF;

    // Approximate heading along geodesic trace curve
    var dLon = (route[nextIdx][1] - route[idx][1]);
    var dLat = (route[nextIdx][0] - route[idx][0]);
    var heading = (Math.atan2(dLon, dLat) * 180 / Math.PI + 360) % 360;

    var curTime = this.computeSimulatedTime(fraction);
    var curSpd = this.computeSimulatedSpeed(fraction);
    var latDir = curLat >= 0 ? "N" : "S";
    var lonDir = curLon >= 0 ? "E" : "W";
    var coordStr = Math.abs(curLat).toFixed(3) + "° " + latDir + ", " + Math.abs(curLon).toFixed(3) + "° " + lonDir;

    // Update controller's current plane coordinates
    this.data.current_location = { lat: curLat, lon: curLon, heading: heading };

    // Update direct Google Maps link to current live aircraft position
    var gmapModalLink = document.getElementById("modal-radar-gmap-link");
    if (gmapModalLink && this.containerId === "modal-radar-map-elem") {
      gmapModalLink.href = "https://www.google.com/maps/search/?api=1&query=" + curLat.toFixed(5) + "," + curLon.toFixed(5);
    }
    var gmapDetailLink = document.querySelector("#detail-flight-radar-section .radar-btn-gmap");
    if (gmapDetailLink && this.containerId === "detail-radar-map-elem") {
      gmapDetailLink.href = "https://www.google.com/maps/search/?api=1&query=" + curLat.toFixed(5) + "," + curLon.toFixed(5);
    }

    // Move airplane symbol on the trace line & update live HUD badge
    if (this.airplaneMarker) {
      this.airplaneMarker.setLatLng([curLat, curLon]);
      var iconWrap = this.airplaneMarker.getElement();
      if (iconWrap) {
        var svg = iconWrap.querySelector(".airplane-svg-elem");
        if (svg) svg.style.transform = "rotate(" + Math.round(heading) + "deg)";

        var timeEl = iconWrap.querySelector(".live-hud-time");
        var spdEl = iconWrap.querySelector(".live-hud-spd");
        var latEl = iconWrap.querySelector(".live-hud-lat");
        if (timeEl) timeEl.textContent = curTime;
        if (spdEl) spdEl.textContent = curSpd + " km/h";
        if (latEl) latEl.textContent = coordStr;
      }
    }

    // Update lines along the trace
    if (this.traveledLine && this.remainingLine) {
      var trav = route.slice(0, idx + 1);
      trav.push([curLat, curLon]);
      var rem = [[curLat, curLon]].concat(route.slice(nextIdx));
      this.traveledLine.setLatLngs(trav);
      this.remainingLine.setLatLngs(rem);
    }

    // Sync scrubber input if user is not actively dragging
    var scrubber = document.getElementById(this.containerId + "-scrubber");
    if (scrubber && !scrubber._userDragging) {
      scrubber.value = (fraction * 100).toFixed(1);
    }

    // Update Telemetry HUD if present
    var pctVal = (fraction * 100).toFixed(1);
    var alt = fraction <= 0 || fraction >= 1 ? 0 : (fraction < 0.15 ? Math.round(36000 * (fraction / 0.15)) : (fraction > 0.85 ? Math.round(36000 * ((1 - fraction) / 0.15)) : 35500));
    var phase = fraction <= 0 ? "At Gate / Boarding" : (fraction >= 1 ? "Landed & Arrived" : (fraction < 0.15 ? "Takeoff Climb" : (fraction > 0.85 ? "Descent" : "Cruising at 36,000 ft")));

    var altEl = document.getElementById(this.containerId + "-alt");
    var spdEl = document.getElementById(this.containerId + "-spd");
    var progEl = document.getElementById(this.containerId + "-prog");
    var coordEl = document.getElementById(this.containerId + "-coord");
    var phaseEl = document.getElementById(this.containerId + "-phase");
    var hudTimeEl = document.getElementById(this.containerId + "-time");

    if (progEl) progEl.textContent = pctVal + "%";
    if (coordEl) coordEl.textContent = coordStr;
    if (altEl) altEl.textContent = alt ? alt.toLocaleString() + " ft" : "0 ft (Ground)";
    if (spdEl) spdEl.textContent = curSpd + " km/h";
    if (phaseEl) phaseEl.textContent = phase;
    if (hudTimeEl) hudTimeEl.textContent = curTime;
  };

  function calcHeading(lat1, lon1, lat2, lon2) {
    var phi1 = lat1 * Math.PI / 180;
    var phi2 = lat2 * Math.PI / 180;
    var deltaLam = (lon2 - lon1) * Math.PI / 180;
    var y = Math.sin(deltaLam) * Math.cos(phi2);
    var x = Math.cos(phi1) * Math.sin(phi2) - Math.sin(phi1) * Math.cos(phi2) * Math.cos(deltaLam);
    return (Math.atan2(y, x) * 180 / Math.PI + 360) % 360;
  }

  FlightRadarController.prototype.initMiniFlightTracer = function () {
    if (!this.map || !this.data || !this.data.full_route || this.data.full_route.length < 2) return;

    var route = this.data.full_route;
    var startPt = route[0];
    var nextPt = route[1];
    var heading = calcHeading(startPt[0], startPt[1], nextPt[0], nextPt[1]);

    var tracerIcon = L.divIcon({
      className: "mini-tracer-wrapper",
      html: (
        '<div class="mini-flight-map-tracer" title="Mini Flight Tracing Route">' +
          '<div class="mini-tracer-glow-ring"></div>' +
          '<svg class="mini-tracer-airplane-svg" viewBox="0 0 24 24" style="transform: rotate(' + heading + 'deg);">' +
            '<path fill="#fbbf24" stroke="#ffffff" stroke-width="0.8" d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z"/>' +
          '</svg>' +
          '<div class="mini-tracer-label">✈ MINI FLIGHT</div>' +
        '</div>'
      ),
      iconSize: [36, 36],
      iconAnchor: [18, 18]
    });

    this.miniTracerMarker = L.marker([startPt[0], startPt[1]], {
      icon: tracerIcon,
      zIndexOffset: 1500
    }).addTo(this.map);

    // Glowing contrail polyline that follows the mini tracer along the path
    this.tracerTrailLine = L.polyline([startPt], {
      color: "#fbbf24",
      weight: 3.5,
      opacity: 0.85,
      lineCap: "round"
    }).addTo(this.map);

    this.startTracerLoop();
  };

  FlightRadarController.prototype.startTracerLoop = function () {
    var self = this;
    if (this.tracerTimer) clearInterval(this.tracerTimer);

    var route = this.data.full_route;
    var totalPoints = route.length;
    var trailMaxLen = Math.max(5, Math.floor(totalPoints * 0.28));

    this.tracerTimer = setInterval(function () {
      if (!self.isTracingActive || !self.miniTracerMarker || !self.map) return;

      self.tracerProgress += 0.005;
      if (self.tracerProgress > 1.0) {
        self.tracerProgress = 0.0;
      }

      var fraction = self.tracerProgress;
      var idxFloat = fraction * (totalPoints - 1);
      var idx = Math.floor(idxFloat);
      var nextIdx = Math.min(totalPoints - 1, idx + 1);
      var subF = idxFloat - idx;

      var curLat = route[idx][0] + (route[nextIdx][0] - route[idx][0]) * subF;
      var curLon = route[idx][1] + (route[nextIdx][1] - route[idx][1]) * subF;

      var heading = calcHeading(route[idx][0], route[idx][1], route[nextIdx][0], route[nextIdx][1]);

      // Move mini flight on the map path
      self.miniTracerMarker.setLatLng([curLat, curLon]);
      var el = self.miniTracerMarker.getElement();
      if (el) {
        var svg = el.querySelector(".mini-tracer-airplane-svg");
        if (svg) svg.style.transform = "rotate(" + heading + "deg)";
      }

      // Update glowing trail behind the mini flight
      if (self.tracerTrailLine) {
        var startTrailIdx = Math.max(0, idx - trailMaxLen);
        var trailCoords = route.slice(startTrailIdx, idx + 1);
        trailCoords.push([curLat, curLon]);
        self.tracerTrailLine.setLatLngs(trailCoords);
      }
    }, 35);
  };

  FlightRadarController.prototype.toggleRouteTracer = function (btnElem) {
    this.isTracingActive = !this.isTracingActive;
    if (btnElem) {
      if (this.isTracingActive) {
        btnElem.textContent = "⏸ Pause Trace";
        btnElem.classList.add("active");
      } else {
        btnElem.textContent = "✈️ Trace Route";
        btnElem.classList.remove("active");
      }
    }
  };

  // Global Registry for Active Controllers
  window._flightRadarInstances = window._flightRadarInstances || {};

  window.initFlightRadar = function (containerId, telemetry) {
    var controller = new FlightRadarController(containerId, telemetry);
    window._flightRadarInstances[containerId] = controller;
    return controller;
  };

  window.toggleRadarRouteTracer = function (containerId, btnElem) {
    var inst = window._flightRadarInstances[containerId];
    if (inst) inst.toggleRouteTracer(btnElem);
  };

  window.switchRadarLayer = function (containerId, layerKey, btnElem) {
    var inst = window._flightRadarInstances[containerId];
    if (inst) {
      inst.setLayer(layerKey);
      if (btnElem && btnElem.parentElement) {
        var btns = btnElem.parentElement.querySelectorAll(".layer-opt-btn");
        for (var i = 0; i < btns.length; i++) btns[i].classList.remove("active");
        btnElem.classList.add("active");
      }
    }
  };

  window.recenterRadarAircraft = function (containerId) {
    var inst = window._flightRadarInstances[containerId];
    if (inst) inst.recenterAirplane();
  };

  window.fitRadarRoute = function (containerId) {
    var inst = window._flightRadarInstances[containerId];
    if (inst) inst.fitRoute();
  };

  // =========================================================================
  // Modal Handler for Search Results, Bookings, Confirmation
  // =========================================================================
  window.openLiveFlightMapModal = function (flightNumber, depIata, arrIata, depDate, travelClass, fareType) {
    var backdrop = document.getElementById("flight-map-modal-backdrop");
    if (!backdrop) return;

    var titleEl = document.getElementById("modal-radar-flight-title");
    if (titleEl) {
      titleEl.textContent = (flightNumber || "") + " · " + (depIata || "") + " → " + (arrIata || "");
    }

    backdrop.classList.add("open");

    // Fetch live telemetry from API
    var url = "/api/flight/tracking?number=" + encodeURIComponent(flightNumber || "") +
              "&source=" + encodeURIComponent(depIata || "") +
              "&dest=" + encodeURIComponent(arrIata || "") +
              "&date=" + encodeURIComponent(depDate || "") +
              "&travel_class=" + encodeURIComponent(travelClass || "economy") +
              "&fare_type=" + encodeURIComponent(fareType || "regular");

    fetch(url)
      .then(function (res) { return res.json(); })
      .then(function (telemetry) {
        // Update direct Google Maps link button
        var gmapBtn = document.getElementById("modal-radar-gmap-link");
        if (gmapBtn && telemetry.google_maps_directions_url) {
          gmapBtn.href = telemetry.google_maps_directions_url;
        }

        // Initialize modal map instance
        var inst = window.initFlightRadar("modal-radar-map-elem", telemetry);
        setTimeout(function () {
          if (inst && inst.map) {
            inst.map.invalidateSize();
            inst.fitRoute();
          }
        }, 200);
      })
      .catch(function (err) {
        console.error("Failed to fetch live flight tracking telemetry:", err);
      });
  };

  window.closeLiveFlightMapModal = function () {
    var backdrop = document.getElementById("flight-map-modal-backdrop");
    if (backdrop) backdrop.classList.remove("open");
    var inst = window._flightRadarInstances["modal-radar-map-elem"];
    if (inst) {
      if (inst._traceTimer) clearInterval(inst._traceTimer);
      if (inst.tracerTimer) clearInterval(inst.tracerTimer);
    }
  };

  // Escape key to close modal
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      window.closeLiveFlightMapModal();
    }
  });

})();
