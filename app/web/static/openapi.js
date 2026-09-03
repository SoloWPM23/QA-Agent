const elements = {
  lmStudioUrl: document.getElementById('lmStudioUrl'),
  lmModel: document.getElementById('lmModel'),
  openapiFile: document.getElementById('openapiFile'),
  fileName: document.getElementById('fileName'),
  fileError: document.getElementById('fileError'),
  convertBtn: document.getElementById('convertBtn'),
  progressPanel: document.getElementById('progressPanel'),
  resultPanel: document.getElementById('resultPanel'),
  downloadBtn: document.getElementById('downloadBtn'),
  status: document.getElementById('status'),
};

function setStatus(message, type = 'info') {
  elements.status.textContent = message;
  elements.status.className = `status ${type}`;
  elements.status.classList.remove('hidden');
}

function hideStatus() {
  elements.status.classList.add('hidden');
  elements.status.textContent = '';
}

function showFieldError(element, message) {
  if (!element) {
    return;
  }
  element.textContent = message;
  element.classList.remove('hidden');
}

function hideFieldError(element) {
  if (!element) {
    return;
  }
  element.textContent = '';
  element.classList.add('hidden');
}

function validateForm() {
  let valid = true;

  if (!elements.openapiFile.files || elements.openapiFile.files.length === 0) {
    showFieldError(elements.fileError, 'File OpenAPI wajib dipilih.');
    valid = false;
  } else {
    hideFieldError(elements.fileError);
  }

  if (!elements.lmStudioUrl.value.trim() || !elements.lmModel.value.trim()) {
    setStatus('Base URL dan model name LM Studio wajib diisi.', 'error');
    valid = false;
  } else {
    hideStatus();
  }

  elements.convertBtn.disabled = !valid;
  return valid;
}

async function handleConvert() {
  if (!validateForm()) {
    return;
  }

  elements.resultPanel.classList.add('hidden');
  elements.convertBtn.disabled = true;
  elements.progressPanel.classList.remove('hidden');
  setStatus('Mengkonversi OpenAPI menjadi test suite...', 'info');

  const formData = new FormData();
  formData.append('file', elements.openapiFile.files[0]);
  formData.append('lm_studio_url', elements.lmStudioUrl.value.trim());
  formData.append('lm_model', elements.lmModel.value.trim());

  try {
    const response = await fetch('/api/convert-openapi', {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || `HTTP ${response.status}`);
    }

    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const filename = response.headers.get('content-disposition')?.split('filename=')[1]?.replace(/"/g, '') || 'test-suite.docx';

    elements.downloadBtn.href = url;
    elements.downloadBtn.download = filename;
    elements.resultPanel.classList.remove('hidden');
    setStatus('Konversi selesai.', 'success');
  } catch (err) {
    setStatus(`Gagal mengkonversi: ${err.message}`, 'error');
  } finally {
    elements.convertBtn.disabled = false;
    elements.progressPanel.classList.add('hidden');
  }
}

elements.convertBtn.addEventListener('click', handleConvert);
elements.openapiFile.addEventListener('change', () => {
  const file = elements.openapiFile.files[0];
  elements.fileName.textContent = file ? file.name : 'Belum ada file dipilih';
  validateForm();
});
elements.lmStudioUrl.addEventListener('input', validateForm);
elements.lmModel.addEventListener('input', validateForm);

validateForm();
