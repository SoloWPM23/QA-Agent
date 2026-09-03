const elements = {
  lmStudioUrl: document.getElementById('lmStudioUrl'),
  lmModel: document.getElementById('lmModel'),
  testConnectionBtn: document.getElementById('testConnectionBtn'),
  connectionStatus: document.getElementById('connectionStatus'),
  baseUrl: document.getElementById('baseUrl'),
  baseUrlError: document.getElementById('baseUrlError'),
  authType: document.getElementById('authType'),
  authFields: document.getElementById('authFields'),
  file: document.getElementById('file'),
  fileName: document.getElementById('fileName'),
  fileError: document.getElementById('fileError'),
  runBtn: document.getElementById('runBtn'),
  progressPanel: document.getElementById('progressPanel'),
  currentCase: document.getElementById('currentCase'),
  progressFill: document.getElementById('progressFill'),
  resultPanel: document.getElementById('resultPanel'),
  summaryTotal: document.getElementById('summaryTotal'),
  summaryPass: document.getElementById('summaryPass'),
  summaryFail: document.getElementById('summaryFail'),
  summarySkip: document.getElementById('summarySkip'),
  verdictList: document.getElementById('verdictList'),
  downloadBtn: document.getElementById('downloadBtn'),
  status: document.getElementById('status'),
};

const AUTH_TEMPLATES = {
  basic: `
    <div class="form-row">
      <div class="form-group">
        <label for="username">Username</label>
        <input type="text" id="username" name="username" autocomplete="off">
        <div id="usernameError" class="field-error hidden"></div>
      </div>
      <div class="form-group">
        <label for="password">Password</label>
        <input type="password" id="password" name="password" autocomplete="off">
        <div id="passwordError" class="field-error hidden"></div>
      </div>
    </div>
  `,
  bearer: `
    <div class="form-group">
      <label for="token">Token</label>
      <input type="password" id="token" name="token" autocomplete="off">
      <div id="tokenError" class="field-error hidden"></div>
    </div>
  `,
  api_key: `
    <div class="form-row">
      <div class="form-group">
        <label for="api_key_header">Nama Header</label>
        <input type="text" id="api_key_header" name="api_key_header" value="X-API-Key" autocomplete="off">
        <div id="api_key_headerError" class="field-error hidden"></div>
      </div>
      <div class="form-group">
        <label for="api_key_value">Nilai API Key</label>
        <input type="password" id="api_key_value" name="api_key_value" autocomplete="off">
        <div id="api_key_valueError" class="field-error hidden"></div>
      </div>
    </div>
  `,
};

function renderAuthFields() {
  const type = elements.authType.value;
  elements.authFields.innerHTML = AUTH_TEMPLATES[type] || '';
  attachAuthListeners();
  updateRunButtonState();
}

function showFieldError(element, message) {
  if (!element) {
    return;
  }
  element.textContent = message;
  element.classList.remove('hidden');
  const input = element.previousElementSibling;
  if (input && (input.tagName === 'INPUT' || input.tagName === 'SELECT')) {
    input.classList.add('invalid');
  }
}

function hideFieldError(element) {
  if (!element) {
    return;
  }
  element.textContent = '';
  element.classList.add('hidden');
  const input = element.previousElementSibling;
  if (input && (input.tagName === 'INPUT' || input.tagName === 'SELECT')) {
    input.classList.remove('invalid');
  }
}

function isValidUrl(value) {
  try {
    new URL(value);
    return true;
  } catch {
    return false;
  }
}

function validateBaseUrl() {
  const value = elements.baseUrl.value.trim();
  if (!value) {
    showFieldError(elements.baseUrlError, 'Base URL target API wajib diisi.');
    return false;
  }
  if (!isValidUrl(value)) {
    showFieldError(elements.baseUrlError, 'Format URL tidak valid.');
    return false;
  }
  hideFieldError(elements.baseUrlError);
  return true;
}

function validateAuth() {
  const type = elements.authType.value;
  if (type === 'none') {
    return true;
  }
  if (type === 'basic') {
    const username = document.getElementById('username');
    const password = document.getElementById('password');
    const usernameError = document.getElementById('usernameError');
    const passwordError = document.getElementById('passwordError');
    let valid = true;
    if (!username || !username.value.trim()) {
      showFieldError(usernameError, 'Username wajib diisi.');
      valid = false;
    } else {
      hideFieldError(usernameError);
    }
    if (!password || !password.value.trim()) {
      showFieldError(passwordError, 'Password wajib diisi.');
      valid = false;
    } else {
      hideFieldError(passwordError);
    }
    return valid;
  }
  if (type === 'bearer') {
    const token = document.getElementById('token');
    const tokenError = document.getElementById('tokenError');
    if (!token || !token.value.trim()) {
      showFieldError(tokenError, 'Token wajib diisi.');
      return false;
    }
    hideFieldError(tokenError);
    return true;
  }
  if (type === 'api_key') {
    const header = document.getElementById('api_key_header');
    const value = document.getElementById('api_key_value');
    const headerError = document.getElementById('api_key_headerError');
    const valueError = document.getElementById('api_key_valueError');
    let valid = true;
    if (!header || !header.value.trim()) {
      showFieldError(headerError, 'Nama header wajib diisi.');
      valid = false;
    } else {
      hideFieldError(headerError);
    }
    if (!value || !value.value.trim()) {
      showFieldError(valueError, 'Nilai API key wajib diisi.');
      valid = false;
    } else {
      hideFieldError(valueError);
    }
    return valid;
  }
  return true;
}

