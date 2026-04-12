# Changelog

All notable changes to this project are documented in this file.

## 2026-04-12

### Added

- Deterministic full-match server regression test covering challenge creation, pending counterable spell flow, advance and counter-advance, battle prep, three-round battle resolution, and checkmate game-over finalization.
- Client dialogue-flow contract tests for FIFO notification queue ordering, opponent-turn summary payload construction, and acknowledgement-driven progression to queued notifications.
- Explicit test-oracle documentation in advanced regression test classes so expected outcomes are clear and reviewable.

### Validation

- Local pytest suite: 155 passed.