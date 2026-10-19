/* Exercise the actual panel update path with plain actor substitutes. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = {
    imports: {
        gi: {St: {}, Clutter: {}, Gio: {}, GLib: {
            build_filenamev: paths => paths.join('/'), get_user_data_dir: () => '/tmp',
            get_user_runtime_dir: () => '/tmp',
        }, GObject: {registerClass: (_, cls) => cls}},
        ui: {main: {}, panelMenu: {Button: class {}}, popupMenu: {}},
        misc: {util: {}}, byteArray: {},
    },
};
vm.runInNewContext(fs.readFileSync('desktop/pulse-panel@local/panel.js', 'utf8')+
    '\nglobalThis.updatePanel = Indicator.prototype._update;', context);
const actor = {
    _position: 'left', _lastTime: 0, _history: {cpu: [], gpu: [], memory: []},
    _metrics: {}, _quota: {},
    _quotaRows: ['5小时', '一周'].map(name => ({name, color: [1, .6, .4],
        text: {set_style(style) { this.style = style; }},
        bar: {queue_repaint() {}}})),
    _cpuChart: {queue_repaint() {}}, _gpuChart: {queue_repaint() {}},
    _summary: {label: {}},
};
const data = {
    wall_time: Date.now()/1000, cpu: 10, memory_percent: 20, memory_used: 1024,
    cores: 4, down: 0, up: 0, gpu: null,
    panel: {position: 'left', style: 'numbers', color: true, width: 50, fields: {codex: true}},
    codex_usage: {updated_at: Date.now()/1000, windows: [{remaining: 58}, {remaining: 78}]},
};
context.updatePanel.call(actor, data);
assert.equal(actor._quota.visible, true);
assert.deepEqual(actor._quotaRows.map(row => row.text.text), ['5小时58%', '一周78%']);
assert.deepEqual(actor._quotaRows.map(row => row.bar.remaining), [58, 78]);
assert.equal(actor._quotaRows[0].bar.width, 50);
data.codex_usage = {error: 'offline'};
context.updatePanel.call(actor, data);
assert.deepEqual(actor._quotaRows.map(row => row.text.text), ['5小时—', '一周—']);
assert.equal(actor._quotaRows[0].bar.remaining, null);
data.codex_usage = {updated_at: Date.now()/1000-181, windows: [{remaining: 100}]};
context.updatePanel.call(actor, data);
assert.equal(actor._quotaRows[0].bar.remaining, null);
data.panel.fields.codex = false;
context.updatePanel.call(actor, data);
assert.equal(actor._quota.visible, false);
console.log('PASS panel quota: labels, remaining bars, optional visibility, errors, stale data');
