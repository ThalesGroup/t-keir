#!/usr/bin/env bash
# Cosign sign-blob: local keypair on developer machines; keyless only in GHA/OIDC.
# Avoids Rekor "transparency log certificate does not match" on laptops.
set -euo pipefail

BUNDLE_DIR="${COSIGN_BUNDLE_DIR:?}"
BUNDLE_NAME="${1:?bundle name}"
ARTIFACT="${2:?artifact path}"
REKOR_URL="${REKOR_URL:-https://rekor.sigstore.dev}"
FULCIO_URL="${FULCIO_URL:-https://fulcio.sigstore.dev}"
COSIGN_YES="${COSIGN_YES:---yes}"
STRICT_SIGNING="${STRICT_SIGNING:-0}"

# Local by default. Keyless only when explicitly requested or on GitHub Actions.
# COSIGN_KEYLESS_FORCE=1 overrides the GHA-only auto-enable.
if [ "${COSIGN_KEYLESS_FORCE:-0}" = "1" ]; then
	COSIGN_KEYLESS=1
elif [ -z "${COSIGN_KEYLESS+x}" ]; then
	if [ "${GITHUB_ACTIONS:-}" = "true" ]; then
		COSIGN_KEYLESS=1
	else
		COSIGN_KEYLESS=0
	fi
elif [ "${GITHUB_ACTIONS:-}" != "true" ] && [ "${COSIGN_ALLOW_KEYLESS_LOCAL:-0}" != "1" ]; then
	# Ignore accidental COSIGN_KEYLESS=1 on laptops (Rekor cert mismatches).
	if [ "$COSIGN_KEYLESS" = "1" ]; then
		echo "WARN: ignoring COSIGN_KEYLESS=1 outside GitHub Actions (set COSIGN_ALLOW_KEYLESS_LOCAL=1 to force)"
		COSIGN_KEYLESS=0
	fi
fi

mkdir -p "$BUNDLE_DIR"
bundle_path="$BUNDLE_DIR/$BUNDLE_NAME"
mode_path="$BUNDLE_DIR/${BUNDLE_NAME}.mode"

sign_local() {
	echo "WARN: using local COSIGN keypair (offline / no OIDC)"
	if [ ! -f "$BUNDLE_DIR/ci.key" ]; then
		COSIGN_PASSWORD="" cosign generate-key-pair \
			--output-key-prefix "$BUNDLE_DIR/ci"
	fi
	extra=(--use-signing-config=false)
	# Prefer no transparency log — verify on laptop must not depend on Rekor/TUF.
	if cosign sign-blob --help 2>&1 | grep -q -- '--tlog-upload'; then
		extra+=(--tlog-upload=false)
	fi
	if cosign sign-blob --help 2>&1 | grep -q -- '--new-bundle-format'; then
		extra+=(--new-bundle-format=false)
	fi
	COSIGN_PASSWORD="" cosign sign-blob $COSIGN_YES \
		--key "$BUNDLE_DIR/ci.key" \
		--bundle "$bundle_path" \
		"${extra[@]}" \
		"$ARTIFACT"
	echo "local" >"$mode_path"
	echo "local" >"$BUNDLE_DIR/.mode"
	echo "Signed (local key) → $bundle_path"
}

if [ "$COSIGN_KEYLESS" = "1" ]; then
	if cosign sign-blob $COSIGN_YES \
		--bundle "$bundle_path" \
		--rekor-url "$REKOR_URL" \
		--fulcio-url "$FULCIO_URL" \
		"$ARTIFACT" >/dev/null 2>&1; then
		# Smoke-verify; Rekor cert rotations often break inclusion proofs locally.
		if cosign verify-blob \
			--bundle "$bundle_path" \
			--certificate-identity-regexp '.*' \
			--certificate-oidc-issuer-regexp '.*' \
			--insecure-ignore-tlog=true \
			"$ARTIFACT" >/dev/null 2>&1 \
			|| cosign verify-blob \
				--bundle "$bundle_path" \
				--certificate-identity-regexp '.*' \
				--certificate-oidc-issuer-regexp '.*' \
				"$ARTIFACT" >/dev/null 2>&1; then
			echo "Signed (keyless) → $bundle_path"
			echo "keyless" >"$mode_path"
			echo "keyless" >"$BUNDLE_DIR/.mode"
			exit 0
		fi
		echo "WARN: keyless bundle failed verify — falling back to local key"
	elif [ "$STRICT_SIGNING" = "1" ]; then
		echo "ERROR: keyless cosign failed and STRICT_SIGNING=1" >&2
		exit 1
	else
		echo "WARN: keyless signing unavailable — falling back to local key"
	fi
fi

sign_local
