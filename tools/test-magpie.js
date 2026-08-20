#!/usr/bin/env node
/**
 * Magpie annotation builder tests.
 *
 * Run from the exet directory:
 *   node tools/test-magpie.js
 */

const fs = require('fs');
const path = require('path');
const vm = require('vm');

function Exet() {}
const context = {Exet, console};
vm.createContext(context);
vm.runInContext(
    fs.readFileSync(path.join(__dirname, '..', 'exet-magpie.js'), 'utf8'),
    context);

const proto = Exet.prototype;
let passed = 0;
let failed = 0;

function assertEqual(actual, expected, name) {
  if (actual === expected) {
    passed++;
    return;
  }
  failed++;
  console.error(`FAIL: ${name}`);
  console.error(`  expected: ${JSON.stringify(expected)}`);
  console.error(`  actual:   ${JSON.stringify(actual)}`);
}

function assertOk(cond, name) {
  if (cond) {
    passed++;
    return;
  }
  failed++;
  console.error(`FAIL: ${name}`);
}

function makeHarness(answer) {
  const exet = Object.create(proto);
  const st = exet.magpieDefaultState(answer);
  exet.currClue = () => ({_magpieBuilder: st});
  exet.magpieRender = () => {};
  exet.magpieRoot = {querySelectorAll: () => []};
  exet.magpieAnswer = null;
  return {exet, st};
}

function splitState(exet, st, answer, splitIndices) {
  st.splits = splitIndices.slice().sort((a, b) => a - b);
  st.parts = exet.magpieBuildParts(answer, st.splits);
}

function part(answer, start, end, op) {
  return {start, end, fodder: answer.slice(start, end), op: op || null};
}

function preview(exet, st) {
  return exet.magpiePreviewFromState(st);
}

function select(exet, st, partIndex, extend) {
  exet.magpieSelectPart(partIndex, !!extend);
}

console.log('Magpie tests\n');

// --- Letter ops ---
assertEqual(proto.magpieReverseText('CASE'), 'ESAC', 'reverse text');
assertEqual(proto.magpieReverseText('A'), 'A', 'reverse single letter');
assertEqual(proto.magpieReverseText(''), '', 'reverse empty');
assertEqual(proto.magpieReverseText('BOB'), 'BOB', 'reverse palindrome');

{
  const {exet, st} = makeHarness('PARS');
  st.parts[0].op = 'anagram';
  assertEqual(exet.magpieFormatPart(st.parts[0]), 'PARS*', 'format part anagram');
}

{
  const {exet, st} = makeHarness('CASE');
  st.parts[0].op = 'reverse';
  assertEqual(exet.magpieFormatPart(st.parts[0]), 'ESAC<', 'format part reverse');
}

{
  const {exet, st} = makeHarness('KNIGHT');
  st.parts[0].op = 'homophone';
  assertEqual(exet.magpieFormatPart(st.parts[0]), '"KNIGHT"', 'format part homophone');
}

{
  const {exet, st} = makeHarness('AB');
  splitState(exet, st, 'AB', [1]);
  st.groups = [{id: 0, partIndices: [0, 1], fodder: 'AB', op: 'reverse'}];
  assertEqual(
      exet.magpieFormatGroup(st.groups[0], st), 'BA<', 'format group reverse');
}

// --- Charades ---
{
  const {exet, st} = makeHarness('NUANCED');
  splitState(exet, st, 'NUANCED', [2, 5]);
  assertEqual(preview(exet, st), '[NU + ANC + ED]', 'charade from splits');
}

{
  const {exet, st} = makeHarness('A');
  assertEqual(preview(exet, st), '[A]', 'single-letter charade');
}

{
  const {exet, st} = makeHarness('PAR SNIP');
  splitState(exet, st, 'PAR SNIP', [3, 4]);
  assertEqual(preview(exet, st), '[PAR +   + SNIP]', 'charade with space part');
}

{
  const {exet, st} = makeHarness('ABCDEF');
  splitState(exet, st, 'ABCDEF', [3, 5]);
  st.parts[0].op = 'anagram';
  st.parts[2].op = 'homophone';
  assertEqual(preview(exet, st), '[ABC* + DE + "F"]', 'ops on split charade parts');
}

{
  const {exet, st} = makeHarness('ABCD');
  splitState(exet, st, 'ABCD', [1, 2, 3]);
  assertEqual(preview(exet, st), '[A + B + C + D]', 'four-way charade');
}

