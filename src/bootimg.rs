// Copyright 2023, The Android Open Source Project
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

//! Bootimg Handling Library

use core::mem::size_of;
use zerocopy::{AsBytes, ByteSlice, FromBytes, LayoutVerified};

/// Android magic boot string size.
pub const BOOT_MAGIC_SIZE: usize = 8;
/// Android magic boot string.
pub const BOOT_MAGIC: [u8; BOOT_MAGIC_SIZE] = [b'A', b'N', b'D', b'R', b'O', b'I', b'D', b'!'];
/// Maximum product name size.
pub const BOOT_NAME_SIZE: usize = 16;
/// Maximum size of kernel commandline.
pub const BOOT_ARGS_SIZE: usize = 512;
/// Maximum size of supplemental commandline.
pub const BOOT_EXTRA_ARGS_SIZE: usize = 1024;
/// Vendor magic boot string size.
pub const VENDOR_BOOT_MAGIC_SIZE: usize = 8;
/// Vendor magic boot string.
pub const VENDOR_BOOT_MAGIC: [u8; VENDOR_BOOT_MAGIC_SIZE] =
    [b'V', b'N', b'D', b'R', b'B', b'O', b'O', b'T'];
/// Maximum size of vendor commandline.
pub const VENDOR_BOOT_ARGS_SIZE: usize = 2048;
/// Maximum size of vendor boot name.
pub const VENDOR_BOOT_NAME_SIZE: usize = 16;
/// Maximum size of vendor ramdisk name.
pub const VENDOR_RAMDISK_NAME_SIZE: usize = 32;
/// Maximum size of string describing the board, soc or platform which this
/// ramdisk is intended to be loaded on.
pub const VENDOR_RAMDISK_TABLE_ENTRY_BOARD_ID_SIZE: usize = 16;

#[derive(PartialEq, Debug)]
/// Boot related errors.
pub enum BootError {
    /// The provided buffer was too small to hold a header.
    BufferTooSmall,
    /// The magic string was incorrect.
    BadMagic,
    /// The header version present is not supported.
    UnknownVersion,
    /// Catch-all for remaining errors.
    UnknownError,
}

type BootResult<T> = Result<T, BootError>;

#[repr(C)]
#[derive(FromBytes, AsBytes, Copy, Clone, Debug, PartialEq)]
/// Type field for vendor ramdisk entries.
pub struct VendorRamdiskType(u32);
impl VendorRamdiskType {
    /// Indicates the value is unspecified.
    pub const NONE: Self = Self(0);
    /// Ramdisk contains platform specific bits, so the bootloader should always load these into memory.
    pub const PLATFORM: Self = Self(1);
    /// Ramdisk contains recovery resources, so the bootloader should load these when booting into recovery.
    pub const RECOVERY: Self = Self(2);
    /// Ramdisk contains dynamic loadable kernel modules.
    pub const DLKM: Self = Self(3);
}

type Major = u8;
type Minor = u8;
type Patch = u8;
type Year = u8;
type Month = u8;

/// Operating system version and security patch level.
/// For version "A.B.C" and patch level "Y-M-D":
///   (7 bits for each of A, B, C; 7 bits for (Y-2000), 4 bits for M)
///   os_version = A[31:25] B[24:18] C[17:11] (Y-2000)[10:4] M[3:0]
pub fn os_version(major: Major, minor: Minor, patch: Patch, year: Year, month: Month) -> u32 {
    ((u32::from(major) & 0x7F) << 25)
        | ((u32::from(minor) & 0x7F) << 18)
        | ((u32::from(patch) & 0x7F) << 11)
        | (((u32::from(year) - 2000) & 0x7F) << 4)
        | (u32::from(month) & 0xF)
}

