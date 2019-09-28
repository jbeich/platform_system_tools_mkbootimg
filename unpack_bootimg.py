#!/usr/bin/env python
# Copyright 2018, The Android Open Source Project
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

"""unpacks the bootimage.

Extracts the kernel, ramdisk, second bootloader, dtb and recovery dtbo images.
"""

from __future__ import print_function
from argparse import ArgumentParser, FileType
from struct import unpack
import os

BOOT_IMAGE_HEADER_V3_PAGESIZE = 4096

def create_out_dir(dir_path):
    """creates a directory 'dir_path' if it does not exist"""
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)


def extract_image(offset, size, bootimage, extracted_image_name):
    """extracts an image from the bootimage"""
    bootimage.seek(offset)
    with open(extracted_image_name, 'wb') as file_out:
        file_out.write(bootimage.read(size))


def get_number_of_pages(image_size, page_size):
    """calculates the number of pages required for the image"""
    return (image_size + page_size - 1) // page_size


def unpack_bootimage(args):
    """extracts kernel, ramdisk, second bootloader and recovery dtbo"""
    boot_magic = unpack('8s', args.boot_img.read(8))[0].decode()
    print('boot_magic: %s' % boot_magic)
    kernel_ramdisk_second_info = unpack('10I', args.boot_img.read(10 * 4))
    print('kernel_size: %s' % kernel_ramdisk_second_info[0])
    print('kernel load address: %#x' % kernel_ramdisk_second_info[1])
    print('ramdisk size: %s' % kernel_ramdisk_second_info[2])
    print('ramdisk load address: %#x' % kernel_ramdisk_second_info[3])
    print('second bootloader size: %s' % kernel_ramdisk_second_info[4])
    print('second bootloader load address: %#x' % kernel_ramdisk_second_info[5])
    print('kernel tags load address: %#x' % kernel_ramdisk_second_info[6])
    print('page size: %s' % kernel_ramdisk_second_info[7])
    print('boot image header version: %s' % kernel_ramdisk_second_info[8])
    print('os version and patch level: %s' % kernel_ramdisk_second_info[9])

    product_name = unpack('16s', args.boot_img.read(16))[0].decode()
    print('product name: %s' % product_name)
    cmdline = unpack('512s', args.boot_img.read(512))[0].decode()
    print('command line args: %s' % cmdline)

    args.boot_img.read(32)  # ignore SHA

    extra_cmdline = unpack('1024s', args.boot_img.read(1024))[0].decode()
    print('additional command line args: %s' % extra_cmdline)

    kernel_size = kernel_ramdisk_second_info[0]
    ramdisk_size = kernel_ramdisk_second_info[2]
    second_size = kernel_ramdisk_second_info[4]
    page_size = kernel_ramdisk_second_info[7]
    version = kernel_ramdisk_second_info[8]
    if version > 0:
        recovery_dtbo_size = unpack('I', args.boot_img.read(1 * 4))[0]
        print('recovery dtbo size: %s' % recovery_dtbo_size)
        recovery_dtbo_offset = unpack('Q', args.boot_img.read(8))[0]
        print('recovery dtbo offset: %#x' % recovery_dtbo_offset)
        boot_header_size = unpack('I', args.boot_img.read(4))[0]
        print('boot header size: %s' % boot_header_size)
    else:
        recovery_dtbo_size = 0
    if version > 1:
        dtb_size = unpack('I', args.boot_img.read(4))[0]
        print('dtb size: %s' % dtb_size)
        dtb_load_address = unpack('Q', args.boot_img.read(8))[0]
        print('dtb address: %#x' % dtb_load_address)
    else:
        dtb_size = 0


    # The first page contains the boot header
    num_header_pages = 1

    num_kernel_pages = get_number_of_pages(kernel_size, BOOT_IMAGE_HEADER_V3_PAGESIZE)
    kernel_offset = page_size * num_header_pages  # header occupies a page
    image_info_list = [(kernel_offset, kernel_size, 'kernel')]

    num_ramdisk_pages = get_number_of_pages(ramdisk_size, page_size)
    ramdisk_offset = BOOT_IMAGE_HEADER_V3_PAGESIZE * (num_header_pages + num_kernel_pages
                                 ) # header + kernel
    image_info_list.append((ramdisk_offset, ramdisk_size, 'ramdisk'))

    if second_size > 0:
        second_offset = page_size * (
                num_header_pages + num_kernel_pages + num_ramdisk_pages
                )  # header + kernel + ramdisk
        image_info_list.append((second_offset, second_size, 'second'))

    if recovery_dtbo_size > 0:
        image_info_list.append((recovery_dtbo_offset, recovery_dtbo_size,
                                'recovery_dtbo'))
    if dtb_size > 0:
        num_second_pages = get_number_of_pages(second_size, page_size)
        num_recovery_dtbo_pages = get_number_of_pages(recovery_dtbo_size, page_size)
        dtb_offset = page_size * (
            num_header_pages + num_kernel_pages + num_ramdisk_pages + num_second_pages +
            num_recovery_dtbo_pages
        )

        image_info_list.append((dtb_offset, dtb_size, 'dtb'))

    for image_info in image_info_list:
        extract_image(image_info[0], image_info[1], args.boot_img,
                      os.path.join(args.out, image_info[2]))


