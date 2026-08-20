/**
 * Interactive Magpie annotation builder (prototype).
 */

Exet.prototype.magpieGroupColorCount = 6;

Exet.prototype.makeMagpieTab = function() {
  const tab = this.tabs['magpie'];
  if (!tab || !tab.content) {
    return;
  }
  tab.content.innerHTML = `
    <div id="xet-magpie-root" class="xet-magpie">
      <label class="xet-magpie-auto">
        <input type="checkbox" id="xet-magpie-auto-populate" />
        Auto-populate annotations
      </label>
      <div class="xet-bold">Magpie annotation builder</div>
      <div id="xet-magpie-empty" class="xet-magpie-empty" style="display:none">
        Fill the current light to use the Magpie builder.
      </div>
      <div id="xet-magpie-workspace">
        <p class="xet-magpie-help">
          Use <b>Select</b> mode to click parts or groups (shift-click to pick
          several — numbered in click order). Use <b>Split</b> mode to hover
          between letters and toggle splits. For <b>around</b> or <b>in</b>,
          shift-click two parts or groups in order (1 = outer/inner as marked).
        </p>
        <div class="xet-magpie-modes">
          <span class="xet-magpie-modes-label">Mode</span>
          <button type="button" class="xlv-small-button xet-magpie-mode-btn"
              data-magpie-mode="select">Select</button>
          <button type="button" class="xlv-small-button xet-magpie-mode-btn"
              data-magpie-mode="split">Split</button>
          <button type="button" class="xlv-small-button" id="xet-magpie-reset-splits"
              title="Remove all splits">Clear splits</button>
        </div>
        <div class="xet-magpie-answer-block">
          <div id="xet-magpie-answer" class="xet-magpie-answer"></div>
        </div>
        <div class="xet-magpie-grouping">
          <span class="xet-magpie-grouping-label">Grouping</span>
          <button type="button" class="xlv-small-button" data-magpie-op="group"
              title="Merge selected parts">Group</button>
          <button type="button" class="xlv-small-button" data-magpie-op="ungroup"
              title="Dissolve selected group">Ungroup</button>
        </div>
        <div class="xet-magpie-label">Wordplay</div>
        <div class="xet-magpie-op-section">
          <div class="xet-magpie-op-heading">Letter ops</div>
          <div class="xet-magpie-ops">
            <button type="button" class="xlv-small-button" data-magpie-op="anagram"
                title="Anagram (*)">* Anagram</button>
            <button type="button" class="xlv-small-button" data-magpie-op="reverse"
                title="Reverse (&lt;)">&lt; Reverse</button>
            <button type="button" class="xlv-small-button" data-magpie-op="homophone"
                title="Homophone (&quot;&quot;)">" Homophone</button>
            <button type="button" class="xlv-small-button" data-magpie-op="clear-op"
                title="Clear op">Clear op</button>
          </div>
        </div>
        <div class="xet-magpie-op-section">
          <div class="xet-magpie-op-heading">Acrostics</div>
          <div class="xet-magpie-ops">
            <button type="button" class="xlv-small-button" data-magpie-op="acrostic-first"
                title="First letters of successive words">First letters</button>
            <button type="button" class="xlv-small-button" data-magpie-op="acrostic-last"
                title="Last letters of successive words (telestich)">Last letters</button>
            <button type="button" class="xlv-small-button" data-magpie-op="acrostic-outside"
                title="First and last letters of successive words">Outside letters</button>
          </div>
        </div>
        <div class="xet-magpie-op-section">
          <div class="xet-magpie-op-heading">Containers</div>
          <div class="xet-magpie-ops">
            <button type="button" class="xlv-small-button" data-magpie-op="in">in</button>
            <button type="button" class="xlv-small-button" data-magpie-op="around">around</button>
            <button type="button" class="xlv-small-button" data-magpie-op="clear-composite"
                title="Back to charade (+)">Clear composite</button>
          </div>
        </div>
        <div class="xet-magpie-op-section">
          <div class="xet-magpie-op-heading">Subtract</div>
          <div class="xet-magpie-field-row">
            <input type="text" id="xet-magpie-subtract-a" class="xet-magpie-word-input"
                placeholder="WORD" spellcheck="false" />
            <span class="xet-magpie-field-label">minus</span>
            <input type="text" id="xet-magpie-subtract-b" class="xet-magpie-word-input"
                placeholder="WORD" spellcheck="false" />
            <label class="xet-magpie-field-check">
              <input type="checkbox" id="xet-magpie-subtract-anagram" />
              Anagram
            </label>
          </div>
        </div>
        <div class="xet-magpie-op-section">
          <div class="xet-magpie-op-heading">Hidden</div>
          <div class="xet-magpie-field-row xet-magpie-hidden-row">
            <span class="xet-magpie-field-paren">(</span>
            <input type="text" id="xet-magpie-hidden-before" class="xet-magpie-word-input"
                placeholder="WORD" spellcheck="false" />
            <span class="xet-magpie-field-paren">)</span>
            <span id="xet-magpie-hidden-answer" class="xet-magpie-hidden-answer"></span>
            <span class="xet-magpie-field-paren">(</span>
            <input type="text" id="xet-magpie-hidden-after" class="xet-magpie-word-input"
                placeholder="WORD" spellcheck="false" />
            <span class="xet-magpie-field-paren">)</span>
          </div>
        </div>
        <div class="xet-magpie-op-section">
          <div class="xet-magpie-op-heading">Clue type</div>
          <div class="xet-magpie-ops">
            <button type="button" class="xlv-small-button" data-magpie-op="2defs">2 defs</button>
            <button type="button" class="xlv-small-button" data-magpie-op="andlit">&amp;lit</button>
          </div>
        </div>
        <div class="xet-magpie-label">Preview</div>
        <div id="xet-magpie-preview" class="xet-magpie-preview"></div>
        <div class="xet-magpie-actions">
          <button type="button" class="xlv-small-button" id="xet-magpie-apply">
            Apply to optional anno →</button>
          <button type="button" class="xlv-small-button" id="xet-magpie-copy">
            Copy preview</button>
        </div>
      </div>
    </div>`;

  this.magpieRoot = document.getElementById('xet-magpie-root');
  this.magpieAnswer = document.getElementById('xet-magpie-answer');
  this.magpiePreview = document.getElementById('xet-magpie-preview');
  this.magpieEmpty = document.getElementById('xet-magpie-empty');
  this.magpieWorkspace = document.getElementById('xet-magpie-workspace');
  this.magpieAutoPopulate = document.getElementById('xet-magpie-auto-populate');
  this.magpieAutoPopulate.checked = !!exetState.magpieAutoPopulate;
  this.magpieAutoPopulate.addEventListener('change', () => {
    exetState.magpieAutoPopulate = this.magpieAutoPopulate.checked;
    exetRevManager.saveLocal(exetRevManager.SPECIAL_KEY, JSON.stringify(exetState));
    if (exetState.magpieAutoPopulate) {
      this.magpieMaybeAutoApply();
    }
  });

  this.magpieAnswer.addEventListener('click', this.handleMagpieClick.bind(this));
  document.getElementById('xet-magpie-reset-splits').addEventListener(
      'click', () => this.magpieResetSplits());
  document.getElementById('xet-magpie-apply').addEventListener(
      'click', () => this.magpieApplyToAnno());
  document.getElementById('xet-magpie-copy').addEventListener(
      'click', () => this.magpieCopyPreview());

  for (const btn of this.magpieRoot.querySelectorAll('[data-magpie-mode]')) {
    btn.addEventListener('click', () => {
      this.magpieSetMode(btn.getAttribute('data-magpie-mode'));
    });
  }
  for (const btn of this.magpieRoot.querySelectorAll('[data-magpie-op]')) {
    btn.addEventListener('click', () => {
      this.magpieApplyOp(btn.getAttribute('data-magpie-op'));
    });
  }

  this.magpieSubtractA = document.getElementById('xet-magpie-subtract-a');
  this.magpieSubtractB = document.getElementById('xet-magpie-subtract-b');
  this.magpieSubtractAnagram = document.getElementById('xet-magpie-subtract-anagram');
  this.magpieHiddenBefore = document.getElementById('xet-magpie-hidden-before');
  this.magpieHiddenAfter = document.getElementById('xet-magpie-hidden-after');
  this.magpieHiddenAnswer = document.getElementById('xet-magpie-hidden-answer');
  this.magpieApplyBtn = document.getElementById('xet-magpie-apply');
  for (const input of [
    this.magpieSubtractA, this.magpieSubtractB,
    this.magpieHiddenBefore, this.magpieHiddenAfter,
  ]) {
    input.addEventListener('input', () => this.magpieOnFieldInput());
  }
  this.magpieSubtractAnagram.addEventListener(
      'change', () => this.magpieOnFieldInput());
};

