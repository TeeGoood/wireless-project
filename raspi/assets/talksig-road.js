// ─────────────────────────────────────────────────────────────────────────────
//  talksig-road.js
//  Separated JS for Talksig Road – includes a built-in debug panel.
//
//  Debug panel shortcut: press  `  (backtick) to toggle it open/closed.
//  It shows every WebSocket send/receive, connection state changes, and errors.
// ─────────────────────────────────────────────────────────────────────────────

// ── WebSocket URL ─────────────────────────────────────────────────────────────
//  When served by FastAPI (localhost:8000) location.host gives the right value.
//  When opened directly as file:// it falls back to localhost:8000.
var wsHost = (location.hostname && location.hostname !== '')
  ? location.host        // e.g.  "localhost:8000"  or  "192.168.1.10:8000"
  : 'localhost:8000';
var wsUrl = (location.protocol === 'https:' ? 'wss:' : 'ws:') + '//' + wsHost + '/ws';

// ── Application state ─────────────────────────────────────────────────────────
var ws = null;
var app = {
  carInfo: {},
  state: '',
  nearby: [],
  incomingRequests: [],
  connectedCarId: null,
  connectedPeerName: '',
  messages: []
};

// ── Debug panel ───────────────────────────────────────────────────────────────
var debugEl = null;
var debugLog = null;
var debugStatus = null;
var MAX_LOG_LINES = 200;

function initDebugPanel() {
  debugEl     = document.getElementById('debug-panel');
  debugLog    = document.getElementById('debug-log');
  debugStatus = document.getElementById('debug-ws-status');

  document.getElementById('debug-btn-clear').addEventListener('click', function () {
    debugLog.innerHTML = '';
  });
  document.getElementById('debug-btn-close').addEventListener('click', function () {
    debugEl.classList.add('hidden');
    document.getElementById('debug-toggle').style.display = 'block';
  });
  document.getElementById('debug-toggle').addEventListener('click', function () {
    debugEl.classList.remove('hidden');
    document.getElementById('debug-toggle').style.display = 'none';
  });

  // backtick key toggles panel
  document.addEventListener('keydown', function (e) {
    if (e.key === '`') {
      var hidden = debugEl.classList.toggle('hidden');
      document.getElementById('debug-toggle').style.display = hidden ? 'block' : 'none';
    }
  });

  dbg('info', 'Debug panel ready. WS target: ' + wsUrl);
  dbg('info', 'Page protocol: ' + location.protocol + '  host: ' + (location.host || '(file://)'));
}

function dbg(kind, text) {
  if (!debugLog) return;
  var line = document.createElement('div');
  line.className = 'log-line ' + kind;
  var ts = new Date().toLocaleTimeString('en-GB', { hour12: false });
  var prefix = { sent: '▶ SEND', recv: '◀ RECV', info: 'ℹ INFO', error: '✖ ERR ' }[kind] || kind;
  line.textContent = '[' + ts + '] ' + prefix + ' ' + text;
  debugLog.appendChild(line);
  // Trim old lines
  while (debugLog.children.length > MAX_LOG_LINES) {
    debugLog.removeChild(debugLog.firstChild);
  }
  debugLog.scrollTop = debugLog.scrollHeight;
  // Mirror to browser console as well
  var consoleFn = kind === 'error' ? console.error : kind === 'sent' || kind === 'recv' ? console.log : console.info;
  consoleFn('[TalksigRoad]', prefix, text);
}

function setWsStatus(state) {
  if (!debugStatus) return;
  debugStatus.className = state; // 'open' | 'closed' | 'connecting'
}

// ── Core helpers ──────────────────────────────────────────────────────────────
function showPage(pageId) {
  document.querySelectorAll('.page').forEach(function (p) { p.classList.remove('active'); });
  var el = document.getElementById('page-' + pageId);
  if (el) el.classList.add('active');
  if (pageId === 'control') {
    renderGeneralInfo();
    renderIncomingRequests();
    renderNearby();
  }
  if (pageId === 'soundboard') {
    document.getElementById('conversation-title').textContent =
      app.connectedPeerName ? (app.connectedPeerName + "'s Conversation") : 'Conversation';
    renderMessages();
  }
}

function toast(msg, isError) {
  var t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.toggle('error', !!isError);
  t.classList.add('show');
  setTimeout(function () { t.classList.remove('show'); }, 3000);
}

function send(cmd) {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    var stateLabel = ws ? ['CONNECTING','OPEN','CLOSING','CLOSED'][ws.readyState] : 'null';
    dbg('error', 'send() called but WS is not OPEN (state=' + stateLabel + ')');
    toast('Not connected to server', true);
    return;
  }
  var payload = JSON.stringify(cmd);
  ws.send(payload);
  dbg('sent', payload);
}

// ── Render helpers ────────────────────────────────────────────────────────────
function renderGeneralInfo() {
  var info = app.carInfo;
  document.getElementById('general-plate').textContent = info.plate || '—';
  document.getElementById('general-car').textContent   = [info.model, info.color].filter(Boolean).join(' ') || '—';
  var statusEl = document.getElementById('general-status');
  statusEl.textContent = app.state || '—';
  statusEl.className   = app.state === 'connected' ? 'status-active' : '';
}

