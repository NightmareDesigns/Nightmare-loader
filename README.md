# Nightmare Loader

**Multi-ISO bootable USB creator – supports UEFI and legacy BIOS.**

Nightmare Loader lets you put as many bootable ISO images as you like onto a
single USB stick (or any other block device) and presents them in a clean GRUB2
menu at boot time.  The same drive boots on any PC regardless of whether it uses
modern UEFI firmware or an older legacy BIOS.

---

## Features

* **Multiple ISOs** – add, remove, and list as many ISO images as your drive
  will hold.
* **UEFI + Legacy BIOS** – GRUB2 is installed for both boot modes from a single
  command.
* **Auto-detection** – Nightmare Loader inspects the ISO's internal layout and
  automatically generates the correct GRUB menu entry for Ubuntu, Debian,
  Fedora, Arch Linux, Manjaro, Kali Linux, openSUSE, Tails, Linux Mint, Windows
  PE, and many other distributions.
* **Simple CLI** – one binary, six subcommands.

---

## Requirements

| Requirement          | Notes                                              |
|----------------------|----------------------------------------------------|
| Linux host           | Required for drive management                      |
| Python ≥ 3.9         |                                                    |
| `grub-install`       | Usually from the `grub2-common` / `grub-pc` package |
| `parted`             | For partitioning                                   |
| `dosfstools`         | For `mkfs.fat`                                     |
| `genisoimage`        | Optional – for accurate ISO file listing (`isoinfo`) |

Install system dependencies on Debian/Ubuntu:
```bash
sudo apt install grub2-common grub-pc-bin grub-efi-amd64-bin parted dosfstools genisoimage
```

---

## Installation

```bash
pip install nightmare-loader
```

Or install directly from source:
```bash
git clone https://github.com/NightmareDesigns/Nightmare-loader.git
cd Nightmare-loader
pip install .
```

---

## Quick Start

### 1 – Find your USB drive

```bash
nightmare-loader drives
# Removable drives:
#   /dev/sdb  SanDisk Ultra  (14.9 GB, usb)
```

### 2 – Prepare the drive  ⚠️ erases all data ⚠️

```bash
sudo nightmare-loader prepare /dev/sdb
```

This will:
1. Create a partition table (MBR by default; use `--layout gpt` for GPT).
2. Format the partition as FAT32 with the label `NIGHTMARE`.
3. Install GRUB2 for **both legacy BIOS and UEFI**.

### 3 – Add ISOs

```bash
sudo nightmare-loader add /dev/sdb ~/Downloads/ubuntu-22.04.iso
sudo nightmare-loader add /dev/sdb ~/Downloads/archlinux-2024.01.01-x86_64.iso
sudo nightmare-loader add /dev/sdb ~/Downloads/Win11_22H2.iso
```

Nightmare Loader copies each ISO into the `/isos` directory on the drive and
updates `grub.cfg` automatically.

### 4 – Boot!

Plug the drive into any PC, select it in the BIOS boot menu, and choose an OS
from the Nightmare Loader menu.

---

## CLI Reference

```
nightmare-loader COMMAND [OPTIONS] [ARGS]

Commands:
  prepare  Partition, format, and install GRUB on a drive
  add      Add an ISO to the drive
  remove   Remove an ISO from the drive
  list     List all registered ISOs on a drive
  update   Re-generate grub.cfg from stored state
  drives   List removable drives on this machine
  info     Show detected distro info for an ISO (no drive needed)
```

### `prepare`

```
sudo nightmare-loader prepare DEVICE [--layout hybrid|gpt] [--label NAME] [--yes]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--layout` | `hybrid` | `hybrid`: single FAT32 partition (works everywhere); `gpt`: separate ESP + data partition |
| `--label` | `NIGHTMARE` | Volume label (max 11 characters) |
| `--yes` / `-y` | off | Skip confirmation prompt |

### `add`

```
sudo nightmare-loader add DEVICE ISO_PATH [--label TEXT] [--no-copy]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--label` | auto | Custom menu label for this entry |
| `--no-copy` | off | Don't copy the file – useful if you've already placed the ISO on the drive manually |

### `remove`

```
sudo nightmare-loader remove DEVICE ISO_NAME [--keep-file]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--keep-file` | off | Remove the menu entry but keep the ISO file on the drive |

### `list`

```
nightmare-loader list DEVICE
```

### `update`

```
sudo nightmare-loader update DEVICE
```

Re-writes `grub.cfg` from the stored state.  Useful after upgrading
Nightmare Loader or if `grub.cfg` was accidentally deleted.

### `info`

```
nightmare-loader info ISO_PATH
```

Prints the detected distro, kernel/initrd paths, and boot command line for an
ISO without touching any drive.

---

## Supported Distributions

| Distribution | Detection method |
|---|---|
| Ubuntu / Ubuntu flavours | `casper/vmlinuz` + `casper/initrd` |
| Linux Mint | `casper/vmlinuz` + `casper/initrd.lz` |
| Debian Live | `live/vmlinuz` + `live/initrd.img` |
| Kali Linux | `live/vmlinuz` + `live/filesystem.squashfs` |
| Tails | `live/vmlinuz` + `live/Tails.module` |
| Fedora / RHEL / CentOS | `isolinux/vmlinuz` + `LiveOS/squashfs.img` |
| Arch Linux | `arch/boot/x86_64/vmlinuz-linux` |
| Manjaro | `manjaro/boot/vmlinuz-x86_64` |
| openSUSE | `boot/x86_64/loader/linux` |
| Windows PE / Setup | `sources/boot.wim` + `bootmgr` (uses wimboot) |
| Generic Linux | Fallback for any other ISO |

---

## How It Works

