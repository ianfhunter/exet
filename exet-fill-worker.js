/*
 * Exet fill worker. All server lexicon I/O and fill propagation happen here,
 * leaving the UI thread free to process grid input.
 */
importScripts('exet-fill-engine.js?v1.00');

'use strict';

let generation = 0;
let activeController = null;
let state = null;
let engine = null;
let runningAutofill = false;
let autofillToken = 0;
let options = {};
let lexicon = null;

class WorkerLexicon {
  constructor(meta, baseUrl, cachedEntries=[]) {
    this.slug = meta.slug;
    this.entryCount = meta.entry_count || 1;
    this.baseUrl = String(baseUrl || '').replace(/\/$/, '');
    this.letters = (meta.letters || 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split(''));
    this.forms = [''];
    this.scores = [0];
    this.formToIndex = new Map([['', 0]]);
    this.sentIndices = new Set([0]);
    for (let index = 1; index < cachedEntries.length; index++) {
      const entry = cachedEntries[index];
      if (!entry || !entry.form) continue;
      this.forms[index] = entry.form;
      this.scores[index] = entry.score || 0;
      this.formToIndex.set(entry.form, index);
      this.sentIndices.add(index);
    }
  }
  lexkey(value) {
    const allowed = new Set(this.letters);
    return Array.from(String(value || '').toUpperCase())
        .filter(letter => allowed.has(letter) || letter == '?');
  }
  cacheEntry(form, score, reversed=false) {
    let index = this.formToIndex.get(form);
    if (index === undefined) {
      index = this.forms.length;
      this.formToIndex.set(form, index);
      this.forms.push(form);
      this.scores.push(score || 0);
    }
    return reversed ? -index : index;
  }
  keyForIndex(signedIndex) {
    const key = this.lexkey(this.forms[Math.abs(signedIndex)] || '');
    if (signedIndex < 0) key.reverse();
    return key;
  }
  async getJson(path, signal) {
    const response = await fetch(this.baseUrl + path, {signal});
    if (!response.ok) throw new Error(`${path} returned ${response.status}`);
    return response.json();
  }
  async getLexChoices(pattern, limit, signal) {
    const result = await this.fillBatch(
        [{ci: 'choice', pattern, limit}], signal);
    return result.choice || [];
  }
  async getAnagrams1(letters, limit, signal) {
    const params = new URLSearchParams({q: letters.join('')});
    if (limit > 0) params.set('limit', String(limit));
    const data = await this.getJson(
        `/api/lexicons/${encodeURIComponent(this.slug)}/anagrams?${params}`,
        signal);
    return (data.anagrams || []).map(entry =>
      this.cacheEntry(entry.form, entry.score, false));
  }
  async getAnagramsK(letters, limit, count, sequenceOK, signal) {
    const params = new URLSearchParams({
      q: letters.join(''),
      k: String(count),
      seq_ok: String(sequenceOK),
    });
    if (limit > 0) params.set('limit', String(limit));
    const data = await this.getJson(
        `/api/lexicons/${encodeURIComponent(this.slug)}/multiword-anagrams?${params}`,
        signal);
    return (data.results || []).map(entry => entry.phrase);
  }
  async getSupersetAnagrams(letters, limit, minusLimit, maxFactor, signal) {
    const params = new URLSearchParams({
      q: letters.join(''),
      limit: String(limit || 0),
      minus_limit: String(minusLimit || 0),
      max_sup_factor: String(maxFactor || 2),
    });
    const data = await this.getJson(
        `/api/lexicons/${encodeURIComponent(this.slug)}/superset-anagrams?${params}`,
        signal);
    return data.results || [];
  }
  async fillBatch(requests, signal) {
    const patterns = [];
    for (const request of requests) {
      const pattern = this.lexkey(request.pattern).join('');
      if (pattern && !patterns.includes(pattern)) patterns.push(pattern);
    }
    if (!patterns.length) return {};
    const response = await fetch(
        `${this.baseUrl}/api/lexicons/${encodeURIComponent(this.slug)}/fill-batch`,
        {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            patterns,
            limit_per: options.unfilledChoicesLimit || 5000,
            min_score: options.minScore || 0,
            no_proper_nouns: !!options.noProperNouns,
            try_rev: !!options.tryReversals,
          }),
          signal,
        });
    if (!response.ok) throw new Error(`fill-batch returned ${response.status}`);
    const data = await response.json();
    const result = {};
    for (const request of requests) {
      const pattern = this.lexkey(request.pattern).join('');
      let choices = (data.results && data.results[pattern]) || [];
      if (request.regexp) {
        const regexp = new RegExp(request.regexp.source, request.regexp.flags);
        choices = choices.filter(choice => regexp.test(choice.form));
      }
      const limit = request.limit || 0;
      result[request.ci] = choices.slice(0, limit || undefined).map(choice =>
        this.cacheEntry(choice.form, choice.score, choice.reversed));
    }
    return result;
  }
  recordsFor(indices) {
    const records = [];
    for (const signedIndex of indices) {
      const index = Math.abs(signedIndex);
      if (!index || this.sentIndices.has(index)) continue;
      this.sentIndices.add(index);
      records.push({index, form: this.forms[index], score: this.scores[index]});
    }
    return records;
  }
}