function renderIncomingRequests() {
  var container = document.getElementById('incoming-requests-container');
  if (!app.incomingRequests.length) {
    container.innerHTML = '<div class="request-item"><span style="color:#888">No pending requests</span></div>';
    return;
  }
  container.innerHTML = app.incomingRequests.map(function (r) {
    var label = [r.owner, r.plate, r.color].filter(Boolean).join(' ') || r.plate || r.car_id;
    return '<div class="request-item">' +
      '<span>' + label + '</span>' +
      '<div class="request-actions">' +
      '<button type="button" class="btn-deny"   title="Reject" data-car-id="' + r.car_id + '">✕</button>' +
      '<button type="button" class="btn-accept" title="Accept" data-car-id="' + r.car_id + '">✓</button>' +
      '</div></div>';
  }).join('');
  container.querySelectorAll('.btn-accept').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var carId = btn.getAttribute('data-car-id');
      send({ type: 'acceptConnection', payload: { car_id: carId } });
      app.incomingRequests = app.incomingRequests.filter(function (r) { return r.car_id !== carId; });
      var peer = app.nearby.find(function (c) { return c.car_id === carId; }) || {};
      app.connectedPeerName = peer.owner || peer.plate || carId;
      app.connectedCarId    = carId;
      showPage('soundboard');
    });
  });
  container.querySelectorAll('.btn-deny').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var carId = btn.getAttribute('data-car-id');
      send({ type: 'rejectConnection', payload: { car_id: carId } });
      app.incomingRequests = app.incomingRequests.filter(function (r) { return r.car_id !== carId; });
      renderIncomingRequests();
    });
  });
}

function renderNearby() {
  var container = document.getElementById('nearby-list-container');
  if (!app.nearby.length) {
    container.innerHTML = '<div class="connection-item"><span style="color:#888">No cars nearby — try scanning</span></div>';
    return;
  }
  container.innerHTML = app.nearby.map(function (c) {
    var label = [c.owner, c.plate, c.color].filter(Boolean).join(' ') || c.plate || c.car_id;
    return '<div class="connection-item">' +
      '<span>' + label + '</span>' +
      '<button type="button" class="btn-link" title="Connect" data-car-id="' + c.car_id + '">⎋</button>' +
      '</div>';
  }).join('');
  container.querySelectorAll('.btn-link').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var carId = btn.getAttribute('data-car-id');
      send({ type: 'connect', payload: { car_id: carId } });
    });
  });
}

function renderMessages() {
  var container = document.getElementById('conversation-messages');
  if (!app.messages.length) { container.innerHTML = ''; return; }
  container.innerHTML = app.messages.map(function (m) {
    return '<div class="message-bubble">' + (m.text || m.kind) + '</div>';
  }).join('');
  container.scrollTop = container.scrollHeight;
}

// ── WebSocket event handling ──────────────────────────────────────────────────
function onMessage(ev) {
  dbg('recv', ev.data);
  var event;
  try {
    event = JSON.parse(ev.data);
  } catch (e) {
    dbg('error', 'JSON parse failed: ' + e.message);
    return;
  }
  var t = event.type;
  var p = event.payload || {};

  switch (t) {
    case 'init':
      app.carInfo          = p.info || {};
      app.state            = p.state || '';
      app.nearby           = p.nearby || [];
      app.incomingRequests = [];
      renderGeneralInfo();
      renderIncomingRequests();
      renderNearby();
      break;
    case 'infoUpdated':
      app.carInfo = Object.assign({}, app.carInfo, p);
      renderGeneralInfo();
      break;
    case 'nearbyList':
      app.nearby = p.cars || [];
      renderNearby();
      break;
    case 'carDiscovered':
    case 'carInfoUpdated': {
      var cid = p.car_id;
      var idx = app.nearby.findIndex(function (c) { return c.car_id === cid; });
      var entry = { car_id: cid, plate: p.plate, color: p.color, model: p.model, owner: p.owner };
      if (idx >= 0) app.nearby[idx] = Object.assign({}, app.nearby[idx], entry);
      else app.nearby.push(entry);
      renderNearby();
      break;
    }
    case 'connectionRequest':
      app.incomingRequests.push({ car_id: p.car_id, plate: p.plate, owner: p.owner, color: p.color });
      renderIncomingRequests();
      break;
    case 'connectionAccepted': {
      app.connectedCarId = p.car_id;
      app.state          = 'connected';
      var peer = app.nearby.find(function (c) { return c.car_id === p.car_id; });
      app.connectedPeerName = peer ? (peer.owner || peer.plate || p.car_id) : p.car_id;
      showPage('soundboard');
      break;
    }
    case 'connectionRejected':
    case 'disconnected':
      app.connectedCarId    = null;
      app.connectedPeerName = '';
      app.state             = (t === 'disconnected' ? '' : app.state);
      renderGeneralInfo();
      break;
    case 'peerDisconnected':
      app.connectedCarId    = null;
      app.connectedPeerName = '';
      app.state             = '';
      toast('Peer disconnected');
      showPage('control');
      break;
    case 'messageReceived':
      if (p.kind === 'text' && p.text) {
        app.messages.push({ text: p.text, from: p.car_id });
        renderMessages();
      }
      break;
    case 'error':
      dbg('error', 'Server error: ' + (p.message || JSON.stringify(p)));
      toast(p.message || 'Error', true);
      break;
    default:
      dbg('info', 'Unhandled event type: ' + t);
      break;
  }
}