#[repr(C, packed)]
#[derive(FromBytes, AsBytes, Debug, PartialEq, Copy, Clone)]
/// When a boot header is of version 0, the structure of the boot image is as follows:
///
/// +-----------------+
/// | boot header     | 1 page
/// +-----------------+
/// | kernel          | n pages
/// +-----------------+
/// | ramdisk         | m pages
/// +-----------------+
/// | second stage    | o pages
/// +-----------------+
/// n = (kernel_size + page_size - 1) / page_size
/// m = (ramdisk_size + page_size - 1) / page_size
/// o = (second_size + page_size - 1) / page_size
///
/// 0. All entities are page_size aligned in flash
/// 1. The kernel and ramdisk are required (size != 0)
/// 2. The second is optional (second_size == 0 -> no second)
/// 3. Load each element (kernel, ramdisk, second) at
///    the specified physical address (kernel_addr, etc)
/// 4. Prepare tags at tag_addr.  kernel_args[] is
///    appended to the kernel commandline in the tags.
/// 5. r0 = 0, r1 = MACHINE_TYPE, r2 = tags_addr
/// 6. if second_size != 0: jump to second_addr
///    else: jump to kernel_addr
///
pub struct BootImgHdrV0 {
    /// Must be BOOT_MAGIC.
    pub magic: [u8; BOOT_MAGIC_SIZE],
    /// Kernel size in bytes.
    pub kernel_size: u32,
    /// Kernel physical load address.
    pub kernel_addr: u32,
    /// Kernel ramdisk size in bytes.
    pub ramdisk_size: u32,
    /// Kernel ramdisk physical load address.
    pub ramdisk_addr: u32,
    /// Second size in bytes.
    pub second_size: u32,
    /// Second physical load address.
    pub second_addr: u32,
    /// Physical address for kernel tags (if required).
    pub tags_addr: u32,
    /// Flash page size we assume.
    pub page_size: u32,
    /// Version of the boot image header.
    pub header_version: u32,
    /// Operating system version and security patch level.
    /// See `os_version` for bit level details.
    pub os_version: u32,
    /// asciiz product name.
    pub name: [u8; BOOT_NAME_SIZE],
    /// asciiz kernel commandline.
    pub cmdline: [u8; BOOT_ARGS_SIZE],
    /// Timestamp / checksum / sha1 / etc.
    pub id: [u32; 8],
    /// Supplemental command line data; kept here to maintain
    /// binary compatibility with older versions of mkbootimg.
    /// Asciiz.
    pub extra_cmdline: [u8; BOOT_EXTRA_ARGS_SIZE],
}

impl Default for BootImgHdrV0 {
    fn default() -> Self {
        Self {
            magic: BOOT_MAGIC,
            kernel_size: 0,
            kernel_addr: 0,
            ramdisk_size: 0,
            ramdisk_addr: 0,
            second_size: 0,
            second_addr: 0,
            tags_addr: 0,
            page_size: 0,
            header_version: 0,
            os_version: 0,
            name: [0; BOOT_NAME_SIZE],
            cmdline: [0; BOOT_ARGS_SIZE],
            id: [0; 8],
            extra_cmdline: [0; BOOT_EXTRA_ARGS_SIZE],
        }
    }
}

#[repr(C, packed)]
#[derive(FromBytes, AsBytes, Debug, PartialEq, Copy, Clone)]
/// When a boot header is of version 1, the structure of boot image is as follows:
///
/// +---------------------+
/// | boot header         | 1 page
/// +---------------------+
/// | kernel              | n pages
/// +---------------------+
/// | ramdisk             | m pages
/// +---------------------+
/// | second stage        | o pages
/// +---------------------+
/// | recovery dtbo/acpio | p pages
/// +---------------------+
///
/// n = (kernel_size + page_size - 1) / page_size
/// m = (ramdisk_size + page_size - 1) / page_size
/// o = (second_size + page_size - 1) / page_size
/// p = (recovery_dtbo_size + page_size - 1) / page_size
///
/// 0. All entities are page_size aligned in flash
/// 1. The kernel and ramdisk are required (size != 0)
/// 2. The recovery_dtbo/recovery_acpio is required for recovery.img in non-A/B
///    devices(recovery_dtbo_size != 0)
/// 3. The second is optional (second_size == 0 -> no second)
/// 4. Load each element (kernel, ramdisk, second) at
///    the specified physical address (kernel_addr, etc)
/// 5. If booting to recovery mode in a non-A/B device, extract recovery
///    dtbo/acpio and apply the correct set of overlays on the base device tree
///    depending on the hardware/product revision.
/// 6. Set up registers for kernel entry as required by your architecture
/// 7. if second_size != 0: jump to second_addr
///    else: jump to kernel_addr
///
pub struct BootImgHdrV1 {
    /// Version 0 boot image header prefix.
    pub v0_hdr: BootImgHdrV0,
    /// Size in bytes for recovery DTBO/ACPIO image.
    pub recovery_dtbo_size: u32,
    /// Offset to recovery dtbo/acpio in boot image.
    pub recovery_dtbo_offset: u64,
    /// Header size in bytes.
    pub header_size: u32,
}

impl Default for BootImgHdrV1 {
    fn default() -> Self {
        Self {
            v0_hdr: BootImgHdrV0 { header_version: 1, ..Default::default() },
            recovery_dtbo_size: 0,
            recovery_dtbo_offset: 0,
            header_size: size_of::<Self>() as u32,
        }
    }
}

