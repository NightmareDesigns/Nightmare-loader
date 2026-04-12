# Makefile – Nightmare Loader development tasks
#
# Targets:
#   make install        Install the package + dev dependencies
#   make test           Run the full pytest suite
#   make lint           Check shell scripts for syntax errors
#   make build-iso      Build the live ISO via Docker (no host root required)
#   make run-iso        Boot the live ISO in QEMU (headless smoke-test)
#   make checksum       Generate SHA256 checksum for the built ISO
#   make clean          Remove build artefacts
#   make help           Show this message

.PHONY: install test lint build-iso run-iso checksum clean help

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ISO_NAME  ?= nightmare-loader-live.iso
DOCKER_IMAGE := nightmare-iso-builder
RAM_MB    ?= 1024

# ---------------------------------------------------------------------------
# Development
# ---------------------------------------------------------------------------

install:
	pip install -e ".[dev]"

test:
	python -m pytest tests/ -v --tb=short --cov=nightmare_loader --cov-report=term-missing

# ---------------------------------------------------------------------------
# ISO build scripts lint (fast, no actual build)
# ---------------------------------------------------------------------------

lint:
	@echo "→ Checking bash syntax: build_iso.sh"
	@bash -n build_iso.sh && echo "  ✓  build_iso.sh"
	@echo "→ Checking bash syntax: run_iso.sh"
	@bash -n run_iso.sh && echo "  ✓  run_iso.sh"
	@echo "→ Checking bash syntax: iso_root scripts"
	@for f in iso_root/usr/local/bin/*.sh iso_root/root/.xinitrc iso_root/root/.bash_profile; do \
		[ -f "$$f" ] || continue; \
		bash -n "$$f" && echo "  ✓  $$f"; \
	done
	@echo "All syntax checks passed."

# ---------------------------------------------------------------------------
# ISO build (Docker – no host root required)
# ---------------------------------------------------------------------------

build-iso:
	docker build -t $(DOCKER_IMAGE) -f Dockerfile.iso-builder .
	docker run --rm --privileged \
		-v "$(CURDIR)":/out \
		$(DOCKER_IMAGE) \
		./build_iso.sh --output "/out/$(ISO_NAME)"
	@echo "ISO written to: $(CURDIR)/$(ISO_NAME)"

# ---------------------------------------------------------------------------
# Checksum
# ---------------------------------------------------------------------------

checksum: $(ISO_NAME)
	sha256sum "$(ISO_NAME)" > "$(ISO_NAME).sha256"
	@echo "Checksum written to: $(ISO_NAME).sha256"
	@cat "$(ISO_NAME).sha256"

$(ISO_NAME):
	$(MAKE) build-iso

# ---------------------------------------------------------------------------
# Run / smoke-test
# ---------------------------------------------------------------------------

run-iso: $(ISO_NAME)
	chmod +x run_iso.sh
	./run_iso.sh --iso "$(ISO_NAME)" --ram $(RAM_MB)

smoke-test: $(ISO_NAME)
	chmod +x run_iso.sh
	./run_iso.sh \
		--iso "$(ISO_NAME)" \
		--headless \
		--wait-boot \
		--serial-log /tmp/nightmare-boot.log \
		--no-kvm \
		--ram $(RAM_MB)

# ---------------------------------------------------------------------------
# Clean
# ---------------------------------------------------------------------------

clean:
	rm -f "$(ISO_NAME)" "$(ISO_NAME).sha256"
	rm -rf dist/ build/ *.egg-info .pytest_cache/ htmlcov/ .coverage

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

help:
	@echo ""
	@echo "Nightmare Loader – development targets"
	@echo ""
	@echo "  make install     Install package + dev dependencies"
	@echo "  make test        Run the full pytest suite"
	@echo "  make lint        Validate ISO build scripts (bash syntax)"
	@echo "  make build-iso   Build live ISO via Docker  [ISO_NAME=...] [default: $(ISO_NAME)]"
	@echo "  make run-iso     Boot live ISO in QEMU      [ISO_NAME=...] [RAM_MB=...]"
	@echo "  make smoke-test  Headless QEMU boot test    [ISO_NAME=...] [RAM_MB=...]"
	@echo "  make checksum    Generate SHA256 checksum for the ISO"
	@echo "  make clean       Remove build artefacts"
	@echo ""
