/*
 * Theme word-list generation for Exet preferred fills, using WebLLM in-browser.
 * Loaded by exet.html; used from the Theme tab in exet.js.
 */

const exetThemeLlm = {
  MODEL_ID: 'Llama-3.2-1B-Instruct-q4f16_1-MLC',
  WEBLLM_CDN: 'https://esm.run/@mlc-ai/web-llm',
  MAX_ENTRY_LETTERS: 75,
  MIN_ENTRY_LETTERS: 2,

  /** id → prompt blurb for category checkboxes in the Theme tab */
  CATEGORIES: {
    words: 'single words and short terms',
    phrases: 'multi-word phrases and compound terms',
    sayings: 'proverbs, catchphrases, famous quotations, and mottoes',
    memes: 'internet memes, viral references, and meme phrases',
    names: 'proper nouns: people, places, brands, and titles',
    idioms: 'idioms and figurative expressions',
    slang: 'slang and informal terms',
  },

  DEFAULT_CATEGORIES: ['words', 'phrases'],

  MORE_PROMPT:
      'Please generate more entries for the same theme. ' +
      'Do not repeat any entries you have already given. ' +
      'One entry per line, same rules as before.',

  engine: null,
  enginePromise: null,
  webgpuChecked: null,

  async hasWebGPU() {
    if (this.webgpuChecked !== null) {
      return this.webgpuChecked;
    }
    if (!navigator.gpu) {
      this.webgpuChecked = false;
      return false;
    }
    try {
      const adapter = await navigator.gpu.requestAdapter();
      this.webgpuChecked = !!adapter;
    } catch (e) {
      this.webgpuChecked = false;
    }
    return this.webgpuChecked;
  },

  countLetters(s) {
    if (typeof exetLexicon !== 'undefined' && exetLexicon &&
        typeof exetLexicon.lettersOf === 'function') {
      return exetLexicon.lettersOf(s).length;
    }
    let n = 0;
    for (const ch of s.toUpperCase()) {
      if (ch >= 'A' && ch <= 'Z') {
        n++;
      }
    }
    return n;
  },

  buildPrompt(theme, length, anyLength, categories) {
    let lengthRule = 'Entries may be any length from 2 to 15 letters.';
    if (!anyLength && length > 0) {
      lengthRule =
        `Each entry must contain exactly ${length} letters ` +
        `(ignore spaces, hyphens, and apostrophes when counting).`;
    }

    const typeLines = [];
    for (const id of categories) {
      const blurb = this.CATEGORIES[id];
      if (blurb) {
        typeLines.push(`- ${blurb}`);
      }
    }
    const typesSection = typeLines.length ?
        ('Include these types of entries:\n' + typeLines.join('\n') + '\n') :
        '';

    return (
      `Generate crossword fill entries related to: "${theme}"\n\n` +
      typesSection +
      'Rules:\n' +
      '- One entry per line\n' +
      "- Only letters, spaces, hyphens (-), and apostrophes (')\n" +
      '- No numbering, bullets, or explanations\n' +
      '- Include proper nouns if relevant to the theme\n' +
      `- ${lengthRule}\n\n` +
      'Generate about 200 entries, spread across the requested types.'
    );
  },

  cleanLine(raw) {
    let s = raw.trim();
    if (!s || s.startsWith('#')) {
      return null;
    }
    s = s.replace(/^[-*]\s*/, '').replace(/^\d+[.)]\s*/, '');
    s = s.replace(/^["']|["']$/g, '').trim();
    if (!s) {
      return null;
    }
    return s.replace(/\s+/g, ' ').trim();
  },

  isValidChars(s) {
    return /^[A-Za-z \-']+$/.test(s);
  },

  /**
   * Parse and filter raw LLM output.
   * Returns { kept: string[], rawCount: number, skipped: number }.
   */
  filterWords(rawText, length, anyLength, existingSeen) {
    const lines = rawText.split(/\r?\n/);
    const kept = [];
    const seen = {};
    let rawCount = 0;
    let skipped = 0;

    for (const raw of lines) {
      const s = this.cleanLine(raw);
      if (!s) {
        continue;
      }
      rawCount++;
      if (!this.isValidChars(s)) {
        skipped++;
        continue;
      }
      const n = this.countLetters(s);
      if (n < this.MIN_ENTRY_LETTERS || n > this.MAX_ENTRY_LETTERS) {
        skipped++;
        continue;
      }
      if (!anyLength && length > 0 && n !== length) {
        skipped++;
        continue;
      }
      const key = s.toLowerCase();
      if (seen[key] || (existingSeen && existingSeen[key])) {
        skipped++;
        continue;
      }
      seen[key] = true;
      kept.push(s);
    }
    return { kept, rawCount, skipped };
  },

  async getEngine(onProgress) {
    if (this.engine) {
      return this.engine;
    }
    if (this.enginePromise) {
      return this.enginePromise;
    }
    this.enginePromise = (async () => {
      const { CreateMLCEngine } = await import(this.WEBLLM_CDN);
      const engine = await CreateMLCEngine(this.MODEL_ID, {
        initProgressCallback: (report) => {
          if (onProgress) {
            onProgress(report);
          }
        },
      });
      this.engine = engine;
      return engine;
    })();
    return this.enginePromise;
  },

  /**
   * One chat round: send messages, parse/filter response.
   * Returns { kept, rawCount, skipped, messages, content, empty }.
   * messages in the result is ready for the next "generate more" round.
   */
  async chatRound(messages, length, anyLength, existingSeen, onProgress) {
    const engine = await this.getEngine(onProgress);

    const reply = await engine.chat.completions.create({
      messages,
      temperature: 0.7,
      max_tokens: 3000,
    });

    const content = reply?.choices?.[0]?.message?.content ?? '';
    if (!content.trim()) {
      return {
        kept: [],
        rawCount: 0,
        skipped: 0,
        messages,
        content: '',
        empty: true,
      };
    }

    const filtered = this.filterWords(
        content, length, anyLength, existingSeen);
    const nextMessages = messages.concat(
        { role: 'assistant', content },
        { role: 'user', content: this.MORE_PROMPT });

    return {
      ...filtered,
      messages: nextMessages,
      content,
      empty: false,
    };
  },

  /**
   * Generate themed words (single batch). Kept for compatibility.
   */
  async generate(theme, length, anyLength, categories, onProgress) {
    if (onProgress) {
      onProgress({ text: 'Generating word list…' });
    }
    const prompt = this.buildPrompt(theme, length, anyLength, categories);
    return this.chatRound(
        [{ role: 'user', content: prompt }],
        length,
        anyLength,
        null,
        onProgress);
  },
};
