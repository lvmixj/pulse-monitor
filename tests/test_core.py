"""Headless behavioral checks; all user settings live in a temporary directory."""
import atexit
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
_USER = tempfile.TemporaryDirectory(prefix='pulse-test-user-')
atexit.register(_USER.cleanup)
os.environ['XDG_CONFIG_HOME'] = str(Path(_USER.name)/'config')
os.environ['XDG_DATA_HOME'] = str(Path(_USER.name)/'data')

from PySide6.QtCore import QSettings, QSortFilterProxyModel, Qt
from PySide6.QtWidgets import QApplication
from pulse.collector import Collector
from pulse.processes import ProcessModel
from pulse.theme import STYLE
from pulse.ui import MainWindow

APP = QApplication.instance() or QApplication([])
APP.setStyle('Fusion')
APP.setStyleSheet(STYLE)


class SamplingTests(unittest.TestCase):
    def test_real_samples_are_fresh_and_memory_consistent(self):
        collector = Collector()
        first = collector.sample()
        time.sleep(.05)
        second = collector.sample()
        self.assertGreater(second['time'], first['time'])
        self.assertLess(abs(second['wall_time']-time.time()), 5)
        self.assertEqual(len(second['cpus']), second['cores'])
        self.assertTrue(all(0 <= value <= 100 for value in second['cpus']))
        memory = second['memory']
        self.assertEqual(memory['used'], memory['total']-memory['available'])
        self.assertAlmostEqual(memory['used']/memory['total']*100, memory['percent'], delta=.1)
        for group, keys in [('network', ('down', 'up')), ('disk', ('read', 'write'))]:
            self.assertTrue(all(second[group][key] >= 0 for key in keys))

    def test_gpu_absence_and_driver_failures_are_visible(self):
        collector = Collector()
        collector.gpu_command = None
        cards, error = collector.gpu()
        self.assertEqual(cards, [])
        self.assertIn('nvidia-smi', error)
        collector.gpu_command = '/usr/bin/nvidia-smi'
        with patch('pulse.collector.subprocess.run', side_effect=subprocess.TimeoutExpired('nvidia-smi', 2)):
            cards, error = collector.gpu()
            self.assertEqual(cards, [])
            self.assertIn('超时', error)
        with patch('pulse.collector.subprocess.run', return_value=subprocess.CompletedProcess([], 1, '', 'driver unavailable')):
            cards, error = collector.gpu()
            self.assertEqual(cards, [])
            self.assertIn('driver unavailable', error)

    def test_gpu_unsupported_fields_keep_missing_values(self):
        collector = Collector()
        collector.gpu_command = '/usr/bin/nvidia-smi'
        result = subprocess.CompletedProcess([], 0, 'Demo GPU, 25, 1024, 8192, [N/A], [N/A]\n', '')
        with patch('pulse.collector.subprocess.run', return_value=result):
            cards, error = collector.gpu()
        self.assertEqual(error, '')
        self.assertEqual(cards[0]['usage'], 25)
        self.assertIsNone(cards[0]['temperature'])
        self.assertIsNone(cards[0]['power'])


class InterfaceTests(unittest.TestCase):
    def test_process_sort_uses_numbers(self):
        model = ProcessModel()
        model.replace([dict(name='worker', pid=pid, cpu=cpu, memory=memory, user='demo', status='running')
                       for pid, cpu, memory in [(2, 9, 1024), (10, 100, 512), (3, 20, 4096)]])
        proxy = QSortFilterProxyModel()
        proxy.setSourceModel(model)
        proxy.setSortRole(Qt.ItemDataRole.UserRole)
        proxy.sort(2, Qt.SortOrder.DescendingOrder)
        self.assertEqual([proxy.index(i, 1).data(Qt.ItemDataRole.UserRole) for i in range(3)], [10, 3, 2])
        proxy.sort(3, Qt.SortOrder.DescendingOrder)
        self.assertEqual([proxy.index(i, 1).data(Qt.ItemDataRole.UserRole) for i in range(3)], [3, 2, 10])

    def test_every_page_and_widget_render_without_gpu(self):
        settings = QSettings(str(Path(_USER.name)/'ui.ini'), QSettings.Format.IniFormat)
        window = MainWindow(settings)
        collector = Collector()
        collector.gpu_command = None
        window.show()
        window.receive(collector.sample())
        APP.processEvents()
        try:
            for page in window.pages:
                window.navigate(page)
                APP.processEvents()
                self.assertFalse(window.grab().isNull(), page)
            window.toggle_widget(True)
            APP.processEvents()
            self.assertFalse(window.widget.grab().isNull())
            window.toggle_pause()
            self.assertTrue(window.paused)
            window.receive(collector.sample())
            window.toggle_pause()
            self.assertFalse(window.paused)
        finally:
            window.widget.hide()
            window.hide()
            window.deleteLater()
            APP.processEvents()


if __name__ == '__main__':
    unittest.main()
