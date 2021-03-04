#!/usr/bin/env python3
#
# Copyright 2020, The Android Open Source Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests mkbootimg and unpack_bootimg."""

import json
import logging
import os
import subprocess
import sys
import tempfile
import unittest

BOOT_ARGS_OFFSET = 64
BOOT_ARGS_SIZE = 512
BOOT_EXTRA_ARGS_OFFSET = 608
BOOT_EXTRA_ARGS_SIZE = 1024
BOOT_V3_ARGS_OFFSET = 44
VENDOR_BOOT_ARGS_OFFSET = 28
VENDOR_BOOT_ARGS_SIZE = 2048


def create_blank_file(pathname, size):
    """Creates a zero-filled file and returns its pathname."""
    with open(pathname, 'wb') as f:
        f.write(b'\x00' * size)
    return pathname


def subsequence_of(list1, list2):
    """Returns True if list1 is a subsequence of list2.

    >>> subsequence_of([], [1])
    True
    >>> subsequence_of([2, 4], [1, 2, 3, 4])
    True
    >>> subsequence_of([1, 2, 2], [1, 2, 3])
    False
    """
    if len(list1) == 0:
        return True
    if len(list2) == 0:
        return False
    if list1[0] == list2[0]:
        return subsequence_of(list1[1:], list2[1:])
    return subsequence_of(list1, list2[1:])


