#!/usr/bin/env bash
# run_iso.sh
# Boot the Nightmare Loader live ISO in QEMU for local testing / development.
#
# Supports graphical window (default), VNC, and headless serial-console modes.
# KVM is used automatically when /dev/kvm is accessible.
# UEFI boot (OVMF) is optionally selectable via --uefi.
#
# Usage:
#   ./run_iso.sh [--iso PATH] [--uefi] [--bios] [--ram MB] [--cpus N]
#                [--headless] [--vnc] [--vnc-port PORT] [--no-kvm]
#
# Quick-start (build then run):
#   sudo ./build_iso.sh && ./run_iso.sh
#
# Docker build then run:
#   docker build -t nightmare-iso-builder -f Dockerfile.iso-builder .
#   docker run --rm --privileged -v "$(pwd)":/out nightmare-iso-builder
#   ./run_iso.sh

set -euo pipefail

# ── Colour helpers ────────────────────────────────────────────────────────────
BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
RESET='\033[0m'

info()  { echo -e "${GREEN}[INFO]${RESET}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
step()  { echo -e "\n${BOLD}── $* ──${RESET}"; }
die()   { echo -e "${RED}[ERROR]${RESET} $*" >&2; exit 1; }

# ── Defaults ──────────────────────────────────────────────────────────────────
ISO="$(pwd)/nightmare-loader-live.iso"
RAM=1024
CPUS=2
UEFI=0
HEADLESS=0
VNC=0
VNC_PORT=5900
FORCE_NO_KVM=0
SERIAL_LOG=""        # set to a path to also capture serial output to a file
BOOT_TIMEOUT=180     # seconds to wait in --wait-boot mode before declaring failure
WAIT_BOOT=0          # set via --wait-boot; watches serial for successful login prompt

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Boot the Nightmare Loader live ISO in QEMU.

Options:
  --iso PATH         Path to the ISO image  [default: ./nightmare-loader-live.iso]
  --ram MB           RAM to give the VM     [default: 1024]
  --cpus N           vCPU count             [default: 2]
  --uefi             Boot in UEFI mode (requires OVMF firmware)
  --bios             Boot in legacy BIOS mode (default)
  --no-kvm           Disable KVM even when /dev/kvm is available
  --headless         Run without a display window; serial console on stdout
                     Press Ctrl-A X to quit QEMU, Ctrl-A C for the monitor.
  --vnc              Expose display over VNC instead of opening a window
  --vnc-port PORT    VNC port                [default: 5900]
  --serial-log FILE  Append serial output to FILE (works with all display modes)
  --wait-boot        In headless mode, exit 0 when the login prompt appears,
                     exit 1 on timeout (${BOOT_TIMEOUT}s).  Useful in CI.
  -h, --help         Show this help

Examples:
  # Graphical window, BIOS, KVM
  ./run_iso.sh

  # UEFI graphical window
  ./run_iso.sh --uefi

  # Headless CI smoke-test (exits when boot is complete)
  ./run_iso.sh --headless --wait-boot --serial-log /tmp/boot.log

  # VNC session on port 5901
  ./run_iso.sh --vnc --vnc-port 5901
EOF
    exit 0
}

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --iso)          ISO="$2";        shift 2 ;;
        --ram)          RAM="$2";        shift 2 ;;
        --cpus)         CPUS="$2";       shift 2 ;;
        --uefi)         UEFI=1;          shift   ;;
        --bios)         UEFI=0;          shift   ;;
        --no-kvm)       FORCE_NO_KVM=1;  shift   ;;
        --headless)     HEADLESS=1;      shift   ;;
        --vnc)          VNC=1;           shift   ;;
        --vnc-port)     VNC_PORT="$2";   shift 2 ;;
        --serial-log)   SERIAL_LOG="$2"; shift 2 ;;
        --wait-boot)    WAIT_BOOT=1;     shift   ;;
        -h|--help)      usage ;;
        *) die "Unknown option: $1\n  Run  $(basename "$0") --help  for usage." ;;
    esac
done

# --wait-boot only makes sense in headless mode (we need to read serial output).
if [[ $WAIT_BOOT -eq 1 ]] && [[ $HEADLESS -eq 0 ]]; then
    warn "--wait-boot implies --headless; enabling headless mode."
    HEADLESS=1
fi

# ── Check ISO exists ──────────────────────────────────────────────────────────
[[ -f "$ISO" ]] || die "ISO not found: $ISO

  Build it first with one of:
    sudo ./build_iso.sh
    docker build -t nightmare-iso-builder -f Dockerfile.iso-builder . && \\
    docker run --rm --privileged -v \"\$(pwd)\":/out nightmare-iso-builder"