Exet.prototype.magpieOnFieldInput = function() {
  const st = this.magpieGetState();
  if (!st) {
    return;
  }
  st.subtractA = this.magpieSubtractA.value;
  st.subtractB = this.magpieSubtractB.value;
  st.subtractAnagram = this.magpieSubtractAnagram.checked;
  st.hiddenBefore = this.magpieHiddenBefore.value;
  st.hiddenAfter = this.magpieHiddenAfter.value;
  if (st.subtractA.trim() || st.subtractB.trim() ||
      st.hiddenBefore.trim() || st.hiddenAfter.trim()) {
    st.composite = null;
    st.acrostic = null;
  }
  this.magpieRefreshPreview();
};

Exet.prototype.magpieSyncFieldInputs = function(st) {
  if (!st || !this.magpieSubtractA) {
    return;
  }
  this.magpieSubtractA.value = st.subtractA || '';
  this.magpieSubtractB.value = st.subtractB || '';
  this.magpieSubtractAnagram.checked = !!st.subtractAnagram;
  this.magpieHiddenBefore.value = st.hiddenBefore || '';
  this.magpieHiddenAfter.value = st.hiddenAfter || '';
  if (this.magpieHiddenAnswer) {
    this.magpieHiddenAnswer.textContent = st.answer || '';
  }
};

