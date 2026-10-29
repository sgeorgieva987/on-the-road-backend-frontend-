const API = '';
const tokenKey = 'otr_bulgaria_token';
let accessToken = sessionStorage.getItem(tokenKey) || '';
let currentUser = null;
let currentAccountMode = 'login';
let destinations = [];
let visibleCount = 8;
let selectedRoutePlaces = new Map();
let currentLatitude = null;
let currentLongitude = null;
let lastPlannerPayload = null;

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
}

function showToast(message) {
  const toast = $('#toast');
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add('show');
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove('show'), 3600);
}

function setStatus(id, message, isError = false) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = message || '';
  el.style.color = isError ? '#b33939' : '';
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`);
  const isForm = options.body instanceof FormData;
  if (options.body && !isForm && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  let response;
  try {
    response = await fetch(`${API}${path}`, { ...options, headers });
  } catch (error) {
    throw new Error(`API сървърът не е достъпен. Стартирай приложението на http://127.0.0.1:8000 и опитай отново. (${error.message})`);
  }
  if (response.status === 204) return null;
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = typeof data.detail === 'string' ? data.detail : `Request failed (${response.status})`;
    throw new Error(message);
  }
  return data;
}

// -------- GeoJSON loading + projection --------

function getAllRings(data) {
  if (data && data.type === 'FeatureCollection') {
    const rings = [];
    for (const feature of data.features || []) {
      if (!feature.geometry) continue;
      if (feature.geometry.type === 'Polygon') {
        rings.push(...feature.geometry.coordinates);
      } else if (feature.geometry.type === 'MultiPolygon') {
        for (const polygon of feature.geometry.coordinates) {
          rings.push(...polygon);
        }
      }
    }
    if (rings.length === 0) throw new Error('No polygon boundaries found in the GeoJSON file.');
    return rings;
  }
  if (data && data.type === 'Feature' && data.geometry) {
    if (data.geometry.type === 'Polygon') return data.geometry.coordinates;
    if (data.geometry.type === 'MultiPolygon') return data.geometry.coordinates.flat();
  }
  throw new Error(`Unsupported GeoJSON type: ${data && data.type}`);
}

let rings = [];
let project = () => ({ x: 0, y: 0 });
let createCountryPath = () => '';
const SVG_WIDTH = 1000;
const SVG_HEIGHT = 650;

async function initMapGeometry() {
  const res = await fetch('/static/bulgaria.geojson');
  if (!res.ok) throw new Error(`GeoJSON load failed: ${res.status}`);
  const municipalitiesGeoJSON = await res.json();

  rings = getAllRings(municipalitiesGeoJSON);
  const allCoordinates = rings.flat();
  const longitudes = allCoordinates.map(([lon]) => lon);
  const latitudes = allCoordinates.map(([, lat]) => lat);

  const bounds = {
    minLon: Math.min(...longitudes),
    maxLon: Math.max(...longitudes),
    minLat: Math.min(...latitudes),
    maxLat: Math.max(...latitudes),
  };

  const MAP_PADDING = 45;
  const longitudeSpan = bounds.maxLon - bounds.minLon;
  const latitudeSpan = bounds.maxLat - bounds.minLat;
  const longitudeCorrection = Math.cos(((bounds.minLat + bounds.maxLat) / 2) * Math.PI / 180);

  const projectedWidth = longitudeSpan * longitudeCorrection;
  const projectedHeight = latitudeSpan;

  const scale = Math.min(
    (SVG_WIDTH - MAP_PADDING * 2) / projectedWidth,
    (SVG_HEIGHT - MAP_PADDING * 2) / projectedHeight
  );

  const drawnWidth = projectedWidth * scale;
  const drawnHeight = projectedHeight * scale;
  const offsetX = (SVG_WIDTH - drawnWidth) / 2;
  const offsetY = (SVG_HEIGHT - drawnHeight) / 2;

  project = (longitude, latitude) => ({
    x: offsetX + (longitude - bounds.minLon) * longitudeCorrection * scale,
    y: SVG_HEIGHT - offsetY - (latitude - bounds.minLat) * scale,
  });

  createCountryPath = () =>
    rings.map(ring =>
      ring.map(([lon, lat], i) => {
        const p = project(lon, lat);
        return `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(2)} ${p.y.toFixed(2)}`;
      }).join(' ') + ' Z'
    ).join(' ');
}

// -------- Rendering --------

