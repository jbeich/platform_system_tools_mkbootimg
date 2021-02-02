#!/usr/bin/env python3
#
# Copyright 2021, The Android Open Source Project
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

import argparse
import enum
import json
import os
import shutil
import subprocess
import tempfile


class TempFileManager:
    """Manages temporary files and dirs."""

    def __init__(self):
        self._temp_files = []

    def __del__(self):
        """Removes temp dirs and files."""
        for f in self._temp_files:
            if os.path.isdir(f):
                shutil.rmtree(f, ignore_errors=True)
            else:
                os.remove(f)

    def make_temp_dir(self, prefix='tmp', suffix=''):
        """Makes a temporary dir that will be cleaned up in the destructor.

        Returns:
            The absolute pathname of the new directory.
        """
        dir_name = tempfile.mkdtemp(prefix=prefix, suffix=suffix)
        self._temp_files.append(dir_name)
        return dir_name

    def make_temp_file(self, prefix='tmp', suffix=''):
        """Make a temp file that will be deleted in the destructor.

        Returns:
            The absolute pathname of the new file.
        """
        fd, file_name = tempfile.mkstemp(prefix=prefix, suffix=suffix)
        os.close(fd)
        self._temp_files.append(file_name)
        return file_name


class RamdiskFormat(enum.Enum):
    """Enum class for different ramdisk compression formats."""
    LZ4 = 1
    GZIP = 2


class BootImageType(enum.Enum):
    """Enum class for different boot image types."""
    BOOT_IMAGE = 1
    VENDOR_BOOT_IMAGE = 2


class RamdiskImage:
    """A class that supports packing/unpacking a ramdisk."""
    def __init__(self, ramdisk_img):
        self._ramdisk_img = ramdisk_img
        self._ramdisk_format = None
        self._ramdisk_dir = None
        self._temp_file_manager = TempFileManager()

        self._unpack_ramdisk()

    def _unpack_ramdisk(self):
        """Unpacks the ramdisk."""
        self._ramdisk_dir = self._temp_file_manager.make_temp_dir(
            suffix=os.path.basename(self._ramdisk_img))

        # The compression format might be in 'lz4' or 'gzip' format,
        # trying lz4 first.
        for compression_util in ('lz4', 'minigzip'):
            try:
                decompression_cmd = '%s -d -c %s | cpio -idm ' % (
                    compression_util, self._ramdisk_img)

                subprocess.check_call(decompression_cmd,
                                      shell=True,
                                      cwd=self._ramdisk_dir)

                if compression_util == 'lz4':
                    self._ramdisk_format = RamdiskFormat.LZ4
                else:
                    self._ramdisk_format = RamdiskFormat.GZIP

                break
            except subprocess.CalledProcessError as e:
                print("Failed to decompress ramdisk via '{}': {}".format(
                    compression_util, e))

        if self._ramdisk_format is not None:
            print("=== Unpacked ramdisk: '{}' ===".format(
                self._ramdisk_img))
        else:
            raise RuntimeError('Failed to decompress ramdisk.')

    def repack_ramdisk(self, out_ramdisk_file):
        """Repacks a ramdisk from self._ramdisk_dir.

        Args:
            out_ramdisk_file: the output ramdisk file to save.
        """
        compression_cmd = 'lz4 -l -12 --favor-decSpeed'
        if self._ramdisk_format == RamdiskFormat.GZIP:
            compression_cmd = 'minigzip'

        make_ramdisk_cmd = 'mkbootfs %s | %s > %s' % (
            self._ramdisk_dir, compression_cmd, out_ramdisk_file)

        print('Repacking ramdisk, which might take a few seconds ...')
        subprocess.check_call(make_ramdisk_cmd, shell=True)
        print('=== Repacked ramdisk ===')

    @property
    def ramdisk_dir(self):
        """Returns the internal ramdisk dir."""
        return self._ramdisk_dir


