/*
 * Exet plugin manager.
 *
 * Discovers plugins under plugins/<group>/<id>/ via directory listing when the
 * HTTP server provides it, or plugins/_registry.json as fallback (needed for
 * GitHub Pages and similar static hosts).
 *
 * Regenerate the registry after adding a group:
 *   node scripts/update-plugin-registry.mjs
 *
 * Plugin ids are qualified as <group>/<id>. Enabled ids persist in
 * exetState.enabledPlugins.
 *
 * ## Plugin API (stable extension surface)
 *
 * Plugins call exetPlugins.register({ id, setup(api) { ... } }). Inside setup,
 * use api.on(), api.addFilter(), api.registerMenuItem(), and api.onInput().
 *
 * Events (api.on):
 *   exet:init              { exet }
 *   puzzle:set             { exet, puz }
 *   puzzle:set:done        { exet, puz }
 *   arrowNav:before        { exet, key, nav }  nav: 'continue' | 'skip-default'
 *   grid:spec:before       { exet, puz, variableWidth }
 *
 * Filters (api.addFilter) — handlers mutate ctx; semantics are filter-specific:
 *   gridCell.solution.valid  { exet, puz, solution, valid }  first non-undefined valid wins
 *   gridCell.entry           { exet, puz, gridCell, entry, solved }  chained transforms
 *   gridFill.skipLight       { exet, ci, skip }  any skip=true skips fill
 *   gridFill.disabledMessage { exet, ci, message }  first non-empty message wins
 *
 * Menus (api.registerMenuItem):
 *   registerMenuItem(menuId, { order, html(exet) })
 *   menuId: 'open', ...
 *
 * Input (api.onInput):
 *   onInput('grid', 'keydown', handler, { capture })
 *   handler is bound to exet; attached after puzzle:set:done
 */

const EXET_PLUGINS_REGISTRY_URL = 'plugins/_registry.json';
const EXET_REGISTRY_SKIP = new Set([
  'README.md', 'manifest.json', '_registry.json', '.gitkeep',
]);

class ExetPlugins {
  constructor() {
    this.plugins = {};
    this.manifest = [];
    this.loaded = new Set();
    this.loadingGroup = null;
    this.loadingPluginId = null;
    this._registeringPluginId = null;
    this._events = {};
    this._filters = {};
    this._menuItems = {};
    this._inputHandlers = [];
  }

  _currentPluginId() {
    return this._registeringPluginId || this.loadingPluginId || '';
  }

  _enabledHandlers(items) {
    const enabled = new Set(exetState.enabledPlugins || []);
    return items.filter(item => enabled.has(item.pluginId));
  }

  _addEvent(event, handler, pluginId) {
    if (!this._events[event]) {
      this._events[event] = [];
    }
    this._events[event].push({handler, pluginId});
  }

  _addFilter(name, handler, pluginId) {
    if (!this._filters[name]) {
      this._filters[name] = [];
    }
    this._filters[name].push({handler, pluginId});
  }

  on(event, handler) {
    this._addEvent(event, handler, this._currentPluginId());
  }

  addFilter(name, handler) {
    this._addFilter(name, handler, this._currentPluginId());
  }

  registerMenuItem(menuId, spec) {
    if (!this._menuItems[menuId]) {
      this._menuItems[menuId] = [];
    }
    this._menuItems[menuId].push({
      order: spec.order || 0,
      html: spec.html,
      pluginId: this._currentPluginId(),
    });
  }

  onInput(target, event, handler, opts={}) {
    this._inputHandlers.push({
      target,
      event,
      handler,
      capture: !!opts.capture,
      pluginId: this._currentPluginId(),
    });
  }