{
  const {exet, st} = makeHarness('WORD');
  st.parts = [part('WORD', 0, 2, null), part('WORD', 2, 4, 'reverse')];
  assertEqual(preview(exet, st), '[WO + DR<]', 'mixed charade letter ops');
}

// --- Grouping ---
{
  const {exet, st} = makeHarness('NUANCED');
  splitState(exet, st, 'NUANCED', [2, 5]);
  st.groups = [{
    id: 0, partIndices: [0, 2], fodder: 'NUED', op: 'anagram',
  }];
  assertEqual(preview(exet, st), '[NUED* + ANC]', 'grouped anagram charade');
}

{
  const {exet, st} = makeHarness('ABCD');
  splitState(exet, st, 'ABCD', [1, 2, 3]);
  st.selected = [{kind: 'part', index: 0}, {kind: 'part', index: 2}];
  exet.magpieApplyOp('group');
  assertEqual(st.groups[0].fodder, 'AC', 'group non-adjacent parts');
}

{
  const {exet, st} = makeHarness('ABCD');
  splitState(exet, st, 'ABCD', [2]);
  st.groups = [{id: 0, partIndices: [0, 1], fodder: 'AB', op: null}];
  st.selected = [{kind: 'part', index: 0}, {kind: 'part', index: 1}];
  exet.magpieApplyOp('group');
  assertEqual(st.groups.length, 1, 'regroup replaces overlapping group');
  assertEqual(st.groups[0].partIndices.join(','), '0,1', 'regroup indices');
}

{
  const {exet, st} = makeHarness('ABCDEF');
  splitState(exet, st, 'ABCDEF', [2, 4]);
  st.groups = [
    {id: 0, partIndices: [0, 1], fodder: 'ABCD', op: 'anagram'},
    {id: 1, partIndices: [2], fodder: 'EF', op: null},
  ];
  assertEqual(
      preview(exet, st), '[ABCD* + EF]', 'two groups in charade no dup tokens');
}

// --- Containers (continued) ---
{
  const {exet, st} = makeHarness('NUANCED');
  splitState(exet, st, 'NUANCED', [2, 5]);
  st.groups = [{id: 0, partIndices: [0, 2], fodder: 'NUED', op: 'anagram'}];
  st.composite = {
    type: 'around',
    a: {kind: 'group', id: 0},
    b: {kind: 'part', index: 1},
  };
  assertEqual(preview(exet, st), '[NUED* around ANC]', 'around group and part');
}

{
  const {exet, st} = makeHarness('CATNIP');
  splitState(exet, st, 'CATNIP', [3]);
  st.composite = {
    type: 'in',
    a: {kind: 'part', index: 1},
    b: {kind: 'part', index: 0},
  };
  assertEqual(preview(exet, st), '[NIP in CAT]', 'in container');
}

{
  const {exet, st} = makeHarness('ABCD');
  splitState(exet, st, 'ABCD', [2]);
  st.groups = [
    {id: 0, partIndices: [0, 1], fodder: 'ABC', op: 'reverse'},
    {id: 1, partIndices: [2], fodder: 'D', op: 'anagram'},
  ];
  st.composite = {
    type: 'around',
    a: {kind: 'group', id: 0},
    b: {kind: 'group', id: 1},
  };
  assertEqual(preview(exet, st), '[CBA< around D*]', 'around two groups with ops');
}

{
  const {exet, st} = makeHarness('AB');
  st.composite = {
    type: 'in',
    a: {kind: 'part', index: 99},
    b: {kind: 'part', index: 0},
  };
  assertOk(
      preview(exet, st).indexOf('in') >= 0,
      'in with bad part index does not throw');
}

// --- Subtract / hidden ---
{
  const {exet, st} = makeHarness('SPARE');
  st.subtractA = 'SPARE';
  st.subtractB = 'R';
  assertEqual(preview(exet, st), '[SPARE − R]', 'subtract');
}

{
  const {exet, st} = makeHarness('SPARE');
  st.subtractA = 'SPARE';
  st.subtractB = 'R';
  st.subtractAnagram = true;
  assertEqual(preview(exet, st), '[SPARE* − R]', 'subtract with anagram');
}

{
  const {exet, st} = makeHarness('SPARE');
  st.subtractA = '  SPARE  ';
  st.subtractB = ' R ';
  assertEqual(preview(exet, st), '[SPARE − R]', 'subtract trims whitespace');
}

{
  const {exet, st} = makeHarness('SPARE');
  st.subtractA = 'SPARE';
  st.subtractB = '';
  assertEqual(preview(exet, st), '[SPARE]', 'partial subtract falls through to charade');
}

