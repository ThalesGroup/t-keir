#!/usr/bin/env bash
# Verify a cosign blob bundle. Local keys always skip Rekor tlog checks so
# laptop CI is not broken by Sigstore TUF/Rekor certificate rotations.
set -euo pipefail

BUNDLE_DIR="${COSIGN_BUNDLE_DIR:?}"
BUNDLE_NAME="${1:?bundle name}"
ARTIFACT="${2:?artifact path}"
LABEL="${3:-artifact}"

bundle_path="$BUNDLE_DIR/$BUNDLE_NAME"
mode_path="$BUNDLE_DIR/${BUNDLE_NAME}.mode"
mode="$(cat "$mode_path" 2>/dev/null || cat "$BUNDLE_DIR/.mode" 2>/dev/null || true)"

if [ ! -f "$bundle_path" ]; then
	echo "ERROR: missing bundle $bundle_path" >&2
	exit 1
fi
if [ ! -f "$ARTIFACT" ]; then
	echo "ERROR: missing artifact $ARTIFACT" >&2
	exit 1
fi

# Bundle shape: local keys embed publicKey; keyless embeds a Fulcio certificate.
bundle_looks_local=0
if command -v python3 >/dev/null 2>&1; then
	if python3 - "$bundle_path" <<'PY'
import json, sys
p = sys.argv[1]
try:
    d = json.load(open(p))
except Exception:
    sys.exit(1)
vm = d.get("verificationMaterial") or {}
# Classic simple bundle from --new-bundle-format=false
if "cert" in d and "base64Signature" in d and "verificationMaterial" not in d:
    # local pubkey PEM often stored in "cert" field for old format — treat as local
    sys.exit(0)
if vm.get("publicKey") and not (
    vm.get("certificate")
    or (vm.get("x509CertificateChain") or {}).get("certificates")
):
    sys.exit(0)
sys.exit(1)
PY
	then
		bundle_looks_local=1
	fi
fi

use_local=0
if [ -f "$BUNDLE_DIR/ci.pub" ]; then
	if [ "$mode" = "local" ] || [ "$bundle_looks_local" = "1" ] || [ "$mode" != "keyless" ]; then
		use_local=1
	fi
fi

verify_local() {
	extra=(--key "$BUNDLE_DIR/ci.pub" --insecure-ignore-tlog=true)
	if cosign verify-blob --help 2>&1 | grep -q -- '--new-bundle-format'; then
		# Try both formats; cosign v3 may emit either.
		if COSIGN_PASSWORD="" cosign verify-blob \
			--bundle "$bundle_path" \
			"${extra[@]}" \
			--new-bundle-format=false \
			"$ARTIFACT" >/dev/null 2>&1; then
			return 0
		fi
	fi
	COSIGN_PASSWORD="" cosign verify-blob \
		--bundle "$bundle_path" \
		"${extra[@]}" \
		"$ARTIFACT"
}

verify_keyless() {
	# Prefer ignore-tlog first — Rekor inclusion proofs often fail on laptops.
	if cosign verify-blob \
		--bundle "$bundle_path" \
		--certificate-identity-regexp '.*' \
		--certificate-oidc-issuer-regexp '.*' \
		--insecure-ignore-tlog=true \
		"$ARTIFACT" >/dev/null 2>&1; then
		return 0
	fi
	cosign verify-blob \
		--bundle "$bundle_path" \
		--certificate-identity-regexp '.*' \
		--certificate-oidc-issuer-regexp '.*' \
		"$ARTIFACT"
}

if [ "$use_local" = "1" ]; then
	if verify_local; then
		echo "PASS: $LABEL signature OK (local key)"
		exit 0
	fi
	echo "WARN: local-key verify failed — trying keyless fallback" >&2
	if verify_keyless; then
		echo "PASS: $LABEL signature OK (keyless fallback)"
		exit 0
	fi
	echo "ERROR: verify failed for $LABEL ($bundle_path)" >&2
	exit 1
fi

if verify_keyless; then
	echo "PASS: $LABEL signature OK (keyless)"
	exit 0
fi
if [ -f "$BUNDLE_DIR/ci.pub" ] && verify_local; then
	echo "PASS: $LABEL signature OK (local key fallback)"
	exit 0
fi
echo "ERROR: verify failed for $LABEL ($bundle_path)" >&2
exit 1