class BootImage:
    """A class that supports packing/unpacking a boot.img and ramdisk."""

    def __init__(self, bootimg):
        self._bootimg = bootimg
        self._bootimg_dir = None
        self._bootimg_type = None
        self._dtb = None
        self._kernel = None
        self._ramdisk = None
        self._temp_file_manager = TempFileManager()

        self._unpack_bootimg()

    def _unpack_bootimg(self):
        """Unpacks the boot.img and the ramdisk inside."""
        self._bootimg_dir = self._temp_file_manager.make_temp_dir(
            suffix=os.path.basename(self._bootimg))

        # Unpacks the boot.img first.
        subprocess.check_call(
            ['unpack_bootimg', '--boot_img', self._bootimg,
             '--out', self._bootimg_dir])
        print("=== Unpacked boot image: '{}' ===".format(self._bootimg))

        kernel = os.path.join(self._bootimg_dir, 'kernel')
        if os.path.exists(kernel):
            self._kernel = kernel

        dtb = os.path.join(self._bootimg_dir, 'dtb')
        if os.path.exists(dtb):
            self._dtb = dtb

        # From the output dir, checks there is 'ramdisk' or 'vendor_ramdisk'.
        ramdisk = os.path.join(self._bootimg_dir, 'ramdisk')
        vendor_ramdisk = os.path.join(self._bootimg_dir, 'vendor_ramdisk')
        if os.path.exists(ramdisk):
            self._ramdisk = RamdiskImage(ramdisk)
            self._bootimg_type = BootImageType.BOOT_IMAGE
        elif os.path.exists(vendor_ramdisk):
            self._ramdisk = RamdiskImage(vendor_ramdisk)
            self._bootimg_type = BootImageType.VENDOR_BOOT_IMAGE
        else:
            raise RuntimeError('Both ramdisk and vendor_ramdisk do not exist.')

    @property
    def _previous_mkbootimg_args(self):
        """Returns the previous used mkbootimg args from mkbootimg.json file."""
        # Loads the saved mkbootimg.json from previous unpack_bootimg.
        command = []
        mkbootimg_config = os.path.join(self._bootimg_dir, 'mkbootimg.json')
        with open (mkbootimg_config) as config:
            mkbootimg_args = json.load(config)
            for argname, value in mkbootimg_args.items():
                # argname, e.g., 'board', 'header_version', etc., does not have
                # prefix '--', which is required when invoking `mkbootimg.py`.
                # Prepends '--' to make the full args, e.g., --header_version.
                command.extend(['--' + argname, value])
        return command


    def repack_bootimg(self):
        """Repacks the ramdisk and rebuild the boot.img"""

        new_ramdisk = self._temp_file_manager.make_temp_file(
            prefix='ramdisk-patched')
        self._ramdisk.repack_ramdisk(new_ramdisk)

        mkbootimg_cmd = ['mkbootimg']

        if self._dtb:
            mkbootimg_cmd.extend(['--dtb', self._dtb])

        # Uses previous mkbootimg args, e.g., --vendor_cmdline, --dtb_offset.
        mkbootimg_cmd.extend(self._previous_mkbootimg_args)

        if self._bootimg_type == BootImageType.VENDOR_BOOT_IMAGE:
            mkbootimg_cmd.extend(['--vendor_ramdisk', new_ramdisk])
            mkbootimg_cmd.extend(['--vendor_boot', self._bootimg])
            # TODO(bowgotsai): add support for multiple vendor ramdisk.
        else:
            mkbootimg_cmd.extend(['--kernel', self._kernel])
            mkbootimg_cmd.extend(['--ramdisk', new_ramdisk])
            mkbootimg_cmd.extend(['--output', self._bootimg])

        subprocess.check_call(mkbootimg_cmd)
        print("=== Repacked boot image: '{}' ===".format(self._bootimg))


    def update_files(self, src_dir, files):
        """Copy files from the src_dir into current ramdisk.

        Args:
            src_dir: a source dir containing the files to copy from.
            files: a list of files to copy from src_dir.
        """
        for f in files:
            src_file = os.path.join(src_dir, f)
            dst_file = os.path.join(self._ramdisk.ramdisk_dir, f)
            print("Copying file '{}' into '{}'".format(
                src_file, self._bootimg))
            shutil.copy2(src_file, dst_file)

    @property
    def ramdisk_dir(self):
        """Returns the internal ramdisk dir."""
        return self._ramdisk.ramdisk_dir


def _parse_args():
    """Parse command-line options."""
    parser = argparse.ArgumentParser()

    parser.add_argument(
        '--src_bootimg', help='path to source boot image',
        type=str, required=True)
    parser.add_argument(
        '--dst_bootimg', help='path to destination boot image',
        type=str, required=True)
    parser.add_argument(
        '--files', help='A list of files to import',
        nargs='+', default=['first_stage_ramdisk/userdebug_plat_sepolicy.cil']
    )

    return parser.parse_args()


if __name__ == '__main__':
    args = _parse_args()
    src_bootimg = BootImage(args.src_bootimg)
    dst_bootimg = BootImage(args.dst_bootimg)
    dst_bootimg.update_files(src_bootimg.ramdisk_dir, args.files)
    dst_bootimg.repack_bootimg()