function labelForCategory(destination) {
  const categories = destination.categories || [];
  const tags = destination.tags || [];
  if (categories.some(x => /природа|nature|hiking|геология/i.test(x))) return 'Природа';
  if (categories.some(x => /музей|археология|museum|archaeology/i.test(x))) return 'Археология';
  if (categories.some(x => /традиции|занаяти|crafts|food|wine|вино/i.test(x))) return 'Местни истории';
  if (tags.some(x => /по-малко познато/i.test(x))) return 'Скрита находка';
  return 'Култура и история';
}

function renderDestinationCard(d, index) {
  const category = labelForCategory(d);
  const tags = (d.tags || []).slice(0, 2).map(tag => `<span class="mini-tag">${escapeHtml(tag)}</span>`).join('');
  const review = d.verification_status === 'verified' ? '' : '<span class="status-tag">Чака проверка</span>';
  const isSelected = selectedRoutePlaces.has(Number(d.id));
  return `
    <article class="destination-card">
      <div class="destination-index">${String(index + 1).padStart(2, '0')}</div>
      <div class="destination-content">
        <h4>${escapeHtml(d.name)}</h4>
        <p>${escapeHtml(d.description || 'Няма добавено описание.')}</p>
        <div class="tag-row"><span class="mini-tag">${escapeHtml(category)}</span>${tags}${review}</div>
        <div class="card-actions">
          <button class="card-action" data-detail="${d.id}" type="button">Детайли ↗</button>
          <button class="card-action" data-route-add="${d.id}" type="button">${isSelected ? '✓ В маршрута' : '+ Добави към маршрута'}</button>
          <button class="card-action" data-save="${d.id}" type="button">${accessToken ? '♡ Запази' : '♡ Запази след вход'}</button>
        </div>
      </div>
    </article>
  `;
}

function updateMap(list) {
  const mapElement = $('#destinationMap');
  if (!mapElement) return;

  if (!rings.length) {
    mapElement.innerHTML = '<div class="map-error"><strong>Картата се зарежда…</strong></div>';
    return;
  }

  const markers = list
    .map((d) => {
      if (!Number.isFinite(Number(d.latitude)) || !Number.isFinite(Number(d.longitude))) return '';
      const point = project(Number(d.longitude), Number(d.latitude));
      const left = (point.x / SVG_WIDTH) * 100;
      const top = (point.y / SVG_HEIGHT) * 100;

      return `
        <button
          class="map-marker"
          style="left: ${left}%; top: ${top}%"
          data-place-id="${d.id}"
          aria-label="${escapeHtml(d.name)}"
          title="${escapeHtml(d.name)}"
          type="button"
        >
          <span>${d.type === 'restaurant' ? '🍴' : '🌿'}</span>
        </button>
      `;
    })
    .join('');

  mapElement.innerHTML = `
    <div class="bulgaria-map" style="position: relative; width: 100%; height: 100%; min-height: 400px;">
      <svg
        class="map-svg-bg"
        viewBox="0 0 ${SVG_WIDTH} ${SVG_HEIGHT}"
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label="Географска карта на България"
        style="width: 100%; height: 100%; display: block;"
      >
        <defs>
          <linearGradient id="mapLandGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#108a78" />
            <stop offset="100%" stop-color="#0e4c6f" />
          </linearGradient>
          <linearGradient id="mapFillGrad" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stop-color="#e6f4f0" />
            <stop offset="100%" stop-color="#cbe6dc" />
          </linearGradient>
        </defs>
        <path
          d="${createCountryPath()}"
          fill="url(#mapFillGrad)"
          stroke="url(#mapLandGrad)"
          stroke-width="1.2"
          stroke-linejoin="round"
          fill-rule="evenodd"
        />
      </svg>
      ${markers}
    </div>
  `;

  mapElement.querySelectorAll('.map-marker').forEach((marker) => {
    marker.addEventListener('click', () => {
      const placeId = marker.dataset.placeId;
      const found = destinations.find(item => String(item.id) === String(placeId));
      if (found) openDetail(found.id);
    });
  });
}

function renderSelectedRouteSummary() {
  const target = $('#selectedRouteSummary');
  if (!target) return;
  const placesArr = [...selectedRoutePlaces.values()];
  if (!placesArr.length) {
    target.innerHTML = '<span class="muted">Все още няма избрани места.</span>';
    return;
  }
  target.innerHTML = placesArr.map((place, index) => `
    <span class="selected-route-chip">
      <b>${index + 1}.</b> ${escapeHtml(place.name)}
      <button type="button" data-route-remove="${place.id}" aria-label="Премахни ${escapeHtml(place.name)}">×</button>
    </span>
  `).join('');
}

