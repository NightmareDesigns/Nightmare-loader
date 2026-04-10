# Nightmare Loader

**Multi-ISO bootable USB creator – UEFI · Legacy BIOS · Windows PE · Android/Termux · Web UI**

[![Tests](https://img.shields.io/badge/tests-203%20passed-brightgreen)]()
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)]()
[![License](https://img.shields.io/badge/license-MIT-red)]()
[![Version](https://img.shields.io/badge/version-1.1.0-crimson)]()

Nightmare Loader lets you put as many bootable images as you like onto a single USB stick
and presents them in a clean, themed GRUB2 menu at boot time.
Drive any PC regardless of whether it uses modern UEFI firmware or older legacy BIOS.

---

## Features

| Feature | Details |
|---|---|
| **Multiple images** | Add, remove, and list as many bootable images as the drive will hold |
| **UEFI + Legacy BIOS** | Single `prepare` command installs GRUB2 for both boot modes |
| **All major formats** | Upload or register `.iso` `.img` `.wim` `.vhd` `.vhdx` `.vmdk` `.vdi` `.raw` |
| **Auto-detection** | Inspects each image's internal layout and generates the correct GRUB entry automatically |
| **Web UI** | Full graphical interface — no terminal needed for day-to-day use |
| **ISO downloader** | Download images directly from URLs inside the web UI, with progress tracking |
| **File upload** | Drag-and-drop upload any image format through the browser |
| **WiFi manager** | Connect to WiFi networks from inside the web UI |
| **Auto-update** | One-click update to the latest release from within the web UI |
| **Gemini AI** | Built-in Gemini 2.5 AI assistant for troubleshooting and guidance |
| **Windows PE** | Boot Windows PE / Windows Setup ISOs via wimboot (auto-installed) |
| **Windows host** | Full support for managing drives from Windows |
| **Android / Termux** | Run on Android via Termux — manage drives over USB OTG |
| **Bootable live ISO** | Build a self-contained Nightmare Loader live ISO for use from any PC |

---

## Requirements

### Runtime

| Requirement | Notes |
|---|---|
| Python ≥ 3.9 | |
| `grub-install` | `grub2-common` / `grub-pc` package |
| `parted` | Partitioning |
| `dosfstools` | `mkfs.fat` |
| `genisoimage` | Optional — accurate ISO file listing via `isoinfo` |
| `p7zip` (`7z`) | Optional — UDF/hybrid ISO support (improves distro detection) |

Install system dependencies on Debian/Ubuntu:

```bash
sudo apt install grub2-common grub-pc-bin grub-efi-amd64-bin parted dosfstools genisoimage p7zip-full
```

### Python package

```bash
pip install nightmare-loader
```

Or install from source:

```bash
git clone https://github.com/NightmareDesigns/Nightmare-loader.git
cd Nightmare-loader
pip install .
```

---

## Quick Start

### 1 — Find your USB drive

```bash
nightmare-loader drives
# Removable drives:
#   /dev/sdb  SanDisk Ultra  (14.9 GB, usb)
```

### 2 — Prepare the drive ⚠️ erases all data ⚠️

```bash
sudo nightmare-loader prepare /dev/sdb
```

This creates a partition table, formats the partition as FAT32 (`NIGHTMARE` label), and installs GRUB2 for both legacy BIOS and UEFI.

### 3 — Add images

```bash
# ISO files
sudo nightmare-loader add /dev/sdb ~/Downloads/ubuntu-22.04.iso
sudo nightmare-loader add /dev/sdb ~/Downloads/archlinux-2024.iso

# Raw disk images, WIM, VHD, VMDK — same command
sudo nightmare-loader add /dev/sdb ~/Downloads/disk.img
```

### 4 — Or use the Web UI

```bash
nightmare-loader ui          # opens http://localhost:8321 in your browser
nightmare-loader ui --port 9000 --no-browser   # custom port, no auto-open
```

### 5 — Boot!

Plug the drive into any PC, select it in the BIOS boot menu, and choose an OS from the Nightmare Loader menu.

---

## Web UI

Start the web UI with `nightmare-loader ui`. The printed URL opens in your local browser automatically. The server also binds to all network interfaces, so you can open the same URL from any phone, tablet, or PC on the same network using the **Network access** address printed in the terminal.

The interface is a windowed desktop environment with a vertical dock on the left:

| Panel | Icon | Description |
|---|---|---|
| **Drive Manager** | 💀 | List all connected removable drives with size, model, and serial number |
| **Drive Forge** | ⚙️ | Partition, format, and install GRUB on a drive (hybrid or GPT layout) |
| **ISO Loader** | 📀 | Add a bootable image — by host path **or** by uploading a file from your machine |
| **ISO Vault** | 🗄️ | Browse and remove all registered images on a drive |
| **ISO Inspector** | 🔬 | Inspect any image file to see its detected distro, kernel, initrd, and boot cmdline |
| **Windows PE** | 🪟 | One-click shortcut for adding Windows PE / Windows Setup images |
| **Gemini AI** | 🤖 | Built-in Gemini 2.5 AI assistant for troubleshooting and guidance |
| **Operation Log** | 📟 | Live log of all operations performed in the current session |
| **WiFi Manager** | 📶 | Scan for WiFi networks and connect without leaving the UI |
| **ISO Downloader** | ⬇️ | Download images directly from URLs, with real-time progress |
| **File Manager** | 📁 | Browse the host filesystem and pick files for use in other panels |
| **Update** | 🔄 | Check for and install the latest Nightmare Loader release |

### Uploading image files

In the **ISO Loader** panel, switch to the **⬆ Upload File** tab to upload any supported image directly from your browser — no need to type a path:

1. Select **Target Device**
2. Click **⬆ Upload File** tab
3. Choose a file (`.iso` `.img` `.wim` `.vhd` `.vhdx` `.vmdk` `.vdi` `.raw`)
4. Optionally set a custom save directory and menu label
5. Click **⬆ Upload & Add** — progress bar updates in real time

---

## CLI Reference

```
nightmare-loader COMMAND [OPTIONS] [ARGS]

Commands:
  prepare          Partition, format, and install GRUB on a drive
  add              Add a bootable image to the drive
  remove           Remove an image from the drive
  list             List all registered images on a drive
  update           Re-generate grub.cfg from stored state
  drives           List removable drives on this machine
  info             Show detected distro info for an image (no drive needed)
  ui               Launch the web UI
  install-launcher Install a desktop / Start Menu / widget launcher
  build-iso        Build the bootable Nightmare Loader live ISO
```

### `prepare`

```
sudo nightmare-loader prepare DEVICE [--layout hybrid|gpt] [--label NAME] [--yes]
```

| Option | Default | Description |
|---|---|---|
| `--layout` | `hybrid` | `hybrid`: single FAT32 partition (works everywhere); `gpt`: separate ESP + data partition |
| `--label` | `NIGHTMARE` | Volume label (max 11 characters) |
| `--yes` / `-y` | off | Skip confirmation prompt |

### `add`

```
sudo nightmare-loader add DEVICE IMAGE_PATH [--label TEXT] [--no-copy]
```

| Option | Default | Description |
|---|---|---|
| `--label` | auto | Custom boot menu label |
| `--no-copy` | off | Register only — don't copy the file (useful if already placed manually) |

### `remove`

```
sudo nightmare-loader remove DEVICE IMAGE_NAME [--keep-file]
```

| Option | Default | Description |
|---|---|---|
| `--keep-file` | off | Remove the menu entry but keep the file on the drive |

### `list`

```
nightmare-loader list DEVICE
```

### `update`

```
sudo nightmare-loader update DEVICE
```

Re-writes `grub.cfg` from stored state. Useful after upgrading Nightmare Loader or if `grub.cfg` was accidentally deleted.

### `info`

```
nightmare-loader info IMAGE_PATH
```

Prints the detected distro, kernel/initrd paths, and boot command line for an image without touching any drive.

### `ui`

```
nightmare-loader ui [--port PORT] [--no-browser]
```

| Option | Default | Description |
|---|---|---|
| `--port` / `-p` | `8321` | TCP port for the web server |
| `--no-browser` | off | Don't open the browser automatically |

### `install-launcher`

```
nightmare-loader install-launcher [--desktop]
```

| Platform | What it installs |
|---|---|
| Linux | `.desktop` file in `~/.local/share/applications/` |
| Windows | `.lnk` shortcut in the Start Menu Programs folder |
| Android/Termux | Script in `~/.shortcuts/` for Termux:Widget |

### `build-iso`

```
nightmare-loader build-iso [--output PATH]
```

Builds the bootable Nightmare Loader live ISO. Supports three build paths automatically:

| Environment | Method |
|---|---|
| Native Linux | `debootstrap` + Debian rootfs + `grub-mkrescue` |
| Termux (rooted Android) | Alpine x86_64 + QEMU binfmt_misc + `grub-mkrescue` inside chroot |
| Docker | `Dockerfile.iso-builder` — no root on the host machine required |

---

## Supported Image Formats

| Format | Extension(s) | Notes |
|---|---|---|
| ISO 9660 disc image | `.iso` | The standard format for Linux and Windows installers |
| Raw disk image | `.img` `.raw` | Sector-for-sector disk dumps |
| Windows Imaging Format | `.wim` | Windows PE / Windows Setup source files |
| Virtual Hard Disk | `.vhd` `.vhdx` | Hyper-V / Azure disk images |
| VMware Virtual Disk | `.vmdk` | VMware Workstation / ESXi images |
| VirtualBox Disk Image | `.vdi` | VirtualBox native format |

---

## Supported Distributions (auto-detected)

| Distribution | Detection |
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
| Windows PE / Setup | `sources/boot.wim` + `bootmgr` (uses wimboot, auto-installed) |
| Generic Linux | Fallback for any other bootable ISO |

---

## How It Works

Nightmare Loader uses **GRUB2's `loopback` command** to mount each image as a virtual CD-ROM at boot time. The kernel and initrd are loaded directly from inside the mounted image — no extraction required.

```grub
menuentry "Ubuntu 22.04" {
    set isofile="/isos/ubuntu-22.04.iso"
    loopback loop "$isofile"
    linux  (loop)/casper/vmlinuz boot=casper iso-scan/filename=$isofile quiet splash ---
    initrd (loop)/casper/initrd
}
```

GRUB is installed for two targets:

* **Legacy BIOS** – `grub-install --target=i386-pc` into the MBR
* **UEFI** – `grub-install --target=x86_64-efi --removable` → `EFI/BOOT/BOOTX64.EFI`

State is tracked in a `.nightmare-loader.json` file at the root of the USB drive, so `grub.cfg` can always be regenerated from scratch with `nightmare-loader update`.

---

## Windows

Nightmare Loader runs natively on Windows 8+.

* Drive listing uses PowerShell `Get-Disk BusType=USB` (with WMI fallback for Windows 7/8)
* UAC elevation is requested automatically via `ctypes.ShellExecuteW`
* The `install-launcher` command creates a Start Menu shortcut (`.lnk`)
* A pre-built `.exe` is available for download — no Python required

```bat
# Run as Administrator in cmd.exe or PowerShell:
nightmare-loader prepare I:\
nightmare-loader add I:\ C:\Downloads\ubuntu-22.04.iso
```

---

## Android / Termux

Nightmare Loader runs on Android via [Termux](https://termux.dev/)
(install from **F-Droid** or GitHub Releases — **not** the outdated Play Store version).

Run the all-in-one setup script to install all dependencies in one pass:

```bash
bash setup_android.sh
```

### Without root — any Android device

| Command | Description |
|---|---|
| `nightmare-loader info my.iso` | Inspect an image file |
| `nightmare-loader drives` | Detect connected USB drives |
| `nightmare-loader ui` | Start the web UI (open the printed URL in your browser) |

**Managing a drive Android has already mounted** (USB OTG):

```bash
# List images on a drive mounted by Android at /storage/ABCD-1234
nightmare-loader list   /dev/sda --mount-point /storage/ABCD-1234

# Add an image
nightmare-loader add    /dev/sda ~/Downloads/ubuntu.iso --mount-point /storage/ABCD-1234

# Remove an image
nightmare-loader remove /dev/sda ubuntu.iso --mount-point /storage/ABCD-1234

# Re-generate grub.cfg
nightmare-loader update /dev/sda --mount-point /storage/ABCD-1234
```

### With root — rooted device

```bash
# Prepare a drive (wipes data!)
tsu bash -c 'nightmare-loader prepare /dev/sda'

# Add an image
tsu bash -c 'nightmare-loader add /dev/sda ubuntu.iso'
```

### Termux:Widget home-screen shortcut

Install **Termux:Widget** from F-Droid, then:

```bash
nightmare-loader install-launcher
```

Add the Termux:Widget to your home screen and tap **nightmare-loader** to launch the web UI.

---

## Bootable Live ISO

Nightmare Loader can be built into a **hybrid BIOS + UEFI bootable live ISO** — boot it on any x86-64 PC to get a full Nightmare Loader environment with no installation required.

### Option A — Native Linux (requires root)

```bash
sudo apt install debootstrap squashfs-tools grub-pc-bin grub-efi-amd64-bin xorriso mtools
sudo ./build_iso.sh
# Custom output path:
sudo ./build_iso.sh --output ~/Downloads/nightmare-loader-live.iso
```

Or via the CLI (from the repo checkout):

```bash
nightmare-loader build-iso
nightmare-loader build-iso --output ~/Downloads/nightmare-loader-live.iso
```

### Option B — Termux on rooted Android

```bash
bash setup_android.sh   # installs all build tools (skip if already done)
nightmare-loader build-iso --output /sdcard/nightmare-loader-live.iso
```

### Option C — Docker (no host root required)

```bash
docker build -t nightmare-iso-builder -f Dockerfile.iso-builder .
docker run --rm --privileged -v "$(pwd)":/out nightmare-iso-builder
# → nightmare-loader-live.iso appears in the current directory
```

### Using the ISO from Android

| Method | Root required? | How |
|---|---|---|
| **EtchDroid** | No | Copy ISO to phone → plug USB drive via OTG → open EtchDroid → write → boot PC |
| **DriveDroid** | Yes | Add ISO in DriveDroid as CD-ROM → connect phone to PC via USB → PC boots from phone |

### Live environment

* Full `nightmare-loader` CLI and web UI
* All runtime dependencies pre-installed (`grub-install`, `parted`, `mkfs.fat`, `genisoimage`)
* Auto-login as root on `tty1`
* Nightmare Loader branded splash + welcome banner on every login

---

## Development

```bash
git clone https://github.com/NightmareDesigns/Nightmare-loader.git
cd Nightmare-loader
pip install -e ".[dev]"
pytest
```

### Running tests

```bash
pytest                  # all 203 tests
pytest tests/test_server.py -v   # server / API tests only
```

---

## License

See [LICENSE](LICENSE).

