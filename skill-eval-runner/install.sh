#!/bin/bash

# Installer for the run-evals command

set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_SCRIPT="$SCRIPT_DIR/run-evals.sh"
INSTALL_DIR="$HOME/.local/bin"
TARGET_SCRIPT="$INSTALL_DIR/run-evals"

echo -e "${BLUE}════════════════════════════════════════${NC}"
echo -e "${BLUE}  Run-Evals Installer${NC}"
echo -e "${BLUE}════════════════════════════════════════${NC}"
echo ""

if [ ! -f "$SOURCE_SCRIPT" ]; then
    echo -e "${RED}✗ Error: run-evals.sh not found at $SOURCE_SCRIPT${NC}"
    exit 1
fi

mkdir -p "$INSTALL_DIR"

if [ -f "$TARGET_SCRIPT" ] || [ -L "$TARGET_SCRIPT" ]; then
    echo -e "${YELLOW}run-evals is already installed at $TARGET_SCRIPT${NC}"
    read -p "Reinstall? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[YySs]$ ]]; then
        echo -e "${YELLOW}Installation cancelled.${NC}"
        exit 0
    fi
    rm -f "$TARGET_SCRIPT"
fi

chmod +x "$SOURCE_SCRIPT"
ln -sf "$SOURCE_SCRIPT" "$TARGET_SCRIPT" 2>/dev/null || true

# Without real symlinks (Git Bash on Windows copies the file instead), a copy would stay frozen at
# the version installed and miss every later fix. A launcher that runs the repo script stays current.
if [ ! -L "$TARGET_SCRIPT" ]; then
    rm -f "$TARGET_SCRIPT"
    printf '#!/usr/bin/env bash\n# run-evals launcher written by skill-eval-runner/install.sh: runs the repo script, never a copy.\nexec bash %q "$@"\n' "$SOURCE_SCRIPT" > "$TARGET_SCRIPT"
    chmod +x "$TARGET_SCRIPT"
fi

if [ -x "$TARGET_SCRIPT" ]; then
    if [ -L "$TARGET_SCRIPT" ]; then
        echo -e "${GREEN}✓ run-evals installed → $TARGET_SCRIPT (symlink to $SOURCE_SCRIPT)${NC}"
    else
        echo -e "${GREEN}✓ run-evals installed → $TARGET_SCRIPT (launcher for $SOURCE_SCRIPT)${NC}"
    fi
else
    echo -e "${RED}✗ Error during installation: $TARGET_SCRIPT is not executable${NC}"
    exit 1
fi

echo ""

if [[ ":$PATH:" != *":$INSTALL_DIR:"* ]]; then
    echo -e "${YELLOW}⚠ $INSTALL_DIR is not in your PATH${NC}"
    echo -e "  Add: ${GREEN}export PATH=\"\$HOME/.local/bin:\$PATH\"${NC}"
    echo ""
fi

echo -e "${BLUE}Usage:${NC}"
echo -e "  ${GREEN}run-evals${NC}                     Run evals for skill in current dir"
echo -e "  ${GREEN}run-evals path/to/skill${NC}       Run evals for a specific skill"
echo -e "  ${GREEN}run-evals --all${NC}               Run evals for all skills"
echo -e "  ${GREEN}run-evals --pretty${NC}            Human-readable colored report"
echo -e "  ${GREEN}run-evals --provider codex${NC}    Override provider"
echo ""
