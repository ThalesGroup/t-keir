#!/bin/bash
# Install Tesseract OCR when missing (required for PDF image text extraction).
set -euo pipefail

if command -v tesseract >/dev/null 2>&1; then
    echo "Tesseract already installed: $(tesseract --version 2>&1 | head -1)"
    exit 0
fi

os="$(uname -s)"
echo "Tesseract not found. Detected OS: ${os}"

install_with_brew() {
    if ! command -v brew >/dev/null 2>&1; then
        echo "Homebrew is required on macOS. Install from https://brew.sh/" >&2
        exit 1
    fi
    echo "Installing tesseract via Homebrew..."
    brew install tesseract
}

install_with_apt() {
    if ! command -v apt-get >/dev/null 2>&1; then
        echo "apt-get not found" >&2
        exit 1
    fi
    echo "Installing tesseract-ocr via apt..."
    sudo apt-get update
    sudo apt-get install -y tesseract-ocr
}

install_with_dnf() {
    if ! command -v dnf >/dev/null 2>&1; then
        echo "dnf not found" >&2
        exit 1
    fi
    echo "Installing tesseract via dnf..."
    sudo dnf install -y tesseract
}

install_with_yum() {
    if ! command -v yum >/dev/null 2>&1; then
        echo "yum not found" >&2
        exit 1
    fi
    echo "Installing tesseract via yum..."
    sudo yum install -y tesseract
}

install_with_pacman() {
    if ! command -v pacman >/dev/null 2>&1; then
        echo "pacman not found" >&2
        exit 1
    fi
    echo "Installing tesseract via pacman..."
    sudo pacman -S --noconfirm tesseract
}

case "${os}" in
    Darwin)
        install_with_brew
        ;;
    Linux)
        if [ -f /etc/debian_version ] || command -v apt-get >/dev/null 2>&1; then
            install_with_apt
        elif [ -f /etc/fedora-release ] || command -v dnf >/dev/null 2>&1; then
            install_with_dnf
        elif [ -f /etc/redhat-release ] || command -v yum >/dev/null 2>&1; then
            install_with_yum
        elif [ -f /etc/arch-release ] || command -v pacman >/dev/null 2>&1; then
            install_with_pacman
        else
            echo "Unsupported Linux distribution. Install tesseract manually:" >&2
            echo "  Debian/Ubuntu: sudo apt-get install tesseract-ocr" >&2
            echo "  Fedora/RHEL:     sudo dnf install tesseract" >&2
            echo "  Arch:            sudo pacman -S tesseract" >&2
            exit 1
        fi
        ;;
    *)
        echo "Unsupported OS: ${os}. Install tesseract manually." >&2
        exit 1
        ;;
esac

echo "Tesseract installed: $(tesseract --version 2>&1 | head -1)"
