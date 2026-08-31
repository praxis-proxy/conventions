# syntax=docker/dockerfile:1

# ------------------------------------------------------------------------------
# Stage 1: Build
# ------------------------------------------------------------------------------

FROM rust:1.96-alpine AS builder

RUN apk add --no-cache musl-dev

WORKDIR /src

# ------------------------------------------------------------------------------
# Cache Build
# ------------------------------------------------------------------------------

# Cache dependency builds: copy only manifests first, then
# create stub source files so `cargo build` resolves and
# compiles all dependencies without the real source code.
# See: https://shaneutt.com/blog/rust-fast-small-docker-image-builds/

COPY Cargo.toml Cargo.lock ./
COPY crates/conventions-probe/Cargo.toml crates/conventions-probe/Cargo.toml

RUN mkdir -p crates/conventions-probe/src \
    && echo '//! stub' > crates/conventions-probe/src/lib.rs \
    && printf '//! stub\nfn main() {}\n' > crates/conventions-probe/src/main.rs

RUN --mount=type=cache,target=/usr/local/cargo/registry \
    --mount=type=cache,target=/src/target \
    cargo build --release -p conventions-probe

# ------------------------------------------------------------------------------
# Cache Tricks
# ------------------------------------------------------------------------------

# Replace stubs with real source, then rebuild. Only the
# project crates recompile; all dependencies are cached.

COPY crates/conventions-probe/src crates/conventions-probe/src

# Touch the source files so cargo sees them as newer than
# the cached stub artifacts.
RUN find crates -name '*.rs' -exec touch {} +

# ------------------------------------------------------------------------------
# Build
# ------------------------------------------------------------------------------

RUN --mount=type=cache,target=/usr/local/cargo/registry \
    --mount=type=cache,target=/src/target \
    cargo build --release -p conventions-probe \
    && cp target/release/conventions-probe /usr/local/bin/conventions-probe

# ------------------------------------------------------------------------------
# Stage 2: Runtime
# ------------------------------------------------------------------------------

FROM alpine:3.24

LABEL org.opencontainers.image.source="https://github.com/praxis-proxy/conventions" \
    org.opencontainers.image.description="Conventions probe binary" \
    org.opencontainers.image.licenses="Apache-2.0"

RUN apk add --no-cache ca-certificates \
    && addgroup -S probe \
    && adduser -S -G probe -h /nonexistent -s /sbin/nologin probe

COPY --from=builder --chown=root:root --chmod=0555 \
    /usr/local/bin/conventions-probe /usr/local/bin/conventions-probe

USER probe:probe

# When scaffolding a long-running service, add EXPOSE and a HEALTHCHECK
# here and update the container workflow to wait for healthy status.

ENTRYPOINT ["conventions-probe"]
