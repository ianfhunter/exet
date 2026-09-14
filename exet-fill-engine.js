/*
MIT License

Copyright (c) 2022 Viresh Ratnakar

See the full Exet license notice in exet.js.
*/

/**
 * DOM-free fill engine shared by the Exet UI and exet-fill-worker.js.
 *
 * The engine deliberately receives all puzzle and lexicon operations through
 * `ctx`. This keeps the expensive propagation and beam-search code usable in a
 * Worker without importing Exolve or touching the live puzzle.
 */
(function(root) {
  'use strict';

  class ExetDherCore {
    constructor(limit) {
      this.maxelts = [];
      this.minelts = [];
      this.lim = limit;
    }
    size() {
      return this.maxelts.length;
    }
    parent(index) {
      return index == 0 ? 0 : (index - 1) >> 1;
    }
    heapifyUp(inMax, index) {
      const elts = inMax ? this.maxelts : this.minelts;
      while (index > 0) {
        const parent = this.parent(index);
        const ordered = inMax ?
            elts[parent].score >= elts[index].score :
            elts[parent].score <= elts[index].score;
        if (ordered) return;
        [elts[parent], elts[index]] = [elts[index], elts[parent]];
        elts[index].dher[inMax] = index;
        elts[parent].dher[inMax] = parent;
        index = parent;
      }
    }
    heapifyDown(inMax, index) {
      const elts = inMax ? this.maxelts : this.minelts;
      while (index < elts.length) {
        const left = (index << 1) + 1;
        if (left >= elts.length) return;
        const right = left + 1;
        let child = left;
        if (right < elts.length &&
            (inMax ? elts[right].score > elts[left].score :
                     elts[right].score < elts[left].score)) {
          child = right;
        }
        const ordered = inMax ?
            elts[index].score >= elts[child].score :
            elts[index].score <= elts[child].score;
        if (ordered) return;
        [elts[index], elts[child]] = [elts[child], elts[index]];
        elts[index].dher[inMax] = index;
        elts[child].dher[inMax] = child;
        index = child;
      }
    }
    popInner(inMax, index) {
      const elts = inMax ? this.maxelts : this.minelts;
      const length = elts.length;
      const last = elts.pop();
      if (length == 1 || index >= length - 1) return last;
      const result = elts[index];
      elts[index] = last;
      last.dher[inMax] = index;
      const parent = this.parent(index);
      if (index > 0 &&
          (inMax ? last.score > elts[parent].score :
                   last.score < elts[parent].score)) {
        this.heapifyUp(inMax, index);
      } else {
        this.heapifyDown(inMax, index);
      }
      return result;
    }
    pop(inMax, index=0) {
      const elts = inMax ? this.maxelts : this.minelts;
      if (index < 0 || index >= elts.length) return null;
      const otherIndex = elts[index].dher[!inMax];
      this.popInner(!inMax, otherIndex);
      return this.popInner(inMax, index);
    }
    peep(inMax, index=0) {
      const elts = inMax ? this.maxelts : this.minelts;
      return index < 0 || index >= elts.length ? null : elts[index];
    }
    add(candidate) {
      let size = this.minelts.length;
      if (size == this.lim) {
        const worst = this.minelts[0];
        if (candidate.score < worst.score ||
            (candidate.score == worst.score && Math.random() < 0.5)) {
          return candidate;
        }
        this.pop(false);
        size--;
      }
      candidate.dher = {[true]: size, [false]: size};
      this.maxelts.push(candidate);
      this.minelts.push(candidate);
      this.heapifyUp(true, size);
      this.heapifyUp(false, size);
      return null;
    }
  }

  class ExetFillStateCore {
    constructor(source) {
      this.gridWidth = source.gridWidth;
      this.gridHeight = source.gridHeight;
      this.viable = source.viable ?? true;
      this.grid = source.grid.map(row => row.map(cell => {
        const copy = {...cell};
        copy.cChoices = {...(cell.cChoices || {})};
        return copy;
      }));
      this.clues = {};
      for (const ci in source.clues) {
        const clue = source.clues[ci];
        this.clues[ci] = {
          ...clue,
          childrenClueIndices: (clue.childrenClueIndices || []).slice(),
          cells: (clue.cells || []).map(cell => cell.slice()),
          cellsOfOrphan: clue.cellsOfOrphan ?
              clue.cellsOfOrphan.map(cell => cell.slice()) : undefined,
          lChoices: (clue.lChoices || []).slice(),
          lRejects: (clue.lRejects || []).slice(),
        };
      }
      this.preflexUsed = new Set(source.preflexUsed || []);
      this.dontReuse = new Set(source.dontReuse || []);
    }
    initViability(letters) {
      this.viable = true;
      const letterSet = Object.fromEntries(letters.map(letter => [letter, true]));
      for (const row of this.grid) {
        for (const cell of row) {
          if (!cell.isLight) continue;
          if (cell.solution != '?') {
            cell.cChoices = {[cell.solution]: true};
            cell.viability = 1;
          } else {
            cell.cChoices = {...letterSet};
            cell.viability = 5;
          }
        }
      }
    }
    isFull() {
      return !this.unfilled || this.unfilled.length == 0;
    }
    hash() {
      let value = '';
      for (const row of this.grid) {
        for (const cell of row) {
          if (cell.isLight) value += cell.currLetter || '?';
        }
      }
      let hash = 0;
      const bytes = new TextEncoder().encode(value);
      for (const byte of bytes) {
        hash = ((hash << 5) - hash) + ((byte << 24) >> 24);
        hash |= 0;
      }
      return hash;
    }
  }

  class ExetFillEngine {
    constructor(ctx) {
      this.ctx = ctx;
    }
    getLinkedClues(ci, clues) {
      const clue = clues[ci];
      if (!clue) return [];
      if (clue.parentClueIndex) {
        const parent = clue.parentClueIndex;
        return [parent].concat(clues[parent].childrenClueIndices || []);
      }
      return [ci].concat(clue.childrenClueIndices || []);
    }
    getAllCells(ci, clues) {
      const cells = [];
      for (const clueIndex of this.getLinkedClues(ci, clues)) {
        const clue = clues[clueIndex];
        const part = clue.cellsOfOrphan || (clue.cells || []).slice(clue.linkedOffset || 0);
        for (const cell of part) cells.push(cell);
      }
      if (cells.length > 1) {
        const last = cells.length - 1;
        if (cells[0][0] == cells[last][0] &&
            cells[0][1] == cells[last][1]) {
          cells.pop();
        }
      }
      return cells;
    }
    addToDontReuse(index, set) {
      if (this.ctx.noStemDupes && this.ctx.stemGroup) {
        for (const stem of this.ctx.stemGroup(index)) set.add(stem);
      } else {
        set.add(index);
      }
    }
    noteReject(clue, choices) {
      const room = Math.max(0, 1000 - clue.lRejects.length);
      clue.lRejects.push(...choices.slice(0, room));
    }
    viability(length) {
      return length == 0 ? 0 :
          (length >= 16 ? 5 : 1 + Math.log2(length));
    }
    resetFromChoices(state, choicesByClue) {
      state.initViability(this.ctx.letters);
      state.dontReuse = new Set();
      state.preflexUsed = new Set();
      for (const ci in state.clues) {
        const clue = state.clues[ci];
        clue.lChoices = (choicesByClue[ci] || []).slice();
        clue.lRejects = [];
        if (clue.solution && !clue.solution.includes('?') && clue.lChoices.length) {
          const index = Math.abs(clue.lChoices[0]);
          this.addToDontReuse(index, state.dontReuse);
          if (this.ctx.preflexSet[index]) state.preflexUsed.add(index);
        }
      }
    }
    refineLightChoices(state, limit=0) {
      state.preflexUsed = new Set();
      state.dontReuse = new Set();
      for (const ci in state.clues) {
        const clue = state.clues[ci];
        if (clue.parentClueIndex || !clue.solution || clue.solution.includes('?')) continue;
        if (clue.lChoices.length) {
          const index = Math.abs(clue.lChoices[0]);
          this.addToDontReuse(index, state.dontReuse);
          if (this.ctx.preflexSet[index]) state.preflexUsed.add(index);
        }
      }
      let changes = 0;
      for (const ci in state.clues) {
        const clue = state.clues[ci];
        if (clue.parentClueIndex || !clue.solution ||
            !clue.solution.includes('?') || clue.hasRebus) continue;
        const cells = this.getAllCells(ci, state.clues);
        const count = limit <= 0 ? clue.lChoices.length :
            Math.min(limit, clue.lChoices.length);
        const choices = clue.lChoices.slice(0, count);
        const remaining = clue.lChoices.slice(count);
        clue.lChoices = [];
        const cellSets = cells.map(() => ({}));
        for (const signedIndex of choices) {
          if (state.dontReuse.has(Math.abs(signedIndex))) {
            changes++;
            continue;
          }
          const key = this.ctx.keyForIndex(signedIndex);
          let viable = key.length == cells.length;
          for (let i = 0; viable && i < key.length; i++) {
            const cell = state.grid[cells[i][0]][cells[i][1]];
            if (cell.solution == '?' && !cell.cChoices[key[i]]) viable = false;
          }
          if (!viable) {
            this.noteReject(clue, [signedIndex]);
            changes++;
            continue;
          }
          clue.lChoices.push(signedIndex);
          for (let i = 0; i < key.length; i++) cellSets[i][key[i]] = true;
        }
        let forced = true;
        for (let i = 0; i < cells.length; i++) {
          const cell = state.grid[cells[i][0]][cells[i][1]];
          if (cell.solution != '?') continue;
          const intersection = {};
          for (const letter in cellSets[i]) {
            if (cell.cChoices[letter]) intersection[letter] = true;
          }
          cell.cChoices = intersection;
          if (Object.keys(intersection).length > 1) forced = false;
        }
        if (forced) {
          for (const signedIndex of clue.lChoices) {
            const index = Math.abs(signedIndex);
            this.addToDontReuse(index, state.dontReuse);
            if (this.ctx.preflexSet[index]) state.preflexUsed.add(index);
          }
          this.noteReject(clue, remaining);
        } else {
          clue.lChoices.push(...remaining);
        }
      }
      for (const row of state.grid) {
        for (const cell of row) {
          if (!cell.isLight || cell.solution != '?') continue;
          const count = Object.keys(cell.cChoices).length;
          if (!count) state.viable = false;
          cell.viability = this.viability(count);
        }
      }
      return changes;
    }
    someClueTurnsNonViable(state, shownChoices=200, smallLimit=4) {
      const candidateLists = {};
      for (const ci in state.clues) {
        candidateLists[ci] = (state.clues[ci].lChoices || []).slice();
      }
      for (const ci in state.clues) {
        const clue = state.clues[ci];
        if (clue.parentClueIndex || !clue.solution ||
            !clue.solution.includes('?')) continue;
        const cells = this.getAllCells(ci, state.clues);
        const letterSets = cells.map(() => ({}));
        for (const choice of candidateLists[ci].slice(0, shownChoices)) {
          const key = this.ctx.keyForIndex(choice);
          for (let i = 0; i < key.length; i++) letterSets[i][key[i]] = true;
        }
        for (let i = 0; i < cells.length; i++) {
          const cell = state.grid[cells[i][0]][cells[i][1]];
          if (cell.solution != '?') continue;
          const intersection = {};
          for (const letter in letterSets[i]) {
            if (cell.cChoices[letter]) intersection[letter] = true;
          }
          cell.cChoices = intersection;
        }
      }
      for (const ci in state.clues) {
        const clue = state.clues[ci];
        const choices = candidateLists[ci];
        if (clue.parentClueIndex || !clue.solution ||
            !clue.solution.includes('?') || choices.length > smallLimit) {
          continue;
        }
        const cells = this.getAllCells(ci, state.clues);
        const anyViable = choices.some(choice => {
          const key = this.ctx.keyForIndex(choice);
          return key.length == cells.length && key.every((letter, i) => {
            const cell = state.grid[cells[i][0]][cells[i][1]];
            return cell.solution != '?' || cell.cChoices[letter];
          });
        });
        if (choices.length && !anyViable) return true;
      }
      return false;
    }
    choiceCreatesDeadend(state, ci, choice) {
      const cells = this.getAllCells(ci, state.clues);
      const key = this.ctx.keyForIndex(choice);
      if (key.length != cells.length) return true;
      const candidate = new ExetFillStateCore(state);
      for (let i = 0; i < cells.length; i++) {
        candidate.grid[cells[i][0]][cells[i][1]].cChoices = {[key[i]]: true};
      }
      return this.someClueTurnsNonViable(candidate);
    }
    pangramCell(state, row, col, options) {
      const cell = state.grid[row][col];
      if (!cell.isLight) return false;
      if (options.pangramAll) return true;
      if (options.pangramCircled && cell.hasCircle) return true;
      const lights = Number(!!cell.acrossClueLabel) +
          Number(!!cell.downClueLabel) + Number(!!cell.z3dClueLabel);
      if (options.pangramChecked && lights > 1) return true;
      if (options.pangramUnchecked && lights == 1) return true;
      if (!options.pangramFirsts && !options.pangramLasts) return false;
      const firsts = [];
      if (cell.startsAcrossClue) firsts.push('A' + cell.startsClueLabel);
      if (cell.startsDownClue) firsts.push('D' + cell.startsClueLabel);
      if (cell.startsZ3dClue) firsts.push('Z' + cell.startsClueLabel);
      const lasts = [];
      if (cell.endsAcrossClue) lasts.push('A' + cell.endsAcrossClue);
      if (cell.endsDownClue) lasts.push('D' + cell.endsDownClue);
      if (cell.endsZ3dClue) lasts.push('Z' + cell.endsZ3dClue);
      return (options.pangramFirsts && firsts.length > 0) ||
          (options.pangramLasts && lasts.length > 0);
    }
    score(state, options) {
      state.scoreF = 0;
      state.scoreV = 0;
      state.scoreP = 0;
      state.score = 0;
      state.unfilled = [];
      state.lettersUsed = {};
      state.constrLetters = {};
      state.reversals = 0;
      let entries = 0;
      for (const ci in state.clues) {
        const clue = state.clues[ci];
        if (clue.lChoices.length == 1 && clue.lChoices[0] < 0) state.reversals++;
        if (clue.parentClueIndex) continue;
        if (clue.lChoices.length) {
          const index = Math.abs(clue.lChoices[0]);
          state.scoreP += state.preflexUsed.has(index) ? 1 :
              Math.max(0, Math.min(1, this.ctx.scoreForIndex(index) / 100));
        }
        entries++;
      }
      if (entries) state.scoreP /= entries;
      state.score += state.scoreP;
      let lightCells = 0;
      for (let row = 0; row < state.gridHeight; row++) {
        for (let col = 0; col < state.gridWidth; col++) {
          const cell = state.grid[row][col];
          if (!cell.isLight) continue;
          lightCells++;
          const letter = cell.solution != '?' ? cell.solution : cell.currLetter;
          if (letter && letter != '?') {
            state.lettersUsed[letter] = true;
            if (this.pangramCell(state, row, col, options)) {
              state.constrLetters[letter] = true;
            }
            continue;
          }
          if (cell.viability <= 0) {
            state.viable = false;
            state.score = -Number.MAX_VALUE;
            return;
          }
          state.scoreV += Math.log(cell.viability);
          state.unfilled.push([row, col, cell.viability]);
        }
      }
      state.numLettersUsed = Object.keys(state.lettersUsed).length;
      state.numConstrLetters = Object.keys(state.constrLetters).length;
      let rarityBoost = 0;
      if (options.boostPangram) {
        for (const letter in state.constrLetters) {
          rarityBoost += (this.ctx.letterRarities || {})[letter] || 0;
        }
      }
      if (options.boostPangram &&
          state.numConstrLetters < this.ctx.letters.length) {
        for (const candidate of state.unfilled) {
          if (!this.pangramCell(
              state, candidate[0], candidate[1], options)) {
            candidate.push(0);
            continue;
          }
          let rarity = 0;
          for (const letter in state.grid[candidate[0]][candidate[1]].cChoices) {
            if (!state.constrLetters[letter]) {
              rarity = Math.max(
                  rarity, (this.ctx.letterRarities || {})[letter] || 0);
            }
          }
          candidate.push(rarity ? rarity + 0.1 * Math.random() : 0);
        }
        state.unfilled.sort(
            (a, b) => a[3] == b[3] ? a[2] - b[2] : b[3] - a[3]);
      } else {
        state.unfilled.sort((a, b) => a[2] - b[2]);
      }
      state.scoreV /= 100;
      state.score += state.scoreV;
      state.scoreF =
          30 * (lightCells - state.unfilled.length + rarityBoost) / 100;
      state.score += state.scoreF;
    }
    hasPatternOfDeath(state) {
      for (const row of state.grid) {
        for (const cell of row) {
          if (!cell.isLight || cell.currLetter != '?' ||
              !cell.acrossClueLabel || !cell.downClueLabel) continue;
          let acrossIndex = 'A' + cell.acrossClueLabel;
          let downIndex = 'D' + cell.downClueLabel;
          let across = state.clues[acrossIndex];
          let down = state.clues[downIndex];
          if (!across || !down) continue;
          if (across.parentClueIndex) acrossIndex = across.parentClueIndex;
          if (down.parentClueIndex) downIndex = down.parentClueIndex;
          across = state.clues[acrossIndex];
          down = state.clues[downIndex];
          if (across.solution != down.solution) continue;
          const entry = ci => this.getAllCells(ci, state.clues)
              .map(([r, c]) => state.grid[r][c].currLetter).join('');
          const acrossEntry = entry(acrossIndex);
          if (acrossEntry != entry(downIndex)) continue;
          const unknown = acrossEntry.indexOf('?');
          if (unknown >= 0 &&
              !acrossEntry.slice(0, unknown).includes('?') &&
              !acrossEntry.slice(unknown + 1).includes('?')) return true;
        }
      }
      return false;
    }
  }

  root.ExetDherCore = ExetDherCore;
  root.ExetFillStateCore = ExetFillStateCore;
  root.ExetFillEngine = ExetFillEngine;
})(typeof self != 'undefined' ? self : globalThis);