function makeContext() {
  return {
    letters: lexicon.letters,
    entryCount: lexicon.entryCount,
    letterRarities: options.letterRarities || {},
    preflexSet: options.preflexSet || {},
    noStemDupes: !!options.noStemDupes,
    keyForIndex: index => lexicon.keyForIndex(index),
    scoreForIndex: index => lexicon.scores[Math.abs(index)] || 0,
    // Server-backed indices do not carry the original stemming ring.
    stemGroup: index => [index],
  };
}

function requestList(fillState) {
  const requests = [];
  for (const ci in fillState.clues) {
    const clue = fillState.clues[ci];
    if (!clue.solution || clue.parentClueIndex || clue.hasRebus) continue;
    requests.push({
      ci,
      pattern: clue.solution,
      limit: clue.solution.includes('?') ?
          (options.unfilledChoicesLimit || 5000) : 1,
      regexp: options.regexps && options.regexps[ci],
    });
  }
  return requests;
}

async function rebuild(message) {
  const myGeneration = message.gen;
  generation = myGeneration;
  runningAutofill = false;
  autofillToken++;
  if (activeController) activeController.abort();
  activeController = new AbortController();
  options = {...options, ...(message.options || {})};
  options.preflexSet = {};
  for (const form of options.preflexForms || []) {
    const index = lexicon.cacheEntry(form, 100, false);
    options.preflexSet[index] = true;
  }
  state = new ExetFillStateCore(message.state);
  engine = new ExetFillEngine(makeContext());
  postMessage({type: 'busy', gen: myGeneration, busy: true});
  try {
    const choices = await lexicon.fillBatch(
        requestList(state), activeController.signal);
    if (myGeneration != generation) return;
    engine.resetFromChoices(state, choices);
    postSnapshot('viability');
    // Propagation is intentionally split into turns. A newer setState message
    // can be processed between turns and invalidate this generation.
    for (let pass = 0; pass < (options.maxSweepPasses || 20); pass++) {
      await yieldTurn();
      if (myGeneration != generation) return;
      const changed = engine.refineLightChoices(
          state, options.sweepMaxChoices || 5000);
      postSnapshot('viability');
      if (!changed) break;
    }
    const constrained = Object.keys(state.clues)
        .filter(ci => {
          const clue = state.clues[ci];
          return !clue.parentClueIndex && clue.solution &&
              clue.solution.includes('?') && clue.lChoices.length;
        })
        .sort((a, b) =>
          state.clues[a].lChoices.length - state.clues[b].lChoices.length);
    if (constrained.length) {
      const ci = constrained[0];
      const clue = state.clues[ci];
      const checked = clue.lChoices.slice(0, options.shownChoices || 200);
      const viable = [];
      for (let start = 0; start < checked.length; start += 3) {
        await yieldTurn();
        if (myGeneration != generation) return;
        for (const choice of checked.slice(start, start + 3)) {
          if (engine.choiceCreatesDeadend(state, ci, choice)) {
            engine.noteReject(clue, [choice]);
          } else {
            viable.push(choice);
          }
        }
      }
      clue.lChoices = viable.concat(
          clue.lChoices.slice(options.shownChoices || 200));
      postSnapshot('viability');
    }
    if (myGeneration == generation) {
      postMessage({type: 'busy', gen: myGeneration, busy: false});
    }
  } catch (error) {
    if (error.name == 'AbortError' || myGeneration != generation) return;
    postMessage({
      type: 'error',
      gen: myGeneration,
      message: error.message || String(error),
    });
    postMessage({type: 'busy', gen: myGeneration, busy: false});
  }
}

