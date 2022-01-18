#!/bin/bash
#
# Copyright (C) 2022 The Android Open Source Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

#
# Retrofits GKI boot images for upgrading devices.
#

set -eo errtrace

usage() {
  cat <<EOF
Usage:
  $0 --boot BOOT --init_boot INIT_BOOT --version {3,4} -o OUTPUT
  $0 --boot BOOT --init_boot INIT_BOOT --vendor_boot VENDOR_BOOT --version 2 -o OUTPUT

Options:
  --boot FILE
    Path to the generic boot image.
  --init_boot FILE
    Path to the generic init_boot image.
  --vendor_boot FILE
    Path to the vendor boot image.
  --version {2,3,4}
    Boot image header version to retrofit to.
  -o, --output FILE
    Path to the output boot image.
  -v, --verbose
    Show debug messages.
  -h, --help, --usage
    Show this help message.
EOF
}

die() {
  echo >&2 "ERROR: ${@}"
  exit 1
}

get_arg() {
  local arg="$1"
  shift
  while [[ "$#" -gt 0 ]]; do
    if [[ "$1" == "${arg}" ]]; then
      shift
      echo "$1"
      return
    fi
    shift
  done
}

exit_handler() {
  readonly EXIT_CODE="$?"
  [[ -n "${TEMP_DIR}" ]] && rm -rf "${TEMP_DIR}"
  exit "${EXIT_CODE}"
}

trap exit_handler EXIT
trap 'die "line ${LINENO}, ${FUNCNAME:-<main>}(): \"${BASH_COMMAND}\" returned \"$?\"" ' ERR

while [[ "$1" =~ ^- ]]; do
  case "$1" in
    --boot )
      shift
      BOOT_IMAGE="$1"
      ;;
    --init_boot )
      shift
      INIT_BOOT_IMAGE="$1"
      ;;
    --vendor_boot )
      shift
      VENDOR_BOOT_IMAGE="$1"
      ;;
    --version )
      shift
      OUTPUT_BOOT_IMAGE_VERSION="$1"
      ;;
    -o | --output )
      shift
      OUTPUT_BOOT_IMAGE="$1"
      ;;
    -v | --verbose )
      VERBOSE=1
      ;;
    -- )
      shift
      break
      ;;
    -h | --help | --usage )
      usage
      exit 0
      ;;
    * )
      echo >&2 "Unexpected flag: '$1'"
      usage >&2
      exit 1
  esac
  shift
done

readonly BOOT_IMAGE
readonly INIT_BOOT_IMAGE
readonly VENDOR_BOOT_IMAGE
declare -i OUTPUT_BOOT_IMAGE_VERSION
readonly OUTPUT_BOOT_IMAGE_VERSION
readonly OUTPUT_BOOT_IMAGE
readonly VERBOSE

# Make sure the input arguments make sense.
[[ -f "${BOOT_IMAGE}" ]] || die "argument '--boot': not a regular file: '${BOOT_IMAGE}'"
[[ -f "${INIT_BOOT_IMAGE}" ]] || die "argument '--init_boot': not a regular file: '${INIT_BOOT_IMAGE}'"
if [[ "${OUTPUT_BOOT_IMAGE_VERSION}" < 2 ]] || [[ "${OUTPUT_BOOT_IMAGE_VERSION}" > 4 ]]; then
  die "argument '--version': valid choices are {2, 3, 4}"
elif [[ "${OUTPUT_BOOT_IMAGE_VERSION}" -eq 2 ]]; then
  [[ -f "${VENDOR_BOOT_IMAGE}" ]] || die "argument '--vendor_boot': not a regular file: '${VENDOR_BOOT_IMAGE}'"
fi

readonly TEMP_DIR="$(mktemp -d --tmpdir retrofit_gki.XXXXXXXX)"
readonly BOOT_DIR="${TEMP_DIR}/boot"
readonly INIT_BOOT_DIR="${TEMP_DIR}/init_boot"
readonly VENDOR_BOOT_DIR="${TEMP_DIR}/vendor_boot"
readonly VENDOR_BOOT_MKBOOTIMG_ARGS="${TEMP_DIR}/vendor_boot.mkbootimg_args"
readonly OUTPUT_RAMDISK="${TEMP_DIR}/out.ramdisk"
readonly OUTPUT_BOOT_SIGNATURE="${TEMP_DIR}/out.boot_signature"

