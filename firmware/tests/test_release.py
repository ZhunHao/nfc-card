"""Real AVR object fixtures exercise size and packaging failures."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CC = os.environ.get('AVR_CC', 'avr-gcc')
OBJCOPY = os.environ.get('AVR_OBJCOPY', 'avr-objcopy')
OBJDUMP = os.environ.get('AVR_OBJDUMP', 'avr-objdump')


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.build = Path(self.tmp.name)
        self.fixture()

    def fixture(self, flash=4, bss=3, noinit=2):
        assembly = self.build / 'fixture.S'
        assembly.write_text(f'.text\n.space {flash}\n.data\n.byte 1\n.bss\n.space {bss}\n.section .noinit,"aw",@nobits\n.space {noinit}\n')
        for name in ('animation', 'diagnostic'):
            subprocess.run([CC, '-mmcu=attiny1616', '-c', str(assembly), '-o', str(self.build / (name + '.elf'))], check=True, capture_output=True)
            subprocess.run([OBJCOPY, '-O', 'ihex', str(self.build / (name + '.elf')), str(self.build / (name + '.hex'))], check=True, capture_output=True)

    def run_tool(self, name, *args):
        return subprocess.run([sys.executable, str(ROOT / 'tools' / name), '--build', str(self.build), '--cc', CC, '--objdump', OBJDUMP, *args], text=True, capture_output=True)

    def check_failure(self, result, reason):
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(reason, result.stderr)

    def test_missing_compiler_rejects_even_existing_images(self):
        self.check_failure(self.run_tool('check_build.py', '--cc', '/nonexistent/avr-gcc'), 'compiler')

    def test_missing_image_is_rejected(self):
        (self.build / 'diagnostic.hex').unlink()
        self.check_failure(self.run_tool('check_build.py'), 'diagnostic.hex')

    def test_flash_above_limit_is_rejected(self):
        self.fixture(flash=16384)
        self.check_failure(self.run_tool('check_build.py'), 'flash')

    def test_static_ram_includes_noinit_and_reserves_stack(self):
        self.fixture(bss=1535, noinit=1)
        self.check_failure(self.run_tool('check_build.py'), 'static RAM')

    def test_exact_memory_limits_are_accepted(self):
        self.fixture(flash=16383, bss=1534, noinit=1)
        result = self.run_tool('check_build.py')
        self.assertEqual(result.returncode, 0, result.stderr)
        usage = json.loads((self.build / 'memory.json').read_text())
        self.assertEqual(usage['animation']['flash_bytes'], 16384)
        self.assertEqual(usage['animation']['static_ram_bytes'], 1536)
        self.assertEqual(usage['animation']['stack_budget_bytes'], 512)

    def test_release_records_hashes_provenance_and_is_repeatable(self):
        result = self.run_tool('release.py')
        self.assertEqual(result.returncode, 0, result.stderr)
        folder = self.build / 'release'
        first = {p.name: p.read_bytes() for p in folder.iterdir()}
        manifest = json.loads(first['manifest.json'])
        self.assertEqual(manifest['validation'], 'physical validation pending')
        self.assertEqual(manifest['mcu'], 'attiny1616')
        self.assertEqual(manifest['f_cpu_hz'], 1_000_000)
        self.assertEqual(manifest['images']['card.hex']['sha256'], hashlib.sha256((self.build / 'animation.hex').read_bytes()).hexdigest())
        self.assertEqual(manifest['memory']['animation']['static_ram_bytes'], 6)
        self.assertRegex(manifest['source']['commit'], r'^[0-9a-f]{40}$')
        self.assertIsInstance(manifest['source']['dirty'], bool)
        self.assertIn('14.3.0', manifest['tools']['compiler'])
        for name in ('card.elf', 'card.hex', 'diagnostic.elf', 'diagnostic.hex'):
            self.assertEqual(manifest['images'][name]['sha256'], hashlib.sha256(first[name]).hexdigest())
        result = self.run_tool('release.py')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(first, {p.name: p.read_bytes() for p in folder.iterdir()})

    def test_release_refuses_missing_image(self):
        (self.build / 'animation.elf').unlink()
        self.check_failure(self.run_tool('release.py'), 'animation.elf')
        self.assertFalse((self.build / 'release').exists())


class MakeGateTests(unittest.TestCase):
    def test_environment_compiler_override_reaches_make(self):
        env = {k: v for k, v in os.environ.items() if k not in ('MAKEFLAGS', 'MFLAGS', 'MAKEOVERRIDES')}
        env['AVR_CC'] = CC
        result = subprocess.run(['make', '-C', str(ROOT), 'toolchain-check'], env=env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_unreviewed_flags_fail_before_build(self):
        env = {k: v for k, v in os.environ.items() if k not in ('MAKEFLAGS', 'MFLAGS', 'MAKEOVERRIDES')}
        env['AVR_CC'] = CC
        result = subprocess.run(['make', '-C', str(ROOT), 'toolchain-check', 'AVR_FLAGS=-O0'], env=env, text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('flags', result.stderr)

    def test_missing_environment_compiler_cannot_reuse_existing_images(self):
        env = {k: v for k, v in os.environ.items() if k not in ('MAKEFLAGS', 'MFLAGS', 'MAKEOVERRIDES')}
        env['AVR_CC'] = '/nonexistent/avr-gcc'
        result = subprocess.run(['make', '-C', str(ROOT), 'avr'], env=env, text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('compiler', result.stderr)


if __name__ == '__main__':
    unittest.main()