  _pluginApi(pluginId) {
    return {
      on: (event, handler) => this._addEvent(event, handler, pluginId),
      addFilter: (name, handler) => this._addFilter(name, handler, pluginId),
      registerMenuItem: (menuId, spec) => {
        if (!this._menuItems[menuId]) {
          this._menuItems[menuId] = [];
        }
        this._menuItems[menuId].push({
          order: spec.order || 0,
          html: spec.html,
          pluginId,
        });
      },
      onInput: (target, event, handler, opts={}) => {
        this._inputHandlers.push({
          target, event, handler,
          capture: !!opts.capture,
          pluginId,
        });
      },
    };
  }

  emit(event, ctx) {
    for (const {handler} of this._enabledHandlers(this._events[event] || [])) {
      handler(ctx);
    }
  }

  runFilter(name, ctx) {
    for (const {handler} of this._enabledHandlers(this._filters[name] || [])) {
      handler(ctx);
    }
    return ctx;
  }

  register(plugin) {
    if (!plugin.id) {
      throw 'Exet plugin must have an id';
    }
    const fullId = this.loadingGroup ?
        this.loadingGroup + '/' + plugin.id : plugin.id;
    plugin.id = fullId;
    plugin.group = this.loadingGroup || '';
    this.plugins[fullId] = plugin;
    if (plugin.setup) {
      this._registeringPluginId = fullId;
      plugin.setup(this._pluginApi(fullId));
      this._registeringPluginId = null;
    }
  }

  manifestEntry(id) {
    return this.manifest.find(p => p.id == id);
  }

  isEnabled(id) {
    return (exetState.enabledPlugins || []).includes(id);
  }

  puzzleNeedsPlugin(puz, entry) {
    const req = entry.requires;
    if (!req || !req.puzzleProperty) {
      return false;
    }
    const val = puz[req.puzzleProperty];
    if (req.minValue !== undefined) {
      return val >= req.minValue;
    }
    if (req.minExclusive !== undefined) {
      return val > req.minExclusive;
    }
    return !!val;
  }

  missingPluginsForPuzzle(puz) {
    const missing = [];
    for (const entry of this.manifest) {
      if (this.puzzleNeedsPlugin(puz, entry) && !this.isEnabled(entry.id)) {
        missing.push(entry);
      }
    }
    return missing;
  }

  async fetchJson(url) {
    const resp = await fetch(url);
    if (!resp.ok) {
      throw new Error('HTTP ' + resp.status + ' fetching ' + url);
    }
    return resp.json();
  }

  normalizePluginEntry(raw, group, pluginId) {
    const id = raw.id || pluginId;
    if (!id) {
      throw 'Plugin entry missing id';
    }
    const base = 'plugins/' + group + '/' + id;
    return {
      id: group + '/' + id,
      group,
      pluginId: id,
      name: raw.name || id,
      description: raw.description || '',
      js: raw.js || (base + '/plugin.js'),
      css: raw.css || (base + '/plugin.css'),
      requires: raw.requires || null,
    };
  }

  async loadRegistry() {
    try {
      return await this.fetchJson(EXET_PLUGINS_REGISTRY_URL);
    } catch (err) {
      return null;
    }
  }

  parseDirectoryListing(html) {
    const dirs = [];
    const seen = new Set();
    const re = /href="([^"?#]+)"/gi;
    let m;
    while ((m = re.exec(html))) {
      let href = decodeURIComponent(m[1]);
      if (!href.endsWith('/')) {
        continue;
      }
      let name = href.slice(0, -1);
      const slash = name.lastIndexOf('/');
      if (slash >= 0) {
        name = name.substring(slash + 1);
      }
      if (!name || name == '..' || name == '.' || name.startsWith('.')) {
        continue;
      }
      if (EXET_REGISTRY_SKIP.has(name) || name.startsWith('_')) {
        continue;
      }
      if (!seen.has(name)) {
        seen.add(name);
        dirs.push(name);
      }
    }
    return dirs.sort();
  }

  async listDirectory(url) {
    try {
      const resp = await fetch(url);
      if (!resp.ok) {
        return [];
      }
      const text = await resp.text();
      if (!text.includes('href=')) {
        return [];
      }
      return this.parseDirectoryListing(text);
    } catch (err) {
      return [];
    }
  }

