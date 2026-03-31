## [Unreleased]

### Breaking Changes
- remove `free-proxy/coding`, use `free-proxy/auto` instead
- `/v1/models` now returns only `free-proxy/auto`

### Added
- `requested_model` support for internal routing preference
- health-driven candidate pool for `auto`
- unified JSON/SSE response normalization

### Changed
- route `/v1/chat/completions` through a unified relay pipeline instead of scattered service/server logic
- lazily load provider-listed fallback models immediately after the failed static default for the same provider
- migrate OpenCode and OpenClaw config output to `auto` only while cleaning legacy `coding` entries

### Fixed
- reject legacy `coding` runtime requests with explicit `model_deprecated` instead of silently falling back
- preserve upstream SSE chunks for OpenAI-compatible streaming clients
- document local proxy interference during localhost SSE verification
