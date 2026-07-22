# docker buildx bake — local tags by default (`local/tkeir-*`)
#
# Shared Python runtime is built once as `tkeir-lib`; api/ingest/mcp/agent/
# governor/audit are thin layers on that context (not a re-run of uv sync).
# HMI stays on NODE_BASE; indexer keeps its own Dockerfile (spaCy models + OCR).
#
# Local (native platform):
#   make images
# Single target (pulls in tkeir-lib when needed):
#   make image-api
# Multi-arch push (set publish registry):
#   make images-push IMAGE_REGISTRY=ghcr.io/thalesgroup/t-keir PLATFORMS=linux/amd64,linux/arm64

variable "REGISTRY" {
  default = "local"
}

variable "TAG" {
  default = "dev"
}

variable "VERSION" {
  default = "0.0.0-dev"
}

variable "GIT_COMMIT" {
  default = "unknown"
}

variable "BUILD_DATE" {
  default = ""
}

# Absolute repo root (Make passes CONTEXT). Relative "../.." triggers
# buildx FS entitlement checks against parent paths on some hosts.
variable "CONTEXT" {
  default = "../.."
}

variable "PYTHON_BASE" {
  default = "python:3.11-slim@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93"
}

variable "NODE_BASE" {
  default = "node:22-bookworm-slim@sha256:6c74791e557ce11fc957704f6d4fe134a7bc8d6f5ca4403205b2966bd488f6b3"
}

variable "MODEL_MODE" {
  default = "fetch"
}

group "default" {
  targets = [
    "tkeir-lib",
    "tkeir-api",
    "tkeir-indexer",
    "tkeir-indexer-slim",
    "tkeir-hmi",
    "tkeir-ingest",
    "tkeir-audit",
    "tkeir-governor",
    "tkeir-mcp",
    "tkeir-agent",
  ]
}

target "_common" {
  context = CONTEXT
  args = {
    VERSION    = VERSION
    GIT_COMMIT = GIT_COMMIT
    BUILD_DATE = BUILD_DATE
  }
}

# Shared Python venv — built once; consumed via named context `tkeir-lib`.
target "tkeir-lib" {
  inherits   = ["_common"]
  dockerfile = "deploy/images/Dockerfile.tkeir-lib"
  args = {
    PYTHON_BASE = PYTHON_BASE
  }
  tags = [
    "${REGISTRY}/tkeir-lib:${TAG}",
    "${REGISTRY}/tkeir-lib:${VERSION}",
  ]
}

target "_from-lib" {
  inherits = ["_common"]
  contexts = {
    tkeir-lib = "target:tkeir-lib"
  }
}

target "tkeir-api" {
  inherits   = ["_from-lib"]
  dockerfile = "deploy/images/Dockerfile.tkeir-api"
  args = {
    MODEL_MODE = MODEL_MODE
  }
  tags = [
    "${REGISTRY}/tkeir-api:${TAG}",
    "${REGISTRY}/tkeir-api:${VERSION}",
  ]
}

target "tkeir-indexer" {
  inherits   = ["_common"]
  dockerfile = "deploy/images/Dockerfile.tkeir-indexer"
  args = {
    PYTHON_BASE = PYTHON_BASE
    INSTALL_OCR = "1"
    VARIANT     = "full"
  }
  tags = [
    "${REGISTRY}/tkeir-indexer:${TAG}",
    "${REGISTRY}/tkeir-indexer:${VERSION}",
  ]
}

target "tkeir-indexer-slim" {
  inherits   = ["_common"]
  dockerfile = "deploy/images/Dockerfile.tkeir-indexer"
  args = {
    PYTHON_BASE = PYTHON_BASE
    INSTALL_OCR = "0"
    VARIANT     = "slim"
  }
  tags = [
    "${REGISTRY}/tkeir-indexer-slim:${TAG}",
    "${REGISTRY}/tkeir-indexer-slim:${VERSION}",
  ]
}

target "tkeir-hmi" {
  inherits   = ["_common"]
  dockerfile = "deploy/images/Dockerfile.tkeir-hmi"
  args = {
    NODE_BASE = NODE_BASE
  }
  tags = [
    "${REGISTRY}/tkeir-hmi:${TAG}",
    "${REGISTRY}/tkeir-hmi:${VERSION}",
  ]
}

target "tkeir-ingest" {
  inherits   = ["_from-lib"]
  dockerfile = "deploy/images/Dockerfile.tkeir-ingest"
  tags = [
    "${REGISTRY}/tkeir-ingest:${TAG}",
    "${REGISTRY}/tkeir-ingest:${VERSION}",
  ]
}

target "tkeir-audit" {
  inherits   = ["_from-lib"]
  dockerfile = "deploy/images/Dockerfile.tkeir-audit"
  tags = [
    "${REGISTRY}/tkeir-audit:${TAG}",
    "${REGISTRY}/tkeir-audit:${VERSION}",
  ]
}

target "tkeir-governor" {
  inherits   = ["_from-lib"]
  dockerfile = "deploy/images/Dockerfile.tkeir-governor"
  tags = [
    "${REGISTRY}/tkeir-governor:${TAG}",
    "${REGISTRY}/tkeir-governor:${VERSION}",
  ]
}

target "tkeir-mcp" {
  inherits   = ["_from-lib"]
  dockerfile = "deploy/images/Dockerfile.tkeir-mcp"
  tags = [
    "${REGISTRY}/tkeir-mcp:${TAG}",
    "${REGISTRY}/tkeir-mcp:${VERSION}",
  ]
}

target "tkeir-agent" {
  inherits   = ["_from-lib"]
  dockerfile = "deploy/images/Dockerfile.tkeir-agent"
  tags = [
    "${REGISTRY}/tkeir-agent:${TAG}",
    "${REGISTRY}/tkeir-agent:${VERSION}",
  ]
}