function validateFile() {
  if (!elements.file.files || elements.file.files.length === 0) {
    showFieldError(elements.fileError, 'Dokumen test suite wajib dipilih.');
    return false;
  }
  hideFieldError(elements.fileError);
  return true;
}

function updateRunButtonState() {
  const baseOk = validateBaseUrl();
  const authOk = validateAuth();
  const fileOk = validateFile();
  elements.runBtn.disabled = !(baseOk && authOk && fileOk);
}

function setStatus(message, type = 'info') {
  elements.status.textContent = message;
  elements.status.className = `status ${type}`;
  elements.status.classList.remove('hidden');
}

function hideStatus() {
  elements.status.classList.add('hidden');
  elements.status.textContent = '';
}

function showConnectionStatus(message, ok) {
  elements.connectionStatus.textContent = message;
  elements.connectionStatus.className = `connection-status ${ok ? 'ok' : 'error'}`;
  elements.connectionStatus.classList.remove('hidden');
}

function attachAuthListeners() {
  const inputs = elements.authFields.querySelectorAll('input');
  inputs.forEach((input) => {
    input.addEventListener('input', updateRunButtonState);
  });
}

async function testConnection() {
  const url = elements.lmStudioUrl.value.trim();
  const model = elements.lmModel.value.trim();

  if (!url || !model) {
    showConnectionStatus('Base URL dan model name wajib diisi.', false);
    return;
  }

  elements.testConnectionBtn.disabled = true;
  showConnectionStatus('Menghubungi LM Studio...', true);

  const formData = new FormData();
  formData.append('lm_studio_url', url);
  formData.append('lm_model', model);

  try {
    const response = await fetch('/api/test-connection', {
      method: 'POST',
      body: formData,
    });
    if (response.ok) {
      showConnectionStatus('LM Studio terhubung.', true);
    } else {
      const text = await response.text();
      showConnectionStatus(`Gagal: ${text}`, false);
    }
  } catch (err) {
    showConnectionStatus(`Error: ${err.message}`, false);
  } finally {
    elements.testConnectionBtn.disabled = false;
  }
}

async function pollResult(jobId) {
  const response = await fetch(`/api/result/${jobId}`);
  if (!response.ok) {
    setStatus('Gagal membaca status job.', 'error');
    updateRunButtonState();
    elements.progressPanel.classList.add('hidden');
    return;
  }

  const job = await response.json();

  if (job.current_case) {
    elements.currentCase.textContent = job.current_case;
  }

  if (job.status === 'queued' || job.status === 'running') {
    elements.progressFill.style.width = '60%';
    setTimeout(() => pollResult(jobId), 1200);
    return;
  }

  updateRunButtonState();
  elements.progressPanel.classList.add('hidden');

  if (job.status === 'done') {
    setStatus('Eksekusi selesai.', 'success');
    showResults(job);
  } else {
    setStatus(`Eksekusi gagal: ${job.error || 'Terjadi kesalahan'}`, 'error');
  }
}

function showResults(job) {
  const summary = job.summary || {};
  elements.summaryTotal.textContent = summary.total ?? 0;
  elements.summaryPass.textContent = summary.passed ?? 0;
  elements.summaryFail.textContent = summary.failed ?? 0;
  elements.summarySkip.textContent = summary.skipped ?? 0;

  elements.downloadBtn.href = `/api/reports/${job.job_id}.xlsx`;

  const verdicts = summary.verdicts || [];
  elements.verdictList.innerHTML = verdicts.map((v) => renderVerdictCard(v)).join('');

  elements.resultPanel.classList.remove('hidden');
  attachDetailToggles();
}