#[repr(C, packed)]
#[derive(FromBytes, AsBytes, Debug, PartialEq, Copy, Clone)]
/// When the boot image header has a version of 2, the structure of the boot image is as follows:
///
/// +---------------------+
/// | boot header         | 1 page
/// +---------------------+
/// | kernel              | n pages
/// +---------------------+
/// | ramdisk             | m pages
/// +---------------------+
/// | second stage        | o pages
/// +---------------------+
/// | recovery dtbo/acpio | p pages
/// +---------------------+
/// | dtb                 | q pages
/// +---------------------+
/// n = (kernel_size + page_size - 1) / page_size
/// m = (ramdisk_size + page_size - 1) / page_size
/// o = (second_size + page_size - 1) / page_size
/// p = (recovery_dtbo_size + page_size - 1) / page_size
/// q = (dtb_size + page_size - 1) / page_size
///
/// 0. All entities are page_size aligned in flash
/// 1. The kernel, ramdisk and DTB are required (size != 0)
/// 2. The recovery_dtbo/recovery_acpio is required for recovery.img in non-A/B
///    devices(recovery_dtbo_size != 0)
/// 3. The second is optional (second_size == 0 -> no second)
/// 4. Load each element (kernel, ramdisk, second, dtb) at
///    the specified physical address (kernel_addr, etc)
/// 5. If booting to recovery mode in a non-A/B device, extract recovery
///    dtbo/acpio and apply the correct set of overlays on the base device tree
///    depending on the hardware/product revision.
/// 6. Set up registers for kernel entry as required by your architecture
/// 7. if second_size != 0: jump to second_addr
///    else: jump to kernel_addr
///
pub struct BootImgHdrV2 {
    /// Version 1 boot image header prefix.
    pub v1_hdr: BootImgHdrV1,
    /// Size in bytes for DTB image.
    pub dtb_size: u32,
    /// Physical load address for DTB image.
    pub dtb_addr: u64,
}

impl Default for BootImgHdrV2 {
    fn default() -> Self {
        Self {
            v1_hdr: BootImgHdrV1 {
                v0_hdr: BootImgHdrV0 { header_version: 2, ..Default::default() },
                ..Default::default()
            },
            dtb_size: 0,
            dtb_addr: 0,
        }
    }
}

#[repr(C, packed)]
#[derive(FromBytes, AsBytes, Debug, PartialEq, Copy, Clone)]
/// When the boot image header has a version of 3, the structure of the boot
/// image is as follows:
///
/// +---------------------+
/// | boot header         | 4096 bytes
/// +---------------------+
/// | kernel              | m pages
/// +---------------------+
/// | ramdisk             | n pages
/// +---------------------+
///
/// m = (kernel_size + 4096 - 1) / 4096
/// n = (ramdisk_size + 4096 - 1) / 4096
///
/// Note that in version 3 of the boot image header, page size is fixed at 4096 bytes.
///
pub struct BootImgHdrV3 {
    /// Must be VENDOR_BOOT_MAGIC.
    pub magic: [u8; BOOT_MAGIC_SIZE],
    /// Kernel size in bytes.
    pub kernel_size: u32,
    /// Ramdisk size in bytes.
    pub ramdisk_size: u32,
    /// Operating system version and security patch level.
    /// See `os_version` for bit level details.
    pub os_version: u32,
    /// Header size in bytes.
    pub header_size: u32,
    /// Reserved, used for padding so that header_version starts at byte 40.
    pub reserved: [u32; 4],
    /// Version of the boot image header.
    pub header_version: u32,
    /// Flash page size we assume, always 4096.
    pub page_size: u32,
    /// Kernel physical load addr.
    pub kernel_addr: u32,
    /// Ramdisk physical load addr.
    pub ramdisk_addr: u32,
    /// Vendor ramdisk size in bytes.
    pub vendor_ramdisk_size: u32,
    /// Asciiz kernel commandline.
    pub cmdline: [u8; VENDOR_BOOT_ARGS_SIZE],
    /// Physical addr for kernel tags (if required).
    pub tags_addr: u32,
    /// Asciiz product name.
    pub name: [u8; VENDOR_BOOT_NAME_SIZE],
    /// DTB image size in bytes.
    pub dtb_size: u32,
    /// DTB image physical load address.
    pub dtb_addr: u64,
}