Exet.prototype.magpieClearFieldInputs = function(st) {
  if (!st) {
    return;
  }
  st.subtractA = '';
  st.subtractB = '';
  st.subtractAnagram = false;
  st.hiddenBefore = '';
  st.hiddenAfter = '';
  this.magpieSyncFieldInputs(st);
};

Exet.prototype.magpieRefreshPreview = function() {
  if (!this.magpiePreview) {
    return;
  }
  this.magpiePreview.textContent = this.magpiePreviewText();
  this.magpieMaybeAutoApply();
};

Exet.prototype.magpieSetMode = function(mode) {
  const st = this.magpieGetState();
  if (!st || (mode != 'select' && mode != 'split')) {
    return;
  }
  st.mode = mode;
  this.magpieRender();
};

Exet.prototype.magpieFindGroup = function(st, groupId) {
  if (!st || !st.groups) {
    return null;
  }
  return st.groups.find(g => g.id == groupId) || null;
};

Exet.prototype.magpieFindGroupForPart = function(st, partIndex) {
  if (!st || !st.groups) {
    return null;
  }
  return st.groups.find(g => g.partIndices.indexOf(partIndex) >= 0) || null;
};

Exet.prototype.magpieGroupColorClass = function(group) {
  if (!group) {
    return '';
  }
  const c = group.id % this.magpieGroupColorCount;
  return ' xet-magpie-group-c' + c;
};

Exet.prototype.magpieDefaultGroupFodder = function(st, partIndices) {
  return partIndices.slice().sort((a, b) => a - b)
      .map(i => st.answer.slice(st.parts[i].start, st.parts[i].end))
      .join('');
};

Exet.prototype.magpieReverseText = function(text) {
  return text.split('').reverse().join('');
};

Exet.prototype.magpieFormatGroup = function(group, st) {
  if (!group) {
    return '';
  }
  let text = group.fodder || this.magpieDefaultGroupFodder(st, group.partIndices);
  if (group.op == 'homophone') {
    return '"' + text + '"';
  }
  if (group.op == 'anagram') {
    return text + '*';
  }
  if (group.op == 'reverse') {
    return this.magpieReverseText(text) + '<';
  }
  return text;
};

