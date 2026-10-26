const API = '';
const tokenKey = 'otr_bulgaria_token';
let accessToken = sessionStorage.getItem(tokenKey) || '';
let currentUser = null;
let currentAccountMode = 'login';
let destinations = [];
let visibleCount = 8;
let map = null;
let mapProvider = 'google_maps';
let googleMapsApiKey = null;
let googleInfoWindow = null;
let GoogleMap = null;
let GoogleInfoWindow = null;
let GoogleMarker = null;
let GooglePolyline = null;
let GoogleLatLngBounds = null;
let mapLoadError = false;
let mapMarkers = [];
let currentRouteOverlay = null;
let selectedRoutePlaces = new Map();
let currentLatitude = null;
let currentLongitude = null;
let lastPlannerPayload = null;
let sourceMetadataCache = [];

window.gm_authFailure = () => {
  const message = 'Google rejected the Maps JavaScript API key. Check billing, Maps JavaScript API activation, and HTTP referrer restrictions.';
  console.error('[Google Maps] gm_authFailure:', message);
  setStatus('locationStatus', message, true);
  showMapError(message);
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
}
function showToast(message) {
  const toast = $('#toast');
  toast.textContent = message;
  toast.classList.add('show');
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove('show'), 3600);
}
function setStatus(id, message, isError = false) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = message || '';
  el.style.color = isError ? '#a15e43' : '';
}
function showMapError(message) {
  const mapElement = $('#destinationMap');
  if (mapElement && !window.google?.maps) {
    mapElement.innerHTML = `<div class="map-error" role="alert"><strong>Google Maps не можа да се зареди.</strong><span>${escapeHtml(message)}</span><small>Провери конзолата на браузъра и HTTP referrer ограниченията на browser API key.</small></div>`;
  }
}
async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`);
  const isForm = options.body instanceof FormData;
  if (options.body && !isForm && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  let response;
  try {
    response = await fetch(`${API}${path}`, {...options, headers});
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
  return `<article class="destination-card"><div class="destination-index">${String(index + 1).padStart(2,'0')}</div><div class="destination-content"><h4>${escapeHtml(d.name)}</h4><p>${escapeHtml(d.description || 'Няма добавено описание.')}</p><div class="tag-row"><span class="mini-tag">${escapeHtml(category)}</span>${tags}${review}</div><div class="card-actions"><button class="card-action" data-detail="${d.id}">Детайли ↗</button><button class="card-action" data-route-add="${d.id}">${isSelected ? '✓ В маршрута' : '+ Добави към маршрута'}</button><button class="card-action" data-save="${d.id}">${accessToken ? '♡ Запази' : '♡ Запази след вход'}</button></div></div></article>`;
}
async function loadGoogleMapsScript(key) {
  if (window.google && window.google.maps) return true;
  return new Promise(resolve => {
    const script = document.createElement('script');
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}&v=weekly&loading=async`;
    script.async = true;
    script.defer = true;
    script.onload = () => {
      // Google can load the script successfully and still reject the key later
      // (billing, API activation, or referrer restrictions). Give it a moment
      // to install the Maps namespace before declaring success.
      window.setTimeout(() => resolve(!!(window.google && window.google.maps)), 0);
    };
    script.onerror = () => resolve(false);
    document.head.appendChild(script);
  });
}
async function configureMapProvider() {
  try {
    const config = await api('/api/config');
    googleMapsApiKey = config.google_maps_js_api_key || null;
    if (!googleMapsApiKey) throw new Error('Google Maps JavaScript API key is not configured.');
    if (!await loadGoogleMapsScript(googleMapsApiKey)) throw new Error('Google Maps JavaScript API failed to load.');
    // With the async Maps JS loader, constructors are provided through the
    // modular library API rather than being guaranteed on google.maps.
    const coreLibrary = await google.maps.importLibrary('core');
    const mapsLibrary = await google.maps.importLibrary('maps');
    const markerLibrary = await google.maps.importLibrary('marker');
    GoogleMap = mapsLibrary.Map;
    GoogleInfoWindow = mapsLibrary.InfoWindow;
    GooglePolyline = mapsLibrary.Polyline;
    GoogleLatLngBounds = coreLibrary.LatLngBounds;
    GoogleMarker = markerLibrary.AdvancedMarkerElement || markerLibrary.Marker;
    if (!GoogleMap || !GoogleInfoWindow || !GoogleMarker) throw new Error('Google Maps libraries failed to initialize.');
  } catch (error) {
    mapProvider = 'google_maps';
    mapLoadError = true;
    setStatus('locationStatus', `Google Maps: ${error.message} Провери Maps JavaScript API и ключа в Google Cloud.`, true);
    showMapError(error.message);
  }
}
function initMap() {
  if (map || !$('#destinationMap')) return;
  if (mapLoadError) return;
  if (GoogleMap) {
    map = new GoogleMap($('#destinationMap'), {
      center: {lat: 42.7, lng: 25.3},
      zoom: 7,
      mapTypeControl: false,
      streetViewControl: false,
      fullscreenControl: true,
      mapTypeId: 'roadmap'
    });
    googleInfoWindow = new GoogleInfoWindow();
    return;
  }
  const message = 'Google Maps не е наличен. Провери Maps JavaScript API ключа и неговите ограничения.';
  setStatus('locationStatus', message, true);
  showMapError(message);
}
function mapPopupHtml(d) {
  return `<div class="map-popup"><strong>${escapeHtml(d.name)}</strong><span>${escapeHtml(d.region || 'България')} · ${escapeHtml(labelForCategory(d))}</span><br><a href="#" class="map-detail-link" data-map-detail="${d.id}">Виж детайли ↗</a></div>`;
}
function updateMap(list) {
  initMap();
  if (!map) return;
  if (!window.google || !window.google.maps) return;
  mapMarkers.forEach(marker => marker.setMap(null));
  mapMarkers = [];
  list.forEach(d => {
    const markerOptions = {position: {lat: Number(d.latitude), lng: Number(d.longitude)}, map, title: d.name};
    const marker = new GoogleMarker(markerOptions);
    marker.addListener('click', () => {
      googleInfoWindow.setContent(mapPopupHtml(d));
      googleInfoWindow.open({map, anchor: marker});
    });
    mapMarkers.push(marker);
  });
}
function decodePolyline(encoded) {
  if (!encoded) return [];
  const points = [];
  let index = 0, lat = 0, lng = 0;
  while (index < encoded.length) {
    let result = 0, shift = 0, byte;
    do { byte = encoded.charCodeAt(index++) - 63; result |= (byte & 0x1f) << shift; shift += 5; } while (byte >= 0x20 && index < encoded.length);
    const deltaLat = (result & 1) ? ~(result >> 1) : (result >> 1);
    lat += deltaLat;
    result = 0; shift = 0;
    do { byte = encoded.charCodeAt(index++) - 63; result |= (byte & 0x1f) << shift; shift += 5; } while (byte >= 0x20 && index < encoded.length);
    const deltaLng = (result & 1) ? ~(result >> 1) : (result >> 1);
    lng += deltaLng;
    points.push({lat: lat / 1e5, lng: lng / 1e5});
  }
  return points;
}
function drawRoutePolyline(encoded) {
  if (!encoded || mapProvider !== 'google_maps') return;
  initMap();
  const path = decodePolyline(encoded);
  if (!map || !path.length) return;
  if (currentRouteOverlay) {
    currentRouteOverlay.setMap(null);
    currentRouteOverlay = null;
  }
  currentRouteOverlay = new GooglePolyline({path, map, geodesic: true, strokeColor: '#36543a', strokeOpacity: 0.9, strokeWeight: 5});
  const bounds = new GoogleLatLngBounds();
  path.forEach(point => bounds.extend(point));
  map.fitBounds(bounds, 36);
}
function renderSelectedRouteSummary() {
  const target = $('#selectedRouteSummary');
  if (!target) return;
  const places = [...selectedRoutePlaces.values()];
  if (!places.length) {
    target.innerHTML = '<span class="muted">Все още няма избрани места.</span>';
    return;
  }
  target.innerHTML = places.map((place, index) => `<span class="selected-route-chip"><b>${index + 1}.</b> ${escapeHtml(place.name)} <button type="button" data-route-remove="${place.id}" aria-label="Премахни ${escapeHtml(place.name)}">×</button></span>`).join('');
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
  $('#destinationList').innerHTML = slice.length
    ? slice.map((d,i) => renderDestinationCard(d, i)).join('')
    : '<div class="archive-placeholder"><span>⌕</span><p>Няма намерени дестинации. Промени думата за търсене или премахни част от филтрите.</p></div>';
  $('#resultsCount').textContent = `Показани ${slice.length} от ${list.length} резултата`;
  $('#loadMore').classList.toggle('hidden', slice.length >= list.length || list.length === 0);
  updateMap(list);
}
async function loadDestinations(reset = true) {
  if (reset) visibleCount = 8;
  const q = $('#destinationSearch').value.trim();
  const category = $('#categoryFilter').value;
  const params = new URLSearchParams({limit:'250'});
  if (q) params.set('q', q);
  if (category) params.set('category', category);
  if (currentLatitude !== null && currentLongitude !== null && $('#useLocation').dataset.radius === 'true') {
    params.set('latitude', currentLatitude);
    params.set('longitude', currentLongitude);
    params.set('radius_km', $('#useLocation').dataset.radiusKm || '80');
  }
  setStatus('locationStatus', '');
  $('#destinationList').innerHTML = '<div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div>';
  try {
    destinations = await api(`/api/destinations?${params.toString()}`);
    renderList(destinations);
    if (!destinations.length) setStatus('locationStatus', 'Не открихме съвпадения за тези филтри.');
  } catch (error) {
    $('#destinationList').innerHTML = '<div class="archive-placeholder"><p>Не успяхме да заредим дестинациите. Провери дали API сървърът работи.</p></div>';
    setStatus('locationStatus', error.message, true);
  }
}
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
  dialog.innerHTML = `<button class="dialog-close" aria-label="Затвори">×</button><div class="eyebrow"><span class="eyebrow-line"></span> ${escapeHtml(d.region || 'БЪЛГАРИЯ')}</div><h2>${escapeHtml(d.name)}</h2><div class="tag-row">${(d.categories || []).filter(x => /[А-Яа-я]/.test(x)).slice(0,4).map(x => `<span class="mini-tag">${escapeHtml(x)}</span>`).join('')}<span class="status-tag">${d.verification_status === 'verified' ? 'Проверено' : 'Чака редакторска проверка'}</span></div><p class="dialog-intro">${escapeHtml(info.summary || d.description || '')}</p><div class="detail-note"><b>Подходящо е, ако…</b><ul>${list(info.good_for)}</ul><p><strong>${escapeHtml(decision.best_for || '')}</strong> · трудност: ${escapeHtml(decision.difficulty || 'Провери на място')}</p></div>${info.highlights?.length ? `<div class="detail-note"><b>Какво ще видиш</b><ul>${list(info.highlights)}</ul></div>` : ''}<div class="detail-note"><b>Практично преди да тръгнеш</b><ul><li>Време за посещение: ${escapeHtml(practical.visit_minutes || d.estimated_visit_minutes || '—')} минути</li><li>Цена: ${cost}</li><li>Среда: ${escapeHtml(experience.terrain || 'Провери условията')}</li><li>${escapeHtml(practical.access || 'Провери достъпа, работното време и сезонните ограничения.')}</li></ul></div><div class="detail-note" id="detailSourceRefs"><b>Исторически източници</b><p>Проверяваме дали има свързани източници…</p></div>${d.source_url ? `<p><a class="source-link" href="${escapeHtml(d.source_url)}" target="_blank" rel="noopener">Източник ↗</a></p>` : ''}<button class="btn btn-primary btn-full" data-dialog-save="${d.id}">♡ Запази мястото</button>`;
  dialog.querySelector('.dialog-close').addEventListener('click', () => dialog.close());
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
    $('#accountDialog').showModal();
    setStatus('accountStatus', 'Влез или се регистрирай, за да запазваш места.');
    return;
  }
  try {
    await api(`/api/auth/me/saved-destinations/${destinationId}`, {method:'POST'});
    showToast('Мястото е запазено в профила ти.');
  } catch (error) { showToast(error.message); }
}
async function loadRecommendations() {
  const interests = $$('#plannerInterests input:checked').map(el => el.value);
  const payload = {interests, include_unverified:true, limit:12};
  if (currentLatitude !== null && currentLongitude !== null) {
    payload.latitude = currentLatitude;
    payload.longitude = currentLongitude;
  }
  try {
    const rows = await api('/api/recommendations', {method:'POST', body:JSON.stringify(payload)});
    destinations = rows.map(item => item.destination);
    visibleCount = 8;
    renderList(destinations);
    $('#resultsCount').textContent = `Подбрани ${destinations.length} препоръки по интересите ти`;
    document.querySelector('#explore').scrollIntoView({behavior:'smooth'});
  } catch (error) { showToast(error.message); }
}
function getSelectedPlannerInterests() {
  return $$('#plannerInterests input:checked').map(el => el.value);
}
function plannerPayload() {
  const budgetText = $('#budget').value.trim();
  const radiusText = $('#radius').value.trim();
  const payload = {
    start_latitude: Number($('#startLat').value),
    start_longitude: Number($('#startLon').value),
    available_time_minutes: Number($('#timeBudget').value),
    transport_mode: $('#transportMode').value,
    interests: getSelectedPlannerInterests(),
    include_unverified: $('#includeUnverified').checked,
    return_to_start: $('#returnToStart').checked,
    max_destinations: 5,
    selected_destination_ids: [...selectedRoutePlaces.keys()],
    remember_interests: $('#rememberTripInterests').checked,
  };
  if (budgetText !== '') payload.budget_eur = Number(budgetText);
  if (radiusText !== '') payload.radius_km = Number(radiusText);
  return payload;
}
function renderItinerary(data) {
  $('#itineraryEmpty').classList.add('hidden');
  const target = $('#itineraryResults');
  target.classList.remove('hidden');
  const cost = data.estimated_total_cost_eur === null ? 'Неизвестна' : `€${Number(data.estimated_total_cost_eur).toFixed(0)}`;
  const stops = data.stops || [];
  const routeLabel = data.route_provider === 'google_routes_api' ? 'Google Maps Routes API' : 'Ориентировъчна оценка';
  target.innerHTML = `<div class="eyebrow"><span class="eyebrow-line"></span> ГОТОВ МАРШРУТ</div><h3>${stops.length ? 'Твоята идея за път' : 'Промени параметрите'}</h3><p class="route-provider-note">${escapeHtml(routeLabel)}${data.route_is_estimate ? ' · времената са приблизителни' : ' · оценката не гарантира текущ трафик'}</p><div class="itinerary-summary"><div class="itinerary-metric"><b>${Math.floor(data.estimated_total_minutes/60)}ч ${data.estimated_total_minutes%60}м</b><small>Път + посещения</small></div><div class="itinerary-metric"><b>${Number(data.total_route_distance_km).toFixed(1)} км</b><small>Общо разстояние</small></div><div class="itinerary-metric"><b>${cost}</b><small>Разходи за посещения</small></div></div>${stops.length ? stops.map(stop => `<article class="stop-card"><div class="stop-number">${stop.order}</div><div class="stop-body"><h4>${escapeHtml(stop.destination.name)}</h4><p>${escapeHtml(stop.destination.description || '')}</p><div class="stop-details"><span>↗ ${stop.distance_from_previous_km} км до спирката</span><span>◷ ${stop.travel_minutes_from_previous} мин път</span><span>◎ ${stop.visit_minutes} мин посещение</span></div>${stop.destination.verification_status !== 'verified' ? '<span class="status-tag">Демо запис · изисква проверка</span>' : ''}</div></article>`).join('') : '<div class="archive-placeholder"><p>Нито една дестинация не се побира в този времеви и бюджетен лимит. Увеличи времето или промени избраните места.</p></div>'}<div class="warning-list">${(data.warnings || []).map(w => `• ${escapeHtml(w)}`).join('<br>')}</div>${data.google_maps_url && stops.length ? `<a class="btn btn-primary btn-full map-route-link" href="${escapeHtml(data.google_maps_url)}" target="_blank" rel="noopener noreferrer">Отвори този маршрут в Google Maps ↗</a>` : ''}<button class="btn btn-outline btn-full save-plan" id="savePlanButton">Запази маршрута в профила ↗</button>`;
  $('#savePlanButton').addEventListener('click', saveItinerary);
  if (data.route_polyline) drawRoutePolyline(data.route_polyline);
}

