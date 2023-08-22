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

//! The public interface for bootimg structs
use core::mem::size_of;
use zerocopy::{ByteSlice, LayoutVerified};

use bootimg_private::{
    boot_img_hdr_v0, boot_img_hdr_v1, boot_img_hdr_v2, boot_img_hdr_v3, boot_img_hdr_v4,
    vendor_boot_img_hdr_v3, vendor_boot_img_hdr_v4, BOOT_MAGIC, BOOT_MAGIC_SIZE, VENDOR_BOOT_MAGIC,
    VENDOR_BOOT_MAGIC_SIZE,
};

/// Generalized boot image from a backing store of bytes.
#[derive(PartialEq, Debug)]
pub enum BootImg<B: ByteSlice + PartialEq> {
    /// Version 0 header
    V0Hdr(LayoutVerified<B, boot_img_hdr_v0>),
    /// Version 1 header
    V1Hdr(LayoutVerified<B, boot_img_hdr_v1>),
    /// Version 2 header
    V2Hdr(LayoutVerified<B, boot_img_hdr_v2>),
    /// Version 3 header
    V3Hdr(LayoutVerified<B, boot_img_hdr_v3>),
    /// Version 4 header
    V4Hdr(LayoutVerified<B, boot_img_hdr_v4>),
}

/// Generalized vendor boot header from a backing store of bytes.
#[derive(PartialEq, Debug)]
pub enum VendorBootHdr<B: ByteSlice + PartialEq> {
    /// Version 3 header
    V3Hdr(LayoutVerified<B, vendor_boot_img_hdr_v3>),
    /// Version 4 header
    V4Hdr(LayoutVerified<B, vendor_boot_img_hdr_v4>),
}

/// Boot related errors.
#[derive(PartialEq, Debug)]
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

/// Common result type for use with boot headers
pub type BootResult<T> = Result<T, BootError>;

impl<B: ByteSlice + PartialEq> BootImg<B> {
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
    pub fn parse_boot_image(buffer: B) -> BootResult<Self> {
        let magic_size = BOOT_MAGIC_SIZE as usize;
        // In all headers, the version is a 32 bit integer starting at byte 40.
        // TODO(dovs): when core::offset_of has stabilized, use that instead of raw sizes
        if buffer.len() < 44 {
            return Err(BootError::BufferTooSmall);
        }

        let version = u32::from_le_bytes(
            (&buffer)[40..44]
                .try_into()
                .map_err(|_| BootError::BufferTooSmall)?,
        );

        // In all headers, the first 8 bytes are the magic string.
        if (&buffer)[0..magic_size].ne(&BOOT_MAGIC[..magic_size]) {
            return Err(BootError::BadMagic);
        }

        match version {
            0 => {
                let (head, _) = LayoutVerified::<B, boot_img_hdr_v0>::new_from_prefix(buffer)
                    .ok_or(BootError::BufferTooSmall)?;
                Ok(Self::V0Hdr(head))
            }
            1 => {
                let (head, _) = LayoutVerified::<B, boot_img_hdr_v1>::new_from_prefix(buffer)
                    .ok_or(BootError::BufferTooSmall)?;
                Ok(Self::V1Hdr(head))
            }
            2 => {
                let (head, _) = LayoutVerified::<B, boot_img_hdr_v2>::new_from_prefix(buffer)
                    .ok_or(BootError::BufferTooSmall)?;
                Ok(Self::V2Hdr(head))
            }
            3 => {
                let (head, _) = LayoutVerified::<B, boot_img_hdr_v3>::new_from_prefix(buffer)
                    .ok_or(BootError::BufferTooSmall)?;
                Ok(Self::V3Hdr(head))
            }
            4 => {
                let (head, _) = LayoutVerified::<B, boot_img_hdr_v4>::new_from_prefix(buffer)
                    .ok_or(BootError::BufferTooSmall)?;
                Ok(Self::V4Hdr(head))
            }
            _ => Err(BootError::UnknownVersion),
        }
    }
}