function renderVerdictCard(verdict) {
  const statusClass = verdict.status.toLowerCase();
  const detail = verdict.detail || {};
  const requestBody = formatJson(detail.request_body);
  const responseBody = formatJson(detail.response_body);

  let explanationHtml = '';
  if (verdict.status === 'FAIL' && verdict.explanation) {
    explanationHtml = `
      <div class="verdict-explanation">
        <div class="verdict-explanation-label">Penjelasan</div>
        <div>${escapeHtml(verdict.explanation)}</div>
      </div>
    `;
  }

  return `
    <div class="verdict-card ${statusClass}">
      <div class="verdict-header">
        <div>
          <h3 class="verdict-title">${escapeHtml(verdict.case_id)}${detail.title ? ` - ${escapeHtml(detail.title)}` : ''}</h3>
          <div class="verdict-meta">${escapeHtml(detail.method || '')} ${escapeHtml(detail.path || '')}</div>
        </div>
        <span class="verdict-badge ${statusClass}">${verdict.status}</span>
      </div>
      <div class="verdict-reason">${escapeHtml(verdict.reason || '')}</div>
      ${explanationHtml}
      <div class="verdict-detail">
        <button type="button" class="detail-toggle" data-case="${escapeHtml(verdict.case_id)}">Lihat Detail</button>
        <div class="detail-content" id="detail-${escapeHtml(verdict.case_id)}">
          <div class="detail-block">
            <div class="detail-block-label">Request Body</div>
            <pre>${requestBody}</pre>
          </div>
          <div class="detail-block">
            <div class="detail-block-label">Response Status</div>
            <pre>${escapeHtml(String(detail.response_status ?? '-'))}</pre>
          </div>
          <div class="detail-block">
            <div class="detail-block-label">Response Body</div>
            <pre>${responseBody}</pre>
          </div>
          <div class="detail-block">
            <div class="detail-block-label">Assertions</div>
            <pre>${renderAssertions(verdict.assertions)}</pre>
          </div>
        </div>
      </div>
    </div>
  `;
}

function renderAssertions(assertions) {
  if (!assertions || assertions.length === 0) {
    return '-';
  }
  return assertions.map((a) => {
    const status = a.passed ? 'PASS' : 'FAIL';
    return `[${status}] ${a.name}: expected=${a.expected}, actual=${a.actual}, ${a.details}`;
  }).join('\n');
}

function formatJson(value) {
  if (value === null || value === undefined) {
    return '-';
  }
  if (typeof value === 'string') {
    return escapeHtml(value);
  }
  return escapeHtml(JSON.stringify(value, null, 2));
}

function attachDetailToggles() {
  document.querySelectorAll('.detail-toggle').forEach((btn) => {
    btn.addEventListener('click', () => {
      const caseId = btn.dataset.case;
      const content = document.getElementById(`detail-${caseId}`);
      if (content) {
        content.classList.toggle('open');
        btn.textContent = content.classList.contains('open') ? 'Sembunyikan Detail' : 'Lihat Detail';
      }
    });
  });
}

function escapeHtml(text) {
  if (text === null || text === undefined) {
    return '';
  }
  const div = document.createElement('div');
  div.textContent = String(text);
  return div.innerHTML;
}

async function handleRun() {
  if (!validateBaseUrl() || !validateAuth() || !validateFile()) {
    updateRunButtonState();
    return;
  }

  elements.resultPanel.classList.add('hidden');
  elements.runBtn.disabled = true;
  elements.progressPanel.classList.remove('hidden');
  elements.progressFill.style.width = '10%';
  elements.currentCase.textContent = 'Memulai...';
  setStatus('Mengunggah file dan memulai job...', 'info');

  const formData = new FormData();
  formData.append('file', elements.file.files[0]);
  formData.append('base_url', elements.baseUrl.value.trim());
  formData.append('auth_type', elements.authType.value);
  formData.append('lm_studio_url', elements.lmStudioUrl.value.trim());
  formData.append('lm_model', elements.lmModel.value.trim());

  const authFields = elements.authFields.querySelectorAll('input');
  authFields.forEach((input) => {
    if (input.value) {
      formData.append(input.name, input.value);
    }
  });

  try {
    const response = await fetch('/api/run', {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || `HTTP ${response.status}`);
    }

    const data = await response.json();
    setStatus(`Job ${data.job_id} dimulai. Menunggu hasil...`, 'info');
    pollResult(data.job_id);
  } catch (err) {
    setStatus(`Gagal memulai job: ${err.message}`, 'error');
    updateRunButtonState();
    elements.progressPanel.classList.add('hidden');
  }
}

elements.authType.addEventListener('change', renderAuthFields);
elements.testConnectionBtn.addEventListener('click', testConnection);
elements.runBtn.addEventListener('click', handleRun);
elements.baseUrl.addEventListener('input', updateRunButtonState);
elements.file.addEventListener('change', () => {
  const file = elements.file.files[0];
  elements.fileName.textContent = file ? file.name : 'Belum ada file dipilih';
  updateRunButtonState();
});

renderAuthFields();
