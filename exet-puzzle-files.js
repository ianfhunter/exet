/**
 * Load/save puzzles via the ipuz_files git submodule (backend API).
 */
const exetPuzzleFiles = (function() {
  let enabled = false;
  let panel = null;
  let mode = 'open'; // 'open' | 'save'
  /** Set when opening from ipuz_files: { kind, name, format } */
  let loadedSource = null;

  function formatFromName(name) {
    const lower = (name || '').toLowerCase();
    if (lower.endsWith('.puz')) return 'puz';
    if (lower.endsWith('.ipuz')) return 'ipuz';
    if (lower.endsWith('.json')) return 'json';
    return null;
  }

  function noteLoaded(name, kind) {
    const format = formatFromName(name);
    if (format) {
      loadedSource = {kind: kind, name: name, format: format};
    }
  }

  function clearLoadedSource() {
    loadedSource = null;
  }

  function defaultSaveFormat() {
    const fromFile = formatFromName(exet.exolveFile);
    if (fromFile) return fromFile;
    if (loadedSource && loadedSource.format) return loadedSource.format;
    return 'ipuz';
  }

  function defaultSaveFilename(fmt) {
    const ext = '.' + fmt;
    if (loadedSource && loadedSource.name) {
      return loadedSource.name.replace(/\.(puz|ipuz|json)$/i, '') + ext;
    }
    if (exet.exolveFile) {
      return exet.exolveFile.replace(/\.(puz|ipuz|json)$/i, '') + ext;
    }
    return defaultFilename(ext);
  }

  function baseUrl() {
    if (typeof exetConfig !== 'undefined' && exetConfig.dataServerUrl) {
      return String(exetConfig.dataServerUrl).replace(/\/$/, '');
    }
    return '';
  }

  function fetchJson(path, options) {
    return fetch(baseUrl() + path, options).then((r) => {
      return r.json().then((body) => {
        if (!r.ok) {
          const detail = body && body.detail ? body.detail : ('HTTP ' + r.status);
          throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
        }
        return body;
      });
    });
  }

  function probe() {
    return fetchJson('/api/puzzles/status').then((st) => {
      enabled = !!(st && st.ok);
      return enabled;
    }).catch(() => {
      enabled = false;
      return false;
    });
  }

  function isEnabled() {
    return enabled;
  }

  function bytesToBase64(bytes) {
    let binary = '';
    const chunk = 0x8000;
    for (let i = 0; i < bytes.length; i += chunk) {
      binary += String.fromCharCode.apply(
          null, bytes.subarray(i, Math.min(i + chunk, bytes.length)));
    }
    return btoa(binary);
  }

  function base64ToBytes(b64) {
    const binary = atob(b64);
    const out = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
      out[i] = binary.charCodeAt(i);
    }
    return out;
  }

  function defaultFilename(ext) {
    const title = exet.fileTitle();
    return 'exet-' + title + ext;
  }

  function buildJsonDump() {
    const exolve = exet.getExolve();
    const rev = {
      id: exet.puz.id,
      title: exet.puz.title || '',
      revNum: 0,
      revType: 0,
      timestamp: Date.now(),
      details: 'ipuz_files export',
      maxRevNum: 0,
      prefix: exet.prefix,
      suffix: exet.suffix,
      exolve: exolve,
      scratchPad: exet.puz.scratchPad ? exet.puz.scratchPad.value : '',
      navState: [exet.puz.currDir, exet.puz.currRow, exet.puz.currCol],
      preflexHash: exet.preflexHash,
      unpreflexHash: exet.unpreflexHash,
      noProperNouns: exet.noProperNouns,
      noStemDupes: exet.noStemDupes,
      region: exet.region,
      asymOK: exet.asymOK,
      tryReversals: exet.tryReversals,
      minpop: exet.minpop,
      minscore: exet.minscore,
      lexId: exetLexicon.id,
      requireEnums: exet.requireEnums,
      lightRegexps: exet.lightRegexps,
    };
    return JSON.stringify({
      format: 'exet-json',
      version: 1,
      exportedAt: new Date().toISOString(),
      id: exet.puz.id,
      rev: rev,
      preflex: exet.preflex,
      unpreflex: exet.unpreflex,
    }, null, 2);
  }

  function buildSaveContent(fmt) {
    if (fmt === 'puz') {
      const dotPuz = exolveToPuz(exet.puz);
      if (!dotPuz) {
        throw new Error('Could not build .puz file');
      }
      return bytesToBase64(dotPuz);
    }
    if (fmt === 'ipuz') {
      const ipuz = exolveToIpuz(exet.puz);
      if (!ipuz) {
        throw new Error('Could not build .ipuz file');
      }
      const enc = new TextEncoder();
      return bytesToBase64(enc.encode(ipuz));
    }
    if (fmt === 'json') {
      const enc = new TextEncoder();
      return bytesToBase64(enc.encode(buildJsonDump()));
    }
    throw new Error('Unknown format: ' + fmt);
  }

  function ensurePanel() {
    if (panel) {
      return panel;
    }
    panel = document.createElement('div');
    panel.id = 'xet-ipuz-files-panel';
    panel.className = 'xet-rev-chooser';
    panel.style.display = 'none';
    document.body.appendChild(panel);
    return panel;
  }

  function showLoading(msg) {
    exetModals.hide();
    exetModals.freezeUI(msg);
  }

  function hideLoading() {
    exetModals.unfreezeUI();
  }

  function renderLoading(msg) {
    showLoading(msg);
  }

  function renderError(msg) {
    ensurePanel().innerHTML =
        '<div class="xet-pad-top xet-red"><b>Error:</b> ' + msg +
        '<br><br><button class="xlv-small-button" id="xet-ipuz-close">Close</button></div>';
    document.getElementById('xet-ipuz-close').onclick = () => exetModals.hide();
  }

  function fileListHtml(kind, files) {
    if (!files || files.length === 0) {
      return '<p class="xet-smaller-text"><i>No files yet.</i></p>';
    }
    let html = '<table class="xet-choices"><tbody>';
    for (const f of files) {
      const when = f.modified ? new Date(f.modified).toLocaleString() : '';
      html += '<tr class="xet-ipuz-file-row" data-kind="' + kind +
              '" data-name="' + f.name + '">' +
              '<td><b>' + f.name + '</b>' +
              (when ? '<br><span class="xet-small-action">' + when + '</span>' : '') +
              '</td><td>' + exet.inMB(f.size / (1024 * 1024)) + ' MB</td></tr>';
    }
    html += '</tbody></table>';
    return html;
  }

  function renderOpenList(data) {
    const el = ensurePanel();
    el.innerHTML =
        '<div class="xet-pad-top">' +
        '<h3>Open from ipuz_files</h3>' +
        '<p class="xet-smaller-text">Synced from GitHub. Click a file to open.</p>' +
        '<h4>Drafts</h4>' +
        '<div class="xet-choices-box">' + fileListHtml('drafts', data.drafts) + '</div>' +
        '<h4>Puzzles</h4>' +
        '<div class="xet-choices-box">' + fileListHtml('puzzles', data.puzzles) + '</div>' +
        '<br><button class="xlv-small-button" id="xet-ipuz-close">Close</button>' +
        '</div>';
    document.getElementById('xet-ipuz-close').onclick = () => exetModals.hide();
    for (const row of el.querySelectorAll('.xet-ipuz-file-row')) {
      row.style.cursor = 'pointer';
      row.onclick = () => loadFile(row.dataset.kind, row.dataset.name);
    }
  }

  function renderSaveForm() {
    const el = ensurePanel();
    const fmt = defaultSaveFormat();
    const fname = defaultSaveFilename(fmt);
    const kind = (loadedSource && loadedSource.kind) || 'drafts';
    const fmtOptions = [
      {value: 'ipuz', label: 'IPUZ'},
      {value: 'puz', label: 'PUZ'},
      {value: 'json', label: 'JSON (Exet data dump)'},
    ];
    let fmtSelectHtml = '';
    for (const opt of fmtOptions) {
      fmtSelectHtml += '<option value="' + opt.value + '"' +
          (opt.value === fmt ? ' selected' : '') + '>' + opt.label + '</option>';
    }
    el.innerHTML =
        '<div class="xet-pad-top">' +
        '<h3>Save to ipuz_files</h3>' +
        '<p class="xet-smaller-text">Saved files are committed and pushed to GitHub.</p>' +
        '<div style="margin:8px 0">' +
        'Folder: ' +
        '<label><input type="radio" name="xet-ipuz-kind" value="drafts"' +
            (kind === 'drafts' ? ' checked' : '') + '> Draft</label> ' +
        '<label><input type="radio" name="xet-ipuz-kind" value="puzzles"' +
            (kind === 'puzzles' ? ' checked' : '') + '> Puzzle</label>' +
        '</div>' +
        '<div style="margin:8px 0">Format: ' +
        '<select id="xet-ipuz-format">' + fmtSelectHtml + '</select></div>' +
        '<div style="margin:8px 0">Filename:<br>' +
        '<input id="xet-ipuz-filename" type="text" size="40" value="' + fname + '"></div>' +
        '<div id="xet-ipuz-save-status"></div>' +
        '<button class="xlv-small-button" id="xet-ipuz-save-btn">Save &amp; push</button> ' +
        '<button class="xlv-small-button" id="xet-ipuz-close">Cancel</button>' +
        '</div>';
    const fmtSel = document.getElementById('xet-ipuz-format');
    const nameInp = document.getElementById('xet-ipuz-filename');
    fmtSel.onchange = () => {
      const ext = '.' + fmtSel.value;
      const base = nameInp.value.replace(/\.(puz|ipuz|json)$/i, '');
      nameInp.value = base + ext;
    };
    document.getElementById('xet-ipuz-close').onclick = () => exetModals.hide();
    document.getElementById('xet-ipuz-save-btn').onclick = () => saveCurrent();
  }

  function loadFile(kind, name) {
    showLoading('Loading ' + name + '…');
    fetchJson('/api/puzzles/file?kind=' + encodeURIComponent(kind) +
              '&name=' + encodeURIComponent(name))
        .then((resp) => {
          hideLoading();
          noteLoaded(name, kind);
          const bytes = base64ToBytes(resp.content_base64);
          exetLoadFromBytes(bytes, name);
        })
        .catch((err) => {
          hideLoading();
          exetModals.showModal(ensurePanel());
          renderError(err.message);
        });
  }

  function saveCurrent() {
    const kind = document.querySelector('input[name="xet-ipuz-kind"]:checked').value;
    const fmt = document.getElementById('xet-ipuz-format').value;
    let name = document.getElementById('xet-ipuz-filename').value.trim();
    if (!/\.(puz|ipuz|json)$/i.test(name)) {
      name = name + '.' + fmt;
    }
    const status = document.getElementById('xet-ipuz-save-status');
    status.innerHTML = xetSpinnerInlineHtml('Saving…');
    let contentB64;
    try {
      contentB64 = buildSaveContent(fmt);
    } catch (err) {
      status.innerHTML = '<span class="xet-red">' + err.message + '</span>';
      return;
    }
    fetchJson('/api/puzzles/save', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({kind: kind, name: name, content_base64: contentB64}),
    }).then((resp) => {
      loadedSource = {
        kind: kind,
        name: name,
        format: fmt,
      };
      exet.exolveFile = name;
      status.innerHTML = '<span class="xet-green">Saved ' + resp.path +
                         (resp.committed ? ' and pushed' : ' (unchanged, pushed)') +
                         '</span>';
    }).catch((err) => {
      status.innerHTML = '<span class="xet-red">' + err.message + '</span>';
    });
  }

  function showOpen() {
    if (!enabled) {
      alert('ipuz_files storage is not available. Start Exet via the backend server ' +
            'and ensure the ipuz_files submodule is initialized.');
      return;
    }
    mode = 'open';
    showLoading('Syncing from GitHub (git pull)…');
    fetchJson('/api/puzzles/list')
        .then((data) => {
          hideLoading();
          exetModals.showModal(ensurePanel());
          renderOpenList(data);
        })
        .catch((err) => {
          hideLoading();
          exetModals.showModal(ensurePanel());
          renderError(err.message);
        });
  }

  function showSave() {
    if (!enabled) {
      alert('ipuz_files storage is not available. Start Exet via the backend server ' +
            'and ensure the ipuz_files submodule is initialized.');
      return;
    }
    if (!exet || !exet.puz) {
      alert('No puzzle loaded.');
      return;
    }
    mode = 'save';
    exetModals.showModal(ensurePanel());
    renderSaveForm();
  }

  function wireMenus() {
    const openBtn = document.getElementById('xet-open-ipuz-files');
    const saveBtn = document.getElementById('xet-save-ipuz-files');
    if (openBtn) {
      openBtn.style.display = enabled ? '' : 'none';
      openBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        showOpen();
      });
    }
    if (saveBtn) {
      saveBtn.style.display = enabled ? '' : 'none';
      saveBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        showSave();
      });
    }
  }

  function init() {
    probe().then(() => wireMenus());
  }

  return {
    init,
    probe,
    isEnabled,
    showOpen,
    showSave,
    clearLoadedSource,
  };
})();