Exet.prototype.magpieCreateGroup = function(st, partIndices) {
  const indices = partIndices.slice().sort((a, b) => a - b);
  if (indices.length < 2) {
    return;
  }
  st.groups = (st.groups || []).filter(g => {
    return !g.partIndices.some(i => indices.indexOf(i) >= 0);
  });
  const id = st.nextGroupId || 0;
  st.nextGroupId = id + 1;
  st.groups.push({
    id: id,
    partIndices: indices,
    fodder: this.magpieDefaultGroupFodder(st, indices),
    op: null,
  });
  st.selected = [{kind: 'group', id: id}];
  st.composite = null;
};

Exet.prototype.magpieDissolveGroup = function(st, groupId) {
  st.groups = (st.groups || []).filter(g => g.id != groupId);
  st.selected = [];
  st.composite = null;
};

Exet.prototype.magpieSelectionKey = function(item) {
  return item.kind + ':' + (item.kind == 'group' ? item.id : item.index);
};

Exet.prototype.magpieSelectionIndex = function(st, item) {
  const key = this.magpieSelectionKey(item);
  for (let i = 0; i < st.selected.length; i++) {
    if (this.magpieSelectionKey(st.selected[i]) == key) {
      return i;
    }
  }
  return -1;
};

Exet.prototype.magpieOrderBadgeForPart = function(st, partIndex) {
  for (let i = 0; i < st.selected.length; i++) {
    const sel = st.selected[i];
    if (sel.kind == 'part' && sel.index == partIndex) {
      return i + 1;
    }
    if (sel.kind == 'group') {
      const group = this.magpieFindGroup(st, sel.id);
      if (group && group.partIndices.indexOf(partIndex) >= 0) {
        const first = Math.min.apply(null, group.partIndices);
        if (partIndex == first) {
          return i + 1;
        }
      }
    }
  }
  return 0;
};

Exet.prototype.magpiePartIsSelected = function(st, partIndex) {
  for (const sel of st.selected) {
    if (sel.kind == 'part' && sel.index == partIndex) {
      return true;
    }
    if (sel.kind == 'group') {
      const group = this.magpieFindGroup(st, sel.id);
      if (group && group.partIndices.indexOf(partIndex) >= 0) {
        return true;
      }
    }
  }
  return false;
};

Exet.prototype.magpieFormatSelectionItem = function(st, item) {
  if (!item) {
    return '';
  }
  if (item.kind == 'group') {
    return this.magpieFormatGroup(this.magpieFindGroup(st, item.id), st);
  }
  const part = st.parts[item.index];
  if (!part) {
    return '';
  }
  return this.magpieFormatPart(part);
};

Exet.prototype.magpieCharadeTokens = function(st) {
  const emitted = new Set();
  const tokens = [];
  for (let i = 0; i < st.parts.length; i++) {
    const group = this.magpieFindGroupForPart(st, i);
    if (group) {
      if (emitted.has(group.id)) {
        continue;
      }
      emitted.add(group.id);
      tokens.push(this.magpieFormatGroup(group, st));
    } else {
      tokens.push(this.magpieFormatPart(st.parts[i]));
    }
  }
  return tokens;
};

Exet.prototype.magpieDefaultState = function(answer) {
  return {
    answer: answer,
    mode: 'select',
    splits: [],
    parts: this.magpieBuildParts(answer, []),
    groups: [],
    nextGroupId: 0,
    selected: [],
    composite: null,
    subtractA: '',
    subtractB: '',
    subtractAnagram: false,
    hiddenBefore: '',
    hiddenAfter: '',
    twoDefs: false,
    andLit: false,
    acrostic: null,
  };
};

Exet.prototype.magpieAcrosticSuffix = function(kind) {
  if (kind == 'first') {
    return 'from first letters';
  }
  if (kind == 'last') {
    return 'from last letters';
  }
  if (kind == 'outside') {
    return 'from outside letters';
  }
  return '';
};

Exet.prototype.magpieSetAcrostic = function(st, kind) {
  if (!st) {
    return;
  }
  if (st.acrostic == kind) {
    st.acrostic = null;
  } else {
    st.acrostic = kind;
    st.composite = null;
    st.twoDefs = false;
    st.andLit = false;
    this.magpieClearFieldInputs(st);
  }
};

