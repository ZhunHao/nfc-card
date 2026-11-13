#!/usr/bin/env python3
"""Package images after `make release` has freshly built and verified them."""
import hashlib
from pathlib import Path
import shutil
import sys

from check_build import arguments, inspect_build, output, write_json


def package(args):
    versions, usage = inspect_build(args)
    repo = Path(__file__).resolve().parents[2]
    source = {'commit': output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], 'source commit').strip(),
              'dirty': bool(output(['git', '-C', str(repo), 'status', '--porcelain', '--untracked-files=normal'], 'source state').strip())}
    folder = args.build / 'release'
    folder.mkdir(exist_ok=True)
    images = {}
    for name, source_name in (('card', 'animation'), ('diagnostic', 'diagnostic')):
        for suffix in ('.elf', '.hex'):
            filename = name + suffix
            shutil.copyfile(args.build / (source_name + suffix), folder / filename)
            data = (folder / filename).read_bytes()
            images[filename] = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
    manifest = {
        'schema_version': 1, 'artifact_kind': 'prototype',
        'validation': 'physical validation pending', 'mcu': 'attiny1616',
        'f_cpu_hz': 1_000_000, 'source': source, 'tools': versions,
        'build_flags': args.flags + ' -Wl,--gc-sections',
        'fuse_field_intentions': {'freqsel': 'fcpu_16mhz', 'bodactive': 'bod_enabled',
                                  'bodlevel': 'bod_1v8 (BODLEVEL0)', 'sut': 'sut_0ms', 'rstpincfg': 'updi (preserve)',
                                  'other_fields': 'preserve readback'},
        'runtime_clock_divider': 16, 'vlm_level': 0,
        'elf_build_provenance': 'ELF debug/symbol data retains build paths and GCC temporary object names; fresh ELF rebuilds may differ while executable HEX bytes agree.',
        'timing_document': 'firmware/docs/timing.md',
        'timing_document_sha256': hashlib.sha256((repo / 'firmware/docs/timing.md').read_bytes()).hexdigest(),
        'memory': usage, 'images': images,
        'validation_scope': 'Host behavior tests, both AVR builds, memory gate and emitted ISR instruction checks via make release; main-loop timing is a manual audit. No bench validation.',
    }
    write_json(folder / 'manifest.json', manifest)
    checksum_files = sorted([*images, 'manifest.json'])
    (folder / 'SHA256SUMS').write_text(''.join(f'{hashlib.sha256((folder / name).read_bytes()).hexdigest()}  {name}\n' for name in checksum_files))
    print(f'Prototype package: {folder} (physical validation pending)')


def main():
    try:
        package(arguments())
    except (ValueError, OSError) as error:
        print(f'FAIL release: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