  async probeUrl(url) {
    try {
      const resp = await fetch(url, {method: 'HEAD'});
      if (resp.ok) {
        return true;
      }
    } catch (err) {
    }
    try {
      const resp = await fetch(url);
      return resp.ok;
    } catch (err) {
      return false;
    }
  }

  async loadPlugin(group, pluginId) {
    const pluginJsonUrl = 'plugins/' + group + '/' + pluginId + '/plugin.json';
    if (!await this.probeUrl(pluginJsonUrl)) {
      return;
    }
    const meta = await this.fetchJson(pluginJsonUrl);
    this.manifest.push(this.normalizePluginEntry(meta, group, pluginId));
  }

  async loadGroup(group, registryPlugins=null) {
    let pluginIds = await this.listDirectory('plugins/' + group + '/');
    if (pluginIds.length == 0 && registryPlugins) {
      pluginIds = registryPlugins;
    }
    for (const pluginId of pluginIds) {
      await this.loadPlugin(group, pluginId);
    }
  }

  async discoverPlugins() {
    this.manifest = [];
    const registry = await this.loadRegistry();
    let groups = await this.listDirectory('plugins/');
    if (groups.length == 0 && registry) {
      groups = Object.keys(registry).sort();
    }
    for (const group of groups) {
      await this.loadGroup(group, registry && registry[group]);
    }
  }

  loadStylesheet(url) {
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.type = 'text/css';
    link.href = url;
    document.head.appendChild(link);
  }

