/* exported init */
'use strict';
const {St, Clutter, Gio, GLib, GObject} = imports.gi;
const Main = imports.ui.main;
const PanelMenu = imports.ui.panelMenu;
const PopupMenu = imports.ui.popupMenu;
const Util = imports.misc.util;
const ByteArray = imports.byteArray;
const UUID = 'pulse-panel@local';
const LAUNCHER = GLib.build_filenamev([GLib.get_user_data_dir(), 'pulse-monitor', 'launch']);
const RUNTIME = GLib.get_user_runtime_dir();
const COLORS = {cpu: [0.38, 0.71, 1], gpu: [0.35, 0.85, 0.75], memory: [0.74, 0.61, 1]};

function command(...args) {
    Util.spawn([LAUNCHER, ...args]);
}
function rate(value) {
    return value >= 1048576 ? `${(value / 1048576).toFixed(1)}M` : `${(value / 1024).toFixed(0)}K`;
}
function graph(color, height = 20, width = 50) {
    const area = new St.DrawingArea({width, height, y_align: Clutter.ActorAlign.CENTER});
    area.samples = [];
    area.mode = 'graphs';
    area.color = color;
    area.seconds = 60;
    area.connect('repaint', () => {
        const cr = area.get_context();
        const [w, h] = area.get_surface_size();
        cr.setSourceRGBA(1, 1, 1, 0.09);
        cr.rectangle(0, 0, w, h);
        cr.fill();
        const samples = area.samples;
        if (samples.length) {
            cr.setSourceRGBA(...area.color, 1);
            if (area.mode === 'bars') {
                if (area.cores && area.cores.length) {
                    const step = w/area.cores.length;
                    area.cores.forEach((value, i) => {
                        const barHeight = (h-2)*value/100;
                        cr.rectangle(i*step, h-1-barHeight, Math.max(0.5, step-0.4), barHeight);
                    });
                    cr.fill();
                } else {
                    const value = samples[samples.length-1].value;
                    if (value !== null) { cr.rectangle(0, h*0.3, w*value/100, h*0.4); cr.fill(); }
                }
            } else {
                cr.setLineWidth(1.5);
                const now = samples[samples.length-1].time;
                let started = false;
                for (const sample of samples) {
                    if (now-sample.time > area.seconds) continue;
                    if (sample.value === null) { started = false; continue; }
                    const x = w - (now-sample.time)/area.seconds*w;
                    const y = h-1-(h-2)*sample.value/100;
                    if (started) cr.lineTo(x, y); else cr.moveTo(x, y);
                    started = true;
                }
                cr.stroke();
            }
        }
        cr.$dispose();
    });
    return area;
}

function quotaBar(color) {
    const area = new St.DrawingArea({width: 42, height: 4, y_align: Clutter.ActorAlign.CENTER});
    area.remaining = null;
    area.color = color;
    area.connect('repaint', () => {
        const cr = area.get_context();
        const [w, h] = area.get_surface_size();
        cr.setSourceRGBA(1, 1, 1, 0.16);
        cr.rectangle(0, 0, w, h);
        cr.fill();
        if (area.remaining !== null) {
            cr.setSourceRGBA(...area.color, 1);
            cr.rectangle(0, 0, w*area.remaining/100, h);
            cr.fill();
        }
        cr.$dispose();
    });
    return area;
}

