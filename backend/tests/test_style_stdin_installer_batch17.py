"""Batch 17 conservative installer regression tests (no project files modified)."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

INSTALLER = Path(__file__).resolve().parents[1] / 'tools' / 'install_stdin_batch17.py'
spec = importlib.util.spec_from_file_location('batch17_stdin_installer_for_tests', INSTALLER)
installer = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = installer
spec.loader.exec_module(installer)


class InstallerTests(unittest.TestCase):
    def test_anchor_replacement_exactly_one(self):
        self.assertEqual(installer._replace('abc', 'b', 'X', 'sample'), 'aXc')

    def test_missing_anchor_rejected(self):
        with self.assertRaises(RuntimeError):
            installer._replace('abc', 'z', 'X', 'sample')

    def test_duplicate_anchor_rejected(self):
        with self.assertRaises(RuntimeError):
            installer._replace('aa', 'a', 'X', 'sample')

    def test_bom_and_crlf_preservation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'sample.py'
            path.write_bytes(b'\xef\xbb\xbfhello\r\nworld\r\n')
            value, eol, bom = installer._read(path)
            self.assertEqual(value, 'hello\nworld\n')
            self.assertTrue(bom)
            self.assertEqual(eol, '\r\n')
            self.assertEqual(installer._encode(value,eol,bom),path.read_bytes())

    def test_missing_dependency_aborts_before_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(RuntimeError):
                installer.build_changes(Path(directory))

    def test_installed_fixtures_are_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in installer.ALL:
                path=root/relative
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text('# '+installer.MARK+'\n',encoding='utf-8')
            for relative, payload in installer.NEW_FILES.items():
                path = root/relative
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes((installer.PAYLOAD/payload).read_bytes())
            changes,status=installer.build_changes(root)
            self.assertEqual(status,'already_installed')
            self.assertEqual(changes,{})

    def test_installer_creates_backup_without_overwriting_in_git(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'.git').mkdir()
            file=root/'backend'/'test.py'
            file.parent.mkdir(parents=True)
            file.write_bytes(b'old\n')
            with patch.object(installer,'build_changes',return_value=({file:b'new\n'},'ready')):
                message=installer.install(root)
            self.assertIn('installed:',message)
            self.assertEqual(file.read_bytes(),b'new\n')
            self.assertEqual((root/'.git'/'capstone_batch17_backups'/'backend'/'test.py').read_bytes(),b'old\n')

    def test_check_does_not_modify_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'.git').mkdir()
            file=root/'backend'/'test.py'
            file.parent.mkdir(parents=True)
            file.write_bytes(b'old')
            with patch.object(installer,'build_changes',return_value=({file:b'new'},'ready')):
                message=installer.install(root,check=True)
            self.assertIn('ready',message)
            self.assertEqual(file.read_bytes(),b'old')


if __name__ == '__main__':
    unittest.main()