Exet.prototype.magpieBuildParts = function(answer, splits) {
  const sorted = splits.slice().sort((a, b) => a - b);
  const parts = [];
  let start = 0;
  for (const split of sorted) {
    if (split <= start || split >= answer.length) {
      continue;
    }
    parts.push(this.magpieNewPart(answer, start, split));
    start = split;
  }
  parts.push(this.magpieNewPart(answer, start, answer.length));
  return parts;
};

Exet.prototype.magpieNewPart = function(answer, start, end) {
  return {
    start: start,
    end: end,
    fodder: answer.slice(start, end),
    op: null,
  };
};

Exet.prototype.magpieMigrateState = function(st) {
  if (!st.groups) {
    st.groups = [];
  }
  if (st.nextGroupId == null) {
    st.nextGroupId = 0;
  }
  if (!st.mode) {
    st.mode = 'select';
  }
  if (st.selected && st.selected.length && typeof st.selected[0] == 'number') {
    const migrated = [];
    for (const idx of st.selected) {
      migrated.push({kind: 'part', index: idx});
    }
    st.selected = migrated;
  } else if (!st.selected) {
    st.selected = [];
  }
  if (st.selectedGroup != null) {
    st.selected = [{kind: 'group', id: st.selectedGroup}];
    delete st.selectedGroup;
  }
  if (st.composite && st.composite.customOuter) {
    st.composite = null;
  } else if (st.composite && st.composite.type == 'subtract') {
    st.composite = null;
  } else if (st.composite && typeof st.composite.a == 'number') {
    st.composite = {
      type: st.composite.type,
      a: {kind: 'part', index: st.composite.a},
      b: {kind: 'part', index: st.composite.b},
    };
  }
  for (const part of st.parts || []) {
    delete part.deletions;
  }
  if (st.subtractA == null) {
    st.subtractA = '';
  }
  if (st.subtractB == null) {
    st.subtractB = '';
  }
  if (st.subtractAnagram == null) {
    st.subtractAnagram = false;
  }
  if (st.hiddenBefore == null) {
    st.hiddenBefore = '';
  }
  if (st.hiddenAfter == null) {
    st.hiddenAfter = '';
  }
  if (st.acrostic === undefined) {
    st.acrostic = null;
  }
};

Exet.prototype.magpieGetState = function() {
  const theClue = this.currClue();
  if (!theClue || !theClue._magpieBuilder) {
    return null;
  }
  this.magpieMigrateState(theClue._magpieBuilder);
  return theClue._magpieBuilder;
};

Exet.prototype.magpieEnsureState = function(answer) {
  const theClue = this.currClue();
  if (!theClue) {
    return null;
  }
  const clean = (answer || '').toUpperCase();
  if (!theClue._magpieBuilder || theClue._magpieBuilder.answer != clean) {
    theClue._magpieBuilder = this.magpieDefaultState(clean);
  }
  return theClue._magpieBuilder;
};

Exet.prototype.updateMagpieTab = function() {
  if (!this.magpieAnswer) {
    return;
  }
  const theClue = this.currClue();
  let answer = theClue ? (theClue.solution || '') : '';
  answer = answer.replace(/\?/g, '').toUpperCase().trim();
  const hasAnswer = answer.length > 0 && answer.indexOf('?') < 0;

  this.magpieEmpty.style.display = hasAnswer ? 'none' : '';
  this.magpieWorkspace.style.display = hasAnswer ? '' : 'none';

  if (!hasAnswer) {
    this.magpiePreview.textContent = '';
    return;
  }
  this.magpieEnsureState(answer);
  this.magpieRender();
};

Exet.prototype.magpieResetSplits = function() {
  const st = this.magpieGetState();
  if (!st) {
    return;
  }
  st.splits = [];
  st.parts = this.magpieBuildParts(st.answer, st.splits);
  st.groups = [];
  st.nextGroupId = 0;
  st.selected = [];
  st.composite = null;
  st.twoDefs = false;
  st.andLit = false;
  st.acrostic = null;
  this.magpieClearFieldInputs(st);
  this.magpieRender();
};

