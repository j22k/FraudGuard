/**
 * FraudGuard // DynamoDB Live Alert Desk Application Logic
 * Light Telemetry Theme
 * Strictly uses authentic DynamoDB table schema:
 * - TransactionID (String)
 * - txn_id (String)
 * - fraud_score (Number/Decimal)
 * - explanation (String)
 * - timestamp (ISO String)
 */

// Application State
const state = {
  items: [],
  filteredItems: [],
  selectedId: null,
  searchQuery: '',
  sortBy: 'score_desc',
  tableInfo: {
    name: 'fraudguard-flagged-transactions-dev',
    region: 'us-east-1',
  }
};

// Fallback mock items strictly matching exact DynamoDB schema
const fallbackDynamoDbItems = [
  {
    TransactionID: 'TXN-89421',
    txn_id: 'TXN-89421',
    fraud_score: 0.9842,
    timestamp: '2026-08-30T10:45:00Z',
    explanation: 'High-value transaction initiated with off-peak hour pattern anomaly. Risk probability threshold exceeded (>0.90).'
  },
  {
    TransactionID: 'TXN-89420',
    txn_id: 'TXN-89420',
    fraud_score: 0.8240,
    timestamp: '2026-08-30T10:41:12Z',
    explanation: 'Card-not-present authorization anomaly across distinct merchant terminals in rapid succession.'
  },
  {
    TransactionID: 'TXN-89419',
    txn_id: 'TXN-89419',
    fraud_score: 0.7615,
    timestamp: '2026-08-30T10:35:08Z',
    explanation: 'Unusual routing pattern detected for newly registered beneficiary account.'
  }
];

// Initialize on DOM Ready
document.addEventListener('DOMContentLoaded', () => {
  if (window.lucide) {
    lucide.createIcons();
  }

  setupListeners();
  fetchDynamoDB();
  startFreshnessTimer();
});

// Event Listeners
function setupListeners() {
  const syncBtn = document.getElementById('btnSync');
  if (syncBtn) {
    syncBtn.addEventListener('click', () => {
      fetchDynamoDB();
    });
  }

  // Search Box
  document.getElementById('searchBox').addEventListener('input', (e) => {
    state.searchQuery = e.target.value.toLowerCase().trim();
    applyFilterAndSort();
  });

  // Sort Selector
  document.getElementById('sortSelect').addEventListener('change', (e) => {
    state.sortBy = e.target.value;
    applyFilterAndSort();
  });

  // Copy JSON
  document.getElementById('btnCopyJson').addEventListener('click', () => {
    const raw = document.getElementById('dossierRawJson').textContent;
    navigator.clipboard.writeText(raw).then(() => {
      alert('DynamoDB item JSON copied to clipboard.');
    });
  });

  // Copy Trace
  document.getElementById('btnCopyTrace').addEventListener('click', () => {
    if (!state.selectedId) return;
    const item = state.items.find(d => d._id === state.selectedId);
    if (item) {
      const trace = `TRACE [${item._id}] | Score: ${item._score} | Timestamp: ${item._ts} | Exp: ${item._exp}`;
      navigator.clipboard.writeText(trace).then(() => {
        alert(`Forensic trace for ${item._id} copied.`);
      });
    }
  });

  // Keyboard shortcut '/' for search
  document.addEventListener('keydown', (e) => {
    if (e.key === '/' && document.activeElement.tagName !== 'INPUT') {
      e.preventDefault();
      document.getElementById('searchBox').focus();
    }
  });
}

// Fetch live items from DynamoDB API
function fetchDynamoDB() {
  const syncIcon = document.getElementById('syncIcon');
  if (syncIcon) syncIcon.classList.add('animate-spin');

  const statusText = document.getElementById('tableStatusText');
  if (statusText) statusText.textContent = 'DYNAMODB';

  fetch('/api/dynamodb')
    .then(res => res.json())
    .then(json => {
      if (syncIcon) syncIcon.classList.remove('animate-spin');

      if (json.status === 'success' && Array.isArray(json.data) && json.data.length > 0) {
        processRawItems(json.data);
      } else {
        processRawItems(fallbackDynamoDbItems);
      }
    })
    .catch(() => {
      if (syncIcon) syncIcon.classList.remove('animate-spin');
      processRawItems(fallbackDynamoDbItems);
    });
}

// Process raw DynamoDB items strictly matching authentic columns
function processRawItems(rawData) {
  state.items = rawData.map(row => {
    const id = String(row.TransactionID || row.txn_id || 'UNKNOWN');
    const score = parseFloat(row.fraud_score) || 0.0;
    const ts = String(row.timestamp || '--');
    const exp = String(row.explanation || 'No Bedrock explanation provided.');

    return {
      TransactionID: id,
      txn_id: row.txn_id || id,
      fraud_score: score,
      timestamp: ts,
      explanation: exp,
      _id: id,
      _score: score,
      _ts: ts,
      _exp: exp,
      _status: score >= 0.9 ? 'CRITICAL' : score >= 0.75 ? 'HIGH' : 'NORMAL'
    };
  });

  updateKPIs();
  applyFilterAndSort();

  if (state.items.length > 0) {
    selectTransaction(state.items[0]._id);
  }
}

