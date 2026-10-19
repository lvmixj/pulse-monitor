"""Quota protocol and visible remaining-quota behavior, without real credentials."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from pulse.codex_usage import UsageError, quota_window, read_usage
from pulse.ui import MainWindow
from pulse.panel_config import read_panel


class QuotaTests(unittest.TestCase):
    def test_remaining_and_missing_data(self):
        self.assertEqual(quota_window({'usedPercent': 34})['remaining'], 66)
        self.assertEqual(quota_window({'usedPercent': 110})['remaining'], 0)
        self.assertIsNone(quota_window(None))
        for invalid in (None, '34', float('nan')):
            with self.assertRaises(UsageError):
                quota_window({'usedPercent': invalid})

    def fake_server(self, directory, account, limits):
        path = Path(directory)/'codex'
        replies = {'initialize': {}, 'account/read': {'account': account},
                   'account/rateLimits/read': limits}
        path.write_text(f'''#!{sys.executable}
import json, sys
replies = json.loads({json.dumps(replies)!r})
for line in sys.stdin:
    msg = json.loads(line)
    if 'id' in msg:
        print(json.dumps({{'method':'notification'}}), flush=True)
        print(json.dumps({{'id':msg['id'], 'result':replies[msg['method']]}}), flush=True)
''')
        path.chmod(0o700)
        return str(path)

    def test_actual_stdio_protocol_uses_codex_bucket(self):
        with tempfile.TemporaryDirectory() as directory:
            command = self.fake_server(directory, {'type': 'chatgpt', 'email': 'demo@example.com', 'planType': 'plus'},
                {'rateLimits': {'primary': {'usedPercent': 99}},
                 'rateLimitsByLimitId': {'codex': {'primary': {'usedPercent': 34, 'windowDurationMins': 300}, 'secondary': None}}})
            result = read_usage(command=command)
            self.assertEqual(result['windows'][0]['remaining'], 66)
            self.assertIsNone(result['windows'][1])
            self.assertEqual(result['email'], 'demo@example.com')

    def test_api_auth_and_no_login_are_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            for account in (None, {'type': 'apiKey'}):
                command = self.fake_server(directory, account, {})
                with self.assertRaises(UsageError):
                    read_usage(command=command)

    def test_timeout_ends_server(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'codex'
            path.write_text(f'#!{sys.executable}\nimport time\ntime.sleep(30)\n')
            path.chmod(0o700)
            started = time.monotonic()
            with self.assertRaisesRegex(UsageError, '超时'):
                read_usage(command=str(path), timeout=.1)
            self.assertLess(time.monotonic()-started, 3)

    def test_interface_clears_percentage_on_failure(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            window = MainWindow(QSettings(str(Path(directory)/'test.ini'), QSettings.Format.IniFormat))
            try:
                window.receive_usage(dict(email='demo@example.com', plan='plus', updated_at=time.time(),
                    windows=[quota_window({'usedPercent': 34, 'windowDurationMins': 300, 'resetsAt': time.time()+7200}), None]))
                title, bar, reset = window.quota_rows[0]
                self.assertEqual(title.text(), '5小时剩余 66%')
                self.assertEqual(bar.value(), 660)
                self.assertIn('后重置', reset.text())
                window.receive_usage({'error': '查询超时'})
                self.assertEqual(bar.format(), '—')
                self.assertEqual(window.quota_status.text(), '查询超时')
                self.assertFalse(read_panel(window.settings)['fields']['codex'])
                window.panel_fields['codex'].setChecked(True)
                self.assertTrue(read_panel(window.settings)['fields']['codex'])
                self.assertIn('Codex剩余额度', window.panel_preview.text())
            finally:
                window.widget.hide()
                window.hide()
                window.deleteLater()
                app.processEvents()