ISO="$(realpath "$ISO")"

# ── Locate QEMU ───────────────────────────────────────────────────────────────
QEMU_CMD=""
for _q in qemu-system-x86_64; do
    command -v "$_q" &>/dev/null && { QEMU_CMD="$_q"; break; }
done
[[ -n "$QEMU_CMD" ]] || die "qemu-system-x86_64 not found.

  Install with:
    Debian/Ubuntu : sudo apt-get install qemu-system-x86
    Fedora/RHEL   : sudo dnf install qemu-kvm
    Arch          : sudo pacman -S qemu-system-x86
    macOS         : brew install qemu"

# ── KVM acceleration ──────────────────────────────────────────────────────────
KVM_ARGS=()
if [[ $FORCE_NO_KVM -eq 0 ]] && [[ -r /dev/kvm ]]; then
    KVM_ARGS=(-enable-kvm -cpu host)
    KVM_LABEL="enabled"
else
    KVM_ARGS=(-cpu qemu64)
    if [[ $FORCE_NO_KVM -eq 0 ]]; then
        KVM_LABEL="not available (/dev/kvm unreadable) – emulation will be slower"
    else
        KVM_LABEL="disabled (--no-kvm)"
    fi
fi

# ── UEFI firmware (OVMF) ──────────────────────────────────────────────────────
OVMF_ARGS=()
if [[ $UEFI -eq 1 ]]; then
    OVMF_FW=""
    for _fw in \
        /usr/share/OVMF/OVMF_CODE.fd \
        /usr/share/ovmf/OVMF.fd \
        /usr/share/edk2/ovmf/OVMF_CODE.fd \
        /usr/share/qemu/ovmf-x86_64.bin \
        /opt/homebrew/share/qemu/edk2-x86_64-code.fd \
        /usr/share/qemu/edk2-x86_64-code.fd; do
        [[ -f "$_fw" ]] && { OVMF_FW="$_fw"; break; }
    done
    if [[ -n "$OVMF_FW" ]]; then
        OVMF_ARGS=(-drive "if=pflash,format=raw,readonly=on,file=${OVMF_FW}")
    else
        warn "OVMF firmware not found – falling back to BIOS mode."
        warn "  Install with:  sudo apt-get install ovmf   (Debian/Ubuntu)"
        warn "                 brew install ovmf            (macOS)"
        UEFI=0
    fi
fi

# ── Serial / display configuration ───────────────────────────────────────────
# serial: always add a serial port; output goes to file, stdio, or chardev.
SERIAL_ARGS=()
if [[ -n "$SERIAL_LOG" ]]; then
    # Always write serial to a file; also mirror to stdio when headless.
    SERIAL_ARGS=(-serial "file:${SERIAL_LOG}")
    if [[ $HEADLESS -eq 1 ]]; then
        # Two serial devices: first → log file, second → stdio monitor
        SERIAL_ARGS+=(-serial mon:stdio)
    fi
else
    if [[ $HEADLESS -eq 1 ]]; then
        SERIAL_ARGS=(-serial mon:stdio)
    else
        SERIAL_ARGS=(-serial null)
    fi
fi

DISPLAY_ARGS=()
if [[ $HEADLESS -eq 1 ]]; then
    # -display none hides the window; serial redirection is handled by SERIAL_ARGS.
    # Do NOT use -nographic here: it also tries to redirect serial to stdio which
    # conflicts with any explicit -serial options and causes QEMU 7+ to error.
    DISPLAY_ARGS=(-display none)
elif [[ $VNC -eq 1 ]]; then
    VNC_DISPLAY=$(( VNC_PORT - 5900 ))
    DISPLAY_ARGS=(-vga std -vnc ":${VNC_DISPLAY}")
else
    DISPLAY_ARGS=(-vga std)
fi

# ── Print summary ─────────────────────────────────────────────────────────────
step "Nightmare Loader ISO Runner"
info "ISO   : $ISO  ($(du -sh "$ISO" | cut -f1))"
info "QEMU  : $QEMU_CMD  ($("$QEMU_CMD" --version 2>&1 | head -1))"
info "KVM   : $KVM_LABEL"
info "RAM   : ${RAM} MB"
info "CPUs  : $CPUS"
if [[ $UEFI -eq 1 ]]; then
    info "Boot  : UEFI  ($OVMF_FW)"