function toggleRouteDestination(destinationId) {
  const id = Number(destinationId);
  if (selectedRoutePlaces.has(id)) {
    selectedRoutePlaces.delete(id);
  } else {
    if (selectedRoutePlaces.size >= 9) { showToast('Можеш да добавиш до 9 места към един маршрут.'); return; }
    const place = destinations.find(item => Number(item.id) === id);
    if (!place) return;
    selectedRoutePlaces.set(id, place);
  }
  renderSelectedRouteSummary();
  renderList(destinations);
}

function renderList(list = destinations, count = visibleCount) {
  const slice = list.slice(0, count);
  const listContainer = $('#destinationList');
  if (listContainer) {
    listContainer.innerHTML = slice.length
      ? slice.map((d, i) => renderDestinationCard(d, i)).join('')
      : '<div class="archive-placeholder"><span>⌕</span><p>Няма намерени дестинации. Промени думата за търсене или премахни част от филтрите.</p></div>';
  }
  const countContainer = $('#resultsCount');
  if (countContainer) {
    countContainer.textContent = `Показани ${slice.length} от ${list.length} резултата`;
  }
  const loadMoreBtn = $('#loadMore');
  if (loadMoreBtn) {
    loadMoreBtn.classList.toggle('hidden', slice.length >= list.length || list.length === 0);
  }
  updateMap(list);
}

async function loadDestinations(reset = true) {
  if (reset) visibleCount = 8;
  const searchInput = $('#destinationSearch');
  const categoryFilter = $('#categoryFilter');
  const q = searchInput ? searchInput.value.trim() : '';
  const category = categoryFilter ? categoryFilter.value : '';

  const params = new URLSearchParams({ limit: '250' });
  if (q) params.set('q', q);
  if (category) params.set('category', category);

  setStatus('locationStatus', '');
  const listContainer = $('#destinationList');
  if (listContainer) {
    listContainer.innerHTML = '<div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div>';
  }

  try {
    destinations = await api(`/api/destinations?${params.toString()}`);
    renderList(destinations);
    if (!destinations.length) setStatus('locationStatus', 'Не открихме съвпадения за тези филтри.');
  } catch (error) {
    if (listContainer) {
      listContainer.innerHTML = '<div class="archive-placeholder"><p>Не успяхме да заредим дестинациите. Провери дали API сървърът работи.</p></div>';
    }
    setStatus('locationStatus', error.message, true);
  }
}

// -------- Detail dialog --------

function openDetail(destinationId) {
  const d = destinations.find(item => item.id === Number(destinationId));
  if (!d) return;
  let dialog = $('#destinationDialog');
  if (!dialog) {
    dialog = document.createElement('dialog');
    dialog.id = 'destinationDialog';
    dialog.className = 'account-dialog destination-dialog';
    document.body.appendChild(dialog);
  }
  const info = d.information || {};
  const practical = info.practical || {};
  const experience = info.experience || {};
  const decision = info.decision || {};
  const list = values => (values || []).filter(Boolean).map(value => `<li>${escapeHtml(value)}</li>`).join('');
  const cost = practical.cost_eur == null ? 'Провери цената' : `${escapeHtml(practical.cost_eur)} € ориентировъчно`;

  dialog.innerHTML = `
    <button class="dialog-close" aria-label="Затвори" type="button">×</button>
    <div class="eyebrow"><span class="eyebrow-line"></span> ${escapeHtml(d.region || 'БЪЛГАРИЯ')}</div>
    <h2>${escapeHtml(d.name)}</h2>
    <div class="tag-row">
      ${(d.categories || []).filter(x => /[А-Яа-я]/.test(x)).slice(0, 4).map(x => `<span class="mini-tag">${escapeHtml(x)}</span>`).join('')}
      <span class="status-tag">${d.verification_status === 'verified' ? 'Проверено' : 'Чака редакторска проверка'}</span>
    </div>
    <p class="dialog-intro">${escapeHtml(info.summary || d.description || '')}</p>
    <div class="detail-note">
      <b>Подходящо е, ако…</b>
      <ul>${list(info.good_for)}</ul>
      <p><strong>${escapeHtml(decision.best_for || '')}</strong> · трудност: ${escapeHtml(decision.difficulty || 'Провери на място')}</p>
    </div>
    ${info.highlights?.length ? `<div class="detail-note"><b>Какво ще видиш</b><ul>${list(info.highlights)}</ul></div>` : ''}
    <div class="detail-note">
      <b>Практично преди да тръгнеш</b>
      <ul>
        <li>Време за посещение: ${escapeHtml(practical.visit_minutes || d.estimated_visit_minutes || '—')} минути</li>
        <li>Цена: ${cost}</li>
        <li>Среда: ${escapeHtml(experience.terrain || 'Провери условията')}</li>
        <li>${escapeHtml(practical.access || 'Провери достъпа, работното време и сезонните ограничения.')}</li>
      </ul>
    </div>
    <div class="detail-note" id="detailSourceRefs"><b>Исторически източници</b><p>Проверяваме дали има свързани източници…</p></div>
    ${d.source_url ? `<p><a class="source-link" href="${escapeHtml(d.source_url)}" target="_blank" rel="noopener">Източник ↗</a></p>` : ''}
    <button class="btn btn-primary btn-full" data-dialog-save="${d.id}" type="button">♡ Запази мястото</button>
  `;

  dialog.querySelector('.dialog-close').addEventListener('click', () => dialog.close());
  dialog.querySelector('[data-dialog-save]').addEventListener('click', () => saveDestination(d.id));
  dialog.showModal();
  loadDestinationSources(d.id, dialog);
}

