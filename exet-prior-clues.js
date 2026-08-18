/**
 * Offline published-clue lookup for Exet (answer → prior clues).
 * Core loader — data parts are in wordlists/built/prior-clues-part-*.js
 * (see wordlists/built/prior-clues-manifest.js).
 *
 * Cryptic data: cryptics.georgeho.org (ODbL v1.0).
 * xd data: xd.saul.pw / Saul Pwanson crossword clue corpus.
 */
exetPriorClues = (function() {
  const CLUES = [];
  const META = [];
  const INDEX = {};
  const STATS = {ready: false};
  let finalized = false;

  function answerKey(s) {
    if (!s) return '';
    let out = '';
    for (const ch of String(s).toUpperCase()) {
      if (ch >= 'A' && ch <= 'Z') out += ch;
    }
    return out;
  }

  function parseMeta(metaStr) {
    if (!metaStr) {
      return {kind: '', source: '', date: '', label: '', definition: ''};
    }
    const parts = metaStr.split('|');
    const kind = parts[0] || '';
    if (kind === 'g') {
      return {
        kind: 'cryptic',
        source: parts[1] || '',
        date: parts[2] || '',
        label: parts[3] || '',
        definition: parts[4] || '',
      };
    }
    if (kind === 'x') {
      const pub = parts[1] || '';
      const year = parts[2] || '';
      return {
        kind: 'xd',
        source: pub,
        date: year,
        label: pub + (year ? (' ' + year) : ''),
        definition: '',
      };
    }
    return {kind: '', source: '', date: '', label: metaStr, definition: ''};
  }

  function loadPart(part) {
    if (!part || finalized) {
      return;
    }
    if (part.stats) {
      Object.assign(STATS, part.stats);
    }
    if (part.clues && part.clues.length) {
      CLUES.push.apply(CLUES, part.clues);
    }
    if (part.meta && part.meta.length) {
      META.push.apply(META, part.meta);
    }
    if (part.index) {
      for (const k in part.index) {
        if (Object.prototype.hasOwnProperty.call(part.index, k)) {
          INDEX[k] = part.index[k];
        }
      }
    }
  }

  function finalize() {
    finalized = true;
    STATS.ready = true;
  }

  function lookUp(answer) {
    if (!finalized) {
      return [];
    }
    const key = answerKey(answer);
    if (!key || !INDEX[key]) {
      return [];
    }
    return INDEX[key].map(([ci, mi]) => {
      const clue = CLUES[ci];
      const metaStr = META[mi] || '';
      const parsed = parseMeta(metaStr);
      return {
        clue: clue,
        meta: metaStr,
        kind: parsed.kind,
        source: parsed.source,
        date: parsed.date,
        label: parsed.label,
        definition: parsed.definition,
      };
    });
  }

  return {
    loadPart: loadPart,
    finalize: finalize,
    get ready() {
      return finalized;
    },
    stats: STATS,
    answerKey: answerKey,
    lookUp: lookUp,
  };
})();