{
  const {exet, st} = makeHarness('SPARE');
  st.subtractA = 'SPARE';
  st.subtractB = '';
  st.composite = {
    type: 'around',
    a: {kind: 'part', index: 0},
    b: {kind: 'part', index: 0},
  };
  assertEqual(
      preview(exet, st), '[SPARE around SPARE]',
      'partial subtract ignored when composite set');
}

{
  const {exet, st} = makeHarness('ARC');
  st.hiddenBefore = 'BARK';
  st.hiddenAfter = 'ING';
  assertEqual(preview(exet, st), '[(BARK) ARC (ING)]', 'hidden word');
}

{
  const {exet, st} = makeHarness('ARC');
  st.hiddenBefore = '  BARK ';
  st.hiddenAfter = ' ING  ';
  assertEqual(preview(exet, st), '[(BARK) ARC (ING)]', 'hidden trims whitespace');
}

{
  const {exet, st} = makeHarness('ARC');
  st.hiddenBefore = '   ';
  st.hiddenAfter = 'ING';
  assertEqual(preview(exet, st), '[ARC]', 'hidden needs both sides trimmed non-empty');
}

// --- Clue types & priority ---
{
  const {exet, st} = makeHarness('WORD');
  st.defsCount = 2;
  assertEqual(preview(exet, st), '[2 defs]', 'two defs');
}

{
  const {exet, st} = makeHarness('WORD');
  st.defsCount = 3;
  assertEqual(preview(exet, st), '[3 defs]', 'three defs');
}

{
  const {exet, st} = makeHarness('ANIME');
  st.hiddenInside = true;
  assertEqual(preview(exet, st), '[ANIME] inside text', 'hidden inside text');
}

{
  const {exet, st} = makeHarness('ANIME');
  splitState(exet, st, 'ANIME', [1, 2, 3, 4]);
  st.hiddenInside = true;
  assertEqual(
      preview(exet, st), '[A + N + I + M + E] inside text', 'hidden inside split');
}

{
  const {exet, st} = makeHarness('ANIME');
  st.acrostic = 'first';
  st.hiddenInside = true;
  assertEqual(
      preview(exet, st), '[ANIME] from first letters', 'acrostic beats hidden inside');
}

{
  const {exet, st} = makeHarness('WORD');
  st.andLit = true;
  assertEqual(preview(exet, st), '[WORD, &lit]', 'andlit charade');
}

{
  const {exet, st} = makeHarness('WORD');
  st.composite = {
    type: 'in',
    a: {kind: 'part', index: 0},
    b: {kind: 'part', index: 0},
  };
  st.andLit = true;
  assertEqual(preview(exet, st), '[WORD in WORD, &lit]', 'andlit on composite');
}

{
  const {exet, st} = makeHarness('WORD');
  st.defsCount = 2;
  st.andLit = true;
  st.hiddenBefore = 'X';
  st.hiddenAfter = 'Y';
  assertEqual(preview(exet, st), '[2 defs]', 'two defs beats everything');
}

{
  const {exet, st} = makeHarness('WORD');
  st.subtractA = 'A';
  st.subtractB = 'B';
  st.hiddenBefore = 'X';
  st.hiddenAfter = 'Y';
  assertEqual(preview(exet, st), '[(X) WORD (Y)]', 'hidden beats subtract');
}

{
  const {exet, st} = makeHarness('AB');
  st.subtractA = 'AB';
  st.subtractB = 'A';
  st.composite = {
    type: 'in',
    a: {kind: 'part', index: 1},
    b: {kind: 'part', index: 0},
  };
  assertEqual(preview(exet, st), '[AB − A]', 'subtract beats composite');
}

// --- Workflows ---
{
  const {exet, st} = makeHarness('NUANCED');
  splitState(exet, st, 'NUANCED', [2, 5]);
  st.selected = [{kind: 'part', index: 0}, {kind: 'part', index: 2}];
  exet.magpieApplyOp('group');
  st.selected = [{kind: 'group', id: 0}];
  exet.magpieApplyOp('anagram');
  st.selected = [{kind: 'group', id: 0}, {kind: 'part', index: 1}];
  exet.magpieApplyOp('around');
  assertEqual(preview(exet, st), '[NUED* around ANC]', 'NUANCED workflow');
}

