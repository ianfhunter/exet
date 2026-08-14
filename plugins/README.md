# Exet plugins directory

Plugin groups are subdirectories: `plugins/<group>/<plugin-id>/plugin.json`.

## Bundled group

- **official/** — plugins maintained with Exet (includes 3-D crosswords)

## Submodule

- **ians_exet_plugins/** — third-party plugins ([repository](https://github.com/ianfhunter/ians_exet_plugins)), included as a git submodule. Run `git submodule update --init plugins/ians_exet_plugins` after cloning Exet.

Enable plugins under **Edit → Plugins** and reload.

See `.notes/exet-plugins.md` for the plugin API (`setup(api)` with events,
filters, menus, and input).
