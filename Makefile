# -------------------------------------------------------------------
# Configuration
# -------------------------------------------------------------------

CONTAINER_ENGINE ?= $(shell command -v podman 2>/dev/null || command -v docker 2>/dev/null)
NIGHTLY          ?= nightly
V                ?=

# Crates verified by publish-dry-run, in dependency order.
# Replace with the real crate list when scaffolding a project.
PUBLISH_CRATES   := conventions-probe

# Tools verified by check-prereqs before their consuming targets run.
LINT_CMDS        := cargo cargo-machete typos taplo shellcheck actionlint
AUDIT_CMDS       := cargo-audit cargo-deny
KIND_CLUSTER_NAME ?= praxis-dev
PROJECT_IMAGE    ?= project:dev
KUBECTL          ?= kubectl --context kind-$(KIND_CLUSTER_NAME)

ifneq ($(V),)
  _NOCAPTURE := -- --nocapture
endif

.PHONY: all build release check clean \
	test mutants lint lint-extra fmt doc audit semver publish-dry-run \
	coverage coverage-check \
	check-prereqs check-prereqs-audit check-prereqs-nightly \
	require-container-engine \
	images container kind-up kind-down \
	dev-env dev-push dev-integration \
	setup-hooks \
	help

# -------------------------------------------------------------------
# All
# -------------------------------------------------------------------

all: build fmt lint test audit

# -------------------------------------------------------------------
# Build
# -------------------------------------------------------------------

build:
	cargo build --workspace

release:
	cargo build --workspace --release

check:
	cargo check --workspace

clean:
	cargo clean

# -------------------------------------------------------------------
# Test
# -------------------------------------------------------------------

test:
	cargo test --workspace $(_NOCAPTURE)

mutants:
	cargo mutants --workspace

# -------------------------------------------------------------------
# Prerequisites
# -------------------------------------------------------------------

check-prereqs:
	@for cmd in $(LINT_CMDS); do \
		command -v "$$cmd" >/dev/null 2>&1 || { \
			echo "\"$$cmd\" is not installed — install it before running make (see docs/development.md)" >&2; \
			exit 1; \
		}; \
	done

check-prereqs-audit:
	@for cmd in $(AUDIT_CMDS); do \
		command -v "$$cmd" >/dev/null 2>&1 || { \
			echo "\"$$cmd\" is not installed — install it before running make (see docs/development.md)" >&2; \
			exit 1; \
		}; \
	done

check-prereqs-nightly:
	@cargo +$(NIGHTLY) fmt --version >/dev/null 2>&1 || { \
		echo "nightly rustfmt is not installed — run \"rustup toolchain install $(NIGHTLY) --component rustfmt\" (see docs/development.md)" >&2; \
		exit 1; \
	}

# -------------------------------------------------------------------
# Quality
# -------------------------------------------------------------------

lint: check-prereqs check-prereqs-nightly lint-extra
	cargo clippy --workspace --all-targets -- -D warnings
	cargo +$(NIGHTLY) fmt --all -- --check
	cargo machete