{
  const {exet, st} = makeHarness('ABCD');
  splitState(exet, st, 'ABCD', [2]);
  st.parts[0].op = 'anagram';
  exet.magpieToggleSplit(2);
  assertEqual(st.parts[0].op, 'anagram', 'removing split preserves sole sub-part op');
  assertEqual(preview(exet, st), '[ABCD*]', 'merged preview keeps anagram');
}

{
  const {exet, st} = makeHarness('ABCD');
  splitState(exet, st, 'ABCD', [2]);
  st.parts[0].op = 'anagram';
  st.parts[1].op = 'reverse';
  exet.magpieToggleSplit(2);
  assertEqual(st.parts[0].op, null, 'conflicting ops cleared on merge');
}

{
  const {exet, st} = makeHarness('ABCD');
  splitState(exet, st, 'ABCD', [2]);
  st.parts[0].op = 'anagram';
  st.parts[1].op = 'anagram';
  exet.magpieToggleSplit(2);
  assertEqual(st.parts[0].op, 'anagram', 'matching ops preserved on merge');
}

{
  const {exet, st} = makeHarness('ABCDE');
  splitState(exet, st, 'ABCDE', [2, 3]);
  st.parts[0].op = 'anagram';
  exet.magpieToggleSplit(3);
  assertEqual(st.parts[0].op, 'anagram', 'removing unrelated split preserves op');
}

{
  const {exet, st} = makeHarness('ABCD');
  splitState(exet, st, 'ABCD', [2]);
  st.groups = [{id: 0, partIndices: [0, 1], fodder: 'AB', op: null}];
  exet.magpieToggleSplit(2);
  assertEqual(st.groups.length, 0, 'toggle split clears groups');
}

{
  const {exet, st} = makeHarness('ABCD');
  splitState(exet, st, 'ABCD', [2]);
  st.composite = {
    type: 'in',
    a: {kind: 'part', index: 1},
    b: {kind: 'part', index: 0},
  };
  st.subtractA = 'X';
  st.subtractB = 'Y';
  st.selected = [{kind: 'part', index: 0}, {kind: 'part', index: 1}];
  exet.magpieApplyOp('around');
  assertEqual(st.subtractA, '', 'around clears subtract fields');
  assertEqual(st.composite.type, 'around', 'around sets composite');
}

{
  const {exet, st} = makeHarness('WORD');
  st.composite = {
    type: 'in',
    a: {kind: 'part', index: 0},
    b: {kind: 'part', index: 0},
  };
  exet.magpieApplyOp('2defs');
  assertEqual(st.composite, null, '2defs clears composite');
  exet.magpieApplyOp('2defs');
  assertEqual(st.defsCount, 0, '2defs toggles off');
}

{
  const {exet, st} = makeHarness('WORD');
  exet.magpieApplyOp('defs-plus');
  assertEqual(st.defsCount, 2, 'defs plus from off defaults to 2');
  exet.magpieApplyOp('defs-plus');
  assertEqual(st.defsCount, 3, 'defs plus increments');
  exet.magpieApplyOp('defs-minus');
  assertEqual(st.defsCount, 2, 'defs minus decrements');
}

{
  const {exet, st} = makeHarness('WORD');
  exet.magpieApplyOp('andlit');
  exet.magpieApplyOp('2defs');
  assertEqual(st.andLit, false, '2defs clears andlit');
}

{
  const {exet, st} = makeHarness('WORD');
  exet.magpieApplyOp('hidden-inside');
  assertEqual(st.hiddenInside, true, 'hidden inside toggles on');
  exet.magpieApplyOp('hidden-inside');
  assertEqual(st.hiddenInside, false, 'hidden inside toggles off');
}

// --- Selection edge cases ---
{
  const {exet, st} = makeHarness('ABCD');
  splitState(exet, st, 'ABCD', [2]);
  select(exet, st, 0, false);
  select(exet, st, 1, true);
  assertEqual(st.selected.length, 2, 'shift-click adds second part');
  select(exet, st, 1, true);
  assertEqual(st.selected.length, 1, 'shift-click toggles part off');
}

{
  const {exet, st} = makeHarness('ABCD');
  splitState(exet, st, 'ABCD', [2]);
  st.groups = [{id: 0, partIndices: [0, 1], fodder: 'AB', op: null}];
  select(exet, st, 1, false);
  assertEqual(st.selected[0].kind, 'group', 'click grouped part selects group');
  assertEqual(
      exet.magpieOrderBadgeForPart(st, 0), 1, 'order badge on first chunk of group');
  assertEqual(
      exet.magpieOrderBadgeForPart(st, 1), 0, 'no badge on non-first group chunk');
}