async function runPlanner(save = false) {
  const payload = lastPlannerPayload || plannerPayload();
  try {
    setStatus('plannerStatus', save ? 'Запазваме маршрута…' : 'Изчисляваме комбинация от спирки…');
    const query = save ? '?save=true&title=Маршрут%20в%20България' : '';
    const data = await api(`/api/itineraries/plan${query}`, {method:'POST', body:JSON.stringify(payload)});
    if (!save) renderItinerary(data);
    setStatus('plannerStatus', '');
    if (save) showToast('Маршрутът е запазен в профила ти.');
  } catch (error) {
    setStatus('plannerStatus', error.message, true);
  }
}
async function saveItinerary() {
  if (!accessToken) {
    $('#accountDialog').showModal();
    setStatus('accountStatus', 'Влез, за да запазиш маршрута.');
    return;
  }
  await runPlanner(true);
}
function switchAccountMode(mode) {
  currentAccountMode = mode;
  $$('.account-tab').forEach(tab => tab.classList.toggle('active', tab.dataset.accountTab === mode));
  $('#accountSubmit').innerHTML = (mode === 'login' ? 'Вход' : 'Създай профил') + ' <span>↗</span>';
  $('#accountPassword').autocomplete = mode === 'login' ? 'current-password' : 'new-password';
  $('#accountPassword').minLength = mode === 'register' ? 10 : 1;
}
function updateAccountUi() {
  $('#profileLabel').textContent = currentUser ? (currentUser.is_admin ? 'Администратор' : 'Моят профил') : 'Вход / Профил';
  const rememberInterests = $('#rememberTripInterests');
  if (rememberInterests) { rememberInterests.disabled = !currentUser; if (!currentUser) rememberInterests.checked = false; }
  $('#loggedInPanel').classList.toggle('hidden', !currentUser);
  $('#accountForm').classList.toggle('hidden', !!currentUser);
  $('.account-tabs').classList.toggle('hidden', !!currentUser);
  if (currentUser) {
    $('#loggedInEmail').textContent = currentUser.email;
    $('#adminBox').classList.toggle('is-visible', !!currentUser.is_admin);
    if (currentUser.is_admin) loadAdminSources().catch(() => {});
    loadPreferences().catch(() => {});
  } else {
    $('#adminBox').classList.remove('is-visible');
  }
}
async function refreshUser() {
  if (!accessToken) { currentUser = null; updateAccountUi(); return; }
  try {
    currentUser = await api('/api/auth/me');
  } catch {
    accessToken = '';
    sessionStorage.removeItem(tokenKey);
    currentUser = null;
  }
  updateAccountUi();
}
async function loadPreferences() {
  if (!currentUser) return;
  try {
    const pref = await api('/api/auth/me/preferences');
    const form = $('#preferencesForm');
    $$('input[type="checkbox"]', form).forEach(box => box.checked = (pref.interests || []).includes(box.value));
    $$('#plannerInterests input').forEach(box => box.checked = (pref.interests || []).includes(box.value));
    $('#prefTransport').value = pref.preferred_transport || 'car';
    $('#prefBudget').value = pref.budget_eur ?? '';
    // Keep current-trip checkboxes separate from saved profile interests. The backend blends both signals.
    if (['car','walking','train'].includes(pref.preferred_transport)) $('#transportMode').value = pref.preferred_transport;
    if (pref.budget_eur !== null && pref.budget_eur !== undefined) $('#budget').value = pref.budget_eur;
    if (pref.trip_duration_minutes) {
      const options = [180,360,480,720];
      $('#timeBudget').value = String(options.reduce((best, value) => Math.abs(value - pref.trip_duration_minutes) < Math.abs(best - pref.trip_duration_minutes) ? value : best, options[0]));
    }
  } catch (error) { setStatus('accountStatus', error.message, true); }
}
async function doAccountSubmit(event) {
  event.preventDefault();
  const email = $('#accountEmail').value.trim();
  const password = $('#accountPassword').value;
  try {
    setStatus('accountStatus', '');
    const data = await api(`/api/auth/${currentAccountMode === 'login' ? 'login' : 'register'}`, {method:'POST', body:JSON.stringify({email, password})});
    accessToken = data.access_token;
    sessionStorage.setItem(tokenKey, accessToken);
    currentUser = data.user;
    updateAccountUi();
    setStatus('accountStatus', 'Успешен вход.');
    showToast(currentUser.is_admin ? 'Влязъл си като администратор.' : 'Добре дошъл!');
    if (currentUser.is_admin) $('#adminBox').classList.add('is-visible');
  } catch (error) { setStatus('accountStatus', error.message, true); }
}
async function savePreferences(event) {
  event.preventDefault();
  if (!currentUser) return;
  const form = $('#preferencesForm');
  const interests = $$('input[type="checkbox"]', form).filter(box => box.checked).map(box => box.value);
  const payload = {interests, interest_weights:Object.fromEntries(interests.map(x => [x, 1 / Math.max(1, interests.length)])), preferred_transport:$('#prefTransport').value, budget_eur:$('#prefBudget').value === '' ? null : Number($('#prefBudget').value), trip_duration_minutes:180, prefers_lesser_known:false};
  try {
    await api('/api/auth/me/preferences', {method:'PUT', body:JSON.stringify(payload)});
    showToast('Предпочитанията са запазени.');
  } catch (error) { setStatus('accountStatus', error.message, true); }
}
async function searchArchive(event) {
  event.preventDefault();
  const query = $('#archiveQuery').value.trim();
  try {
    setStatus('archiveStatus', 'Търсим в проверената колекция…');
    const results = await api(`/api/sources/search?q=${encodeURIComponent(query)}&limit=30`);
    setStatus('archiveStatus', `${results.length} резултата за „${query}“`);
    $('#archiveResults').innerHTML = results.length ? results.map(item => `<article class="archive-result"><div class="archive-result-top"><div><h4>${escapeHtml(item.source_title)}</h4><small>${escapeHtml(item.author || 'Авторът не е посочен')} · ${item.publication_year || 'годината не е посочена'}</small></div><span class="mini-tag">Стр. ${item.page_number}</span></div><p>${escapeHtml(item.passage)}</p><div class="meta"><span>OCR: ${escapeHtml(item.review_status)}</span><span>Проверка: ${escapeHtml(item.verification_status)}</span><span>Права: ${escapeHtml(item.copyright_status)}</span><span>Източник #${item.source_id}</span>${item.source_url ? `<a href="${escapeHtml(item.source_url)}" target="_blank" rel="noopener">Оригинален източник ↗</a>` : ''}${item.bibliographic_reference ? `<span>${escapeHtml(item.bibliographic_reference)}</span>` : ''}</div></article>`).join('') : '<div class="archive-placeholder"><span>⌕</span><p>Няма публично достъпни съвпадения. В MVP излизат само страници, които са прегледани, проверени и с известни права за използване.</p></div>';
  } catch (error) { setStatus('archiveStatus', error.message, true); }
}
async function uploadSource(event) {
  event.preventDefault();
  const formData = new FormData(event.currentTarget);
  try {
    setStatus('sourceStatus', 'Качваме оригинала…');
    const source = await api('/api/admin/sources', {method:'POST', body:formData});
    event.currentTarget.reset();
    setStatus('sourceStatus', `Източникът „${source.title}“ е качен. Оригиналният файл е запазен.`);
    await loadAdminSources();
  } catch (error) { setStatus('sourceStatus', error.message, true); }
}
async function loadAdminSources() {
  if (!currentUser?.is_admin) return;
  try {
    sourceMetadataCache = await api('/api/admin/sources');
    const container = $('#adminSourcesList');
    if (!sourceMetadataCache.length) { container.innerHTML = '<p class="field-help">Все още няма качени източници.</p>'; return; }
    container.innerHTML = sourceMetadataCache.map(source => `<article class="source-admin-card" data-source="${source.id}"><div class="source-admin-top"><div><b>${escapeHtml(source.title)}</b><small>${escapeHtml(source.author || 'Автор не е посочен')} · ${source.publication_year || 'година неизвестна'} · ${escapeHtml(source.processing_status)}</small></div><div class="source-admin-actions"><button data-process-source="${source.id}">Обработи OCR</button><button data-view-pages="${source.id}">Страници</button><button data-retry-source="${source.id}">Повтори грешките</button></div></div><div class="source-page-list" id="sourcePages-${source.id}"></div></article>`).join('');
  } catch (error) { setStatus('sourceStatus', error.message, true); }
}
async function processSource(sourceId, retry = false) {
  try {
    setStatus('sourceStatus', retry ? 'Повтаряме неуспешните страници…' : 'Поставяме OCR обработката на опашка…');
    await api(`/api/admin/sources/${sourceId}/${retry ? 'retry-failed' : 'process-ocr'}`, {method:'POST'});
    await loadAdminSources();
    for (let attempt = 0; attempt < 300; attempt++) {
      await new Promise(resolve => setTimeout(resolve, 1200));
      const state = await api(`/api/admin/sources/${sourceId}/status`);
      setStatus('sourceStatus', `OCR: ${state.counts.completed || 0} готови · ${state.counts.failed || 0} неуспешни · ${state.counts.processing || 0} в процес. Статус: ${state.status}.`);
      if (!['queued', 'processing'].includes(state.status)) break;
    }
    await loadAdminSources();
    await loadSourcePages(sourceId);
    setStatus('sourceStatus', 'OCR статусът е обновен. Прегледай текста и коригирай грешките, преди да го маркираш като проверен.');
  } catch (error) { setStatus('sourceStatus', error.message, true); }
}
async function loadSourcePages(sourceId) {
  const container = $(`#sourcePages-${sourceId}`);
  if (!container) return;
  try {
    const [pages, allDestinations] = await Promise.all([api(`/api/admin/sources/${sourceId}/pages`), api('/api/destinations?limit=250')]);
    if (!pages.length) { container.innerHTML = '<p class="field-help">Няма OCR страници. Натисни „Обработи OCR“.</p>'; return; }
    const destinationOptions = allDestinations.map(d => `<option value="${d.id}">${escapeHtml(d.name)}</option>`).join('');
    container.innerHTML = pages.map(page => `<div class="page-review" data-page="${page.id}"><h5>Страница ${page.page_number} · ${escapeHtml(page.processing_status)} · ${escapeHtml(page.review_status)} ${page.ocr_confidence === null ? '' : `· увереност ${page.ocr_confidence}%`}</h5>${page.processing_error ? `<p class="field-help">Грешка: ${escapeHtml(page.processing_error)}</p>` : ''}<pre>${escapeHtml(page.raw_ocr_text || 'Няма извлечен текст.')}</pre><label class="field"><span>Текст за проверка / корекция</span><textarea class="review-text" maxlength="100000">${escapeHtml(page.normalized_text || page.raw_ocr_text || '')}</textarea></label><div class="review-actions"><select class="verification-select"><option value="unverified" ${page.verification_status === 'unverified' ? 'selected' : ''}>Непроверено</option><option value="verified" ${page.verification_status === 'verified' ? 'selected' : ''}>Проверено</option><option value="conflicting" ${page.verification_status === 'conflicting' ? 'selected' : ''}>Противоречиво</option></select><button data-review-page="${page.id}">Запази редакцията</button><button data-page-image="${page.id}" data-variant="original">Виж оригинала</button><button data-page-image="${page.id}" data-variant="processed">Виж обработеното</button></div><div class="review-actions"><select class="destination-link-select"><option value="">Свържи с дестинация…</option>${destinationOptions}</select><select class="link-status-select"><option value="needs_review">Връзката е чернова</option><option value="verified">Връзката е проверена</option></select><button data-link-page="${page.id}">Свържи</button></div><div class="page-image"></div></div>`).join('');
  } catch (error) { container.innerHTML = `<p class="field-help">${escapeHtml(error.message)}</p>`; }
}
async function reviewPage(button) {
  const pageId = button.dataset.reviewPage;
  const card = button.closest('.page-review');
  const normalized_text = $('.review-text', card).value;
  const verification_status = $('.verification-select', card).value;
  try {
    const result = await api(`/api/admin/pages/${pageId}/review`, {method:'POST', body:JSON.stringify({normalized_text, verification_status, mark_reviewed:true})});
    showToast(`Страницата е запазена. Създадени текстови части: ${result.passages_created}.`);
    await loadAdminSources();
    const parentSource = card.closest('[data-source]');
    if (parentSource) await loadSourcePages(parentSource.dataset.source);
  } catch (error) { showToast(error.message); }
}
async function linkPageToDestination(button) {
  const card = button.closest('.page-review');
  const destinationId = $('.destination-link-select', card).value;
  if (!destinationId) { showToast('Избери дестинация, към която да свържеш страницата.'); return; }
  const text = $('.review-text', card).value;
  const payload = {destination_id:Number(destinationId), excerpt:text.slice(0, 500), review_status:$('.link-status-select', card).value};
  try {
    const result = await api(`/api/admin/pages/${button.dataset.linkPage}/link-destination`, {method:'POST', body:JSON.stringify(payload)});
    showToast(`Страница ${result.page_number} е свързана с „${result.destination_name}“. Статус: ${result.review_status}.`);
  } catch (error) { showToast(error.message); }
}
async function loadPageImage(button) {
  const pageId = button.dataset.pageImage;
  const card = button.closest('.page-review');
  const target = $('.page-image', card);
  try {
    const headers = new Headers();
    if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`);
    const variant = button.dataset.variant || 'original';
    const response = await fetch(`/api/admin/pages/${pageId}/image?variant=${variant}`, {headers});
    if (!response.ok) throw new Error('Не успяхме да заредим изображението.');
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    target.innerHTML = `<img alt="${variant === 'original' ? 'Оригинално изображение' : 'Обработено изображение'} на страница ${pageId}" src="${url}" style="display:block;max-width:100%;max-height:360px;object-fit:contain;margin-top:10px;border-radius:8px">`;
  } catch (error) { showToast(error.message); }
}
function bindEvents() {
  const on = (selector, event, handler) => {
    const element = $(selector);
    if (element) element.addEventListener(event, handler);
  };
  on('#destinationSearch', 'keydown', event => { if (event.key === 'Enter') { event.preventDefault(); loadDestinations(); } });
  on('#categoryFilter', 'change', () => loadDestinations());
  on('#clearFilters', 'click', () => {
    $('#destinationSearch').value = ''; $('#categoryFilter').value = '';
    currentLatitude = currentLongitude = null; $('#useLocation').dataset.radius = 'false';
    loadDestinations();
  });
  on('#loadMore', 'click', () => { visibleCount += 8; renderList(destinations); });
  on('#useLocation', 'click', () => {
    if (!navigator.geolocation) { setStatus('locationStatus', 'Този браузър не предоставя геолокация.', true); return; }
    setStatus('locationStatus', 'Изчакваме разрешение за местоположението…');
    navigator.geolocation.getCurrentPosition(position => {
      currentLatitude = position.coords.latitude; currentLongitude = position.coords.longitude;
      $('#startLat').value = currentLatitude.toFixed(5); $('#startLon').value = currentLongitude.toFixed(5);
      $('#useLocation').dataset.radius = 'true'; $('#useLocation').dataset.radiusKm = '80';
      setStatus('locationStatus', 'Показваме дестинации в приблизителен радиус 80 км. Географското разстояние не е пътно разстояние.');
      loadDestinations();
      if (map && mapProvider === 'google_maps') { map.setCenter({lat: currentLatitude, lng: currentLongitude}); map.setZoom(8); }
    }, error => setStatus('locationStatus', error.code === 1 ? 'Не е дадено разрешение за местоположение. Можеш да въведеш координатите ръчно.' : 'Местоположението не е достъпно. Въведи координатите ръчно.', true), {timeout:8000, maximumAge:300000});
  });
  on('#recommendationsButton', 'click', loadRecommendations);
  on('#clearRouteSelection', 'click', () => { selectedRoutePlaces.clear(); renderSelectedRouteSummary(); renderList(destinations); });
  on('#plannerForm', 'submit', async event => {
    event.preventDefault(); lastPlannerPayload = plannerPayload(); await runPlanner(false);
  });
  on('#archiveSearchForm', 'submit', searchArchive);
  on('#uploadSourceForm', 'submit', uploadSource);
  on('#loadSources', 'click', loadAdminSources);
  on('#profileOpen', 'click', () => { $('#accountDialog')?.showModal(); });
  on('#closeAccount', 'click', () => $('#accountDialog')?.close());
  $$('.account-tab').forEach(tab => tab.addEventListener('click', () => switchAccountMode(tab.dataset.accountTab)));
  on('#accountForm', 'submit', doAccountSubmit);
  on('#logoutButton', 'click', () => {
    accessToken = ''; currentUser = null; sessionStorage.removeItem(tokenKey); updateAccountUi(); setStatus('accountStatus','Излезе от профила.'); showToast('Излезе от профила.');
  });
  on('#showPreferences', 'click', () => $('#preferencesForm')?.classList.toggle('hidden'));
  on('#preferencesForm', 'submit', savePreferences);
  on('#mobileMenu', 'click', () => $('.main-nav')?.classList.toggle('open'));
  $$('.nav-link').forEach(link => link.addEventListener('click', () => {
    $$('.nav-link').forEach(item => item.classList.toggle('active', item === link));
    $('.main-nav').classList.remove('open');
  }));
  document.addEventListener('click', event => {
    const detail = event.target.closest('[data-detail]');
    const save = event.target.closest('[data-save]');
    const routeAdd = event.target.closest('[data-route-add]');
    const routeRemove = event.target.closest('[data-route-remove]');
    const mapDetail = event.target.closest('[data-map-detail]');
    const dialogSave = event.target.closest('[data-dialog-save]');
    const process = event.target.closest('[data-process-source]');
    const retry = event.target.closest('[data-retry-source]');
    const pages = event.target.closest('[data-view-pages]');
    const review = event.target.closest('[data-review-page]');
    const imageButton = event.target.closest('[data-page-image]');
    const linkPage = event.target.closest('[data-link-page]');
    if (detail) openDetail(detail.dataset.detail);
    else if (routeAdd) toggleRouteDestination(routeAdd.dataset.routeAdd);
    else if (routeRemove) toggleRouteDestination(routeRemove.dataset.routeRemove);
    else if (save) saveDestination(save.dataset.save);
    else if (mapDetail) { event.preventDefault(); openDetail(mapDetail.dataset.mapDetail); }
    else if (dialogSave) saveDestination(dialogSave.dataset.dialogSave);
    else if (process) processSource(process.dataset.processSource, false);
    else if (retry) processSource(retry.dataset.retrySource, true);
    else if (pages) loadSourcePages(pages.dataset.viewPages);
    else if (review) reviewPage(review);
    else if (imageButton) loadPageImage(imageButton);
    else if (linkPage) linkPageToDestination(linkPage);
  });
  document.addEventListener('click', event => {
    if (event.target.classList.contains('dialog-close') && event.target.closest('dialog')) event.target.closest('dialog').close();
  });
  window.addEventListener('resize', () => { if (map && window.google?.maps) google.maps.event.trigger(map, 'resize'); });
}

async function bootstrap() {
  $('#year').textContent = new Date().getFullYear();
  bindEvents();
  await configureMapProvider();
  await refreshUser();
  await loadDestinations();
  initMap();
  renderSelectedRouteSummary();
  switchAccountMode('login');
}
bootstrap();