async function loadDestinationSources(destinationId, dialog) {
  const container = $('#detailSourceRefs', dialog);
  if (!container) return;
  try {
    const references = await api(`/api/destinations/${destinationId}/sources`);
    if (!references.length) {
      container.innerHTML = '<b>Исторически източници</b><p>Все още няма публикувани проверени източници за тази дестинация.</p>';
      return;
    }
    container.innerHTML = `<b>Исторически източници</b>${references.map(ref => `<p><strong>${escapeHtml(ref.source_title)}</strong> · ${escapeHtml(ref.author || 'Автор не е посочен')} · стр. ${escapeHtml(ref.page_number ?? '—')}<br>${escapeHtml(ref.excerpt || '')}${ref.source_url ? ` <a href="${escapeHtml(ref.source_url)}" target="_blank" rel="noopener">Източник ↗</a>` : ''}</p>`).join('')}`;
  } catch {
    container.innerHTML = '<b>Исторически източници</b><p>Информацията за източници в момента не е достъпна.</p>';
  }
}

async function saveDestination(destinationId) {
  if (!accessToken) {
    $('#accountDialog')?.showModal();
    setStatus('accountStatus', 'Влез или се регистрирай, за да запазваш места.');
    return;
  }
  try {
    await api(`/api/auth/me/saved-destinations/${destinationId}`, { method: 'POST' });
    showToast('Мястото е запазено в профила ти.');
  } catch (error) { showToast(error.message); }
}

// -------- Planner --------

function getSelectedPlannerInterests() {
  return $$('#plannerInterests input:checked').map(el => el.value);
}

function plannerPayload() {
  const budgetText = $('#budget')?.value.trim() || '';
  const radiusText = $('#radius')?.value.trim() || '';
  const payload = {
    start_latitude: Number($('#startLat')?.value || 42.6977),
    start_longitude: Number($('#startLon')?.value || 23.3219),
    available_time_minutes: Number($('#timeBudget')?.value || 180),
    transport_mode: $('#transportMode')?.value || 'car',
    interests: getSelectedPlannerInterests(),
    include_unverified: $('#includeUnverified')?.checked ?? true,
    return_to_start: $('#returnToStart')?.checked ?? false,
    max_destinations: 5,
    selected_destination_ids: [...selectedRoutePlaces.keys()],
    remember_interests: $('#rememberTripInterests')?.checked ?? false,
  };
  if (budgetText !== '') payload.budget_eur = Number(budgetText);
  if (radiusText !== '') payload.radius_km = Number(radiusText);
  return payload;
}

