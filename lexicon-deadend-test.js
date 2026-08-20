/**
 * Tiny lexicon for exet-test-deadend-refine.html
 *
 * Grid (4×4 all white), only (3,1)=X is given:
 *
 *     0   1   2   3
 * 0   ?   ?   ?   ?
 * 1   ?   ?   ?   ?   ← across row 1: ????
 * 2   ?   ?   ?   ?
 * 3   ?   X   ?   ?   ← down col 1: ???X
 *
 * CART matches ???? but forces down col 1 to ?A?X, which has zero
 * words in this dictionary. Down still has 5 cached ???X matches (>4),
 * so someClueTurnsNonViable() skips it; refineLightChoices() catches it.
 */
exetLexicon = {
  id: "deadend-test",
  language: "en",
  script: "Latin",
  letters: ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M",
            "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z"],
  lexicon: [
    "",
    "CART", "BART", "DART", "HART", "PART", "TART", "WART",
    "BARX", "CARX", "MARX", "PARX", "WARX",
  ],
  index: {
    "????": [1, 2, 3, 4, 5, 6, 7],
    "???X": [8, 9, 10, 11, 12],
  },
  anagrams: [[]],
  phones: [],
  phindex: [],
  stems: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
  stemsId: "deadend-test",
};