// ── WebSocket lifecycle ───────────────────────────────────────────────────────
function connect() {
  if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) {
    dbg('info', 'connect() called but already connecting/open');
    return;
  }
  dbg('info', 'Opening WebSocket → ' + wsUrl);
  setWsStatus('connecting');
  ws = new WebSocket(wsUrl);

  ws.onopen = function () {
    setWsStatus('open');
    dbg('info', 'WebSocket OPEN  (' + wsUrl + ')');
    toast('Connected');
  };
  ws.onclose = function (e) {
    setWsStatus('closed');
    dbg('error', 'WebSocket CLOSED  code=' + e.code + '  reason="' + (e.reason || 'none') + '"  wasClean=' + e.wasClean);
    toast('Disconnected', true);
  };
  ws.onerror = function (e) {
    setWsStatus('closed');
    // Note: the browser doesn't give us details in onerror for security reasons.
    // Check: is the server running? Is the URL correct? Any CORS/mixed-content issue?
    dbg('error', 'WebSocket ERROR  – check server is running at ' + wsUrl);
    toast('Connection error', true);
  };
  ws.onmessage = onMessage;
}

// ── Login form ────────────────────────────────────────────────────────────────
var formInputs = document.querySelectorAll('#page-login .form-row input');
var btnConfirm = document.querySelector('.btn-confirm');

function allFieldsFilled() {
  return Array.from(formInputs).every(function (input) { return input.value.trim() !== ''; });
}
function updateConfirmState() {
  btnConfirm.disabled = !allFieldsFilled();
  formInputs.forEach(function (input) {
    input.classList.toggle('field-error', input.value.trim() === '');
  });
}
formInputs.forEach(function (input) {
  input.addEventListener('input', updateConfirmState);
  input.addEventListener('blur',  updateConfirmState);
});
updateConfirmState();

btnConfirm.addEventListener('click', function () {
  if (!allFieldsFilled()) return;
  var owner = document.getElementById('name').value.trim();
  var model = document.getElementById('car-model').value.trim();
  var color = document.getElementById('car-colour').value.trim();
  var plate = document.getElementById('license').value.trim();

  connect();

  function doSubmit() {
    if (ws && ws.readyState === WebSocket.OPEN) {
      send({ type: 'changeInfo', payload: { owner: owner, model: model, color: color, plate: plate } });
      showPage('control');
      send({ type: 'getInfo',    payload: {} });
      send({ type: 'scan',       payload: {} });
      send({ type: 'getNearby',  payload: {} });
    } else {
      dbg('info', 'Waiting for WS to open before submitting… (readyState=' + (ws ? ws.readyState : 'null') + ')');
      setTimeout(doSubmit, 100);
    }
  }
  setTimeout(doSubmit, 100);
});

// ── Control panel: refresh nearby ─────────────────────────────────────────────
document.getElementById('btn-refresh-nearby').addEventListener('click', function () {
  send({ type: 'getNearby', payload: {} });
  send({ type: 'beacon',    payload: {} });
});

document.getElementById('btn-edit-profile').addEventListener('click', function () {
  document.getElementById('name').value        = app.carInfo.owner || '';
  document.getElementById('car-model').value   = app.carInfo.model || '';
  document.getElementById('car-colour').value  = app.carInfo.color || '';
  document.getElementById('license').value     = app.carInfo.plate || '';
  showPage('login');
});

// ── Soundboard: phrase buttons → sendText ─────────────────────────────────────
document.querySelectorAll('.soundboard-grid button').forEach(function (btn) {
  btn.addEventListener('click', function () {
    var text = btn.textContent.trim();
    if (text) send({ type: 'sendText', payload: { text: text.slice(0, 26) } });
  });
});

document.getElementById('btn-send-chat').addEventListener('click', function () {
  var input = document.getElementById('chat-input');
  var text  = input.value.trim();
  if (!text) return;
  send({ type: 'sendText', payload: { text: text.slice(0, 26) } });
  input.value = '';
});
document.getElementById('chat-input').addEventListener('keydown', function (e) {
  if (e.key === 'Enter') document.getElementById('btn-send-chat').click();
});

document.getElementById('btn-disconnect').addEventListener('click', function () {
  send({ type: 'disconnect', payload: {} });
  app.connectedCarId    = null;
  app.connectedPeerName = '';
  app.messages          = [];
  showPage('login');
});

// ── Boot ──────────────────────────────────────────────────────────────────────
initDebugPanel();
connect();