Exet.prototype.magpieInheritPartProps = function(np, oldParts) {
  let exact = null;
  const contained = [];
  for (const op of oldParts) {
    if (op.start == np.start && op.end == np.end) {
      exact = op;
      break;
    }
    if (op.start >= np.start && op.end <= np.end) {
      contained.push(op);
    }
  }
  if (exact) {
    np.fodder = exact.fodder;
    np.op = exact.op;
    return;
  }
  const withOps = contained.filter(p => p.op);
  if (withOps.length == 0) {
    return;
  }
  const firstOp = withOps[0].op;
  if (withOps.length == 1 || withOps.every(p => p.op == firstOp)) {
    np.op = firstOp;
  }
};

Exet.prototype.magpieToggleSplit = function(index) {
  const st = this.magpieGetState();
  if (!st || index <= 0 || index >= st.answer.length) {
    return;
  }
  const pos = st.splits.indexOf(index);
  if (pos >= 0) {
    st.splits.splice(pos, 1);
  } else {
    st.splits.push(index);
    st.splits.sort((a, b) => a - b);
  }
  const oldParts = st.parts;
  st.parts = this.magpieBuildParts(st.answer, st.splits);
  for (let i = 0; i < st.parts.length; i++) {
    this.magpieInheritPartProps(st.parts[i], oldParts);
  }
  st.composite = null;
  st.groups = [];
  st.nextGroupId = 0;
  st.selected = [];
  this.magpieRender();
};

Exet.prototype.magpieSelectPart = function(partIndex, extend) {
  const st = this.magpieGetState();
  if (!st || partIndex < 0 || partIndex >= st.parts.length) {
    return;
  }
  const group = this.magpieFindGroupForPart(st, partIndex);
  const item = group ?
      {kind: 'group', id: group.id} :
      {kind: 'part', index: partIndex};
  if (extend) {
    const pos = this.magpieSelectionIndex(st, item);
    if (pos >= 0) {
      st.selected.splice(pos, 1);
    } else {
      st.selected.push(item);
    }
  } else {
    st.selected = [item];
  }
  this.magpieRender();
};

Exet.prototype.handleMagpieClick = function(ev) {
  const el = ev.target.closest('[data-magpie-action]');
  if (!el) {
    return;
  }
  const st = this.magpieGetState();
  if (!st) {
    return;
  }
  const action = el.getAttribute('data-magpie-action');
  if (action == 'split') {
    if (st.mode != 'split') {
      return;
    }
    ev.preventDefault();
    ev.stopPropagation();
    this.magpieToggleSplit(parseInt(el.getAttribute('data-split'), 10));
    return;
  }
  if (st.mode != 'select') {
    return;
  }
  ev.preventDefault();
  if (action == 'part') {
    this.magpieSelectPart(parseInt(el.getAttribute('data-part'), 10), ev.shiftKey);
  }
};

Exet.prototype.magpieApplyOp = function(op) {
  const st = this.magpieGetState();
  if (!st) {
    return;
  }
  if (op == '2defs') {
    st.twoDefs = !st.twoDefs;
    if (st.twoDefs) {
      st.andLit = false;
      st.composite = null;
      st.acrostic = null;
    }
    this.magpieRender();
    return;
  }
  if (op == 'andlit') {
    st.andLit = !st.andLit;
    if (st.andLit) {
      st.twoDefs = false;
      st.acrostic = null;
    }
    this.magpieRender();
    return;
  }
  if (op == 'acrostic-first') {
    this.magpieSetAcrostic(st, 'first');
    this.magpieRender();
    return;
  }
  if (op == 'acrostic-last') {
    this.magpieSetAcrostic(st, 'last');
    this.magpieRender();
    return;
  }
  if (op == 'acrostic-outside') {
    this.magpieSetAcrostic(st, 'outside');
    this.magpieRender();
    return;
  }
  if (op == 'clear-composite') {
    st.composite = null;
    this.magpieRender();
    return;
  }
  if (op == 'group') {
    const partIndices = st.selected
        .filter(s => s.kind == 'part')
        .map(s => s.index);
    if (partIndices.length < 2) {
      return;
    }
    this.magpieCreateGroup(st, partIndices);
    this.magpieRender();
    return;
  }
  if (op == 'ungroup') {
    if (st.selected.length != 1 || st.selected[0].kind != 'group') {
      return;
    }
    this.magpieDissolveGroup(st, st.selected[0].id);
    this.magpieRender();
    return;
  }
  if (op == 'in' || op == 'around') {
    if (st.selected.length != 2) {
      return;
    }
    if (this.magpieSelectionKey(st.selected[0]) ==
        this.magpieSelectionKey(st.selected[1])) {
      return;
    }
    st.composite = {type: op, a: st.selected[0], b: st.selected[1]};
    this.magpieClearFieldInputs(st);
    st.twoDefs = false;
    st.acrostic = null;
    this.magpieRender();
    return;
  }
  if (st.selected.length != 1) {
    return;
  }
  if (st.selected[0].kind == 'group') {
    const group = this.magpieFindGroup(st, st.selected[0].id);
    if (!group) {
      return;
    }
    if (op == 'clear-op') {
      group.op = null;
    } else if (op == 'anagram' || op == 'reverse' || op == 'homophone') {
      group.op = op;
      st.composite = null;
      st.twoDefs = false;
      st.acrostic = null;
    }
    this.magpieRender();
    return;
  }
  const part = st.parts[st.selected[0].index];
  if (op == 'clear-op') {
    part.op = null;
  } else if (op == 'anagram' || op == 'reverse' || op == 'homophone') {
    part.op = op;
    st.composite = null;
    st.twoDefs = false;
    st.acrostic = null;
  }
  this.magpieRender();
};