impl Default for BootImgHdrV3 {
    fn default() -> Self {
        Self {
            magic: BOOT_MAGIC,
            kernel_size: 0,
            ramdisk_size: 0,
            os_version: 0,
            header_size: size_of::<Self>() as u32,
            reserved: [0; 4],
            header_version: 3,
            page_size: 4096,
            kernel_addr: 0,
            ramdisk_addr: 0,
            vendor_ramdisk_size: 0,
            cmdline: [0; VENDOR_BOOT_ARGS_SIZE],
            tags_addr: 0,
            name: [0; VENDOR_BOOT_NAME_SIZE],
            dtb_size: 0,
            dtb_addr: 0,
        }
    }
}

#[repr(C, packed)]
#[derive(FromBytes, AsBytes, Debug, PartialEq, Copy, Clone)]
/// When the boot image header has a version of 4, the structure of the boot
/// image is as follows:
///
/// +---------------------+
/// | boot header         | 4096 bytes
/// +---------------------+
/// | kernel              | m pages
/// +---------------------+
/// | ramdisk             | n pages
/// +---------------------+
/// | boot signature      | g pages
/// +---------------------+
///
/// m = (kernel_size + 4096 - 1) / 4096
/// n = (ramdisk_size + 4096 - 1) / 4096
/// g = (signature_size + 4096 - 1) / 4096
///
/// Note that in version 4 of the boot image header, page size is fixed at 4096
/// bytes.
///
pub struct BootImgHdrV4 {
    /// Version 3 boot image header prefix
    pub v3_hdr: BootImgHdrV3,
    /// Signature size in bytes
    pub signature_size: u32,
}

impl Default for BootImgHdrV4 {
    fn default() -> Self {
        Self { v3_hdr: BootImgHdrV3 { header_version: 4, ..Default::default() }, signature_size: 0 }
    }
}

#[repr(C, packed)]
#[derive(FromBytes, AsBytes, Debug, Copy, Clone)]
/// Entry structure for the vendor ramdisk table.
pub struct VendorRamdiskTableEntryV4 {
    /// Size in bytes for the ramdisk image.
    pub ramdisk_size: u32,
    /// Offset to the ramdisk image in vendor ramdisk section.
    pub ramdisk_offset: u32,
    /// Type of the ramdisk.
    pub ramdisk_type: VendorRamdiskType,
    /// Asciiz ramdisk name.
    pub ramdisk_name: [u8; VENDOR_RAMDISK_NAME_SIZE],
    /// Hardware identifiers describing the board, soc or platform which this
    /// ramdisk is intended to be loaded on.
    pub board_id: [u32; VENDOR_RAMDISK_TABLE_ENTRY_BOARD_ID_SIZE],
}

// TODO(dovs): implement an iterator over ramdisk table entries

#[derive(PartialEq, Debug)]
/// Generalized boot image from a backing store of bytes.
pub enum BootImg<B: ByteSlice + PartialEq> {
    /// Version 0 header
    V0Hdr(LayoutVerified<B, BootImgHdrV0>),
    /// Version 1 header
    V1Hdr(LayoutVerified<B, BootImgHdrV1>),
    /// Version 2 header
    V2Hdr(LayoutVerified<B, BootImgHdrV2>),
    /// Version 3 header
    V3Hdr(LayoutVerified<B, BootImgHdrV3>),
    /// Version 4 header
    V4Hdr(LayoutVerified<B, BootImgHdrV4>),
}