impl<B: ByteSlice + PartialEq> VendorBootHdr<B> {
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
    pub fn parse_vendor_boot_image(buffer: B) -> BootResult<Self> {
        // TODO(dovs): when core::offset_of has stabilized, use that instead of raw sizes
        let magic_size = VENDOR_BOOT_MAGIC_SIZE as usize;
        let version_end_offset = magic_size + size_of::<u32>();
        // In all headers, the version is a 32 bit integer starting at byte 8.
        if buffer.len() < version_end_offset {
            return Err(BootError::BufferTooSmall);
        }

        // In all headers, the first 8 bytes are the magic string.
        if (&buffer)[0..magic_size].ne(&VENDOR_BOOT_MAGIC[..magic_size]) {
            return Err(BootError::BadMagic);
        }

        let version = u32::from_le_bytes(
            (&buffer)[magic_size..version_end_offset]
                .try_into()
                .map_err(|_| BootError::BufferTooSmall)?,
        );
        match version {
            3 => {
                let (head, _) =
                    LayoutVerified::<B, vendor_boot_img_hdr_v3>::new_from_prefix(buffer)
                        .ok_or(BootError::BufferTooSmall)?;
                Ok(Self::V3Hdr(head))
            }
            4 => {
                let (head, _) =
                    LayoutVerified::<B, vendor_boot_img_hdr_v4>::new_from_prefix(buffer)
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
    use zerocopy::AsBytes;

    const MAGIC_SIZE: usize = BOOT_MAGIC_SIZE as usize;
    const VENDOR_MAGIC_SIZE: usize = VENDOR_BOOT_MAGIC_SIZE as usize;

    pub fn add<T: AsBytes>(buffer: &mut [u8], t: T) {
        t.write_to_prefix(buffer).unwrap();
    }

    #[test]
    fn buffer_too_small_for_version() {
        let buffer = [0; 40];
        assert_eq!(
            BootImg::parse_boot_image(&buffer[..]),
            Err(BootError::BufferTooSmall)
        );
    }

    #[test]
    fn buffer_too_small_valid_version() {
        // Note: because the v1 header fully encapsulates the v0 header,
        // we can trigger a buffer-too-small error by providing
        // a perfectly valid v0 header and changing the version to 1.
        let mut buffer = [0; core::mem::size_of::<boot_img_hdr_v0>()];
        add::<boot_img_hdr_v0>(
            &mut buffer,
            boot_img_hdr_v0 {
                magic: BOOT_MAGIC[0..MAGIC_SIZE].try_into().unwrap(),
                header_version: 1,
                ..Default::default()
            },
        );
        assert_eq!(
            BootImg::parse_boot_image(&buffer[..]),
            Err(BootError::BufferTooSmall)
        );
    }

    #[test]
    fn bad_magic() {
        let mut buffer = [0; core::mem::size_of::<boot_img_hdr_v0>()];
        add::<boot_img_hdr_v0>(
            &mut buffer,
            boot_img_hdr_v0 {
                magic: *b"ANDROGEN",
                ..Default::default()
            },
        );
        assert_eq!(
            BootImg::parse_boot_image(&buffer[..]),
            Err(BootError::BadMagic)
        );
    }

    #[test]
    fn bad_version() {
        let mut buffer = [0; core::mem::size_of::<boot_img_hdr_v0>()];
        add::<boot_img_hdr_v0>(
            &mut buffer,
            boot_img_hdr_v0 {
                magic: BOOT_MAGIC[0..MAGIC_SIZE].try_into().unwrap(),
                header_version: 2112,
                ..Default::default()
            },
        );
        assert_eq!(
            BootImg::parse_boot_image(&buffer[..]),
            Err(BootError::UnknownVersion)
        );
    }

    #[test]
    fn parse_v0() {
        let mut buffer = [0; core::mem::size_of::<boot_img_hdr_v0>()];
        add::<boot_img_hdr_v0>(
            &mut buffer,
            boot_img_hdr_v0 {
                magic: BOOT_MAGIC[0..MAGIC_SIZE].try_into().unwrap(),
                header_version: 0,
                ..Default::default()
            },
        );
        let expected = Ok(BootImg::V0Hdr(
            LayoutVerified::<&[u8], boot_img_hdr_v0>::new(&buffer).unwrap(),
        ));
        assert_eq!(BootImg::parse_boot_image(&buffer[..]), expected);
    }

    #[test]
    fn parse_v1() {
        let mut buffer = [0; core::mem::size_of::<boot_img_hdr_v1>()];
        add::<boot_img_hdr_v1>(
            &mut buffer,
            boot_img_hdr_v1 {
                _base: boot_img_hdr_v0 {
                    magic: BOOT_MAGIC[0..MAGIC_SIZE].try_into().unwrap(),
                    header_version: 1,
                    ..Default::default()
                },
                ..Default::default()
            },
        );
        let expected = Ok(BootImg::V1Hdr(
            LayoutVerified::<&[u8], boot_img_hdr_v1>::new(&buffer).unwrap(),
        ));
        assert_eq!(BootImg::parse_boot_image(&buffer[..]), expected);
    }

    #[test]
    fn parse_v2() {
        let mut buffer = [0; core::mem::size_of::<boot_img_hdr_v2>()];
        add::<boot_img_hdr_v2>(
            &mut buffer,
            boot_img_hdr_v2 {
                _base: boot_img_hdr_v1 {
                    _base: boot_img_hdr_v0 {
                        magic: BOOT_MAGIC[0..MAGIC_SIZE].try_into().unwrap(),
                        header_version: 2,
                        ..Default::default()
                    },
                    ..Default::default()
                },
                ..Default::default()
            },
        );
        let expected = Ok(BootImg::V2Hdr(
            LayoutVerified::<&[u8], boot_img_hdr_v2>::new(&buffer).unwrap(),
        ));
        assert_eq!(BootImg::parse_boot_image(&buffer[..]), expected);
    }

    #[test]
    fn parse_v3() {
        let mut buffer = [0; core::mem::size_of::<boot_img_hdr_v3>()];
        add::<boot_img_hdr_v3>(
            &mut buffer,
            boot_img_hdr_v3 {
                magic: BOOT_MAGIC[0..MAGIC_SIZE].try_into().unwrap(),
                header_version: 3,
                ..Default::default()
            },
        );
        let expected = Ok(BootImg::V3Hdr(
            LayoutVerified::<&[u8], boot_img_hdr_v3>::new(&buffer).unwrap(),
        ));
        assert_eq!(BootImg::parse_boot_image(&buffer[..]), expected);
    }

    #[test]
    fn parse_v4() {
        let mut buffer = [0; core::mem::size_of::<boot_img_hdr_v4>()];
        add::<boot_img_hdr_v4>(
            &mut buffer,
            boot_img_hdr_v4 {
                _base: boot_img_hdr_v3 {
                    magic: BOOT_MAGIC[0..MAGIC_SIZE].try_into().unwrap(),
                    header_version: 4,
                    ..Default::default()
                },
                ..Default::default()
            },
        );
        let expected = Ok(BootImg::V4Hdr(
            LayoutVerified::<&[u8], boot_img_hdr_v4>::new(&buffer).unwrap(),
        ));
        assert_eq!(BootImg::parse_boot_image(&buffer[..]), expected);
    }

    #[test]
    fn vendor_buffer_too_small_for_version() {
        let buffer = [0; VENDOR_MAGIC_SIZE + 3];
        assert_eq!(
            VendorBootHdr::parse_vendor_boot_image(&buffer[..]),
            Err(BootError::BufferTooSmall)
        );
    }

    #[test]
    fn vendor_bad_magic() {
        let mut buffer = [0; core::mem::size_of::<vendor_boot_img_hdr_v3>()];
        add::<vendor_boot_img_hdr_v3>(
            &mut buffer,
            vendor_boot_img_hdr_v3 {
                magic: *b"VNDRBOOK",
                header_version: 3,
                ..Default::default()
            },
        );
        assert_eq!(
            VendorBootHdr::parse_vendor_boot_image(&buffer[..]),
            Err(BootError::BadMagic)
        );
    }

    #[test]
    fn vendor_bad_version() {
        let mut buffer = [0; core::mem::size_of::<vendor_boot_img_hdr_v3>()];
        add::<vendor_boot_img_hdr_v3>(
            &mut buffer,
            vendor_boot_img_hdr_v3 {
                magic: VENDOR_BOOT_MAGIC[0..VENDOR_MAGIC_SIZE].try_into().unwrap(),
                header_version: 2112,
                ..Default::default()
            },
        );
        assert_eq!(
            VendorBootHdr::parse_vendor_boot_image(&buffer[..]),
            Err(BootError::UnknownVersion)
        );
    }

    #[test]
    fn vendor_buffer_too_small_valid_version() {
        let mut buffer = [0; core::mem::size_of::<vendor_boot_img_hdr_v3>()];
        add::<vendor_boot_img_hdr_v3>(
            &mut buffer,
            vendor_boot_img_hdr_v3 {
                magic: VENDOR_BOOT_MAGIC[0..VENDOR_MAGIC_SIZE].try_into().unwrap(),
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
        let mut buffer = [0; core::mem::size_of::<vendor_boot_img_hdr_v3>()];
        add::<vendor_boot_img_hdr_v3>(
            &mut buffer,
            vendor_boot_img_hdr_v3 {
                magic: VENDOR_BOOT_MAGIC[0..VENDOR_MAGIC_SIZE].try_into().unwrap(),
                header_version: 3,
                ..Default::default()
            },
        );
        let expected = Ok(VendorBootHdr::V3Hdr(
            LayoutVerified::<&[u8], vendor_boot_img_hdr_v3>::new(&buffer).unwrap(),
        ));
        assert_eq!(
            VendorBootHdr::parse_vendor_boot_image(&buffer[..]),
            expected
        );
    }

    #[test]
    fn vendor_parse_v4() {
        let mut buffer = [0; core::mem::size_of::<vendor_boot_img_hdr_v4>()];
        add::<vendor_boot_img_hdr_v4>(
            &mut buffer,
            vendor_boot_img_hdr_v4 {
                _base: vendor_boot_img_hdr_v3 {
                    magic: VENDOR_BOOT_MAGIC[0..VENDOR_MAGIC_SIZE].try_into().unwrap(),
                    header_version: 4,
                    ..Default::default()
                },
                ..Default::default()
            },
        );
        let expected = Ok(VendorBootHdr::V4Hdr(
            LayoutVerified::<&[u8], vendor_boot_img_hdr_v4>::new(&buffer).unwrap(),
        ));
        assert_eq!(
            VendorBootHdr::parse_vendor_boot_image(&buffer[..]),
            expected
        );
    }
}
