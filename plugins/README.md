# Exet plugins (developer guide)

Plugin groups live under `plugins/<group>/`. Plugin ids are qualified as
`<group>/<id>` (e.g. `official/3d-crosswords`, `ians_exet_plugins/rebus`).

Exet must be served over HTTP (not `file://`).

## Groups

- **official/** — plugins maintained with Exet (includes 3-D crosswords)
- **ians_exet_plugins/** — third-party plugins
  ([repository](https://github.com/ianfhunter/ians_exet_plugins)), included as
  a git submodule. After cloning Exet:

  ```bash
  git submodule update --init plugins/ians_exet_plugins
  ```

To add another third-party group manually:

```bash
git clone git@github.com:someone/their_plugins.git plugins/their_plugins
```

Then add the group and its plugins to `plugins/_registry.json` (see below).

End users enable plugins under **Edit → Plugins** and reload.

## Layout

```
plugins/
  _registry.json                # lists groups/plugins for static hosts
  official/                     # bundled official plugins
    3d-crosswords/
      plugin.json
      plugin.js
  ians_exet_plugins/            # git submodule
    rebus/
      plugin.json
      plugin.js
```

Each plugin folder contains `plugin.json` (metadata) and `plugin.js` (code).

## Registry

On static hosts without directory listing (e.g. GitHub Pages), Exet falls back
to `plugins/_registry.json`. When you add a plugin group or plugin, update this
file manually:

```json
{
  "official": ["3d-crosswords"],
  "ians_exet_plugins": ["rebus"],
  "their_plugins": ["my-plugin"]
}
```

Each key is a group directory name; each value lists plugin folder names within
that group.

## Puzzle requirements

Each `plugin.json` may declare when a puzzle requires that plugin:

```json
"requires": { "puzzleProperty": "hasRebusCells" }
```

or, for numeric properties such as 3-D layer count:

```json
"requires": { "puzzleProperty": "layers3d", "minValue": 2 }
```

Exet blocks loading puzzles that need a disabled plugin.

## Plugin API

Plugins register with `exetPlugins.register({ id, setup(api) { ... } })`.
Inside `setup`, use four extension mechanisms. New extension points in core are
added as new event or filter names — not as one-off hook methods.

### Events (`api.on`)

Handlers receive a context object. Only enabled plugins run.

| Event | Context | Notes |
|-------|---------|-------|
| `exet:init` | `{ exet }` | After Exet initializes |
| `puzzle:set` | `{ exet, puz }` | While syncing Exolve puzzle into Exet |
| `puzzle:set:done` | `{ exet, puz }` | Puzzle fully loaded |
| `arrowNav:before` | `{ exet, key, nav }` | Set `nav = 'skip-default'` to skip default arrow navigation |
| `grid:spec:before` | `{ exet, puz, variableWidth }` | Set `variableWidth = true` for variable-width grid export |

### Filters (`api.addFilter`)

Handlers mutate the context. Semantics are filter-specific:

| Filter | Context | Semantics |
|--------|---------|-----------|
| `gridCell.solution.valid` | `{ exet, puz, solution, valid }` | First handler that sets `valid` wins; leave `undefined` to defer |
| `gridCell.entry` | `{ exet, puz, gridCell, entry, solved }` | Chained transforms of `entry` |
| `gridFill.skipLight` | `{ exet, ci, skip }` | Any handler may set `skip = true` |
| `gridFill.disabledMessage` | `{ exet, ci, message }` | First non-empty `message` wins |

### Menus (`api.registerMenuItem`)

```js
api.registerMenuItem('open', {
  order: 10,
  html(exet) { return '<hr>...'; },
});
```

### Input (`api.onInput`)

Handler is bound to `exet` and attached after `puzzle:set:done`:

```js
api.onInput('grid', 'keydown', handler, { capture: true });
```

### Example

```js
exetPlugins.register({
  id: 'my-feature',

  setup(api) {
    api.on('puzzle:set', (ctx) => { ... });
    api.addFilter('gridCell.entry', (ctx) => { ... });
    api.registerMenuItem('open', { order: 10, html: (exet) => '...' });
    api.onInput('grid', 'keydown', handler, { capture: true });
  },
});
```
