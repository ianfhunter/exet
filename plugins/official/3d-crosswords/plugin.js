/**
 * 3-D crosswords plugin (official Exet plugin group).
 *
 * Adds "New 3-D grid" to the Open menu. Core Exet still renders and saves
 * 3-D puzzles once they exist; this plugin gates creation and loading.
 */

function exetBlank3D(w3d, h3d, d3d, id='') {
  if (w3d <= 0 || h3d <= 0 || d3d <= 0 ||
      w3d % 2 != 1 || h3d % 2 != 1 || d3d % 2 != 1) {
    alert('All dimensions in 3-D crosswords should be positive odd numbers');
    return;
  }
  return exetBlank(w3d, h3d * d3d, h3d, id);
}

exetPlugins.register({
  id: '3d-crosswords',

  setup(api) {
    api.registerMenuItem('open', {
      order: 10,
      html(exet) {
        const uid = 'xet-' + Math.random().toString(36).substring(2, 8);
        return `
          <hr>
          <div class="xet-dropdown-item">
            New 3-D grid:
            <div class="xet-dropdown-submenu">
              <div style="padding:4px;text-align:center">
                <div>
                  <label for="xet-3d-w">Width:</label>
                  <input id="xet-3d-w" name="xet-3d-w" value="7"
                    type="text" size="3" maxlength="3" placeholder="W">
                  </input>
                  &times;
                  <label for="xet-3d-h">Height:</label>
                  <input id="xet-3d-h" name="xet-3d-h" value="5"
                    type="text" size="3" maxlength="3" placeholder="H">
                  </input>
                </div>
                <br>
                <div>
                  &times;
                  <label for="xet-3d-d">Depth:</label>
                  <input id="xet-3d-d" name="xet-3d-d" value="5"
                    type="text" size="3" maxlength="3" placeholder="D">
                  </input>
                </div>
                <br>
                <div>
                  Unique ID:
                  <input id="xet-3d-id" name="xet-3d-id"
                    value="${uid}"
                    title="Please change to a meaningful alphanumeric id (beginning with a letter) to identify easily later"
                    type="text" size="15" maxlength="30" placeholder="alphanumeric unique id">
                  </input>
                </div>
              </div>
              <hr/>
              <div class="xet-dropdown-subitem"
                  onclick="exetBlank3D(document.getElementById('xet-3d-w').value, ` +
                    `document.getElementById('xet-3d-h').value, ` +
                    `document.getElementById('xet-3d-d').value, ` +
                    `document.getElementById('xet-3d-id').value);">
                Create new 3-D grid!
              </div>
            </div>
          </div>`;
      },
    });
  },
});