function snapshot(fillState, kind) {
  const usedIndices = [];
  const cells = fillState.grid.map(row => row.map(cell => {
    if (!cell.isLight) return null;
    return {
      cChoices: Object.keys(cell.cChoices || {}),
      viability: cell.viability,
    };
  }));
  const clues = {};
  for (const ci in fillState.clues) {
    const clue = fillState.clues[ci];
    const choices = (clue.lChoices || []).slice(0, options.shownChoices || 200);
    const rejects = (clue.lRejects || []).slice(0, options.shownChoices || 200);
    usedIndices.push(...choices, ...rejects);
    clues[ci] = {
      lChoices: choices,
      lChoicesTotal: (clue.lChoices || []).length,
      lRejects: rejects,
      lRejectsTotal: (clue.lRejects || []).length,
    };
  }
  return {
    type: 'snapshot',
    kind,
    gen: generation,
    cells,
    clues,
    viable: fillState.viable,
    entries: lexicon.recordsFor(usedIndices),
  };
}

function postSnapshot(kind, fillState=state, progress=null) {
  const message = snapshot(fillState, kind);
  if (progress) message.progress = progress;
  postMessage(message);
}

function yieldTurn() {
  return new Promise(resolve => setTimeout(resolve, 0));
}

async function requestChoices(message) {
  const controller = new AbortController();
  try {
    let result;
    if (message.method == 'fill') {
      result = await lexicon.getLexChoices(
          message.pattern, message.limit || 0, controller.signal);
    } else if (message.method == 'anagrams') {
      result = await lexicon.getAnagrams1(
          message.letters || [], message.limit || 0, controller.signal);
    } else if (message.method == 'multiwordAnagrams') {
      result = await lexicon.getAnagramsK(
          message.letters || [], message.limit || 0, message.count || 2,
          message.sequenceOK !== false, controller.signal);
    } else if (message.method == 'supersetAnagrams') {
      result = await lexicon.getSupersetAnagrams(
          message.letters || [], message.limit || 0, message.minusLimit || 0,
          message.maxFactor || 2, controller.signal);
    } else {
      throw new Error(`Unknown choice method: ${message.method}`);
    }
    postMessage({
      type: 'choices',
      requestId: message.requestId,
      result,
    });
  } catch (error) {
    postMessage({
      type: 'choices',
      requestId: message.requestId,
      error: error.message || String(error),
    });
  }
}

function maybeAddCandidate(search, candidate) {
  if (!candidate.viable) return false;
  const hash = candidate.hash();
  if (search.triedHashes[hash] || engine.hasPatternOfDeath(candidate)) return false;
  search.triedHashes[hash] = true;
  search.beam.add(candidate);
  return true;
}

function getPriorityClues(fillState) {
  const priority = [];
  for (const ci in fillState.clues) {
    const clue = fillState.clues[ci];
    if (!clue.solution || !clue.solution.includes('?')) continue;
    const preferred = clue.lChoices.filter(
        choice => options.preflexSet[Math.abs(choice)]);
    if (preferred.length) priority.push([ci, preferred]);
  }
  return priority;
}

function addPriorityCandidate(search) {
  const child = new ExetFillStateCore(state);
  const remaining = search.priorityClues.slice();
  const used = new Set();
  while (child.viable && remaining.length) {
    const offset = Math.floor(Math.random() * remaining.length);
    const [ci, preferred] = remaining.splice(offset, 1)[0];
    const choice = preferred.find(value => !used.has(Math.abs(value)));
    if (choice === undefined) continue;
    const key = lexicon.keyForIndex(choice);
    const cells = engine.getAllCells(ci, child.clues);
    if (key.length != cells.length) continue;
    child.clues[ci].lChoices = [choice];
    child.clues[ci].lRejects = [];
    for (let index = 0; index < cells.length; index++) {
      const [row, col] = cells[index];
      child.grid[row][col].cChoices = {[key[index]]: true};
      child.grid[row][col].currLetter = key[index];
    }
    used.add(Math.abs(choice));
    for (let pass = 0;
         pass < (search.options.refinementSweeps || 2) && child.viable;
         pass++) {
      if (!engine.refineLightChoices(
          child, search.options.constrainerLimit || 2000)) break;
    }
  }
  if (child.viable) {
    engine.score(child, search.options);
    maybeAddCandidate(search, child);
  }
}

