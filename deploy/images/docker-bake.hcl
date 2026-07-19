# docker buildx bake — images for ghcr.io/thalesgroup/t-keir
#
# Local (native platform):
#   make images
# Single target:
#   make image-api
# Multi-arch push:
#   make images-push PLATFORMS=linux/amd64,linux/arm64

variable "REGISTRY" {
  default = "ghcr.io/thalesgroup/t-keir"
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
  targets = ["tkeir-api", "tkeir-indexer", "tkeir-indexer-slim", "tkeir-hmi", "tkeir-ingest", "tkeir-audit", "tkeir-governor", "tkeir-mcp", "tkeir-agent"]
}

target "_common" {
  context = CONTEXT
  args = {
    VERSION    = VERSION
    GIT_COMMIT = GIT_COMMIT
    BUILD_DATE = BUILD_DATE
  }
}

target "tkeir-api" {
  inherits   = ["_common"]
  dockerfile = "deploy/images/Dockerfile.tkeir-api"
  args = {
    PYTHON_BASE = PYTHON_BASE
    MODEL_MODE  = MODEL_MODE
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
  inherits   = ["_common"]
  dockerfile = "deploy/images/Dockerfile.tkeir-ingest"
  args = {
    PYTHON_BASE = PYTHON_BASE
  }
  tags = [
    "${REGISTRY}/tkeir-ingest:${TAG}",
    "${REGISTRY}/tkeir-ingest:${VERSION}",
  ]
}

target "tkeir-audit" {
  inherits   = ["_common"]
  dockerfile = "deploy/images/Dockerfile.tkeir-audit"
  args = {
    PYTHON_BASE = PYTHON_BASE
  }
  tags = [
    "${REGISTRY}/tkeir-audit:${TAG}",
    "${REGISTRY}/tkeir-audit:${VERSION}",
  ]
}

target "tkeir-governor" {
  inherits   = ["_common"]
  dockerfile = "deploy/images/Dockerfile.tkeir-governor"
  args = {
    PYTHON_BASE = PYTHON_BASE
  }
  tags = [
    "${REGISTRY}/tkeir-governor:${TAG}",
    "${REGISTRY}/tkeir-governor:${VERSION}",
  ]
}

target "tkeir-mcp" {
  inherits   = ["_common"]
  dockerfile = "deploy/images/Dockerfile.tkeir-mcp"
  args = {
    PYTHON_BASE = PYTHON_BASE
  }
  tags = [
    "${REGISTRY}/tkeir-mcp:${TAG}",
    "${REGISTRY}/tkeir-mcp:${VERSION}",
  ]
}

target "tkeir-agent" {
  inherits   = ["_common"]
  dockerfile = "deploy/images/Dockerfile.tkeir-agent"
  args = {
    PYTHON_BASE = PYTHON_BASE
  }
  tags = [
    "${REGISTRY}/tkeir-agent:${TAG}",
    "${REGISTRY}/tkeir-agent:${VERSION}",
  ]
}
