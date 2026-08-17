//! Probe library that verifies the workspace toolchain, lint, and security
//! configuration against a real compilation unit.
//!
//! This crate exists so the template's quality gates have something to chew
//! on: `make lint`, `make test`, `make doc`, `make audit`, and
//! `make coverage-check` all exercise it. Replace it with real crates when
//! scaffolding a project.

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/// Greeting emitted by the probe binary at startup.
pub const GREETING: &str = "conventions probe";

/// Adds two byte counts, saturating at `usize::MAX`.
///
/// # Examples
///
/// ```
/// assert_eq!(conventions_probe::saturating_total(2, 3), 5);
/// ```
#[must_use]
pub fn saturating_total(lhs: usize, rhs: usize) -> usize {
    lhs.saturating_add(rhs)
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::saturating_total;

    #[test]
    fn total_adds_small_values() {
        assert_eq!(saturating_total(2, 3), 5, "small sums must add exactly");
    }

    #[test]
    fn total_saturates_at_bounds() {
        assert_eq!(
            saturating_total(usize::MAX, 1),
            usize::MAX,
            "overflow must saturate at usize::MAX"
        );
    }
}