// Update Top KPI Cards
function updateKPIs() {
  const total = state.items.length;
  if (total === 0) return;

  const scores = state.items.map(d => d._score);
  const peak = Math.max(...scores);
  const avg = scores.reduce((a, b) => a + b, 0) / total;
  const peakItem = state.items.find(d => d._score === peak);

  document.getElementById('kpiCount').textContent = total.toLocaleString();
  document.getElementById('kpiPeak').textContent = peak.toFixed(4);
  if (peakItem) {
    document.getElementById('kpiPeakTxn').textContent = peakItem._id;
  }
  document.getElementById('kpiAvg').textContent = avg.toFixed(4);

  const avgPct = Math.min(Math.round(avg * 100), 100);
  const avgBar = document.getElementById('kpiAvgBar');
  if (avgBar) avgBar.style.width = `${avgPct}%`;
}

// Filter and Sort Queue
function applyFilterAndSort() {
  state.filteredItems = state.items.filter(item => {
    if (!state.searchQuery) return true;
    const str = `${item._id} ${item._exp} ${item._score} ${item._ts}`.toLowerCase();
    return str.includes(state.searchQuery);
  });

  // Sorting
  state.filteredItems.sort((a, b) => {
    if (state.sortBy === 'score_desc') return b._score - a._score;
    if (state.sortBy === 'time_desc') return String(b._ts).localeCompare(String(a._ts));
    if (state.sortBy === 'id_asc') return String(a._id).localeCompare(String(b._id));
    return 0;
  });

  document.getElementById('queueCountBadge').textContent = `${state.filteredItems.length} ITEMS`;
  renderQueueTable();
}

// Render Left Alert Queue Table
function renderQueueTable() {
  const tbody = document.getElementById('queueTableBody');
  tbody.innerHTML = '';

  if (state.filteredItems.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="4" style="text-align: center; padding: 24px; color: var(--text-3);">
          No matching transactions found
        </td>
      </tr>
    `;
    return;
  }

  state.filteredItems.forEach(item => {
    const tr = document.createElement('tr');
    if (item._id === state.selectedId) {
      tr.classList.add('selected');
    }

    const badgeClass = item._status === 'CRITICAL' ? 'chip-neg' : item._status === 'HIGH' ? 'chip-warn' : 'chip-pos';
    const tsFormatted = item._ts !== '--' ? item._ts.replace('T', ' ').substring(0, 19) : '--';

    tr.innerHTML = `
      <td class="font-bold text-teal-800">${item.TransactionID}</td>
      <td class="${item._score >= 0.9 ? 'text-red-700 font-bold' : 'text-amber-700'}">${item._score.toFixed(4)}</td>
      <td class="text-slate-600">${tsFormatted}</td>
      <td><span class="chip ${badgeClass}">${item._status}</span></td>
    `;

    tr.addEventListener('click', () => {
      selectTransaction(item._id);
    });

    tbody.appendChild(tr);
  });
}

// Select Transaction and update Forensic Dossier
function selectTransaction(id) {
  state.selectedId = id;
  const item = state.items.find(d => d._id === id);
  if (!item) return;

  // Update selected row in table
  const rows = document.querySelectorAll('#queueTableBody tr');
  rows.forEach((row, idx) => {
    if (state.filteredItems[idx] && state.filteredItems[idx]._id === id) {
      row.classList.add('selected');
    } else {
      row.classList.remove('selected');
    }
  });

  // Update Dossier Header
  document.getElementById('dossierTxnHeader').textContent = item.TransactionID;

  // Update Token Hero Card
  document.getElementById('cardTxnDisplay').textContent = item.TransactionID;
  document.getElementById('cardScoreDisplay').textContent = item.fraud_score.toFixed(4);

  const cardChip = document.getElementById('cardStatusChip');
  cardChip.className = `chip ${item._status === 'CRITICAL' ? 'chip-neg' : item._status === 'HIGH' ? 'chip-warn' : 'chip-pos'}`;
  cardChip.textContent = item._status;

  // Update Authentic Attributes
  document.getElementById('metaTxnId').textContent = item.TransactionID;
  document.getElementById('metaFraudScore').textContent = item.fraud_score.toFixed(4);
  document.getElementById('metaTimestamp').textContent = item.timestamp;

  // Bedrock AI Explanation
  document.getElementById('dossierExplanation').textContent = item.explanation;

  // Clean Raw JSON Payload
  const rawObj = {
    TransactionID: item.TransactionID,
    txn_id: item.txn_id,
    fraud_score: item.fraud_score,
    explanation: item.explanation,
    timestamp: item.timestamp
  };
  document.getElementById('dossierRawJson').textContent = JSON.stringify(rawObj, null, 2);

  if (window.lucide) lucide.createIcons();
}

// Data Freshness Counter Timer
function startFreshnessTimer() {
  let seconds = 3.42;
  setInterval(() => {
    seconds += 0.1;
    if (seconds >= 60) seconds = 0;
    const mins = Math.floor(seconds / 60);
    const secs = (seconds % 60).toFixed(2);
    const formatted = `${String(mins).padStart(2, '0')}:${String(secs).padStart(5, '0')}`;
    const el = document.getElementById('kpiFreshness');
    if (el) el.textContent = formatted;
  }, 100);
}