function renderItinerary(data) {
  const emptyState = $('#itineraryEmpty');
  if (emptyState) emptyState.classList.add('hidden');
  const target = $('#itineraryResults');
  if (!target) return;
  target.classList.remove('hidden');
  const cost = data.estimated_total_cost_eur === null ? 'Неизвестна' : `€${Number(data.estimated_total_cost_eur).toFixed(0)}`;
  const stops = data.stops || [];

  target.innerHTML = `
    <div class="eyebrow"><span class="eyebrow-line"></span> ГОТОВ МАРШРУТ</div>
    <h3>${stops.length ? 'Твоята идея за път' : 'Промени параметрите'}</h3>
    <div class="itinerary-summary">
      <div class="itinerary-metric"><b>${Math.floor(data.estimated_total_minutes / 60)}ч ${data.estimated_total_minutes % 60}м</b><small>Път + посещения</small></div>
      <div class="itinerary-metric"><b>${Number(data.total_route_distance_km).toFixed(1)} км</b><small>Общо разстояние</small></div>
      <div class="itinerary-metric"><b>${cost}</b><small>Разходи за посещения</small></div>
    </div>
    ${stops.length ? stops.map(stop => `
      <article class="stop-card">
        <div class="stop-number">${stop.order}</div>
        <div class="stop-body">
          <h4>${escapeHtml(stop.destination.name)}</h4>
          <p>${escapeHtml(stop.destination.description || '')}</p>
          <div class="stop-details">
            <span>↗ ${stop.distance_from_previous_km} км до спирката</span>
            <span>◷ ${stop.travel_minutes_from_previous} мин път</span>
            <span>◎ ${stop.visit_minutes} мин посещение</span>
          </div>
        </div>
      </article>
    `).join('') : '<div class="archive-placeholder"><p>Нито една дестинация не се побира в този времеви и бюджетен лимит.</p></div>'}
    <div class="warning-list">${(data.warnings || []).map(w => `• ${escapeHtml(w)}`).join('<br>')}</div>
    <button class="btn btn-outline btn-full save-plan" id="savePlanButton" type="button">Запази маршрута в профила ↗</button>
  `;
  $('#savePlanButton')?.addEventListener('click', saveItinerary);
}

async function runPlanner(save = false) {
  const payload = lastPlannerPayload || plannerPayload();
  try {
    setStatus('plannerStatus', save ? 'Запазваме маршрута…' : 'Изчисляваме комбинация от спирки…');
    const query = save ? '?save=true&title=Маршрут%20в%20България' : '';
    const data = await api(`/api/itineraries/plan${query}`, { method: 'POST', body: JSON.stringify(payload) });
    if (!save) renderItinerary(data);
    setStatus('plannerStatus', '');
    if (save) showToast('Маршрутът е запазен в профила ти.');
  } catch (error) {
    setStatus('plannerStatus', error.message, true);
  }
}

async function saveItinerary() {
  if (!accessToken) {
    $('#accountDialog')?.showModal();
    setStatus('accountStatus', 'Влез, за да запазиш маршрута.');
    return;
  }
  await runPlanner(true);
}

// -------- Bootstrap --------

document.addEventListener('DOMContentLoaded', async () => {
  try {
    await initMapGeometry();
  } catch (err) {
    console.error('Map init failed:', err);
    const mapEl = $('#destinationMap');
    if (mapEl) {
      mapEl.innerHTML = `<div class="map-error"><strong>Картата не можа да се зареди</strong><span>${escapeHtml(err.message)}</span></div>`;
    }
  }

  loadDestinations(true);

  const searchInput = $('#destinationSearch');
  if (searchInput) {
    searchInput.addEventListener('input', () => loadDestinations(true));
  }

  const categoryFilter = $('#categoryFilter');
  if (categoryFilter) {
    categoryFilter.addEventListener('change', () => loadDestinations(true));
  }

  const loadMoreBtn = $('#loadMore');
  if (loadMoreBtn) {
    loadMoreBtn.addEventListener('click', () => {
      visibleCount += 8;
      renderList(destinations, visibleCount);
    });
  }

  const destinationList = $('#destinationList');
  if (destinationList) {
    destinationList.addEventListener('click', (e) => {
      const detailBtn = e.target.closest('[data-detail]');
      if (detailBtn) { openDetail(detailBtn.dataset.detail); return; }
      const routeAddBtn = e.target.closest('[data-route-add]');
      if (routeAddBtn) { toggleRouteDestination(routeAddBtn.dataset.routeAdd); return; }
      const saveBtn = e.target.closest('[data-save]');
      if (saveBtn) { saveDestination(saveBtn.dataset.save); return; }
    });
  }

  const selectedRouteSummary = $('#selectedRouteSummary');
  if (selectedRouteSummary) {
    selectedRouteSummary.addEventListener('click', (e) => {
      const removeBtn = e.target.closest('[data-route-remove]');
      if (removeBtn) toggleRouteDestination(removeBtn.dataset.routeRemove);
    });
  }

  const plannerForm = $('#plannerForm');
  if (plannerForm) {
    plannerForm.addEventListener('submit', (e) => {
      e.preventDefault();
      lastPlannerPayload = plannerPayload();
      runPlanner(false);
    });
  }

  const clearRouteSelection = $('#clearRouteSelection');
  if (clearRouteSelection) {
    clearRouteSelection.addEventListener('click', () => {
      selectedRoutePlaces.clear();
      renderSelectedRouteSummary();
      renderList(destinations);
    });
  }
});