  loadScript(url) {
    return new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = url;
      script.onload = resolve;
      script.onerror = () => reject(new Error('Failed to load ' + url));
      document.head.appendChild(script);
    });
  }

  async probeStylesheet(url) {
    return this.probeUrl(url);
  }

  async loadEnabled() {
    const enabled = exetState.enabledPlugins || [];
    for (const id of enabled) {
      if (this.loaded.has(id)) {
        continue;
      }
      const entry = this.manifestEntry(id);
      if (!entry) {
        console.warn('Unknown Exet plugin id:', id);
        continue;
      }
      if (entry.css && await this.probeStylesheet(entry.css)) {
        this.loadStylesheet(entry.css);
      }
      this.loadingGroup = entry.group;
      this.loadingPluginId = entry.id;
      await this.loadScript(entry.js);
      this.loadingGroup = null;
      this.loadingPluginId = null;
      this.loaded.add(id);
    }
  }

  attachInputHandlers(exet, puz) {
    for (const item of this._enabledHandlers(this._inputHandlers)) {
      if (item.target != 'grid') {
        continue;
      }
      puz.gridInput.addEventListener(
          item.event, item.handler.bind(exet), item.capture);
    }
  }

  /** Core: validate a grid cell solution during puzzle load. */
  isValidGridCellSolution(exet, puz, solution) {
    const ctx = {exet, puz, solution, valid: undefined};
    for (const {handler} of this._enabledHandlers(
        this._filters['gridCell.solution.valid'] || [])) {
      handler(ctx);
      if (ctx.valid !== undefined) {
        return ctx.valid;
      }
    }
    if (solution == '?' || solution == '0') {
      return true;
    }
    return exetLexicon.letterSet[solution];
  }

  /** Core: format one grid cell for Exolve spec export. */
  formatGridCellEntry(exet, puz, gridCell, solved) {
    let letter = (gridCell.currLetter != '0' ?
        ((solved || gridCell.prefill) ?
            gridCell.currLetter : '0') : '?');
    let entry = '.';
    if (gridCell.isLight) {
      if (letter != '?' && letter != '0') {
        entry = puz.stateToDisplayChar(letter);
      } else {
        entry = letter;
      }
      if (gridCell.hasCircle) {
        entry += '@';
      }
      if (gridCell.prefill) {
        entry += '!';
      }
      entry += (gridCell.hasBarAfter && gridCell.hasBarUnder ?
          '+' : (gridCell.hasBarAfter ?
          '|' : (gridCell.hasBarUnder ? '_' : '')));
    }
    const ctx = {exet, puz, gridCell, entry, solved};
    this.runFilter('gridCell.entry', ctx);
    return ctx.entry;
  }

  /** Core: whether grid export uses variable-width cells. */
  useVariableWidthGrid(exet, puz) {
    const ctx = {exet, puz, variableWidth: false};
    this.emit('grid:spec:before', ctx);
    return ctx.variableWidth;
  }

  /** Core: whether grid-fill should skip a light. */
  shouldSkipFillForLight(exet, ci) {
    const ctx = {exet, ci, skip: false};
    this.runFilter('gridFill.skipLight', ctx);
    return ctx.skip;
  }

  /** Core: user-visible message when grid-fill is disabled for a light. */
  fillLightDisabledMessage(exet, ci) {
    const ctx = {exet, ci, message: ''};
    for (const {handler} of this._enabledHandlers(
        this._filters['gridFill.disabledMessage'] || [])) {
      handler(ctx);
      if (ctx.message) {
        return ctx.message;
      }
    }
    return '';
  }

  /** Core: HTML fragments for a dropdown menu contributed by plugins. */
  getMenuItemsHTML(menuId, exet) {
    const items = this._enabledHandlers(this._menuItems[menuId] || [])
        .sort((a, b) => a.order - b.order);
    let html = '';
    for (const item of items) {
      const fragment = typeof item.html === 'function' ?
          item.html(exet) : item.html;
      html += fragment;
    }
    return html;
  }

  getMenuHTML() {
    if (this.manifest.length == 0) {
      return `
              <div class="xet-dropdown-subitem">No plugins installed.</div>`;
    }
    let html = '';
    let lastGroup = null;
    for (const entry of this.manifest) {
      if (entry.group != lastGroup) {
        lastGroup = entry.group;
        html += `
              <div style="padding:8px 10px 2px;font-weight:bold">${entry.group}</div>`;
      }
      const checked = this.isEnabled(entry.id) ? ' checked' : '';
      const desc = entry.description.replace(/"/g, '&quot;');
      html += `
              <div style="padding:10px" title="${desc}">
                <input type="checkbox" class="xet-plugin-toggle"
                    data-plugin-id="${entry.id}"${checked}>
                </input>
                <b>${entry.name}</b>
                <div style="font-size:90%;padding-top:4px">${entry.description}</div>
              </div>`;
    }
    html += `
              <div style="padding:6px 10px;font-size:90%">
                Reload after changing plugins.
              </div>`;
    return html;
  }

  bindMenu(exet) {
    for (const toggle of document.getElementsByClassName('xet-plugin-toggle')) {
      toggle.addEventListener('change', e => {
        const id = toggle.dataset.pluginId;
        if (!exetState.enabledPlugins) {
          exetState.enabledPlugins = [];
        }
        const idx = exetState.enabledPlugins.indexOf(id);
        if (toggle.checked && idx < 0) {
          exetState.enabledPlugins.push(id);
        } else if (!toggle.checked && idx >= 0) {
          exetState.enabledPlugins.splice(idx, 1);
        }
        exetRevManager.saveLocal(
            exetRevManager.SPECIAL_KEY, JSON.stringify(exetState));
      });
    }
  }
}

let exetPlugins = new ExetPlugins();

async function exetPluginsBootstrap() {
  await exetPlugins.discoverPlugins();
  await exetPlugins.loadEnabled();
}

function exetMigratePluginIds() {
  if (!exetState.enabledPlugins) {
    return;
  }
  const legacy = {
    'rebus': 'ians_exet_plugins/rebus',
    '3d-crosswords': 'official/3d-crosswords',
    'example/3d-crosswords': 'official/3d-crosswords',
  };
  exetState.enabledPlugins = exetState.enabledPlugins.map(id => legacy[id] || id);
}