function addChildren(search) {
  if (search.priorityClues.length &&
      search.priorityLoop < (search.options.priorityLoops || 20)) {
    addPriorityCandidate(search);
    search.priorityLoop++;
    return;
  }
  const candidate = search.beam.pop(true);
  if (!candidate || !candidate.unfilled || !candidate.unfilled.length) return;
  let toAdd = 1;
  const cellChoices = [];
  if (search.options.boostPangram &&
      candidate.numConstrLetters < lexicon.letters.length) {
    cellChoices.push(0);
    toAdd = 0;
  }
  const cellLimit = Math.min(candidate.unfilled.length, 4);
  for (let i = 0; i < toAdd; i++) {
    const cellIndex = Math.floor(Math.random() * cellLimit);
    if (!cellChoices.includes(cellIndex)) cellChoices.push(cellIndex);
  }
  let children = 0;
  for (const cellIndex of cellChoices) {
    const [row, col] = candidate.unfilled[cellIndex];
    for (const letter of Object.keys(candidate.grid[row][col].cChoices)) {
      const child = new ExetFillStateCore(candidate);
      child.grid[row][col].cChoices = {[letter]: true};
      child.grid[row][col].currLetter = letter;
      for (let pass = 0;
           pass < (search.options.refinementSweeps || 2) && child.viable;
           pass++) {
        if (!engine.refineLightChoices(
            child, search.options.constrainerLimit || 2000)) break;
      }
      if (!child.viable) continue;
      engine.score(child, search.options);
      if (maybeAddCandidate(search, child) && ++children >= 50) return;
    }
  }
}

async function runAutofill(message) {
  if (!state || message.gen != generation) return;
  const token = ++autofillToken;
  runningAutofill = true;
  const searchOptions = message.options || {};
  const search = {
    options: searchOptions,
    beam: new ExetDherCore(searchOptions.beamWidth || 64),
    triedHashes: {},
    step: 0,
    msUsed: 0,
    priorityClues: [],
    priorityLoop: 0,
  };
  const initial = new ExetFillStateCore(state);
  for (let pass = 0;
       pass < (searchOptions.refinementSweeps || 2) && initial.viable;
       pass++) {
    if (!engine.refineLightChoices(
        initial, searchOptions.constrainerLimit || 2000)) break;
  }
  engine.score(initial, searchOptions);
  if (!initial.viable) {
    runningAutofill = false;
    postMessage({type: 'autofillStatus', gen: generation, status: 'Failed'});
    return;
  }
  search.priorityClues = getPriorityClues(initial);
  search.beam.add(initial);
  postMessage({type: 'busy', gen: generation, busy: true});
  while (runningAutofill && token == autofillToken &&
         message.gen == generation && search.beam.size()) {
    const started = performance.now();
    search.step++;
    addChildren(search);
    search.msUsed += performance.now() - started;
    const best = search.step > state.gridWidth * state.gridHeight * 3 ?
        null : search.beam.peep(true);
    if (!best) break;
    postSnapshot('autofill', best, {
      step: search.step,
      beamSize: search.beam.size(),
      msUsed: Math.round(search.msUsed),
      score: best.score,
      scoreV: best.scoreV,
      scoreP: best.scoreP,
      scoreF: best.scoreF,
      reversals: best.reversals,
      numLettersUsed: best.numLettersUsed,
      numConstrLetters: best.numConstrLetters,
    });
    if (best.isFull()) {
      runningAutofill = false;
      postMessage({type: 'autofillStatus', gen: generation, status: 'Succeeded!'});
      break;
    }
    await new Promise(resolve => setTimeout(resolve, 16));
  }
  if (token == autofillToken && message.gen == generation) {
    if (runningAutofill) {
      runningAutofill = false;
      postMessage({type: 'autofillStatus', gen: generation, status: 'Failed'});
    }
    postMessage({type: 'busy', gen: generation, busy: false});
  }
}

onmessage = event => {
  const message = event.data || {};
  if (message.type == 'init') {
    options = message.options || {};
    lexicon = new WorkerLexicon(
        message.lexicon, message.baseUrl, message.cachedEntries || []);
    postMessage({type: 'ready'});
  } else if (message.type == 'setState') {
    rebuild(message);
  } else if (message.type == 'setOptions' ||
             message.type == 'setPreflex' ||
             message.type == 'setRegexps') {
    options = {...options, ...(message.options || {})};
  } else if (message.type == 'startAutofill') {
    runAutofill(message);
  } else if (message.type == 'pauseAutofill') {
    runningAutofill = false;
    autofillToken++;
    postMessage({type: 'busy', gen: generation, busy: false});
  } else if (message.type == 'requestChoices') {
    requestChoices(message);
  }
};
