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

"""Repacks the boot image.

Unpacks the boot image and the ramdisk inside, then add files into
the ramdisk to repack the boot image.
"""

import argparse
<<<<<<< HEAD   (cdd76b repack_bootimg: support legacy boot.img format)
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
        for compression_type, compression_util in [
            (RamdiskFormat.LZ4, 'lz4'),
            (RamdiskFormat.GZIP, 'minigzip')]:

            # Command arguments:
            #   -d: decompression
            #   -c: write to stdout
            decompression_cmd = [
                compression_util, '-d', '-c', self._ramdisk_img]

            decompressed_result = subprocess.run(
                decompression_cmd, check=False, capture_output=True)

            if decompressed_result.returncode == 0:
                self._ramdisk_format = compression_type
                break

        if self._ramdisk_format is not None:
            # toybox cpio arguments:
            #   -i: extract files from stdin
            #   -d: create directories if needed
            cpio_result = subprocess.run(
                ['toybox', 'cpio', '-id'], check=False,
                input=decompressed_result.stdout, capture_output=True,
                cwd=self._ramdisk_dir)

            # toybox cpio command might return a non-zero code, e.g., found
            # duplicated files in the ramdisk. Treat it as non-fatal with
            # check=False and only print the error message here.
            if cpio_result.returncode != 0:
                print('\n'
                      'WARNNING: cpio command error:\n' +
                      cpio_result.stderr.decode('utf-8').strip() + '\n')

            print("=== Unpacked ramdisk: '{}' ===".format(
                self._ramdisk_img))
        else:
            raise RuntimeError('Failed to decompress ramdisk.')

    def repack_ramdisk(self, out_ramdisk_file):
        """Repacks a ramdisk from self._ramdisk_dir.

        Args:
            out_ramdisk_file: the output ramdisk file to save.
        """
        compression_cmd = ['lz4', '-l', '-12', '--favor-decSpeed']
        if self._ramdisk_format == RamdiskFormat.GZIP:
            compression_cmd = ['minigzip']

        print('Repacking ramdisk, which might take a few seconds ...')

        mkbootfs_result = subprocess.run(
            ['mkbootfs', self._ramdisk_dir], check=True, capture_output=True)

        with open(out_ramdisk_file, 'w') as output_fd:
            subprocess.run(compression_cmd, check=True,
                           input=mkbootfs_result.stdout, stdout=output_fd)

        print("=== Repacked ramdisk: '{}' ===".format(out_ramdisk_file))

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
        self._ramdisk = None
        # Potential images to extract from a boot.img. Unlike the ramdisk,
        # the content of the following images will not be changed during the
        # repack process.
        self._intact_image_candidates = ('dtb', 'kernel',
                                         'recovery_dtbo', 'second')
        self._repack_intact_image_args = []
        self._temp_file_manager = TempFileManager()

        self._unpack_bootimg()

    def _unpack_bootimg(self):
        """Unpacks the boot.img and the ramdisk inside."""
        self._bootimg_dir = self._temp_file_manager.make_temp_dir(
            suffix=os.path.basename(self._bootimg))

        # Unpacks the boot.img first.
        subprocess.check_call(
            ['unpack_bootimg', '--boot_img', self._bootimg,
             '--out', self._bootimg_dir], stdout=subprocess.DEVNULL)
        print("=== Unpacked boot image: '{}' ===".format(self._bootimg))

        for img_name in self._intact_image_candidates:
            img_file = os.path.join(self._bootimg_dir, img_name)
            if os.path.exists(img_file):
                # Prepares args for repacking those intact images. e.g.,
                # --kernel kernel_image, --dtb dtb_image.
                self._repack_intact_image_args.extend(
                    ['--' + img_name, img_file])

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
        """Returns the previous mkbootimg args from mkbootimg_args.json file."""
        # Loads the saved mkbootimg_args.json from previous unpack_bootimg.
        command = []
        mkbootimg_config = os.path.join(self._bootimg_dir, 'mkbootimg_args.json')
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

        # Uses previous mkbootimg args, e.g., --vendor_cmdline, --dtb_offset.
        mkbootimg_cmd.extend(self._previous_mkbootimg_args)

        if self._repack_intact_image_args:
            mkbootimg_cmd.extend(self._repack_intact_image_args)

        if self._bootimg_type == BootImageType.VENDOR_BOOT_IMAGE:
            mkbootimg_cmd.extend(['--vendor_ramdisk', new_ramdisk])
            mkbootimg_cmd.extend(['--vendor_boot', self._bootimg])
            # TODO(bowgotsai): add support for multiple vendor ramdisk.
        else:
            mkbootimg_cmd.extend(['--ramdisk', new_ramdisk])
            mkbootimg_cmd.extend(['--output', self._bootimg])

        subprocess.check_call(mkbootimg_cmd)
        print("=== Repacked boot image: '{}' ===".format(self._bootimg))


    def add_files(self, src_dir, files):
        """Copy files from the src_dir into current ramdisk.

        Args:
            src_dir: a source dir containing the files to copy from.
            files: a list of files to copy from src_dir.
        """
        for f in files:
            src_file = os.path.join(src_dir, f)
            dst_file = os.path.join(self.ramdisk_dir, f)
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
        '--src_bootimg', help='filename to source boot image',
        type=str, required=True)
    parser.add_argument(
        '--dst_bootimg', help='filename to destination boot image',
        type=str, required=True)
    parser.add_argument(
        '--ramdisk_add', help='a list of files to add into the ramdisk',
        nargs='+', default=['first_stage_ramdisk/userdebug_plat_sepolicy.cil']
    )

    return parser.parse_args()


