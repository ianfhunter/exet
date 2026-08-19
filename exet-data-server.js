/**
 * Client for the Exet SQLite data server (same origin).
 * When enabled, prior clues and large lexicons use /api/* instead of JS blobs.
 */
const exetDataServer = (function() {
  const AGM_SHARDS = 2000;
  let enabled = false;
  /** display menu name -> { slug, id, display_name, entry_count } */
  const lexiconByName = {};

  function baseUrl() {
    if (typeof exetConfig !== 'undefined' && exetConfig.dataServerUrl) {
      return String(exetConfig.dataServerUrl).replace(/\/$/, '');
    }
    return '';
  }

  function syncGet(path) {
    const xhr = new XMLHttpRequest();
    xhr.open('GET', baseUrl() + path, false);
    xhr.send(null);
    if (xhr.status < 200 || xhr.status >= 300) {
      throw new Error('HTTP ' + xhr.status + ' for ' + path);
    }
    return JSON.parse(xhr.responseText);
  }

  function fetchJson(path) {
    return fetch(baseUrl() + path).then((r) => {
      if (!r.ok) {
        throw new Error('HTTP ' + r.status + ' for ' + path);
      }
      return r.json();
    });
  }

  function probe() {
    const mode = (typeof exetConfig !== 'undefined' && exetConfig.dataServer) ?
        exetConfig.dataServer : 'auto';
    if (mode === false || mode === 'off') {
      enabled = false;
      return false;
    }
    try {
      const health = syncGet('/health');
      if (!health || !health.ok) {
        enabled = false;
        return false;
      }
      enabled = true;
      const data = syncGet('/api/datasets');
      for (const lx of (data.lexicons || [])) {
        lexiconByName[lx.display_name] = lx;
        // Menu keys from import-wordlists often match display_name.
      }
      console.log('Exet data server enabled (' +
          (data.lexicons || []).length + ' lexicons, ' +
          (health.prior_clues || 0) + ' prior-clue rows)');
      return true;
    } catch (e) {
      enabled = false;
      if (mode === true || mode === 'on') {
        console.warn('Exet dataServer requested but /health failed:', e);
      }
      return false;
    }
  }

  function serverLexicon(name) {
    return lexiconByName[name] || null;
  }

  function makeStub(meta) {
    const letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('');
    const emptyShards = () => Array.from({length: AGM_SHARDS}, () => []);
    return {
      id: meta.id,
      language: 'en',
      script: 'Latin',
      letters: letters,
      lexicon: [''],
      index: {},
      anagrams: emptyShards(),
      phones: [[]],
      phindex: emptyShards(),
      scores: [0, 50],
      stems: [0],
      stemsId: meta.id,
      serverSlug: meta.slug,
      serverCache: {forms: [''], scores: [0]},
    };
  }

  function cacheEntry(stub, form, score, reversed) {
    let idx = stub.serverCache.forms.indexOf(form);
    if (idx < 0) {
      idx = stub.lexicon.length;
      stub.lexicon.push(form);
      stub.scores.push(score);
      stub.stems.push(idx);
      stub.phones.push([]);
      stub.serverCache.forms.push(form);
      stub.serverCache.scores.push(score);
    }
    return reversed ? -idx : idx;
  }

  function minScoreParam() {
    if (typeof exet !== 'undefined' && exet && exet.minscore != null) {
      return exet.minscore;
    }
    return 0;
  }

  function applyServerLexicon() {
    if (!exetLexicon || !exetLexicon.serverSlug) {
      return;
    }
    const slug = exetLexicon.serverSlug;
    exetLexicon.startLen = 1;

    exetLexicon.getLex = function(idx) {
      const i = Math.abs(idx);
      return this.lexicon[i] || '';
    };

    exetLexicon.stemGroup = function(idx) {
      return [Math.abs(Number(idx))];
    };

    exetLexicon.getLexChoices = function(
        partialSol, limit, dontReuse, noProperNouns, indexLimit,
        tryRev, preflexByLen, unpreflexSet, regexp) {
      const key = this.lexkey(partialSol);
      if (!key.length) {
        return [];
      }
      const pattern = key.join('');
      const params = new URLSearchParams();
      params.set('pattern', pattern);
      if (limit > 0) {
        params.set('limit', String(limit));
      }
      params.set('min_score', String(minScoreParam()));
      if (noProperNouns) {
        params.set('no_proper_nouns', 'true');
      }
      if (tryRev) {
        params.set('try_rev', 'true');
      }
      let data;
      try {
        data = syncGet('/api/lexicons/' + encodeURIComponent(slug) +
                       '/fill?' + params.toString());
      } catch (e) {
        console.warn('Server fill lookup failed:', e);
        return [];
      }
      const out = [];
      const seen = {};
      for (const ch of (data.choices || [])) {
        if (regexp && !regexp.test(ch.form)) {
          continue;
        }
        const idx = cacheEntry(this, ch.form, ch.score, ch.reversed);
        const loopIdx = ch.reversed ? -idx : idx;
        if (dontReuse && dontReuse.has(Math.abs(idx))) {
          continue;
        }
        if (unpreflexSet && unpreflexSet[idx]) {
          continue;
        }
        if (seen[loopIdx]) {
          continue;
        }
        seen[loopIdx] = true;
        out.push(loopIdx);
        if (limit > 0 && out.length >= limit) {
          break;
        }
      }
      return out;
    };

    exetLexicon.getAnagrams1 = function(letters, limit, getIndices) {
      const q = letters.join('');
      if (!q) {
        return [];
      }
      const params = new URLSearchParams();
      params.set('q', q);
      if (limit > 0) {
        params.set('limit', String(limit));
      }
      params.set('min_score', String(minScoreParam()));
      let data;
      try {
        data = syncGet('/api/lexicons/' + encodeURIComponent(slug) +
                       '/anagrams?' + params.toString());
      } catch (e) {
        console.warn('Server anagram lookup failed:', e);
        return [];
      }
      const out = [];
      for (const a of (data.anagrams || [])) {
        if (getIndices) {
          out.push(cacheEntry(this, a.form, a.score, false));
        } else {
          out.push(a.form);
        }
        if (limit > 0 && out.length >= limit) {
          break;
        }
      }
      return out;
    };

    exetLexicon.scoresSummary = {min: 0, max: 100};
    console.log('Lexicon served from SQLite API:', slug);
  }

  function loadServerLexicon(displayName, meta) {
    exetLexicon = makeStub(meta);
    exetLexiconNewName = displayName;
    xetAfterPaint(exetLoadedLexicon);
  }

  function fetchPriorClues(answer) {
    const key = String(answer || '').replace(/[^A-Za-z]/g, '').toUpperCase();
    return fetchJson('/api/prior-clues/' + encodeURIComponent(key) + '?limit=500');
  }

  return {
    probe: probe,
    get enabled() {
      return enabled;
    },
    serverLexicon: serverLexicon,
    loadServerLexicon: loadServerLexicon,
    applyServerLexicon: applyServerLexicon,
    fetchPriorClues: fetchPriorClues,
    syncGet: syncGet,
  };
})();