( [[ -n "${VERBOSE}" ]] && set -x
  unpack_bootimg --boot_img "${BOOT_IMAGE}" --out "${BOOT_DIR}" >/dev/null
  unpack_bootimg --boot_img "${INIT_BOOT_IMAGE}" --out "${INIT_BOOT_DIR}" >/dev/null
  cat "${BOOT_DIR}/boot_signature" "${INIT_BOOT_DIR}/boot_signature" > "${OUTPUT_BOOT_SIGNATURE}"
)

if [[ "${OUTPUT_BOOT_IMAGE_VERSION}" -eq 4 ]]; then
  ( [[ -n "${VERBOSE}" ]] && set -x
    mkbootimg \
      --kernel "${BOOT_DIR}/kernel" \
      --ramdisk "${INIT_BOOT_DIR}/ramdisk" \
      --boot_signature "${OUTPUT_BOOT_SIGNATURE}" \
      --header_version "${OUTPUT_BOOT_IMAGE_VERSION}" \
      --output "${OUTPUT_BOOT_IMAGE}"
  )
elif [[ "${OUTPUT_BOOT_IMAGE_VERSION}" -eq 3 ]]; then
  ( [[ -n "${VERBOSE}" ]] && set -x
    mkbootimg \
      --kernel "${BOOT_DIR}/kernel" \
      --ramdisk "${INIT_BOOT_DIR}/ramdisk" \
      --header_version "${OUTPUT_BOOT_IMAGE_VERSION}" \
      --output "${OUTPUT_BOOT_IMAGE}"

    # Pad the boot signature up to page boundary and append it to the end.
    truncate "${OUTPUT_BOOT_SIGNATURE}" -s "%4096"
    cat "${OUTPUT_BOOT_SIGNATURE}" >> "${OUTPUT_BOOT_IMAGE}"
  )
elif [[ "${OUTPUT_BOOT_IMAGE_VERSION}" -eq 2 ]]; then
  ( [[ -n "${VERBOSE}" ]] && set -x
    unpack_bootimg --boot_img "${VENDOR_BOOT_IMAGE}" --out "${VENDOR_BOOT_DIR}" \
      --format=mkbootimg -0 > "${VENDOR_BOOT_MKBOOTIMG_ARGS}"
  )

  declare -a mkbootimg_args=()
  while IFS= read -r -d '' ARG; do
    mkbootimg_args+=("${ARG}")
  done <"${VENDOR_BOOT_MKBOOTIMG_ARGS}"

  declare -i pagesize
  pagesize="$(get_arg --pagesize "${mkbootimg_args[@]}")"
  kernel_offset="$(get_arg --kernel_offset "${mkbootimg_args[@]}")"
  ramdisk_offset="$(get_arg --ramdisk_offset "${mkbootimg_args[@]}")"
  tags_offset="$(get_arg --tags_offset "${mkbootimg_args[@]}")"
  dtb_offset="$(get_arg --dtb_offset "${mkbootimg_args[@]}")"
  kernel_cmdline="$(get_arg --vendor_cmdline "${mkbootimg_args[@]}")"

  ( [[ -n "${VERBOSE}" ]] && set -x
    cat "${VENDOR_BOOT_DIR}/vendor_ramdisk" "${INIT_BOOT_DIR}/ramdisk" > "${OUTPUT_RAMDISK}"
    mkbootimg \
      --pagesize "${pagesize}" \
      --base 0 \
      --kernel_offset "${kernel_offset}" \
      --ramdisk_offset "${ramdisk_offset}" \
      --tags_offset "${tags_offset}" \
      --dtb_offset "${dtb_offset}" \
      --cmdline "${kernel_cmdline}" \
      --kernel "${BOOT_DIR}/kernel" \
      --ramdisk "${OUTPUT_RAMDISK}" \
      --dtb "${VENDOR_BOOT_DIR}/dtb" \
      --header_version "${OUTPUT_BOOT_IMAGE_VERSION}" \
      --output "${OUTPUT_BOOT_IMAGE}"

    # Pad the boot signature up to page boundary and append it to the end.
    truncate "${OUTPUT_BOOT_SIGNATURE}" -s "%${pagesize}"
    cat "${OUTPUT_BOOT_SIGNATURE}" >> "${OUTPUT_BOOT_IMAGE}"
  )
fi

