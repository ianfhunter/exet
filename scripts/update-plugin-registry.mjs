#!/usr/bin/env node
/**
 * Scan exet/plugins/ and write plugins/_registry.json.
 *
 * Run after installing or removing a plugin group. Needed for static hosts
 * (e.g. GitHub Pages) that do not serve directory listings.
 *
 * Usage: node scripts/update-plugin-registry.mjs
 */

import fs from 'fs';
import path from 'path';
import {fileURLToPath} from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const pluginsDir = path.join(__dirname, '..', 'plugins');
const registryPath = path.join(pluginsDir, '_registry.json');

const SKIP_NAMES = new Set([
  'README.md', 'manifest.json', '_registry.json', '.gitkeep',
]);

const registry = {};

for (const group of fs.readdirSync(pluginsDir, {withFileTypes: true})) {
  if (!group.isDirectory()) {
    continue;
  }
  const groupName = group.name;
  if (groupName.startsWith('_') || groupName.startsWith('.')) {
    continue;
  }
  const groupPath = path.join(pluginsDir, groupName);
  const plugins = [];
  for (const entry of fs.readdirSync(groupPath, {withFileTypes: true})) {
    if (!entry.isDirectory()) {
      continue;
    }
    const pluginId = entry.name;
    if (pluginId.startsWith('.')) {
      continue;
    }
    const pluginJson = path.join(groupPath, pluginId, 'plugin.json');
    if (fs.existsSync(pluginJson)) {
      plugins.push(pluginId);
    }
  }
  if (plugins.length > 0) {
    registry[groupName] = plugins.sort();
  }
}

fs.writeFileSync(registryPath, JSON.stringify(registry, null, 2) + '\n');
console.log('Wrote ' + registryPath);
console.log(JSON.stringify(registry, null, 2));
