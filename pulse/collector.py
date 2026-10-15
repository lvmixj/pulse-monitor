"""Read-only system sampling. Rates use actual elapsed monotonic time."""
import csv
import io
import platform
import shutil
import subprocess
import time
from pathlib import Path

import psutil


def byte_text(value, rate=False):
    suffix = '/s' if rate else ''
    for unit in ('B', 'KiB', 'MiB', 'GiB', 'TiB'):
        if abs(value) < 1024 or unit == 'TiB':
            return f'{value:.1f} {unit}{suffix}'
        value /= 1024


def delta_rate(current, previous, elapsed):
    return max(0, current - previous) / elapsed


def cpu_name():
    for line in Path('/proc/cpuinfo').read_text().splitlines():
        if line.startswith('model name'):
            return line.split(':', 1)[1].strip()
    return platform.processor()


class Collector:
    def __init__(self):
        self.cpu_name = cpu_name()
        self.cores = psutil.cpu_count() or 1
        self.physical = psutil.cpu_count(logical=False)
        self.gpu_command = shutil.which('nvidia-smi')
        self.previous_net = psutil.net_io_counters(pernic=True)
        self.previous_disk = psutil.disk_io_counters(perdisk=True)
        self.previous_time = time.monotonic()
        psutil.cpu_percent(percpu=True)
        for proc in psutil.process_iter():
            try:
                proc.cpu_percent()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    def gpu(self):
        if not self.gpu_command:
            return [], '未找到NVIDIA驱动工具；当前版本使用nvidia-smi采集显卡数据。'
        try:
            result = subprocess.run(
                [self.gpu_command, '--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw',
                 '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=2,
            )
        except subprocess.TimeoutExpired:
            return [], '显卡采集超时，下一次采样会重试。'
        if result.returncode:
            return [], '显卡采集失败：' + result.stderr.strip()[:200]
        def number(text):
            try:
                return float(text.strip())
            except ValueError:
                return None
        cards = []
        for row in csv.reader(io.StringIO(result.stdout)):
            if len(row) != 6:
                return [], '显卡驱动返回了无法解析的数据。'
            cards.append(dict(name=row[0].strip(), usage=number(row[1]),
                              used=number(row[2]), total=number(row[3]),
                              temperature=number(row[4]), power=number(row[5])))
        return cards, '' if cards else '驱动未返回显卡信息。'

    def sample(self):
        now = time.monotonic()
        elapsed = now - self.previous_time
        cpus = psutil.cpu_percent(percpu=True)
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        net = psutil.net_io_counters(pernic=True)
        links = psutil.net_if_stats()
        addresses = psutil.net_if_addrs()
        interfaces = []
        for name, counters in net.items():
            old = self.previous_net.get(name)
            interfaces.append(dict(
                name=name, up=name in links and links[name].isup,
                physical=Path('/sys/class/net', name, 'device').exists(),
                down=delta_rate(counters.bytes_recv, old.bytes_recv, elapsed) if old else 0,
                up_rate=delta_rate(counters.bytes_sent, old.bytes_sent, elapsed) if old else 0,
                received=counters.bytes_recv, sent=counters.bytes_sent,
                ip=', '.join(a.address for a in addresses.get(name, []) if a.family == 2),
            ))
        active = [i for i in interfaces if i['physical'] and i['up']]
        disks = psutil.disk_io_counters(perdisk=True)
        read = write = 0
        for name, counters in disks.items():
            # /sys/block holds whole devices, so partitions are never counted twice.
            if not Path('/sys/block', name).exists() or name.startswith(('loop', 'ram', 'dm-', 'md')):
                continue
            old = self.previous_disk.get(name)
            if old:
                read += delta_rate(counters.read_bytes, old.read_bytes, elapsed)
                write += delta_rate(counters.write_bytes, old.write_bytes, elapsed)
        mounts, seen = [], set()
        for partition in psutil.disk_partitions(all=False):
            if partition.device in seen or partition.fstype == 'squashfs':
                continue
            seen.add(partition.device)
            try:
                usage = psutil.disk_usage(partition.mountpoint)
            except (PermissionError, FileNotFoundError):
                continue
            mounts.append(dict(path=partition.mountpoint, device=partition.device,
                               total=usage.total, used=usage.used, free=usage.free,
                               percent=usage.percent))
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'username', 'memory_info', 'status']):
            try:
                info = proc.info
                if info['memory_info'] is None:
                    continue
                processes.append(dict(pid=info['pid'], name=info['name'] or str(info['pid']),
                                      user=info['username'] or '—', status=info['status'],
                                      cpu=proc.cpu_percent() / self.cores,
                                      memory=info['memory_info'].rss))
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        temperatures = psutil.sensors_temperatures()
        cpu_temps = temperatures.get('k10temp', temperatures.get('coretemp', []))
        temperature = max((t.current for t in cpu_temps), default=None)
        freq = psutil.cpu_freq()
        gpus, gpu_error = self.gpu()
        self.previous_net, self.previous_disk, self.previous_time = net, disks, now
        return dict(
            time=now, wall_time=time.time(), cpu=sum(cpus) / len(cpus), cpus=cpus,
            cpu_name=self.cpu_name, cores=self.cores, physical=self.physical,
            frequency=freq.current if freq else None, temperature=temperature,
            memory=dict(total=memory.total, used=memory.total-memory.available,
                        available=memory.available, percent=memory.percent,
                        cached=getattr(memory, 'cached', 0)),
            swap=dict(total=swap.total, used=swap.used, percent=swap.percent),
            network=dict(down=sum(i['down'] for i in active), up=sum(i['up_rate'] for i in active),
                         interfaces=interfaces, names=', '.join(i['name'] for i in active) or '无活动物理网卡'),
            disk=dict(read=read, write=write, mounts=mounts),
            gpus=gpus, gpu_error=gpu_error, processes=processes,
            uptime=time.time()-psutil.boot_time(), load=psutil.getloadavg(), hostname=platform.node(),
        )