/// Given a byte buffer, attempt to parse the contents and return a zero-copy reference
/// to the associated boot image header.
///
/// # Arguments
/// * `buffer` - buffer to parse
///
/// # Returns
///
/// * `Ok(BootImg)` - if parsing was successful.
///
/// * `Err(BootError)` - if `buffer` does not contain a valid boot image header.
///
/// # Example
///
/// ```
/// use bootimg::BootImg;
///
/// let mut buffer = [0; 4096];
/// // Not shown: read first 4096 bytes of boot image into buffer
/// let header = BootImg::parse_boot_image(&buffer[..]).unwrap();
/// ```
impl<B: ByteSlice + PartialEq> BootImg<B> {
    pub fn parse_boot_image(buffer: B) -> BootResult<Self> {
        // In all headers, the version is a 32 bit integer starting at byte 40.
        // TODO(dovs): when core::offset_of has stabilized, use that instead of raw sizes
        if buffer.len() < 44 {
            return Err(BootError::BufferTooSmall);
        }

        let version = u32::from_le_bytes(
            (&buffer)[40..44].try_into().map_err(|_| BootError::BufferTooSmall)?,
        );

        // In all headers, the first 8 bytes are the magic string.
        if (&buffer)[0..BOOT_MAGIC_SIZE].ne(&BOOT_MAGIC) {
            return Err(BootError::BadMagic);
        }

        match version {
            0 => {
                let (head, _) = LayoutVerified::<B, BootImgHdrV0>::new_from_prefix(buffer)
                    .ok_or(BootError::BufferTooSmall)?;
                Ok(Self::V0Hdr(head))
            }
            1 => {
                let (head, _) = LayoutVerified::<B, BootImgHdrV1>::new_from_prefix(buffer)
                    .ok_or(BootError::BufferTooSmall)?;
                Ok(Self::V1Hdr(head))
            }
            2 => {
                let (head, _) = LayoutVerified::<B, BootImgHdrV2>::new_from_prefix(buffer)
                    .ok_or(BootError::BufferTooSmall)?;
                Ok(Self::V2Hdr(head))
            }
            3 => {
                let (head, _) = LayoutVerified::<B, BootImgHdrV3>::new_from_prefix(buffer)
                    .ok_or(BootError::BufferTooSmall)?;
                Ok(Self::V3Hdr(head))
            }
            4 => {
                let (head, _) = LayoutVerified::<B, BootImgHdrV4>::new_from_prefix(buffer)
                    .ok_or(BootError::BufferTooSmall)?;
                Ok(Self::V4Hdr(head))
            }
            _ => Err(BootError::UnknownVersion),
        }
    }
}

#[repr(C, packed)]
#[derive(FromBytes, AsBytes, Debug, PartialEq, Copy, Clone)]
/// The structure of the vendor boot image (introduced with version 3 and
/// required to be present when a v3 boot image is used) is as follows:
///
/// +---------------------+
/// | vendor boot header  | o pages
/// +---------------------+
/// | vendor ramdisk      | p pages
/// +---------------------+
/// | dtb                 | q pages
/// +---------------------+
///
/// o = (2112 + page_size - 1) / page_size
/// p = (vendor_ramdisk_size + page_size - 1) / page_size
/// q = (dtb_size + page_size - 1) / page_size
///
/// 0. All entities in the boot image are 4096-byte aligned in flash, all
///    entities in the vendor boot image are page_size (determined by the vendor
///    and specified in the vendor boot image header) aligned in flash
/// 1. The kernel, ramdisk, vendor ramdisk, and DTB are required (size != 0)
/// 2. Load the kernel and DTB at the specified physical address (kernel_addr,
///    dtb_addr)
/// 3. Load the vendor ramdisk at ramdisk_addr
/// 4. Load the generic ramdisk immediately following the vendor ramdisk in
///    memory
/// 5. Set up registers for kernel entry as required by your architecture
/// 6. If the platform has a second stage bootloader jump to it (must be
///    contained outside boot and vendor boot partitions), otherwise
///    jump to kernel_addr
///
pub struct VendorBootHdrV3 {
    /// Must be VENDOR_BOOT_MAGIC.
    pub magic: [u8; VENDOR_BOOT_MAGIC_SIZE],
    /// Version of the vendor boot image header.
    pub header_version: u32,
    /// Flash page size we assume.
    pub page_size: u32,
    /// Physical load addr.
    pub kernel_addr: u32,
    /// Physical load addr.
    pub ramdisk_addr: u32,
    /// Size in bytes.
    pub vendor_ramdisk_size: u32,
    /// Asciiz kernel commandline.
    pub cmdline: [u8; VENDOR_BOOT_ARGS_SIZE],
    /// Physical addr for kernel tags (if required).
    pub tags_addr: u32,
    /// Asciiz product name.
    pub name: [u8; VENDOR_BOOT_NAME_SIZE],
    /// Size of header in bytes.
    pub header_size: u32,
    /// Size in bytes for DTB image.
    pub dtb_size: u32,
    /// Physical load address for DTB image.
    pub dtb_addr: u64,
}

impl Default for VendorBootHdrV3 {
    fn default() -> Self {
        Self {
            magic: VENDOR_BOOT_MAGIC,
            header_version: 3,
            page_size: 0,
            kernel_addr: 0,
            ramdisk_addr: 0,
            vendor_ramdisk_size: 0,
            cmdline: [0; VENDOR_BOOT_ARGS_SIZE],
            tags_addr: 0,
            name: [0; VENDOR_BOOT_NAME_SIZE],
            header_size: size_of::<Self>() as u32,
            dtb_size: 0,
            dtb_addr: 0,
        }
    }
}

