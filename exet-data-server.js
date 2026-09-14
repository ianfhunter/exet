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

  // Compatibility path for tools whose public API is still synchronous.
  // Grid-fill and autofill never call this: they use exet-fill-worker.js.
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

  async function probe() {
    const mode = (typeof exetConfig !== 'undefined' && exetConfig.dataServer) ?
        exetConfig.dataServer : 'auto';
    if (mode === false || mode === 'off') {
      enabled = false;
      return false;
    }
    try {
      const health = await fetchJson('/health');
      if (!health || !health.ok) {
        enabled = false;
        return false;
      }
      enabled = true;
      const data = await fetchJson('/api/datasets');
      for (const lx of (data.lexicons || [])) {
        lexiconByName[lx.display_name] = lx;
        // Menu keys from import-wordlists often match display_name.
      }
      console.log('Exet data server enabled (' +
          (data.lexicons || []).length + ' lexicons, ' +
          (health.prior_clues || 0) + ' prior-clue rows, ' +
          (health.wordnet_synsets || 0) + ' WordNet synsets)');
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
      serverEntryCount: meta.entry_count || 1,
      serverScoreQuantiles: meta.score_quantiles || [],
      serverCache: {
        forms: [''],
        scores: [0],
        formToIndex: new Map([['', 0]]),
      },
    };
  }

  function cacheEntry(stub, form, score, reversed) {
    let idx = stub.serverCache.formToIndex.get(form);
    if (idx === undefined) {
      idx = stub.lexicon.length;
      stub.lexicon.push(form);
      stub.scores.push(score);
      stub.stems.push(idx);
      stub.phones.push([]);
      stub.serverCache.forms.push(form);
      stub.serverCache.scores.push(score);
      stub.serverCache.formToIndex.set(form, idx);
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
    // This is the size of the server-side list, not the small browser cache.
    // Large-list limits key off startLen.
    exetLexicon.startLen = exetLexicon.serverEntryCount || 1;

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

    /**
     * exet-lexicon.js builds multi-word anagrams from slkIndex, an index over
     * the in-memory lexicon. There is no in-memory lexicon here, so that index
     * is empty and the search finds nothing. Ask the server instead.
     */
    exetLexicon.getAnagramsK = function(letters, limit, k, seqOK) {
      const q = letters.join('');
      if (!q || k < 2) {
        return [];
      }
      const params = new URLSearchParams();
      params.set('q', q);
      params.set('k', String(k));
      if (limit > 0) {
        params.set('limit', String(limit));
      }
      if (!seqOK) {
        params.set('seq_ok', 'false');
      }
      let data;
      try {
        data = syncGet('/api/lexicons/' + encodeURIComponent(slug) +
                       '/multiword-anagrams?' + params.toString());
      } catch (e) {
        console.warn('Server multi-word anagram lookup failed:', e);
        return [];
      }
      const out = [];
      for (const row of (data.results || [])) {
        out.push(row.phrase);
      }
      return out;
    };

    exetLexicon.getSupersetAnagrams = function(letters, limit, minusLimit, maxSupFactor) {
      const q = letters.join('');
      if (!q) {
        return [];
      }
      const params = new URLSearchParams();
      params.set('q', q);
      if (limit > 0) {
        params.set('limit', String(limit));
      }
      if (minusLimit > 0) {
        params.set('minus_limit', String(minusLimit));
      }
      if (maxSupFactor > 0) {
        params.set('max_sup_factor', String(maxSupFactor));
      }
      let data;
      try {
        data = syncGet('/api/lexicons/' + encodeURIComponent(slug) +
                       '/superset-anagrams?' + params.toString());
      } catch (e) {
        console.warn('Server superset anagram lookup failed:', e);
        return [];
      }
      const out = [];
      for (const row of (data.results || [])) {
        const idx = cacheEntry(this, row.form, row.score || 0, false);
        out.push([idx, row.diff, row.anagrams || []]);
      }
      return out;
    };

    // The popularity control picks a percentile of the list, but the server
    // filters on score, so map ranks onto real scores. Without the map we
    // leave scoresSummary null so the UI falls back to unfiltered popularity
    // rather than inventing a cutoff that matches nothing.
    const quantiles = exetLexicon.serverScoreQuantiles || [];
    if (quantiles.length >= 2) {
      const buckets = quantiles.length - 1;
      const lastIndex = Math.max(1, exetLexicon.startLen - 2);
      exetLexicon.scoresSummary = {min: quantiles[buckets], max: quantiles[0]};
      exetLexicon.indexToScore = function(index) {
        const rank = Math.max(0, Math.min(lastIndex, index - 1));
        return quantiles[Math.round(rank / lastIndex * buckets)];
      };
      /** Largest index whose score is still >= score, or 0 if none is. */
      exetLexicon.scoreToIndex = function(score) {
        let left = 0;
        let right = buckets;
        let found = -1;
        while (left <= right) {
          const mid = (left + right) >> 1;
          if (quantiles[mid] >= score) {
            found = mid;
            left = mid + 1;
          } else {
            right = mid - 1;
          }
        }
        if (found < 0) {
          return 0;
        }
        return 1 + Math.round(found / buckets * lastIndex);
      };
    } else {
      exetLexicon.scoresSummary = null;
    }
    console.log('Lexicon served from SQLite API:', slug);
  }

  function loadServerLexicon(displayName, meta) {
    // The stub only becomes a usable lexicon once exetLexiconInit() and
    // applyServerLexicon() have run, so stop any main-thread sweep that would
    // otherwise reach into it during the intervening paint.
    if (typeof exet !== 'undefined' && exet && exet.cancelDeadendSweep) {
      exet.cancelDeadendSweep();
    }
    exetLexicon = makeStub(meta);
    exetLexiconNewName = displayName;
    xetAfterPaint(exetLoadedLexicon);
  }

  function fetchPriorClues(answer) {
    const key = String(answer || '').replace(/[^A-Za-z]/g, '').toUpperCase();
    return fetchJson('/api/prior-clues/' + encodeURIComponent(key) + '?limit=500');
  }

  function fetchSynonyms(word) {
    return fetchJson('/api/synonyms?word=' + encodeURIComponent(String(word || '').trim()));
  }

  return {
    probe: probe,
    baseUrl: baseUrl,
    get enabled() {
      return enabled;
    },
    serverLexicon: serverLexicon,
    loadServerLexicon: loadServerLexicon,
    applyServerLexicon: applyServerLexicon,
    fetchPriorClues: fetchPriorClues,
    fetchSynonyms: fetchSynonyms,
    syncGet: syncGet,
  };
})();