else
    info "Boot  : BIOS (SeaBIOS)"
fi
if [[ $HEADLESS -eq 1 ]]; then
    info "Mode  : headless (serial console on stdio)"
    info "        Ctrl-A X = quit QEMU  |  Ctrl-A C = QEMU monitor"
elif [[ $VNC -eq 1 ]]; then
    info "Mode  : VNC  (connect to  localhost:${VNC_PORT})"
else
    info "Mode  : graphical window"
fi
[[ -n "$SERIAL_LOG" ]] && info "Serial log → $SERIAL_LOG"
echo

# ── If --wait-boot: run QEMU in background and tail the serial log ─────────
if [[ $WAIT_BOOT -eq 1 ]]; then
    [[ -n "$SERIAL_LOG" ]] || SERIAL_LOG="$(mktemp /tmp/nightmare-boot-XXXXXX.log)"

    # Rebuild serial args: file only (no stdio in a background process)
    SERIAL_ARGS=(-serial "file:${SERIAL_LOG}")
    # -display none disables the window; -nographic must NOT be used here
    # because QEMU 7+ rejects combining -nographic with an explicit -display flag.
    DISPLAY_ARGS=(-display none)

    info "Starting QEMU in background (PID will be shown below)…"
    info "Serial log : $SERIAL_LOG"
    info "Timeout    : ${BOOT_TIMEOUT}s"
    echo

    "$QEMU_CMD" \
        "${KVM_ARGS[@]}" \
        -m "$RAM" \
        -smp "$CPUS" \
        -cdrom "$ISO" \
        -boot d \
        "${OVMF_ARGS[@]+"${OVMF_ARGS[@]}"}" \
        "${SERIAL_ARGS[@]}" \
        "${DISPLAY_ARGS[@]}" \
        -netdev user,id=net0 \
        -device virtio-net-pci,netdev=net0 \
        -no-reboot &
    QEMU_PID=$!
    info "QEMU PID : $QEMU_PID"

    # Watch the serial log for the login prompt or the welcome banner
    FOUND=0
    ELAPSED=0
    while [[ $ELAPSED -lt $BOOT_TIMEOUT ]]; do
        sleep 2
        ELAPSED=$(( ELAPSED + 2 ))
        if [[ -f "$SERIAL_LOG" ]]; then
            # Detect successful boot via kernel/systemd messages on ttyS0.
            # "LIVE ENVIRONMENT" appears only on tty1/tty2 (not on ttyS0).
            # "Linux version" is printed by the kernel before any driver loads.
            # "nightmare-loader-live login:" appears when serial getty fires.
            # "Reached target" is a late-stage systemd milestone.
            if grep -qE "(Linux version|nightmare-loader-live login:|Reached target (Multi-User|Graphical))" "$SERIAL_LOG" 2>/dev/null; then
                FOUND=1
                break
            fi
        fi
        # Check if QEMU exited early (e.g. kernel panic)
        if ! kill -0 "$QEMU_PID" 2>/dev/null; then
            warn "QEMU process exited before boot completed."
            break
        fi
    done

    # Terminate QEMU
    kill "$QEMU_PID" 2>/dev/null || true
    wait "$QEMU_PID" 2>/dev/null || true

    echo
    if [[ $FOUND -eq 1 ]]; then
        echo -e "${GREEN}${BOLD}Boot smoke-test PASSED${RESET} (boot prompt detected in ${ELAPSED}s)"
        exit 0
    else
        echo -e "${RED}${BOLD}Boot smoke-test FAILED${RESET} (no prompt within ${BOOT_TIMEOUT}s)"
        echo
        echo "Last 30 lines of serial output ($SERIAL_LOG):"
        tail -30 "$SERIAL_LOG" 2>/dev/null || echo "(log is empty)"
        exit 1
    fi
fi

# ── Interactive / VNC / graphical run ─────────────────────────────────────────
echo -e "${CYAN}Starting QEMU… (close the window or press Ctrl-A X to stop)${RESET}"
echo

exec "$QEMU_CMD" \
    "${KVM_ARGS[@]}" \
    -m "$RAM" \
    -smp "$CPUS" \
    -cdrom "$ISO" \
    -boot d \
    "${OVMF_ARGS[@]+"${OVMF_ARGS[@]}"}" \
    "${SERIAL_ARGS[@]}" \
    "${DISPLAY_ARGS[@]}" \
    -netdev user,id=net0 \
    -device virtio-net-pci,netdev=net0 \
    -no-reboot