Exet.prototype.magpieFormatPart = function(part) {
  let text = part.fodder || '';
  if (part.op == 'homophone') {
    return '"' + text + '"';
  }
  if (part.op == 'anagram') {
    return text + '*';
  }
  if (part.op == 'reverse') {
    return this.magpieReverseText(text) + '<';
  }
  return text;
};

Exet.prototype.magpiePreviewFromState = function(st) {
  if (!st) {
    return '';
  }
  if (st.twoDefs) {
    return '[2 defs]';
  }
  const acrosticSuffix = this.magpieAcrosticSuffix(st.acrostic);
  if (acrosticSuffix) {
    const inner = this.magpieCharadeTokens(st).join(' + ');
    return '[' + inner + '] ' + acrosticSuffix;
  }
  let inner = '';
  const hiddenBefore = (st.hiddenBefore || '').trim();
  const hiddenAfter = (st.hiddenAfter || '').trim();
  const subtractA = (st.subtractA || '').trim();
  const subtractB = (st.subtractB || '').trim();
  if (hiddenBefore && hiddenAfter) {
    inner = '(' + hiddenBefore + ') ' + st.answer + ' (' + hiddenAfter + ')';
  } else if (subtractA && subtractB) {
    inner = subtractA + (st.subtractAnagram ? '*' : '') + ' − ' + subtractB;
  } else if (st.composite) {
    const pa = this.magpieFormatSelectionItem(st, st.composite.a);
    const pb = this.magpieFormatSelectionItem(st, st.composite.b);
    if (st.composite.type == 'in') {
      inner = pa + ' in ' + pb;
    } else if (st.composite.type == 'around') {
      inner = pa + ' around ' + pb;
    }
  } else {
    inner = this.magpieCharadeTokens(st).join(' + ');
  }
  if (st.andLit) {
    inner += ', &lit';
  }
  return '[' + inner + ']';
};

Exet.prototype.magpiePreviewText = function() {
  return this.magpiePreviewFromState(this.magpieGetState());
};