def unpack_bootimage_v3(args):
    """extracts kernel, ramdisk, vendor_ramdisk and dtb"""
    boot_magic = unpack('8s', args.boot_img.read(8))[0].decode()
    print('boot_magic: %s' % boot_magic)
    kernel_ramdisk_second_info = unpack('9I', args.boot_img.read(9 * 4))
    print('kernel_size: %s' % kernel_ramdisk_second_info[0])
    print('ramdisk size: %s' % kernel_ramdisk_second_info[1])
    print('os version and patch level: %s' % kernel_ramdisk_second_info[2])
    print('boot image header version: %s' % kernel_ramdisk_second_info[8])

    cmdline = unpack('1536s', args.boot_img.read(1536))[0].decode()
    print('command line args: %s' % cmdline)

    vendor_boot_magic = unpack('8s', args.vendor_boot_img.read(8))[0].decode()
    print('vendor_boot_magic: %s' % vendor_boot_magic)
    vendor_kernel_ramdisk_second_info = unpack('5I', args.vendor_boot_img.read(5 * 4))
    print('vendor boot image header version: %s' % vendor_kernel_ramdisk_second_info[0])
    print('kernel load address: %#x' % vendor_kernel_ramdisk_second_info[2])
    print('ramdisk load address: %#x' % vendor_kernel_ramdisk_second_info[3])
    print('vendor ramdisk size: %s' % vendor_kernel_ramdisk_second_info[4])

    vendor_cmdline = unpack('2048s', args.vendor_boot_img.read(2048))[0].decode()
    print('vendor command line args: %s' % vendor_cmdline)

    vendor_kernel_ramdisk_third_info = unpack('I', args.vendor_boot_img.read(1 * 4))
    print('kernel tags load address: %#x' % vendor_kernel_ramdisk_third_info[0])

    product_name = unpack('16s', args.boot_img.read(16))[0].decode()
    print('product name: %s' % product_name)

    dtb_size = unpack('2I', args.vendor_boot_img.read(2 * 4))[1]
    print('dtb size: %s' % dtb_size)
    dtb_load_address = unpack('Q', args.vendor_boot_img.read(8))[0]
    print('dtb address: %#x' % dtb_load_address)

    kernel_size = kernel_ramdisk_second_info[0]
    ramdisk_size = kernel_ramdisk_second_info[1]
    vendor_ramdisk_size = vendor_kernel_ramdisk_second_info[4]
    page_size = vendor_kernel_ramdisk_second_info[1]

    # The first page contains the boot header
    num_boot_header_pages = 1

    num_boot_kernel_pages = get_number_of_pages(kernel_size, page_size)
    kernel_offset = page_size * num_boot_header_pages  # header occupies a page
    image_info_list = [(kernel_offset, kernel_size, 'kernel')]

    num_boot_ramdisk_pages = get_number_of_pages(ramdisk_size, page_size)
    ramdisk_offset = page_size * (num_boot_header_pages + num_boot_kernel_pages
                                 ) # header + kernel
    image_info_list.append((ramdisk_offset, ramdisk_size, 'ramdisk'))

    for image_info in image_info_list:
        extract_image(image_info[0], image_info[1], args.boot_img,
                      os.path.join(args.out, image_info[2]))

    # The first page contains the vendor boot header
    num_vendor_boot_header_pages = 1

    num_vendor_boot_ramdisk_pages = get_number_of_pages(vendor_ramdisk_size, page_size)
    vendor_ramdisk_offset = page_size * num_vendor_boot_header_pages # header occupies a page
    vendor_image_info_list = [(vendor_ramdisk_offset, vendor_ramdisk_size, 'vendor_ramdisk')]

    num_vendor_boot_dtb_pages = get_number_of_pages(dtb_size, page_size)
    dtb_offset = page_size * ( num_vendor_boot_header_pages + num_vendor_boot_ramdisk_pages
                             ) # header + vendor_ramdisk
    vendor_image_info_list.append((dtb_offset, dtb_size, 'dtb'))

    for vendor_image_info in vendor_image_info_list:
        extract_image(vendor_image_info[0], vendor_image_info[1], args.vendor_boot_img,
                      os.path.join(args.out, vendor_image_info[2]))

def parse_cmdline():
    """parse command line arguments"""
    parser = ArgumentParser(
        description='Unpacks boot.img/vendor_boot.img/recovery.img, extracts the kernel,'
        'ramdisk, vendor ramdisk, second bootloader, recovery dtbo and dtb')
    parser.add_argument(
        '--boot_img',
        help='path to boot image',
        type=FileType('rb'),
        required=True)
    parser.add_argument(
        '--vendor_boot_img',
        help='path to vendor_boot image',
        type=FileType('rb'),
        required=False)
    parser.add_argument('--out', help='path to out binaries', default='out')
    return parser.parse_args()


def main():
    """parse arguments and unpack boot image"""
    args = parse_cmdline()
    create_out_dir(args.out)
    if not args.vendor_boot_img:
        unpack_bootimage(args)
    else:
        unpack_bootimage_v3(args)


if __name__ == '__main__':
    main()