def main():
    """Parse arguments and repack boot image."""
    args = _parse_args()
    src_bootimg = BootImage(args.src_bootimg)
    dst_bootimg = BootImage(args.dst_bootimg)
    dst_bootimg.add_files(src_bootimg.ramdisk_dir, args.ramdisk_add)
    dst_bootimg.repack_bootimg()
=======
import datetime
import enum
import glob
import os
import shlex
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
    SINGLE_RAMDISK_FRAGMENT = 3
    MULTIPLE_RAMDISK_FRAGMENTS = 4


class RamdiskImage:
    """A class that supports packing/unpacking a ramdisk."""
    def __init__(self, ramdisk_img, unpack=True):
        self._ramdisk_img = ramdisk_img
        self._ramdisk_format = None
        self._ramdisk_dir = None
        self._temp_file_manager = TempFileManager()

        if unpack:
            self._unpack_ramdisk()
        else:
            self._ramdisk_dir = self._temp_file_manager.make_temp_dir(
                suffix='_new_ramdisk')

    def _unpack_ramdisk(self):
        """Unpacks the ramdisk."""
        self._ramdisk_dir = self._temp_file_manager.make_temp_dir(
            suffix='_' + os.path.basename(self._ramdisk_img))

        # The compression format might be in 'lz4' or 'gzip' format,
        # trying lz4 first.
        for compression_type, compression_util in [
            (RamdiskFormat.LZ4, 'lz4'),
            (RamdiskFormat.GZIP, 'minigzip')]:

            # Command arguments:
            #   -d: decompression
            #   -c: write to stdout
            decompression_cmd = [
                compression_util, '-d', '-c', self._ramdisk_img]

            decompressed_result = subprocess.run(
                decompression_cmd, check=False, capture_output=True)

            if decompressed_result.returncode == 0:
                self._ramdisk_format = compression_type
                break

        if self._ramdisk_format is not None:
            # toybox cpio arguments:
            #   -i: extract files from stdin
            #   -d: create directories if needed
            #   -u: override existing files
            subprocess.run(
                ['toybox', 'cpio', '-idu'], check=True,
                input=decompressed_result.stdout, cwd=self._ramdisk_dir)

            print(f"=== Unpacked ramdisk: '{self._ramdisk_img}' at "
                  f"'{self._ramdisk_dir}' ===")
        else:
            raise RuntimeError('Failed to decompress ramdisk.')

    def repack_ramdisk(self, out_ramdisk_file):
        """Repacks a ramdisk from self._ramdisk_dir.

        Args:
            out_ramdisk_file: the output ramdisk file to save.
        """
        compression_cmd = ['lz4', '-l', '-12', '--favor-decSpeed']
        if self._ramdisk_format == RamdiskFormat.GZIP:
            compression_cmd = ['minigzip']

        print('Repacking ramdisk, which might take a few seconds ...')

        mkbootfs_result = subprocess.run(
            ['mkbootfs', self._ramdisk_dir], check=True, capture_output=True)

        with open(out_ramdisk_file, 'w') as output_fd:
            subprocess.run(compression_cmd, check=True,
                           input=mkbootfs_result.stdout, stdout=output_fd)

        print("=== Repacked ramdisk: '{}' ===".format(out_ramdisk_file))

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
        self._ramdisk = None
        self._previous_mkbootimg_args = []
        self._temp_file_manager = TempFileManager()

        self._unpack_bootimg()

    def _get_vendor_ramdisks(self):
        """Returns a list of vendor ramdisks after unpack."""
        return sorted(glob.glob(
            os.path.join(self._bootimg_dir, 'vendor_ramdisk*')))

    def _unpack_bootimg(self):
        """Unpacks the boot.img and the ramdisk inside."""
        self._bootimg_dir = self._temp_file_manager.make_temp_dir(
            suffix='_' + os.path.basename(self._bootimg))

        # Unpacks the boot.img first.
        unpack_bootimg_cmds = [
            'unpack_bootimg',
            '--boot_img', self._bootimg,
            '--out', self._bootimg_dir,
            '--format=mkbootimg',
        ]
        result = subprocess.run(unpack_bootimg_cmds, check=True,
                                capture_output=True, encoding='utf-8')
        self._previous_mkbootimg_args = shlex.split(result.stdout)
        print("=== Unpacked boot image: '{}' ===".format(self._bootimg))

        # From the output dir, checks there is 'ramdisk' or 'vendor_ramdisk'.
        ramdisk = os.path.join(self._bootimg_dir, 'ramdisk')
        vendor_ramdisk = os.path.join(self._bootimg_dir, 'vendor_ramdisk')
        vendor_ramdisks = self._get_vendor_ramdisks()
        if os.path.exists(ramdisk):
            self._ramdisk = RamdiskImage(ramdisk)
            self._bootimg_type = BootImageType.BOOT_IMAGE
        elif os.path.exists(vendor_ramdisk):
            self._ramdisk = RamdiskImage(vendor_ramdisk)
            self._bootimg_type = BootImageType.VENDOR_BOOT_IMAGE
        elif len(vendor_ramdisks) == 1:
            self._ramdisk = RamdiskImage(vendor_ramdisks[0])
            self._bootimg_type = BootImageType.SINGLE_RAMDISK_FRAGMENT
        elif len(vendor_ramdisks) > 1:
            # Creates an empty RamdiskImage() below, without unpack.
            # We'll then add files into this newly created ramdisk, then pack
            # it with other vendor ramdisks together.
            self._ramdisk = RamdiskImage(ramdisk_img=None, unpack=False)
            self._bootimg_type = BootImageType.MULTIPLE_RAMDISK_FRAGMENTS
        else:
            raise RuntimeError('Both ramdisk and vendor_ramdisk do not exist.')

    def repack_bootimg(self):
        """Repacks the ramdisk and rebuild the boot.img"""

        new_ramdisk = self._temp_file_manager.make_temp_file(
            prefix='ramdisk-patched')
        self._ramdisk.repack_ramdisk(new_ramdisk)

        mkbootimg_cmd = ['mkbootimg']

        # Uses previous mkbootimg args, e.g., --vendor_cmdline, --dtb_offset.
        mkbootimg_cmd.extend(self._previous_mkbootimg_args)

        ramdisk_option = ''
        if self._bootimg_type == BootImageType.BOOT_IMAGE:
            ramdisk_option = '--ramdisk'
            mkbootimg_cmd.extend(['--output', self._bootimg])
        elif self._bootimg_type == BootImageType.VENDOR_BOOT_IMAGE:
            ramdisk_option = '--vendor_ramdisk'
            mkbootimg_cmd.extend(['--vendor_boot', self._bootimg])
        elif self._bootimg_type == BootImageType.SINGLE_RAMDISK_FRAGMENT:
            ramdisk_option = '--vendor_ramdisk_fragment'
            mkbootimg_cmd.extend(['--vendor_boot', self._bootimg])
        elif self._bootimg_type == BootImageType.MULTIPLE_RAMDISK_FRAGMENTS:
            mkbootimg_cmd.extend(['--ramdisk_type', 'PLATFORM'])
            ramdisk_name = (
                'RAMDISK_' +
                datetime.datetime.now().strftime('%Y-%m-%d_%H:%M:%S'))
            mkbootimg_cmd.extend(['--ramdisk_name', ramdisk_name])
            mkbootimg_cmd.extend(['--vendor_ramdisk_fragment', new_ramdisk])
            mkbootimg_cmd.extend(['--vendor_boot', self._bootimg])

        if ramdisk_option and ramdisk_option not in mkbootimg_cmd:
            raise RuntimeError("Failed to find '{}' from:\n  {}".format(
                ramdisk_option, shlex.join(mkbootimg_cmd)))
        # Replaces the original ramdisk with the newly packed ramdisk.
        if ramdisk_option:
            ramdisk_index = mkbootimg_cmd.index(ramdisk_option) + 1
            mkbootimg_cmd[ramdisk_index] = new_ramdisk

        subprocess.check_call(mkbootimg_cmd)
        print("=== Repacked boot image: '{}' ===".format(self._bootimg))

    def add_files(self, copy_pairs):
        """Copy files specified by copy_pairs into current ramdisk.

        Args:
            copy_pairs: a list of (src_pathname, dst_file) pairs.
        """
        # Creates missing parent dirs with 0o755.
        original_mask = os.umask(0o022)
        for src_pathname, dst_file in copy_pairs:
            dst_pathname = os.path.join(self.ramdisk_dir, dst_file)
            dst_dir = os.path.dirname(dst_pathname)
            if not os.path.exists(dst_dir):
                print("Creating dir '{}'".format(dst_dir))
                os.makedirs(dst_dir, 0o755)
            print(f"Copying file '{src_pathname}' to '{dst_pathname}'")
            shutil.copy2(src_pathname, dst_pathname, follow_symlinks=False)
        os.umask(original_mask)

    @property
    def ramdisk_dir(self):
        """Returns the internal ramdisk dir."""
        return self._ramdisk.ramdisk_dir


