#!/usr/bin/env python3
"""Validate the reviewed toolchain and both prototype images, including RAM budget."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

IMAGES = ('animation', 'diagnostic')
REVIEWED_GCC = '14.3.0'
REVIEWED_BINUTILS = '2.46.0.20260210'
REVIEWED_FLAGS = '-std=c11 -O2 -g -Wall -Wextra -Werror -mmcu=attiny1616 -DF_CPU=1000000UL -ffunction-sections -fdata-sections -fstack-usage'


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, default=Path('build'))
    for option, env, fallback in (('cc', 'AVR_CC', 'avr-gcc'),
                                  ('objdump', 'AVR_OBJDUMP', 'avr-objdump'),
                                  ('objcopy', 'AVR_OBJCOPY', 'avr-objcopy'),
                                  ('size', 'AVR_SIZE', 'avr-size'),
                                  ('nm', 'AVR_NM', 'avr-nm')):
        parser.add_argument('--' + option, default=os.environ.get(env, fallback))
    parser.add_argument('--flags', default=os.environ.get('AVR_FLAGS', REVIEWED_FLAGS))
    parser.add_argument('--toolchain-only', action='store_true')
    return parser.parse_args()


def output(command, label):
    try:
        return subprocess.check_output(command, text=True, stderr=subprocess.STDOUT)
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError(f'{label}: {error}') from error


def tool_versions(args):
    if args.flags.split() != REVIEWED_FLAGS.split():
        raise ValueError('compiler flags differ from the reviewed timing audit; re-audit before changing AVR_FLAGS')
    versions = {}
    for name, command in (('compiler', args.cc), ('objdump', args.objdump),
                          ('objcopy', args.objcopy), ('size', args.size), ('nm', args.nm)):
        versions[name] = output([command, '--version'], name).splitlines()[0]
        expected = REVIEWED_GCC if name == 'compiler' else REVIEWED_BINUTILS
        if not re.search(r'(?<![\d.])' + re.escape(expected) + r'(?![\d.])', versions[name]):
            raise ValueError(f'{name}: timing audit requires {expected}; found {versions[name]}. Re-audit timing before changing the reviewed version.')
    return versions


def memory_usage(elf, objdump):
    lines = output([objdump, '-h', str(elf)], str(elf)).splitlines()
    flash = 0
    sections = {}
    for index, line in enumerate(lines):
        match = re.match(r'\s*\d+\s+(\S+)\s+([0-9a-fA-F]+)\s+', line)
        if match:
            name, size = match[1], int(match[2], 16)
            flags = lines[index + 1] if index + 1 < len(lines) else ''
            sections[name] = size
            # All loadable sections, including initialized SRAM's flash copy.
            if re.search(r'\bLOAD\b', flags):
                flash += size
    if '.text' not in sections:
        raise ValueError(f'{elf}: no .text section; not a usable AVR image')
    ram = sum(sections.get(name, 0) for name in ('.data', '.bss', '.noinit'))
    if flash > 16384:
        raise ValueError(f'{elf}: flash {flash} exceeds 16384 bytes')
    if ram > 1536:
        raise ValueError(f'{elf}: static RAM {ram} exceeds 1536 bytes (512-byte stack budget required)')
    return {'flash_bytes': flash, 'flash_capacity_bytes': 16384,
            'static_ram_bytes': ram, 'sram_capacity_bytes': 2048,
            'stack_budget_bytes': 512, 'unallocated_after_stack_budget_bytes': 2048 - ram - 512}


def inspect_build(args):
    versions = tool_versions(args)  # Must run even with existing images.
    usage = {}
    for name in IMAGES:
        for suffix in ('.elf', '.hex'):
            image = args.build / (name + suffix)
            if not image.is_file() or not image.stat().st_size:
                raise ValueError(f'missing or empty image: {image}')
        usage[name] = memory_usage(args.build / (name + '.elf'), args.objdump)
    return versions, usage


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def main():
    args = arguments()
    try:
        if args.toolchain_only:
            print(json.dumps(tool_versions(args), sort_keys=True))
        else:
            _, usage = inspect_build(args)
            write_json(args.build / 'memory.json', usage)
            for name, memory in usage.items():
                print(f"{name}: flash {memory['flash_bytes']}/16384; static RAM {memory['static_ram_bytes']}/1536; stack budget 512 bytes (not a worst-case proof)")
    except ValueError as error:
        print(f'FAIL AVR build: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