Exet.prototype.magpieRender = function() {
  const st = this.magpieGetState();
  if (!st || !this.magpieAnswer) {
    return;
  }

  const splitMode = st.mode == 'split';
  this.magpieAnswer.className = 'xet-magpie-answer' +
      (splitMode ? ' xet-magpie-mode-split' : ' xet-magpie-mode-select');

  for (const btn of this.magpieRoot.querySelectorAll('[data-magpie-mode]')) {
    const active = btn.getAttribute('data-magpie-mode') == st.mode;
    btn.classList.toggle('xet-magpie-mode-active', active);
  }

  let html = '';
  const parts = st.parts;
  for (let p = 0; p < parts.length; p++) {
    const part = parts[p];
    const group = this.magpieFindGroupForPart(st, p);
    const selected = this.magpiePartIsSelected(st, p);
    const groupClass = group ? this.magpieGroupColorClass(group) : '';
    const orderBadge = this.magpieOrderBadgeForPart(st, p);
    html += `<span class="xet-magpie-chunk${selected ? ' xet-magpie-chunk-selected' : ''}${groupClass}"
        data-magpie-action="part" data-part="${p}">`;
    if (orderBadge) {
      html += `<span class="xet-magpie-order-badge">${orderBadge}</span>`;
    }
    const text = st.answer.slice(part.start, part.end);
    for (let i = 0; i < text.length; i++) {
      const ch = text[i];
      const isSpace = ch == ' ';
      const letterClass = 'xet-magpie-letter' +
          (isSpace ? ' xet-magpie-letter-space' : '');
      html += `<span class="${letterClass}" data-magpie-action="part"
          data-part="${p}">${ch == ' ' ? '·' : ch}</span>`;
      const splitIndex = part.start + i + 1;
      if (splitMode && splitIndex < st.answer.length) {
        let hideGutter = false;
        if (splitIndex == part.end && group) {
          const nextPart = p + 1;
          if (nextPart < parts.length &&
              group.partIndices.indexOf(p) >= 0 &&
              group.partIndices.indexOf(nextPart) >= 0) {
            hideGutter = true;
          }
        }
        if (!hideGutter) {
          const splitHere = st.splits.indexOf(splitIndex) >= 0;
          html += `<span class="xet-magpie-slot">
              <button type="button" class="xet-magpie-gutter${splitHere ? ' xet-magpie-gutter-on' : ''}"
                  data-magpie-action="split" data-split="${splitIndex}">+</button>
            </span>`;
        }
      }
    }
    html += '</span>';
  }
  this.magpieAnswer.innerHTML = html;

  this.magpieSyncFieldInputs(st);
  this.magpiePreview.textContent = this.magpiePreviewText();

  for (const btn of this.magpieRoot.querySelectorAll('[data-magpie-op="2defs"]')) {
    btn.classList.toggle('xet-magpie-op-active', st.twoDefs);
  }
  for (const btn of this.magpieRoot.querySelectorAll('[data-magpie-op="andlit"]')) {
    btn.classList.toggle('xet-magpie-op-active', st.andLit);
  }
  for (const btn of this.magpieRoot.querySelectorAll('[data-magpie-op="acrostic-first"]')) {
    btn.classList.toggle('xet-magpie-op-active', st.acrostic == 'first');
  }
  for (const btn of this.magpieRoot.querySelectorAll('[data-magpie-op="acrostic-last"]')) {
    btn.classList.toggle('xet-magpie-op-active', st.acrostic == 'last');
  }
  for (const btn of this.magpieRoot.querySelectorAll('[data-magpie-op="acrostic-outside"]')) {
    btn.classList.toggle('xet-magpie-op-active', st.acrostic == 'outside');
  }

  const annoLocked = exet.isAnnoLocked();
  if (this.magpieApplyBtn) {
    this.magpieApplyBtn.title = annoLocked ?
        'Optional anno is locked — unlock it before applying' : '';
  }

  this.magpieMaybeAutoApply();
};

Exet.prototype.magpieMaybeAutoApply = function() {
  if (!exetState.magpieAutoPopulate) {
    return;
  }
  if (exet.isAnnoLocked()) {
    return;
  }
  const preview = this.magpiePreviewText();
  if (!preview) {
    return;
  }
  const anno = document.getElementById('xet-anno');
  if (!anno) {
    return;
  }
  if (anno.innerText.trim() == preview) {
    return;
  }
  anno.innerText = preview;
  this.handleClueChange();
};

Exet.prototype.magpieApplyToAnno = function() {
  const preview = this.magpiePreviewText();
  if (!preview) {
    return;
  }
  if (exet.isAnnoLocked()) {
    alert('Cannot apply: the optional annotation is locked. ' +
        'Click 🔓 to unlock it first.');
    return;
  }
  const anno = document.getElementById('xet-anno');
  if (!anno) {
    return;
  }
  if (anno.innerText.trim() == preview) {
    return;
  }
  anno.innerText = preview;
  this.handleClueChange();
};

Exet.prototype.magpieCopyPreview = function() {
  const preview = this.magpiePreviewText();
  if (!preview) {
    return;
  }
  navigator.clipboard.writeText(preview).catch(() => {
    window.prompt('Copy Magpie preview:', preview);
  });
};