const Indicator = GObject.registerClass({GTypeName: 'PulseNativePanelIndicatorV2'}, class Indicator extends PanelMenu.Button {
    _init() {
        super._init(0.0, 'Pulse系统资源监控');
        this._alive = true;
        this._busy = false;
        this._lastTime = 0;
        this._position = 'left';
        this._history = {cpu: [], gpu: [], memory: []};
        this._row = new St.BoxLayout({style: 'spacing: 12px;'});
        this.add_child(this._row);
        this._brand = new St.Label({text: '◉', y_align: Clutter.ActorAlign.CENTER, style: 'color: #90cbff;'});
        this._row.add_child(this._brand);
        this._metrics = {};
        for (const key of ['memory', 'network', 'cpu', 'frequency', 'gpu', 'vram', 'temperature']) {
            const box = new St.BoxLayout({style: 'spacing: 5px;'});
            const text = new St.Label({text: '—', y_align: Clutter.ActorAlign.CENTER});
            box.add_child(text);
            const chart = COLORS[key] ? graph(COLORS[key]) : null;
            if (chart) box.add_child(chart);
            this._row.add_child(box);
            this._metrics[key] = {box, text, chart};
        }
        this._quota = new St.BoxLayout({vertical: true, y_align: Clutter.ActorAlign.CENTER});
        this._quotaRows = [];
        for (const [name, color] of [['5小时', [0.91, 0.74, 0.44]], ['一周', [0.91, 0.60, 0.72]]]) {
            const row = new St.BoxLayout({style: 'spacing: 5px;'});
            const text = new St.Label({text: `${name}—`, style: 'font-size: 10px; min-width: 60px;'});
            const bar = quotaBar(color);
            row.add_child(text);
            row.add_child(bar);
            this._quota.add_child(row);
            this._quotaRows.push({name, color, text, bar});
        }
        this._quota.hide();
        this._row.add_child(this._quota);
        this._summary = new PopupMenu.PopupMenuItem('正在连接后台', {reactive: false});
        this.menu.addMenuItem(this._summary);
        for (const key of ['cpu', 'gpu']) {
            const item = new PopupMenu.PopupBaseMenuItem({reactive: false});
            const box = new St.BoxLayout({vertical: true, style: 'spacing: 5px;'});
            box.add_child(new St.Label({text: key === 'cpu' ? 'CPU整体利用率 · 最近60秒' : 'GPU利用率 · 最近60秒'}));
            const chart = graph(COLORS[key], 65, 350);
            box.add_child(chart);
            item.add_child(box);
            this.menu.addMenuItem(item);
            this[`_${key}Chart`] = chart;
        }
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        for (const [title, args] of [['打开系统总览', []], ['查看CPU各核心', ['--page', 'cpu']], ['查看GPU引擎', ['--page', 'gpu']], ['顶栏设置', ['--page', 'panel']], ['显示/隐藏桌面小组件', ['--toggle-widget']], ['退出Pulse监控', ['--quit']]])
            this.menu.addAction(title, () => command(...args));
        Main.panel.addToStatusArea(UUID, this, 1, 'left');
        this._file = Gio.File.new_for_path(`${RUNTIME}/pulse-monitor.json`);
        this._marker = Gio.File.new_for_path(`${RUNTIME}/pulse-panel-native.json`);
        this._timer = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 1, () => {
            this._refresh();
            return GLib.SOURCE_CONTINUE;
        });
        this._refresh();
    }
    _refresh() {
        if (!this._alive || this._busy) return;
        this._busy = true;
        this._file.load_contents_async(null, (file, result) => {
            this._busy = false;
            if (!this._alive) return;
            try {
                const [, contents] = file.load_contents_finish(result);
                const data = JSON.parse(ByteArray.toString(contents));
                if (Date.now()/1000-data.wall_time > 10) {
                    this._summary.label.text = '后台数据已中断，点击菜单重新打开Pulse';
                    this._brand.text = 'Ⅱ';
                    return;
                }
                this._brand.text = '◉';
                this._update(data);
            } catch (error) {
                this._summary.label.text = '后台已停止，点击“打开系统总览”启动';
                this._brand.text = 'Ⅱ';
            }
        });
        const marker = JSON.stringify({updated: Date.now(), position: this._position, lastTime: this._lastTime, style: this._style, fields: this._visibleFields, x: this.get_transformed_position()[0],
            codex: {visible: this._quota.visible, labels: this._quotaRows.map(row => row.text.text), remaining: this._quotaRows.map(row => row.bar.remaining)}});
        this._marker.replace_contents_bytes_async(new GLib.Bytes(ByteArray.fromString(marker)), null, false, Gio.FileCreateFlags.PRIVATE, null, (file, result) => {
            try { file.replace_contents_finish(result); } catch (error) { logError(error, 'Pulse panel heartbeat'); }
        });
    }
    _update(data) {
        const config = data.panel || {position: 'left', style: 'graphs', color: true, width: 50, fields: {cpu: true, gpu: true, memory: true, network: true, frequency: true, vram: true}};
        const gpu = data.gpu;
        this._style = config.style;
        this._visibleFields = Object.keys(config.fields).filter(k => config.fields[k]);
        const usage = gpu ? gpu.usage : null;
        const readings = {cpu: data.cpu, memory: data.memory_percent, gpu: usage};
        if (data.wall_time !== this._lastTime) {
            this._lastTime = data.wall_time;
            for (const key of Object.keys(this._history)) {
                this._history[key].push({time: data.wall_time, value: readings[key]});
                this._history[key] = this._history[key].filter(s => data.wall_time-s.time <= 60);
            }
        }
        const values = {
            cpu: `CPU ${data.cpu.toFixed(0)}%`, frequency: data.frequency ? `${(data.frequency/1000).toFixed(2)}GHz` : '频率—',
            memory: `内存 ${(data.memory_used/1073741824).toFixed(1)}G`, network: `↓${rate(data.down)} ↑${rate(data.up)}`,
            gpu: usage === null ? 'GPU —' : `GPU ${usage.toFixed(0)}%`,
            vram: gpu && gpu.used !== null ? `显存 ${(gpu.used/1024).toFixed(1)}G` : '显存—',
            temperature: gpu && gpu.temperature !== null ? `${gpu.temperature.toFixed(0)}°C` : '温度—',
        };
        for (const [key, metric] of Object.entries(this._metrics)) {
            metric.box.visible = !!config.fields[key];
            metric.text.text = values[key];
            const color = config.color && COLORS[key] ? COLORS[key] : [0.9, 0.94, 1];
            metric.text.set_style(config.color && COLORS[key] ? `color: rgb(${color.map(v => Math.round(v*255)).join(',')});` : '');
            if (metric.chart) {
                metric.chart.visible = config.style !== 'numbers';
                metric.chart.width = config.width;
                metric.chart.mode = config.style;
                metric.chart.color = color;
                metric.chart.samples = this._history[key];
                if (key === 'cpu') metric.chart.cores = data.cpus;
                metric.chart.queue_repaint();
            }
        }
        this._quota.visible = !!config.fields.codex;
        const quota = data.codex_usage;
        const fresh = quota && !quota.error && Date.now()/1000-quota.updated_at < 180;
        this._quotaRows.forEach((row, index) => {
            const window = fresh && quota.windows ? quota.windows[index] : null;
            const remaining = window && Number.isFinite(window.remaining) ? Math.max(0, Math.min(100, window.remaining)) : null;
            row.text.text = `${row.name}${remaining === null ? '—' : `${Math.round(remaining)}%`}`;
            const color = config.color ? row.color : [0.9, 0.94, 1];
            row.text.set_style(`font-size: 10px; min-width: 60px; color: rgb(${color.map(v => Math.round(v*255)).join(',')});`);
            row.bar.color = color;
            row.bar.width = config.width;
            row.bar.remaining = remaining;
            row.bar.queue_repaint();
        });
        for (const key of ['cpu', 'gpu']) {
            this[`_${key}Chart`].samples = this._history[key];
            this[`_${key}Chart`].queue_repaint();
        }
        this._summary.label.text = `CPU ${data.cpu.toFixed(1)}% · 内存 ${data.memory_percent.toFixed(1)}% · ${data.cores}线程`;
        if (config.position !== this._position) {
            this._position = config.position;
            const parent = this.container.get_parent();
            if (parent) parent.remove_child(this.container);
            const target = {left: Main.panel._leftBox, center: Main.panel._centerBox, right: Main.panel._rightBox}[this._position];
            target.insert_child_at_index(this.container, 1);
        }
    }
    destroy() {
        this._alive = false;
        if (this._timer) GLib.source_remove(this._timer);
        try { this._marker.delete(null); } catch (error) { /* marker may already be absent */ }
        super.destroy();
    }
});

class Extension {
    enable() { this._indicator = new Indicator(); }
    disable() { if (this._indicator) this._indicator.destroy(); this._indicator = null; }
}
function init() { return new Extension(); }