Nightmare Loader uses **GRUB2's `loopback` command** to mount each ISO image as
a virtual CD-ROM at boot time.  The kernel and initrd are loaded directly from
inside the mounted ISO, so there is no need to extract the ISO contents.

```
menuentry "Ubuntu 22.04" {
    set isofile="/isos/ubuntu-22.04.iso"
    loopback loop "$isofile"
    linux  (loop)/casper/vmlinuz boot=casper iso-scan/filename=$isofile quiet splash ---
    initrd (loop)/casper/initrd
}
```

GRUB is installed twice:
* **Legacy BIOS** – via `grub-install --target=i386-pc` into the MBR.
* **UEFI** – via `grub-install --target=x86_64-efi --removable` into
  `EFI/BOOT/BOOTX64.EFI`.

---

## Android / Termux

Nightmare Loader runs on Android via [Termux](https://termux.dev/) (install
from **F-Droid** or GitHub Releases, **not** the outdated Play Store version).

Run the one-shot setup script to install all dependencies:

```bash
bash setup_android.sh
```

### Without root (any Android device)

These commands work on **any** Android device, no root required:

| Command | Description |
|---------|-------------|
| `nightmare-loader info my.iso` | Inspect an ISO file |
| `nightmare-loader drives` | Detect connected USB drives |
| `nightmare-loader ui` | Start the web UI (open the printed URL in your browser) |

**Managing ISOs on a drive that Android has already mounted** (USB OTG):

When Android mounts a USB drive via OTG it becomes accessible at a path like
`/storage/XXXX-XXXX`.  Pass `--mount-point` to use that path directly — no
root needed:

```bash
# List ISOs on a drive mounted by Android at /storage/ABCD-1234
nightmare-loader list   /dev/sda --mount-point /storage/ABCD-1234

# Add an ISO
nightmare-loader add    /dev/sda ~/Downloads/ubuntu.iso --mount-point /storage/ABCD-1234

# Remove an ISO
nightmare-loader remove /dev/sda ubuntu.iso --mount-point /storage/ABCD-1234

# Re-generate grub.cfg
nightmare-loader update /dev/sda --mount-point /storage/ABCD-1234
```

> **Note**: The drive must have been prepared already (partitioned, formatted,
> and GRUB installed).  Use a Linux PC or a rooted Android device for the
> initial `prepare` step.

### With root (rooted device)

Install `tsu` (the Termux root helper) and prefix commands with `tsu -c`:

```bash
pkg install tsu

# Prepare a drive (wipes data!)
tsu -c 'nightmare-loader prepare /dev/sda'

# Add an ISO (tsu handles mounting automatically)
tsu -c 'nightmare-loader add /dev/sda ubuntu.iso'
```

### Termux:Widget home-screen shortcut

Install **Termux:Widget** from F-Droid, then run:

```bash
nightmare-loader install-launcher
```

Add the Termux:Widget to your Android home screen and tap **nightmare-loader**
to launch the web UI.

---

## Bootable Live ISO (use from your phone)

Nightmare Loader can be built into a **hybrid BIOS + UEFI bootable live ISO**.
Store the ISO on your phone and use it to create multi-ISO USB drives on any
PC — no Linux installation required on the target machine.

The ISO boots with the same **Nightmare Loader themed preloader** (dark matrix
splash, red title, green menu) that appears on every USB drive prepared by
Nightmare Loader, then drops into a root shell showing the quick-start banner.

### Building the ISO

#### Option A – native Linux host (requires root)

```bash
# Install build tools (Debian/Ubuntu)
sudo apt install debootstrap squashfs-tools grub-pc-bin grub-efi-amd64-bin xorriso mtools

# Build (takes ~5–10 minutes; root required for debootstrap/chroot)
sudo ./build_iso.sh

# Custom output path
sudo ./build_iso.sh --output ~/Downloads/nightmare-loader-live.iso
```

#### Option B – Docker (no root on the host)

```bash
docker build -t nightmare-iso-builder -f Dockerfile.iso-builder .
docker run --rm --privileged \
    -v "$(pwd)":/out \
    nightmare-iso-builder
# → nightmare-loader-live.iso appears in the current directory
```

`--privileged` is required because the build runs `debootstrap` + `chroot`
inside the container.

### Using the ISO from your Android phone

| Method | Root required? | How |
|--------|---------------|-----|
| **EtchDroid** | No | Copy the ISO to your phone. Plug in a USB drive via OTG. Open EtchDroid, select the ISO, select the USB drive, write. Boot the PC from the written USB drive. |
| **DriveDroid** | Yes (device) | Copy the ISO to your phone. Add it in DriveDroid as a CD-ROM image. Connect the phone to the PC via USB. The PC boots from the phone directly — no USB drive needed. |

### What the live environment provides

* Full `nightmare-loader` CLI and web UI (`nightmare-loader ui`)
* All runtime dependencies: `grub-install`, `parted`, `mkfs.fat`, `genisoimage`
* Auto-login as root on `tty1` — no password prompt
* Welcome banner with the quick-start workflow printed on every login

### File layout

```
build_iso.sh               Main build script
Dockerfile.iso-builder     Docker build environment
iso_root/                  Overlay applied on top of the live rootfs
  etc/systemd/system/
    getty@tty1.service.d/
      autologin.conf       Auto-login as root on tty1
  usr/local/bin/
    nightmare-welcome.sh   Welcome banner shown on login
  root/
    .bash_profile          Sources nightmare-welcome.sh on login
```

---


```bash
git clone https://github.com/NightmareDesigns/Nightmare-loader.git
cd Nightmare-loader
pip install -e ".[dev]"
pytest
```

---

## License

See [LICENSE](LICENSE).
