#!/usr/bin/env python3
#
# Copyright 2022, The Android Open Source Project
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
#

"""Regenerates the boot_signature for a boot image."""

from argparse import ArgumentParser
import os
import shlex
import subprocess
import tempfile

from gki.generate_gki_certificate import generate_gki_certificate

BOOT_SIGNATURE_SIZE = 16 * 1024


def append_certificate(boot_img, kernel_img, algorithm, key, extra_args):
    """Appends certificates to the end of the boot image.

    This functions appends two certificates to the end of the |boot_img|:
    the 'boot' certificate and the 'generic_kernel' certificate. The former
    is to certify the entire |boot_img|, while the latter is to certify
    the |kernel_img|. It assumes that the same |kernel_img| is packed into
    the |boot_img|.
    """

    def generate_certificate(image, certificate_name):
        """Generates the certificate and returns the certificate content."""
        with tempfile.NamedTemporaryFile() as output_certificate:
            generate_gki_certificate(
                image=image, avbtool='avbtool', name=certificate_name,
                algorithm=algorithm, key=key, salt='d00df00d',
                additional_avb_args=extra_args, output=output_certificate.name)
            output_certificate.seek(os.SEEK_SET, 0)
            return output_certificate.read()

    boot_signature_bytes = b''
    boot_signature_bytes += generate_certificate(boot_img, 'boot')
    boot_signature_bytes += generate_certificate(kernel_img, 'generic_kernel')

    if len(boot_signature_bytes) > BOOT_SIGNATURE_SIZE:
        raise ValueError(
            f'boot_signature size must be <= {BOOT_SIGNATURE_SIZE}')
    boot_signature_bytes += (
        b'\0' * (BOOT_SIGNATURE_SIZE - len(boot_signature_bytes)))
    assert len(boot_signature_bytes) == BOOT_SIGNATURE_SIZE

    with open(boot_img, 'ab') as f:
        f.write(boot_signature_bytes)


def rebuild_plain_boot_image(boot_img, output_boot_img, staging_dir):
    """Rebuilds a plain boot image.

    A boot image might already contain a certificate and/or a AVB footer.
    This function unpacks a boot image and repacks it to erase these additional
    metadata. The output boot image should only contain a boot header, followed
    by a kernel.

    It also saves the unpack results of |boot_img| into |staging_dir|.

    Args:
        boot_img: The input boot image to build from.
        output_boot_img: The output of the plain boot image to build.
        staging_dir: The output directory of unpacking |boot_img|.
    """
    unpack_bootimg_cmds = [
        'unpack_bootimg',
        '--boot_img', boot_img,
        '--out', staging_dir,
        '--format=mkbootimg',
    ]
    result = subprocess.run(unpack_bootimg_cmds, check=True,
                            capture_output=True, encoding='utf-8')
    repack_mkbootimg_args = shlex.split(result.stdout)

    mkbootimg_cmd = ['mkbootimg']
    mkbootimg_cmd.extend(repack_mkbootimg_args)
    mkbootimg_cmd.extend(['--output', output_boot_img])
    subprocess.check_call(mkbootimg_cmd)


def append_avb_footer(image):
    """Appends a AVB hash footer to the image."""

    avbtool_cmd = ['avbtool', 'add_hash_footer', '--image', image,
                   '--partition_name', 'boot', '--dynamic_partition_size']
    subprocess.check_call(avbtool_cmd)


def certified_file_path(path):
    """Appends '-certified' to the file name.

    e.g., /path/to/boot-5.15.img => /path/to/boot-5.15-certified.img.
    """
    root, ext = os.path.splitext(path)
    return root + '-certified' + ext


def parse_cmdline():
    """Parse command-line options."""
    parser = ArgumentParser(add_help=True)

    # Required args.
    parser.add_argument('--boot_img', required=True,
                        help='path to the boot image to certify')
    parser.add_argument('--algorithm', required=True,
                        help='signing algorithm for the certificate')
    parser.add_argument('--key', required=True,
                        help='path to the RSA private key')

    # Optional args.
    parser.add_argument('--extra_args', default=[], action='append',
                        help='extra arguments to be forwarded to avbtool')
    parser.add_argument('-o', '--output', help='output file name')

    args = parser.parse_args()

    extra_args = []
    for a in args.extra_args:
        extra_args.extend(a.split())
    args.extra_args = extra_args

    return args


def main():
    """Parse arguments and certify the boot image."""
    args = parse_cmdline()
    if args.output is None:
        args.output  = certified_file_path(args.boot_img)

    with tempfile.TemporaryDirectory() as temp_dir:
        rebuild_plain_boot_image(args.boot_img, args.output, temp_dir)
        kernel = os.path.join(temp_dir, 'kernel')
        assert os.path.getsize(kernel) > 0

        append_certificate(args.output, kernel, args.algorithm, args.key,
                           args.extra_args)
        append_avb_footer(args.output)


if __name__ == '__main__':
    main()