#[repr(C, packed)]
#[derive(FromBytes, AsBytes, Debug, PartialEq, Copy, Clone)]
/// The structure of the vendor boot image version 4, which is required to be
/// present when a version 4 boot image is used, is as follows:
///
/// +------------------------+
/// | vendor boot header     | o pages
/// +------------------------+
/// | vendor ramdisk section | p pages
/// +------------------------+
/// | dtb                    | q pages
/// +------------------------+
/// | vendor ramdisk table   | r pages
/// +------------------------+
/// | bootconfig             | s pages
/// +------------------------+
///
/// o = (2128 + page_size - 1) / page_size
/// p = (vendor_ramdisk_size + page_size - 1) / page_size
/// q = (dtb_size + page_size - 1) / page_size
/// r = (vendor_ramdisk_table_size + page_size - 1) / page_size
/// s = (vendor_bootconfig_size + page_size - 1) / page_size
///
/// Note that in version 4 of the vendor boot image, multiple vendor ramdisks can
/// be included in the vendor boot image. The bootloader can select a subset of
/// ramdisks to load at runtime. To help the bootloader select the ramdisks, each
/// ramdisk is tagged with a type tag and a set of hardware identifiers
/// describing the board, soc or platform that this ramdisk is intended for.
///
/// The vendor ramdisk section consists of multiple ramdisk images concatenated
/// one after another, and vendor_ramdisk_size is the size of the section, which
/// is the total size of all the ramdisks included in the vendor boot image.
///
/// The vendor ramdisk table holds the size, offset, type, name and hardware
/// identifiers of each ramdisk. The type field denotes the type of its content.
/// The vendor ramdisk names are unique. The hardware identifiers are specified
/// in the board_id field in each table entry. The board_id field consists of a
/// vector of unsigned integer words, and the encoding scheme is defined by the
/// hardware vendor.
///
/// The different types of ramdisk are:
///    - `NONE` indicates the value is unspecified.
///    - `PLATFORM` ramdisks contain platform specific bits, so
///      the bootloader should always load these into memory.
///    - `RECOVERY` ramdisks contain recovery resources, so
///      the bootloader should load these when booting into recovery.
///    - `DLKM` ramdisks contain dynamic loadable kernel
///      modules.
///
/// Version 4 of the vendor boot image also adds a bootconfig section to the end
/// of the image. This section contains Boot Configuration parameters known at
/// build time. The bootloader is responsible for placing this section directly
/// after the generic ramdisk, followed by the bootconfig trailer, before
/// entering the kernel.
///
/// 0. all entities in the boot image are 4096-byte aligned in flash, all
///    entities in the vendor boot image are page_size (determined by the vendor
///    and specified in the vendor boot image header) aligned in flash
/// 1. kernel, ramdisk, and DTB are required (size != 0)
/// 2. load the kernel and DTB at the specified physical address (kernel_addr,
///    dtb_addr)
/// 3. load the vendor ramdisks at ramdisk_addr
/// 4. load the generic ramdisk immediately following the vendor ramdisk in
///    memory
/// 5. load the bootconfig immediately following the generic ramdisk. Add
///    additional bootconfig parameters followed by the bootconfig trailer.
/// 6. set up registers for kernel entry as required by your architecture
/// 7. if the platform has a second stage bootloader jump to it (must be
///    contained outside boot and vendor boot partitions), otherwise
///    jump to kernel_addr
///
pub struct VendorBootHdrV4 {
    /// Version 3 vendor boot header prefix.
    pub v3_img_hdr: VendorBootHdrV3,
    /// Size in bytes for the vendor ramdisk table.
    pub vendor_ramdisk_table_size: u32,
    /// Number of entries in the vendor ramdisk table.
    pub vendor_ramdisk_table_entry_num: u32,
    /// Size in bytes for a vendor ramdisk table entry.
    pub vendor_ramdisk_table_entry_size: u32,
    /// Size in bytes for the bootconfig section.
    pub bootconfig_size: u32,
}

impl Default for VendorBootHdrV4 {
    fn default() -> Self {
        Self {
            v3_img_hdr: VendorBootHdrV3 { header_version: 4, ..Default::default() },
            vendor_ramdisk_table_size: 0,
            vendor_ramdisk_table_entry_num: 0,
            vendor_ramdisk_table_entry_size: 0,
            bootconfig_size: 0,
        }
    }
}

#[derive(PartialEq, Debug)]
/// Generalized vendor boot header from a backing store of bytes.
pub enum VendorBootHdr<B: ByteSlice + PartialEq> {
    /// Version 3 header
    V3Hdr(LayoutVerified<B, VendorBootHdrV3>),
    /// Version 4 header
    V4Hdr(LayoutVerified<B, VendorBootHdrV4>),
}

