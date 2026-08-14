# Exet Plugins

Plugin groups live under `exet/plugins/<group>/`. Plugin ids are qualified as
`<group>/<id>` (e.g. `official/3d-crosswords`, `ians_exet_plugins/rebus`).

## Groups

- **official/** — bundled with Exet
- **ians_exet_plugins/** — git submodule

## Submodule setup

```bash
git submodule update --init plugins/ians_exet_plugins
```

Enable plugins under **Edit → Plugins** and reload.

## Writing a plugin

Each plugin is a folder with `plugin.json` (metadata) and `plugin.js` (code).

```js
exetPlugins.register({
  id: 'my-feature',   // becomes <group>/my-feature

  setup(api) {
    // lifecycle, UI, filters, input — see below
  },
});
```

### Events (`api.on`)

Handlers receive a context object. Only enabled plugins run.

| Event | Context | Notes |
|-------|---------|-------|
| `exet:init` | `{ exet }` | After Exet initializes |
| `puzzle:set` | `{ exet, puz }` | While syncing Exolve puzzle into Exet |
| `puzzle:set:done` | `{ exet, puz }` | Puzzle fully loaded |
| `arrowNav:before` | `{ exet, key, nav }` | Set `nav = 'skip-default'` to skip default arrow navigation |
| `grid:spec:before` | `{ exet, puz, variableWidth }` | Set `variableWidth = true` for variable-width grid export |

New lifecycle points should be added as **new event names** on this bus, not as
one-off hook methods.

### Filters (`api.addFilter`)

Handlers mutate the context object. Semantics are filter-specific:

| Filter | Context | Semantics |
|--------|---------|-----------|
| `gridCell.solution.valid` | `{ exet, puz, solution, valid }` | First handler that sets `valid` wins; leave `undefined` to defer |
| `gridCell.entry` | `{ exet, puz, gridCell, entry, solved }` | Chained transforms of `entry` |
| `gridFill.skipLight` | `{ exet, ci, skip }` | Any handler may set `skip = true` |
| `gridFill.disabledMessage` | `{ exet, ci, message }` | First non-empty `message` wins |

New transform/validation points should be added as **new filter names**.

### Menus (`api.registerMenuItem`)

```js
api.registerMenuItem('open', {
  order: 10,
  html(exet) { return '<hr>...'; },
});
```

### Input (`api.onInput`)

```js
api.onInput('grid', 'keydown', handler, { capture: true });
```

Handler is bound to `exet`. Attached to the grid input after `puzzle:set:done`.

### Puzzle requirements (`plugin.json`)

```json
"requires": { "puzzleProperty": "hasRebusCells" }
```

or for numeric properties:

```json
"requires": { "puzzleProperty": "layers3d", "minValue": 2 }
```

Exet blocks loading puzzles that need a disabled plugin.

## Registry

On static hosts without directory listing, maintain `plugins/_registry.json`:

```bash
node scripts/update-plugin-registry.mjs
```