lint-extra:
	typos
	taplo fmt --check
	shellcheck hack/*.sh .hooks/pre-commit
	actionlint

fmt: check-prereqs-nightly
	cargo +$(NIGHTLY) fmt --all

doc:
	RUSTDOCFLAGS="-D warnings" cargo doc --workspace --no-deps --document-private-items

audit: check-prereqs-audit
	cargo audit
	cargo deny check

coverage:
	cargo llvm-cov --workspace --html --output-dir target/coverage \
		--ignore-filename-regex 'src/main\.rs' \
		--fail-under-lines 90 \
		--fail-under-regions 80

coverage-check:
	cargo llvm-cov --workspace \
		--ignore-filename-regex 'src/main\.rs' \
		--fail-under-lines 90 \
		--fail-under-regions 80

semver:
	cargo semver-checks

# Full packaging verification for every release crate. The final step
# builds the packaged sources exactly as `cargo publish` would; switch it
# to `cargo publish -p <crate> --dry-run` once crates are publishable.
publish-dry-run:
	@for crate in $(PUBLISH_CRATES); do \
		printf "packaging %-25s " "$$crate"; \
		cargo package -p "$$crate" --list > /dev/null 2>&1 \
			&& echo "ok" \
			|| { echo "FAILED"; exit 1; }; \
	done
	cargo package -p $(firstword $(PUBLISH_CRATES))

# -------------------------------------------------------------------
# Container
# -------------------------------------------------------------------

require-container-engine:
ifndef CONTAINER_ENGINE
	$(error No container engine found. Install podman or docker)
endif

container: | require-container-engine
	$(CONTAINER_ENGINE) build -t $(PROJECT_IMAGE) -f Containerfile .

images: | require-container-engine
	$(CONTAINER_ENGINE) build -t $(PROJECT_IMAGE) -f Containerfile .

# -------------------------------------------------------------------
# KIND
# -------------------------------------------------------------------

kind-up: images
	KIND_CLUSTER_NAME=$(KIND_CLUSTER_NAME) \
	bash hack/setup-kind.sh

kind-down:
	KIND_CLUSTER_NAME=$(KIND_CLUSTER_NAME) \
	bash hack/teardown-kind.sh

# -------------------------------------------------------------------
# Iterative Development
# -------------------------------------------------------------------

dev-env: images
	KIND_CLUSTER_NAME=$(KIND_CLUSTER_NAME) \
	bash hack/setup-kind.sh

dev-push: | require-container-engine
	$(CONTAINER_ENGINE) build -t $(PROJECT_IMAGE) -f Containerfile .
	kind load docker-image $(PROJECT_IMAGE) --name $(KIND_CLUSTER_NAME)

dev-integration:
	@kind get kubeconfig --name $(KIND_CLUSTER_NAME) > /tmp/kind-$(KIND_CLUSTER_NAME).kubeconfig
	KUBECONFIG=/tmp/kind-$(KIND_CLUSTER_NAME).kubeconfig \
	cargo test --features integration -- --ignored $(if $(V),--nocapture,)

# -------------------------------------------------------------------
# Dev Setup
# -------------------------------------------------------------------

setup-hooks:
	@ln -sf ../../.hooks/pre-commit .git/hooks/pre-commit
	@echo "Git hooks installed"

# -------------------------------------------------------------------
# Help
# -------------------------------------------------------------------

help:
	@echo "Variables:"
	@echo "  V=1                show test output (--nocapture)"
	@echo "  NIGHTLY            nightly toolchain name for rustfmt"
	@echo "  CONTAINER_ENGINE   container runtime (auto-detected)"
	@echo "  KIND_CLUSTER_NAME  KIND cluster name"
	@echo "  PROJECT_IMAGE      container image tag"
	@echo ""
	@echo "Top-level:"
	@echo "  all              build + lint + test + audit"
	@echo ""
	@echo "Build:"
	@echo "  build            cargo build --workspace"
	@echo "  release          cargo build --workspace --release"
	@echo "  check            cargo check --workspace"
	@echo "  clean            cargo clean"
	@echo ""
	@echo "Test:"
	@echo "  test             run all tests"
	@echo "  mutants          mutation testing (cargo-mutants)"
	@echo ""
	@echo "Quality:"
	@echo "  lint             clippy + rustfmt check + machete + lint-extra"
	@echo "  lint-extra       typos + taplo + shellcheck + actionlint"
	@echo "  fmt              format with nightly rustfmt"
	@echo "  doc              build docs with warnings denied"
	@echo "  audit            cargo audit + cargo deny"
	@echo "  semver           cargo semver-checks"
	@echo "  publish-dry-run  package + verify release crates"
	@echo "  coverage         HTML coverage report"
	@echo "  coverage-check   fail if lines < 90%% or regions < 80%%"
	@echo ""
	@echo "Container:"
	@echo "  container        build container image"
	@echo "  images           build container image"
	@echo ""
	@echo "KIND:"
	@echo "  kind-up          create cluster + deploy"
	@echo "  kind-down        delete cluster"
	@echo ""
	@echo "Dev Setup:"
	@echo "  setup-hooks      install git pre-commit hook"
	@echo ""
	@echo "Development:"
	@echo "  dev-env          create/reuse persistent cluster"
	@echo "  dev-push         build + load + rollout"
	@echo "  dev-integration  run integration tests"