{
  const {exet, st} = makeHarness('AB');
  st.selected = [{kind: 'part', index: 0}];
  exet.magpieApplyOp('around');
  assertEqual(st.composite, null, 'around needs two selections');
}

{
  const {exet, st} = makeHarness('AB');
  splitState(exet, st, 'AB', [1]);
  st.groups = [{id: 0, partIndices: [0, 1], fodder: 'AB', op: null}];
  st.selected = [{kind: 'group', id: 0}, {kind: 'group', id: 0}];
  exet.magpieApplyOp('around');
  assertEqual(st.composite, null, 'around rejects duplicate selection');
}

{
  const {exet, st} = makeHarness('ABCD');
  splitState(exet, st, 'ABCD', [2]);
  st.selected = [{kind: 'part', index: 0}, {kind: 'part', index: 1}];
  exet.magpieApplyOp('anagram');
  assertEqual(st.parts[0].op, null, 'letter op needs exactly one selection');
}

{
  const {exet, st} = makeHarness('ABCD');
  splitState(exet, st, 'ABCD', [2]);
  st.selected = [{kind: 'part', index: 0}];
  exet.magpieApplyOp('group');
  assertEqual(st.groups.length, 0, 'group op needs two parts');
}

{
  const {exet, st} = makeHarness('ABCD');
  splitState(exet, st, 'ABCD', [2]);
  st.groups = [{id: 0, partIndices: [0, 1], fodder: 'AB', op: 'anagram'}];
  st.selected = [{kind: 'group', id: 0}];
  exet.magpieApplyOp('ungroup');
  assertEqual(st.groups.length, 0, 'ungroup removes group');
}

{
  const {exet, st} = makeHarness('ABCD');
  splitState(exet, st, 'ABCD', [2]);
  st.parts[0].op = 'anagram';
  st.selected = [{kind: 'part', index: 0}];
  exet.magpieApplyOp('clear-op');
  assertEqual(st.parts[0].op, null, 'clear-op on part');
}

// --- Splits & build ---
{
  const {exet, st} = makeHarness('ABCD');
  exet.magpieToggleSplit(0);
  exet.magpieToggleSplit(99);
  exet.magpieToggleSplit(4);
  assertEqual(st.splits.length, 0, 'invalid split indices rejected');
}

{
  const {exet} = makeHarness('ABCD');
  const parts = exet.magpieBuildParts('ABCD', [0, 2, 2, 5, 3]);
  assertEqual(parts.length, 3, 'buildParts dedupes bad splits');
  assertEqual(parts.map(p => p.fodder).join('|'), 'AB|C|D', 'buildParts fodder');
}

// --- Migration ---
{
  const migrated = {
    answer: 'TEST',
    splits: [],
    parts: [{start: 0, end: 4, fodder: 'TEST', op: null, deletions: [1]}],
    groups: [],
    selected: [0, 1],
    selectedGroup: 2,
    composite: {type: 'subtract', a: 0, b: 1},
  };
  proto.magpieMigrateState(migrated);
  assertEqual(migrated.selected.length, 1, 'migrate selectedGroup');
  assertEqual(migrated.selected[0].kind, 'group', 'migrate selected kind');
  assertEqual(migrated.composite, null, 'migrate clears old subtract composite');
  assertEqual(migrated.parts[0].deletions, undefined, 'migrate drops deletions');
}

{
  const migrated = {
    answer: 'AB',
    splits: [],
    parts: [{start: 0, end: 2, fodder: 'AB', op: null}],
    groups: [],
    selected: [],
    composite: {type: 'in', a: 1, b: 0},
  };
  proto.magpieMigrateState(migrated);
  assertEqual(migrated.composite.a.kind, 'part', 'migrate numeric composite a');
  assertEqual(migrated.composite.b.index, 0, 'migrate numeric composite b');
}

// --- Group colours ---
assertEqual(
    proto.magpieGroupColorClass({id: 0}), ' xet-magpie-group-c0', 'group colour 0');
assertEqual(
    proto.magpieGroupColorClass({id: 6}), ' xet-magpie-group-c0', 'group colour wraps');

// --- Missing references ---
{
  const {exet, st} = makeHarness('AB');
  st.composite = {
    type: 'around',
    a: {kind: 'group', id: 99},
    b: {kind: 'part', index: 0},
  };
  assertEqual(preview(exet, st), '[ around AB]', 'missing group formats empty');
}

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
