//! Probe binary that proves the workspace configuration compiles, lints, and
//! links its dependencies. Entrypoints stay thin: all logic lives in the
//! library where it is testable and counted by coverage.

use conventions_probe::{GREETING, saturating_total};

/// Emits a startup trace so the binary has observable behavior without
/// printing to stdout.
fn main() {
    let total = saturating_total(1, 2);

    tracing::info!(greeting = GREETING, total, "conventions probe startup");
}