class MkbootimgTest(unittest.TestCase):
    """Tests the functionalities of mkbootimg and unpack_bootimg."""

    def test_vendor_boot_v4(self):
        """Tests vendor_boot version 4."""
        with tempfile.TemporaryDirectory() as temp_out_dir:
            vendor_boot_img = os.path.join(temp_out_dir, 'vendor_boot.img')
            dtb = create_blank_file(os.path.join(temp_out_dir, 'dtb'), 0x1000)
            ramdisk1 = create_blank_file(os.path.join(temp_out_dir, 'ramdisk1'),
                0x1000)
            ramdisk2 = create_blank_file(os.path.join(temp_out_dir, 'ramdisk2'),
                0x2000)
            bootconfig = create_blank_file(os.path.join(temp_out_dir,
                'bootconfig'), 0x1000)
            mkbootimg_cmds = [
                'mkbootimg',
                '--header_version', '4',
                '--vendor_boot', vendor_boot_img,
                '--dtb', dtb,
                '--vendor_ramdisk', ramdisk1,
                '--ramdisk_type', 'PLATFORM',
                '--ramdisk_name', 'RAMDISK1',
                '--vendor_ramdisk_fragment', ramdisk1,
                '--ramdisk_type', 'DLKM',
                '--ramdisk_name', 'RAMDISK2',
                '--board_id0', '0xC0FFEE',
                '--board_id15', '0x15151515',
                '--vendor_ramdisk_fragment', ramdisk2,
                '--vendor_bootconfig', bootconfig,
            ]
            unpack_bootimg_cmds = [
                'unpack_bootimg',
                '--boot_img', vendor_boot_img,
                '--out', os.path.join(temp_out_dir, 'out'),
            ]
            expected_output = [
                'boot_magic: VNDRBOOT',
                'vendor boot image header version: 4',
                'vendor ramdisk total size: 16384',
                'dtb size: 4096',
                'vendor ramdisk table size: 324',
                'size: 4096', 'offset: 0', 'type: 0x0', 'name:',
                '0x00000000, 0x00000000, 0x00000000, 0x00000000,',
                '0x00000000, 0x00000000, 0x00000000, 0x00000000,',
                '0x00000000, 0x00000000, 0x00000000, 0x00000000,',
                '0x00000000, 0x00000000, 0x00000000, 0x00000000,',
                'size: 4096', 'offset: 4096', 'type: 0x1', 'name: RAMDISK1',
                '0x00000000, 0x00000000, 0x00000000, 0x00000000,',
                '0x00000000, 0x00000000, 0x00000000, 0x00000000,',
                '0x00000000, 0x00000000, 0x00000000, 0x00000000,',
                '0x00000000, 0x00000000, 0x00000000, 0x00000000,',
                'size: 8192', 'offset: 8192', 'type: 0x3', 'name: RAMDISK2',
                '0x00c0ffee, 0x00000000, 0x00000000, 0x00000000,',
                '0x00000000, 0x00000000, 0x00000000, 0x00000000,',
                '0x00000000, 0x00000000, 0x00000000, 0x00000000,',
                '0x00000000, 0x00000000, 0x00000000, 0x15151515,',
                'vendor bootconfig size: 4096',
            ]

            subprocess.run(mkbootimg_cmds, check=True)
            result = subprocess.run(unpack_bootimg_cmds, check=True,
                                    capture_output=True, encoding='utf-8')
            output = [line.strip() for line in result.stdout.splitlines()]
            if not subsequence_of(expected_output, output):
                msg = '\n'.join([
                    'Unexpected unpack_bootimg output:',
                    'Expected:',
                    ' ' + '\n '.join(expected_output),
                    '',
                    'Actual:',
                    ' ' + '\n '.join(output),
                ])
                self.fail(msg)

    def test_unpack_boot_image_v3_json_args(self):
        """Tests mkbootimg_args.json when unpacking a boot image version 3."""
        with tempfile.TemporaryDirectory() as temp_out_dir:
            boot_img = os.path.join(temp_out_dir, 'boot.img')
            kernel = create_blank_file(os.path.join(temp_out_dir, 'kernel'),
                0x1000)
            ramdisk = create_blank_file(os.path.join(temp_out_dir, 'ramdisk'),
                0x1000)
            mkbootimg_cmds = [
                'mkbootimg',
                '--header_version', '3',
                '--kernel', kernel,
                '--ramdisk', ramdisk,
                '--cmdline', 'test-cmdline',
                '--os_version', '11.0.0',
                '--os_patch_level', '2021-01',
                '--output', boot_img,
            ]
            unpack_bootimg_cmds = [
                'unpack_bootimg',
                '--boot_img', boot_img,
                '--out', os.path.join(temp_out_dir, 'out'),
            ]
            # The expected dict in mkbootimg_args.json.
            expected_mkbootimg_args = {
                'cmdline': 'test-cmdline',
                'header_version': '3',
                'os_patch_level': '2021-01',
                'os_version': '11.0.0'
            }

            subprocess.run(mkbootimg_cmds, check=True)
            subprocess.run(unpack_bootimg_cmds, check=True)

            json_file = os.path.join(temp_out_dir, 'out', 'mkbootimg_args.json')
            with open (json_file) as json_fd:
                actual_mkbootimg_args = json.load(json_fd)
                self.assertEqual(actual_mkbootimg_args,
                                 expected_mkbootimg_args)

    def test_unpack_vendor_boot_image_v3_json_args(self):
        """Tests mkbootimg_args.json when unpacking a vendor boot image version
        3.
        """
        with tempfile.TemporaryDirectory() as temp_out_dir:
            vendor_boot_img = os.path.join(temp_out_dir, 'vendor_boot.img')
            dtb = create_blank_file(os.path.join(temp_out_dir, 'dtb'), 0x1000)
            ramdisk = create_blank_file(os.path.join(temp_out_dir, 'ramdisk'),
                0x1000)
            mkbootimg_cmds = [
                'mkbootimg',
                '--header_version', '3',
                '--vendor_boot', vendor_boot_img,
                '--vendor_ramdisk', ramdisk,
                '--dtb', dtb,
                '--vendor_cmdline', 'test-vendor_cmdline',
                '--board', 'product_name',
                '--base', '0x00000000',
                '--dtb_offset', '0x01f00000',
                '--kernel_offset', '0x00008000',
                '--pagesize', '0x00001000',
                '--ramdisk_offset', '0x01000000',
                '--tags_offset', '0x00000100',
            ]
            unpack_bootimg_cmds = [
                'unpack_bootimg',
                '--boot_img', vendor_boot_img,
                '--out', os.path.join(temp_out_dir, 'out'),
            ]
            # The expected dict in mkbootimg_args.json.
            expected_mkbootimg_args = {
                'header_version': '3',
                'vendor_cmdline': 'test-vendor_cmdline',
                'board': 'product_name',
                'base': '0x00000000',
                'dtb_offset': '0x0000000001f00000',  # dtb_offset is uint64_t.
                'kernel_offset': '0x00008000',
                'pagesize': '0x00001000',
                'ramdisk_offset': '0x01000000',
                'tags_offset': '0x00000100',
            }

            subprocess.run(mkbootimg_cmds, check=True)
            subprocess.run(unpack_bootimg_cmds, check=True)

            json_file = os.path.join(temp_out_dir, 'out', 'mkbootimg_args.json')
            with open (json_file) as json_fd:
                actual_mkbootimg_args = json.load(json_fd)
                self.assertEqual(actual_mkbootimg_args,
                                 expected_mkbootimg_args)

    def test_boot_image_v2_cmdline_null_terminator(self):
        """Tests that kernel commandline is null-terminated."""
        with tempfile.TemporaryDirectory() as temp_out_dir:
            dtb = create_blank_file(os.path.join(temp_out_dir, 'dtb'), 0x1000)
            kernel = create_blank_file(os.path.join(temp_out_dir, 'kernel'),
                                       0x1000)
            ramdisk = create_blank_file(os.path.join(temp_out_dir, 'ramdisk'),
                                        0x1000)
            cmdline = (BOOT_ARGS_SIZE - 1) * 'x'
            extra_cmdline = (BOOT_EXTRA_ARGS_SIZE - 1) * 'y'
            boot_img = os.path.join(temp_out_dir, 'boot.img')
            mkbootimg_cmds = [
                'mkbootimg',
                '--header_version', '2',
                '--dtb', dtb,
                '--kernel', kernel,
                '--ramdisk', ramdisk,
                '--cmdline', cmdline + extra_cmdline,
                '--output', boot_img,
            ]

            subprocess.run(mkbootimg_cmds, check=True)

            with open(boot_img, 'rb') as f:
                raw_boot_img = f.read()
            raw_cmdline = raw_boot_img[BOOT_ARGS_OFFSET:][:BOOT_ARGS_SIZE]
            raw_extra_cmdline = (raw_boot_img[BOOT_EXTRA_ARGS_OFFSET:]
                                 [:BOOT_EXTRA_ARGS_SIZE])
            self.assertEqual(raw_cmdline, cmdline.encode() + b'\x00')
            self.assertEqual(raw_extra_cmdline,
                             extra_cmdline.encode() + b'\x00')

    def test_boot_image_v3_cmdline_null_terminator(self):
        """Tests that kernel commandline is null-terminated."""
        with tempfile.TemporaryDirectory() as temp_out_dir:
            kernel = create_blank_file(os.path.join(temp_out_dir, 'kernel'),
                                       0x1000)
            ramdisk = create_blank_file(os.path.join(temp_out_dir, 'ramdisk'),
                                        0x1000)
            cmdline = BOOT_ARGS_SIZE * 'x' + (BOOT_EXTRA_ARGS_SIZE - 1) * 'y'
            boot_img = os.path.join(temp_out_dir, 'boot.img')
            mkbootimg_cmds = [
                'mkbootimg',
                '--header_version', '3',
                '--kernel', kernel,
                '--ramdisk', ramdisk,
                '--cmdline', cmdline,
                '--output', boot_img,
            ]

            subprocess.run(mkbootimg_cmds, check=True)

            with open(boot_img, 'rb') as f:
                raw_boot_img = f.read()
            raw_cmdline = (raw_boot_img[BOOT_V3_ARGS_OFFSET:]
                           [:BOOT_ARGS_SIZE + BOOT_EXTRA_ARGS_SIZE])
            self.assertEqual(raw_cmdline, cmdline.encode() + b'\x00')

    def test_vendor_boot_image_v3_cmdline_null_terminator(self):
        """Tests that kernel commandline is null-terminated."""
        with tempfile.TemporaryDirectory() as temp_out_dir:
            dtb = create_blank_file(os.path.join(temp_out_dir, 'dtb'), 0x1000)
            ramdisk = create_blank_file(os.path.join(temp_out_dir, 'ramdisk'),
                                        0x1000)
            vendor_cmdline = (VENDOR_BOOT_ARGS_SIZE - 1) * 'x'
            vendor_boot_img = os.path.join(temp_out_dir, 'vendor_boot.img')
            mkbootimg_cmds = [
                'mkbootimg',
                '--header_version', '3',
                '--dtb', dtb,
                '--vendor_ramdisk', ramdisk,
                '--vendor_cmdline', vendor_cmdline,
                '--vendor_boot', vendor_boot_img,
            ]

            subprocess.run(mkbootimg_cmds, check=True)

            with open(vendor_boot_img, 'rb') as f:
                raw_vendor_boot_img = f.read()
            raw_vendor_cmdline = (raw_vendor_boot_img[VENDOR_BOOT_ARGS_OFFSET:]
                                  [:VENDOR_BOOT_ARGS_SIZE])
            self.assertEqual(raw_vendor_cmdline,
                             vendor_cmdline.encode() + b'\x00')


# I don't know how, but we need both the logger configuration and verbosity
# level > 2 to make atest work. And yes this line needs to be at the very top
# level, not even in the "__main__" indentation block.
logging.basicConfig(stream=sys.stdout)

if __name__ == '__main__':
    unittest.main(verbosity=2)
