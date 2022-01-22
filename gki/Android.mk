_gsi_gki_product_names := \
  aosp_arm \
  aosp_arm64 \
  aosp_x86 \
  aosp_x86_64 \
  gsi_arm \
  gsi_arm64 \
  gsi_x86 \
  gsi_x86_64 \
  gki_arm64 \
  gki_x86_64 \

ifneq (,$(filter $(_gsi_gki_product_names),$(TARGET_PRODUCT)))

droidcore-unbundled: gki_retrofitting_tools

endif

_gsi_gki_product_names :=