def _get_repack_usage():
    return """Usage examples:

  * --ramdisk_add

    Specifies a list of files or src_file:dst_file pairs to copy.
    If --src_bootimg is specified, copy files from the ramdisk of --src_bootimg
    into the ramdisk of --dst_bootimg.
    If --local is given, copy files from the local filesystem into the ramdisk
    of --dst_bootimg.

    $ %(prog)s \\
        --src_bootimg boot-debug-5.4.img --dst_bootimg vendor_boot-debug.img \\
        --ramdisk_add first_stage_ramdisk/userdebug_plat_sepolicy.cil:userdebug_plat_sepolicy.cil

    The above command copies 'first_stage_ramdisk/userdebug_plat_sepolicy.cil'
    from the ramdisk of --src_bootimg to 'userdebug_plat_sepolicy.cil' of the
    ramdisk of --dst_bootimg, then repacks the --dst_bootimg.

    $ %(prog)s \\
        --local --dst_bootimg vendor_boot-debug.img \\
        --ramdisk_add userdebug_plat_sepolicy.cil

    The above command copies a local file 'userdebug_plat_sepolicy.cil' into the
    ramdisk of --dst_bootimg.

    $ %(prog)s \\
        --src_bootimg boot-debug-5.4.img --dst_bootimg vendor_boot-debug.img \\
        --ramdisk_add first_stage_ramdisk/userdebug_plat_sepolicy.cil

    This is similar to the first example, but the source file path and
    destination file path are the same:
        'first_stage_ramdisk/userdebug_plat_sepolicy.cil'.

    We can also combine both usage together with a list of copy instructions.
    For example:

    $ %(prog)s \\
        --src_bootimg boot-debug-5.4.img --dst_bootimg vendor_boot-debug.img \\
        --ramdisk_add file1 file2:subdir/file2 file3
"""


