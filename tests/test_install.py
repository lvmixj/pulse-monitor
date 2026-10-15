"""Exercise installer files and launcher in a temporary user/source tree."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import install

SOURCE = Path(__file__).resolve().parents[1]


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pulse-install-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base/'source with 空格'
        self.root.mkdir()
        shutil.copytree(SOURCE/'desktop', self.root/'desktop')
        shutil.copy2(SOURCE/'run.sh', self.root/'run.sh')
        (self.root/'run.sh').chmod(0o644)
        self.python = self.root/'.venv/bin/python'
        self.python.parent.mkdir(parents=True)
        self.python.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$PULSE_TEST_ARGS"\n')
        self.python.chmod(0o755)
        self.config = self.base/'config'
        self.data = self.base/'data'
        self.fake_bin = self.base/'bin'
        self.fake_bin.mkdir()
        (self.fake_bin/'systemctl').write_text('#!/bin/sh\nexit 0\n')
        (self.fake_bin/'systemctl').chmod(0o755)
        self.env = patch.dict(os.environ, {
            'XDG_CONFIG_HOME': str(self.config), 'XDG_DATA_HOME': str(self.data),
            'PATH': str(self.fake_bin)+os.pathsep+os.environ['PATH'],
            'PULSE_TEST_ARGS': str(self.base/'args'),
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.root_patch = patch.object(install, 'ROOT', self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def invoke(self, *args, version='42.9'):
        with patch.object(sys, 'argv', ['install.py', *args]), \
             patch('install.subprocess.run') as run, \
             patch('install.subprocess.check_output', return_value='GNOME Shell '+version), \
             patch('install.shutil.which', return_value='/usr/bin/gnome-shell'):
            install.main()
        return run

    def test_relocated_install_launcher_and_uninstall_preserve_preferences(self):
        self.invoke()
        service = self.config/'systemd/user/pulse-monitor.service'
        self.assertIn(str(self.root), service.read_text())
        self.assertNotIn('@WORKING_DIRECTORY@', service.read_text())
        application = self.data/'applications/pulse-monitor.desktop'
        self.assertIn('Exec="'+str(self.root), application.read_text())
        extension = self.data/'gnome-shell/extensions/pulse-panel@local'
        self.assertEqual(json.loads((extension/'metadata.json').read_text())['shell-version'], ['42'])
        launcher = self.data/'pulse-monitor/launch'
        subprocess.run([str(launcher), '--page', 'gpu'], check=True)
        self.assertEqual((self.base/'args').read_text().splitlines(), ['-m', 'pulse', '--client', '--page', 'gpu'])
        preference = self.config/'Pulse/ResourceMonitor.conf'
        preference.parent.mkdir(parents=True)
        preference.write_text('keep these settings')
        self.invoke('--uninstall')
        for path in (service, application, launcher, extension):
            self.assertFalse(path.exists(), path)
        self.assertEqual(preference.read_text(), 'keep these settings')
        self.assertTrue(self.python.exists())

    def test_other_gnome_versions_keep_extension_uninstalled(self):
        self.invoke(version='46.0')
        self.assertFalse((self.data/'gnome-shell/extensions/pulse-panel@local').exists())
        self.assertTrue((self.data/'applications/pulse-monitor.desktop').exists())

    def test_generated_desktop_entry_passes_system_parser(self):
        if not shutil.which('desktop-file-validate'):
            self.skipTest('desktop-file-validate unavailable')
        self.invoke()
        subprocess.run(['desktop-file-validate', str(self.data/'applications/pulse-monitor.desktop')], check=True)
        if shutil.which('systemd-analyze'):
            subprocess.run(['systemd-analyze', '--user', 'verify',
                            str(self.config/'systemd/user/pulse-monitor.service')], check=True)


if __name__ == '__main__':
    unittest.main()
