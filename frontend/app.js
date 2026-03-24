(function () {
  const $ = (sel) => document.querySelector(sel);

  const dropZone     = $('#drop-zone');
  const fileInput    = $('#file-input');
  const selectedFile = $('#selected-file');
  const fileName     = $('#file-name');
  const fileSize     = $('#file-size');
  const uploadBtn    = $('#upload-btn');
  const sourceLang   = $('#source-lang');
  const targetLang   = $('#target-lang');

  const uploadSection   = $('#upload-section');
  const progressSection = $('#progress-section');
  const resultSection   = $('#result-section');
  const errorSection    = $('#error-section');

  const progressBar      = $('#progress-bar');
  const progressPct      = $('#progress-pct');
  const progressFilename = $('#progress-filename');
  const statusLabel      = $('#status-label');
  const chunkInfo        = $('#chunk-info');
  const cancelBtn        = $('#cancel-btn');

  const previewBtn      = $('#preview-btn');
  const downloadHtmlBtn = $('#download-html-btn');
  const downloadMdBtn   = $('#download-md-btn');
  const downloadTexBtn  = $('#download-tex-btn');
  const downloadPdfBtn  = $('#download-pdf-btn');

  const errorSummaryEl = $('#error-summary');
  const errorDetailsEl = $('#error-details');
  const errorDetailPre = $('#error-detail-pre');

  const historyList = $('#history-list');

  let selectedFileObj = null;
  let pollInterval = null;
  let currentJobId = null;

  // ── Helpers ──────────────────────────────────────────────

  function formatBytes(bytes) {
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1024 / 1024).toFixed(1) + ' MB';
  }

  function formatDate(iso) {
    if (!iso) return '';
    const d = new Date(iso + 'Z');
    return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit' });
  }

  // ── Sections ─────────────────────────────────────────────

  function showSection(name) {
    [uploadSection, progressSection, resultSection, errorSection]
      .forEach(s => s.classList.add('hidden'));
    if (name === 'upload')   uploadSection.classList.remove('hidden');
    if (name === 'progress') progressSection.classList.remove('hidden');
    if (name === 'result')   resultSection.classList.remove('hidden');
    if (name === 'error')    errorSection.classList.remove('hidden');
  }

  function resetToUpload() {
    stopPolling();
    currentJobId = null;
    localStorage.removeItem('lastJobId');
    selectedFileObj = null;
    selectedFile.classList.add('hidden');
    uploadBtn.disabled = true;
    fileInput.value = '';
    _lastProgress = 0;
    _heartbeatTarget = 0;
    showSection('upload');
  }

  // ── File selection ────────────────────────────────────────

  function handleFile(file) {
    if (!file || !file.name.toLowerCase().endsWith('.pdf')) {
      alert('请选择PDF文件'); return;
    }
    selectedFileObj = file;
    fileName.textContent = file.name;
    fileSize.textContent = formatBytes(file.size);
    selectedFile.classList.remove('hidden');
    uploadBtn.disabled = false;
  }

  fileInput.addEventListener('change', () => fileInput.files[0] && handleFile(fileInput.files[0]));
  dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('dragover'); });
  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
  dropZone.addEventListener('drop', e => {
    e.preventDefault(); dropZone.classList.remove('dragover');
    e.dataTransfer.files[0] && handleFile(e.dataTransfer.files[0]);
  });
  dropZone.addEventListener('click', () => fileInput.click());

  // ── Upload ────────────────────────────────────────────────

  uploadBtn.addEventListener('click', async () => {
    if (!selectedFileObj) return;
    uploadBtn.disabled = true;
    const form = new FormData();
    form.append('file', selectedFileObj);
    form.append('source_lang', sourceLang.value);
    form.append('target_lang', targetLang.value);
    try {
      const res = await fetch('/api/upload', { method: 'POST', body: form });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || '上传失败');
      }
      const { job_id } = await res.json();
      localStorage.setItem('lastJobId', job_id);
      startJob(job_id);
    } catch (err) {
      alert('上传出错：' + err.message);
      uploadBtn.disabled = false;
    }
  });

  // ── Cancel ────────────────────────────────────────────────

  cancelBtn.addEventListener('click', async () => {
    if (!currentJobId) return;
    if (!confirm('确认取消当前翻译任务？')) return;
    try {
      const res = await fetch(`/api/jobs/${currentJobId}`, { method: 'DELETE' });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        alert('取消失败：' + (err.detail || '未知错误'));
        return;
      }
    } catch (_) {}
    stopPolling();
    loadHistory();
    resetToUpload();
  });

  // ── Polling ───────────────────────────────────────────────

  function stopPolling() {
    if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
  }

  function startJob(jobId) {
    currentJobId = jobId;
    _lastProgress = 0;
    _heartbeatTarget = 0;
    showSection('progress');
    stopPolling();
    pollInterval = setInterval(() => pollJob(jobId), 2500);
    pollJob(jobId);
  }

  async function pollJob(jobId) {
    try {
      const res = await fetch(`/api/jobs/${jobId}`);
      if (!res.ok) return;
      const job = await res.json();
      updateProgress(job);
      if (job.status === 'done' || job.status === 'error' || job.status === 'cancelled') {
        stopPolling();
        loadHistory();
        if (job.status === 'done') showResult(job);
        else showError(job.error_summary || '未知错误', job.error_detail || '');
      }
    } catch (_) {}
  }

  let _lastProgress = 0;
  let _heartbeatTarget = 0;

  function updateProgress(job) {
    if (job.progress > _lastProgress) {
      _lastProgress = job.progress;
      _heartbeatTarget = 0;
      progressBar.style.width = job.progress + '%';
      progressPct.textContent = job.progress + '%';
    } else if (job.status === 'translating' || job.status === 'ocr' || job.status === 'validating') {
      const ceiling = Math.min(_lastProgress + 20, 85);
      _heartbeatTarget = Math.min((_heartbeatTarget || _lastProgress) + 0.3, ceiling);
      progressBar.style.width = _heartbeatTarget.toFixed(1) + '%';
      progressPct.textContent = Math.floor(_heartbeatTarget) + '%';
    }
    statusLabel.textContent = job.status_label || job.status;
    if (job.filename) progressFilename.textContent = '📄 ' + job.filename;
    chunkInfo.textContent = job.total_chunks > 0
      ? `第 ${job.current_chunk} / ${job.total_chunks} 批` : '处理中…';
  }

  function showResult(job) {
    const jobId = job.job_id || job;
    showSection('result');
    previewBtn.href      = `/api/preview/${jobId}`;
    downloadHtmlBtn.href = `/api/download/${jobId}/html`;
    downloadMdBtn.href   = `/api/download/${jobId}/md`;
    downloadTexBtn.href  = `/api/download/${jobId}/tex`;

    // 仅在 PDF 编译成功时显示 PDF 下载按钮
    if (job.has_pdf) {
      downloadPdfBtn.href = `/api/download/${jobId}/pdf`;
      downloadPdfBtn.classList.remove('hidden');
    } else {
      downloadPdfBtn.classList.add('hidden');
    }
  }

  function showError(summary, detail) {
    showSection('error');
    errorSummaryEl.textContent = summary;
    if (detail) {
      errorDetailPre.textContent = detail;
      errorDetailsEl.classList.remove('hidden');
    } else {
      errorDetailsEl.classList.add('hidden');
    }
  }

  // ── New task buttons ──────────────────────────────────────

  ['#new-task-btn', '#new-task-btn2', '#new-task-btn3', '#retry-btn'].forEach(sel => {
    const el = $(sel);
    if (el) el.addEventListener('click', resetToUpload);
  });

  // ── History ───────────────────────────────────────────────

  async function loadHistory() {
    try {
      const res = await fetch('/api/jobs');
      if (!res.ok) return;
      const jobs = await res.json();
      renderHistory(jobs);
    } catch (_) {}
  }

  const FILE_ICON = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>`;

  function renderHistory(jobs) {
    if (!jobs.length) {
      historyList.innerHTML = '<p class="history-empty">暂无历史任务</p>';
      return;
    }
    historyList.innerHTML = jobs.map(job => {
      const isActive = !['done', 'error', 'cancelled'].includes(job.status);
      const statusClass = job.status === 'done' ? 'status-done'
        : job.status === 'error' ? 'status-error' : 'status-active';
      const name = job.filename || `${job.source_lang_label} → ${job.target_lang === 'zh' ? '中文' : '英语'}`;
      const sub  = `${job.source_lang_label} → ${job.target_lang === 'zh' ? '中文' : '英语'} · ${formatDate(job.created_at)} · ${job.job_id.slice(0, 8)}`;

      let actions = '';
      if (job.status === 'done') {
        actions = `
          <a href="/api/preview/${job.job_id}" target="_blank" class="btn-sm btn-primary">预览</a>
          <a href="/api/download/${job.job_id}/html" class="btn-sm btn-secondary">HTML</a>
          <a href="/api/download/${job.job_id}/md" class="btn-sm btn-secondary">MD</a>
          <a href="/api/download/${job.job_id}/tex" class="btn-sm btn-secondary">.tex</a>
          ${job.has_pdf ? `<a href="/api/download/${job.job_id}/pdf" class="btn-sm btn-secondary">PDF</a>` : ''}`;
      } else if (job.status === 'error') {
        actions = `<button class="btn-sm btn-secondary" onclick="resumeJob('${job.job_id}')">查看错误</button>`;
      } else if (job.status === 'cancelled') {
        actions = '';
      } else {
        actions = `<button class="btn-sm btn-primary" onclick="resumeJob('${job.job_id}')">查看进度</button>`;
      }

      return `
        <div class="history-item ${isActive ? 'history-active' : ''}">
          <div class="history-file-icon">${FILE_ICON}</div>
          <div class="history-info">
            <div class="history-name">${name}</div>
            <div class="history-sub">${sub}</div>
          </div>
          <div class="history-right">
            <span class="history-status ${statusClass}">${job.status_label}</span>
            <div class="history-actions">${actions}</div>
          </div>
        </div>`;
    }).join('');
  }

  window.resumeJob = function(jobId) {
    localStorage.setItem('lastJobId', jobId);
    startJob(jobId);
  };

  $('#refresh-history-btn').addEventListener('click', loadHistory);

  // ── Restore last job on page load ─────────────────────────

  async function restoreLastJob() {
    const jobId = localStorage.getItem('lastJobId');
    if (!jobId) return;
    try {
      const res = await fetch(`/api/jobs/${jobId}`);
      if (!res.ok) return;
      const job = await res.json();
      if (job.status === 'done') {
        showResult(job);
      } else if (job.status === 'error') {
        showError(job.error_summary || '未知错误', job.error_detail || '');
      } else if (job.status === 'cancelled') {
        // 已取消，不恢复
      } else {
        startJob(jobId);
      }
    } catch (_) {}
  }

  // ── Init ──────────────────────────────────────────────────

  loadHistory();
  restoreLastJob();
})();