def _parse_args():
    """Parse command-line options."""
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description='Repacks boot, recovery or vendor_boot image by importing '
                    'ramdisk files from --src_bootimg to --dst_bootimg.',
        epilog=_get_repack_usage(),
    )

    src_group = parser.add_mutually_exclusive_group(required=True)
    src_group.add_argument(
        '--src_bootimg', help='filename to source boot image',
        type=BootImage)
    src_group.add_argument(
        '--local', help='use local files as repack source',
        action='store_true')

    parser.add_argument(
        '--dst_bootimg', help='filename to destination boot image',
        type=BootImage, required=True)
    parser.add_argument(
        '--ramdisk_add', nargs='+',
        help='a list of files or src_file:dst_file pairs to add into '
             'the ramdisk',
        default=['userdebug_plat_sepolicy.cil']
    )

    args = parser.parse_args()

    # Parse args.ramdisk_add to a list of copy pairs.
    if args.src_bootimg:
        args.ramdisk_add = [
            _parse_ramdisk_copy_pair(p, args.src_bootimg.ramdisk_dir)
            for p in args.ramdisk_add
        ]
    else:
        # Repack from local files.
        args.ramdisk_add = [
            _parse_ramdisk_copy_pair(p) for p in args.ramdisk_add
        ]

    return args


def _parse_ramdisk_copy_pair(pair, src_ramdisk_dir=None):
    """Parse a ramdisk copy pair argument."""
    if ':' in pair:
        src_file, dst_file = pair.split(':', maxsplit=1)
    else:
        src_file = dst_file = pair

    # os.path.join() only works on relative path components.
    # If a component is an absolute path, all previous components are thrown
    # away and joining continues from the absolute path component.
    # So make sure the file name is not absolute before calling os.path.join().
    if src_ramdisk_dir:
        if os.path.isabs(src_file):
            raise ValueError('file name cannot be absolute when repacking from '
                             'a ramdisk: ' + src_file)
        src_pathname = os.path.join(src_ramdisk_dir, src_file)
    else:
        src_pathname = src_file
    if os.path.isabs(dst_file):
        raise ValueError('destination file name cannot be absolute: ' +
                         dst_file)
    return (src_pathname, dst_file)


def main():
    """Parse arguments and repack boot image."""
    args = _parse_args()
    args.dst_bootimg.add_files(args.ramdisk_add)
    args.dst_bootimg.repack_bootimg()
>>>>>>> BRANCH (abf405 Merge "repack_bootimg: Support using local files as repack s)


if __name__ == '__main__':
    main()