/// Given a byte buffer, attempt to parse the contents and return a zero-copy reference
/// to the associated vendor boot image header.
///
/// # Arguments
/// * `buffer` - buffer to parse
///
/// # Returns
///
/// * `Ok(VendorBootHdr)` - if parsing was successful.
///
/// * `Err(BootError)` - If `buffer` does not contain a valid boot image header.
///
/// # Example
///
/// ```
/// use bootimg::VendorBootHdr;
///
/// let mut buffer = [0; 4096];
/// // Not shown: read first 4096 bytes of vendor image into buffer
/// let header = VendorBootHdr::parse_vendor_boot_image(&buffer[..]).unwrap();
/// ```
impl<B: ByteSlice + PartialEq> VendorBootHdr<B> {
    pub fn parse_vendor_boot_image(buffer: B) -> BootResult<Self> {
        // TODO(dovs): when core::offset_of has stabilized, use that instead of raw sizes
        let version_end_offset = VENDOR_BOOT_MAGIC_SIZE + size_of::<u32>();
        // In all headers, the version is a 32 bit integer starting at byte 8.
        if buffer.len() < version_end_offset {
            return Err(BootError::BufferTooSmall);
        }

        // In all headers, the first 8 bytes are the magic string.
        if (&buffer)[0..VENDOR_BOOT_MAGIC_SIZE].ne(&VENDOR_BOOT_MAGIC) {
            return Err(BootError::BadMagic);
        }

        let version = u32::from_le_bytes(
            (&buffer)[VENDOR_BOOT_MAGIC_SIZE..version_end_offset]
                .try_into()
                .map_err(|_| BootError::BufferTooSmall)?,
        );
        match version {
            3 => {
                let (head, _) = LayoutVerified::<B, VendorBootHdrV3>::new_from_prefix(buffer)
                    .ok_or(BootError::BufferTooSmall)?;
                Ok(Self::V3Hdr(head))
            }
            4 => {
                let (head, _) = LayoutVerified::<B, VendorBootHdrV4>::new_from_prefix(buffer)
                    .ok_or(BootError::BufferTooSmall)?;
                Ok(Self::V4Hdr(head))
            }
            _ => Err(BootError::UnknownVersion),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    pub fn add<T: AsBytes>(buffer: &mut [u8], t: T) {
        t.write_to_prefix(buffer).unwrap();
    }

    #[test]
    fn buffer_too_small_for_version() {
        let buffer = [0; 40];
        assert_eq!(BootImg::parse_boot_image(&buffer[..]), Err(BootError::BufferTooSmall));
    }

    #[test]
    fn buffer_too_small_valid_version() {
        // Note: because the v1 header fully encapsulates the v0 header,
        // we can trigger a buffer-too-small error by providing
        // a perfectly valid v0 header and changing the version to 1.
        let mut buffer = [0; core::mem::size_of::<BootImgHdrV0>()];
        add::<BootImgHdrV0>(&mut buffer, BootImgHdrV0 { header_version: 1, ..Default::default() });
        assert_eq!(BootImg::parse_boot_image(&buffer[..]), Err(BootError::BufferTooSmall));
    }

    #[test]
    fn bad_magic() {
        let mut buffer = [0; core::mem::size_of::<BootImgHdrV0>()];
        add::<BootImgHdrV0>(
            &mut buffer,
            BootImgHdrV0 {
                magic: [b'A', b'N', b'D', b'R', b'O', b'G', b'E', b'N'],
                ..Default::default()
            },
        );
        assert_eq!(BootImg::parse_boot_image(&buffer[..]), Err(BootError::BadMagic));
    }

    #[test]
    fn bad_version() {
        let mut buffer = [0; core::mem::size_of::<BootImgHdrV0>()];
        add::<BootImgHdrV0>(
            &mut buffer,
            BootImgHdrV0 { header_version: 2112, ..Default::default() },
        );
        assert_eq!(BootImg::parse_boot_image(&buffer[..]), Err(BootError::UnknownVersion));
    }

    #[test]
    fn parse_v0() {
        let mut buffer = [0; core::mem::size_of::<BootImgHdrV0>()];
        add::<BootImgHdrV0>(&mut buffer, Default::default());
        let expected =
            Ok(BootImg::V0Hdr(LayoutVerified::<&[u8], BootImgHdrV0>::new(&buffer).unwrap()));
        assert_eq!(BootImg::parse_boot_image(&buffer[..]), expected);
    }

    #[test]
    fn parse_v1() {
        let mut buffer = [0; core::mem::size_of::<BootImgHdrV1>()];
        add::<BootImgHdrV1>(&mut buffer, Default::default());
        let expected =
            Ok(BootImg::V1Hdr(LayoutVerified::<&[u8], BootImgHdrV1>::new(&buffer).unwrap()));
        assert_eq!(BootImg::parse_boot_image(&buffer[..]), expected);
    }

    #[test]
    fn parse_v2() {
        let mut buffer = [0; core::mem::size_of::<BootImgHdrV2>()];
        add::<BootImgHdrV2>(&mut buffer, Default::default());
        let expected =
            Ok(BootImg::V2Hdr(LayoutVerified::<&[u8], BootImgHdrV2>::new(&buffer).unwrap()));
        assert_eq!(BootImg::parse_boot_image(&buffer[..]), expected);
    }

    #[test]
    fn parse_v3() {
        let mut buffer = [0; core::mem::size_of::<BootImgHdrV3>()];
        add::<BootImgHdrV3>(&mut buffer, Default::default());
        let expected =
            Ok(BootImg::V3Hdr(LayoutVerified::<&[u8], BootImgHdrV3>::new(&buffer).unwrap()));
        assert_eq!(BootImg::parse_boot_image(&buffer[..]), expected);
    }

    #[test]
    fn parse_v4() {
        let mut buffer = [0; core::mem::size_of::<BootImgHdrV4>()];
        add::<BootImgHdrV4>(&mut buffer, Default::default());
        let expected =
            Ok(BootImg::V4Hdr(LayoutVerified::<&[u8], BootImgHdrV4>::new(&buffer).unwrap()));
        assert_eq!(BootImg::parse_boot_image(&buffer[..]), expected);
    }

    #[test]
    fn vendor_buffer_too_small_for_version() {
        let buffer = [0; VENDOR_BOOT_MAGIC_SIZE + 3];
        assert_eq!(
            VendorBootHdr::parse_vendor_boot_image(&buffer[..]),
            Err(BootError::BufferTooSmall)
        );
    }

    #[test]
    fn vendor_bad_magic() {
        let buffer = [0; core::mem::size_of::<VendorBootHdrV4>()];
        assert_eq!(VendorBootHdr::parse_vendor_boot_image(&buffer[..]), Err(BootError::BadMagic));
    }

    #[test]
    fn vendor_bad_version() {
        let mut buffer = [0; core::mem::size_of::<VendorBootHdrV3>()];
        add::<VendorBootHdrV3>(
            &mut buffer,
            VendorBootHdrV3 { header_version: 2112, ..Default::default() },
        );
        assert_eq!(
            VendorBootHdr::parse_vendor_boot_image(&buffer[..]),
            Err(BootError::UnknownVersion)
        );
    }

    #[test]
    fn vendor_buffer_too_small_valid_version() {
        let mut buffer = [0; core::mem::size_of::<VendorBootHdrV3>()];
        add::<VendorBootHdrV3>(
            &mut buffer,
            VendorBootHdrV3 {
                // Note: because the v4 header fully encapsulates the v3 header,
                // we can trigger a buffer-too-small error by providing
                // a perfectly valid v3 header and changing the version to 4.
                header_version: 4,
                ..Default::default()
            },
        );
        assert_eq!(
            VendorBootHdr::parse_vendor_boot_image(&buffer[..]),
            Err(BootError::BufferTooSmall)
        );
    }

    #[test]
    fn vendor_parse_v3() {
        let mut buffer = [0; core::mem::size_of::<VendorBootHdrV3>()];
        add::<VendorBootHdrV3>(&mut buffer, Default::default());
        let expected = Ok(VendorBootHdr::V3Hdr(
            LayoutVerified::<&[u8], VendorBootHdrV3>::new(&buffer).unwrap(),
        ));
        assert_eq!(VendorBootHdr::parse_vendor_boot_image(&buffer[..]), expected);
    }

    #[test]
    fn vendor_parse_v4() {
        let mut buffer = [0; core::mem::size_of::<VendorBootHdrV4>()];
        add::<VendorBootHdrV4>(&mut buffer, Default::default());
        let expected = Ok(VendorBootHdr::V4Hdr(
            LayoutVerified::<&[u8], VendorBootHdrV4>::new(&buffer).unwrap(),
        ));
        assert_eq!(VendorBootHdr::parse_vendor_boot_image(&buffer[..]), expected);
    }
}
