# v0.3 Release Notes

This document lists every change in the 0.3 series.

<!-- towncrier release notes start -->

## [v0.3.0 (2026-09-02)](https://github.com/jtdub/qgis-mcp/releases/tag/v0.3.0)

### Added

- [#7](https://github.com/jtdub/qgis-mcp/issues/7) - Install the MCP server from PyPI with `uvx qgis-mcp` or `pipx install qgis-mcp`. A clone is no longer needed.
- [#7](https://github.com/jtdub/qgis-mcp/issues/7) - Install the QGIS plugin from the release zip with `Install from ZIP`, instead of copying a folder by hand.
- [#12](https://github.com/jtdub/qgis-mcp/issues/12) - `invoke` drives a Docker development environment. `invoke build` then `invoke tests` runs every check against the same QGIS that CI uses.
- [#12](https://github.com/jtdub/qgis-mcp/issues/12) - `invoke start` with the host-qgis compose file runs only the MCP server in a container, pointed at QGIS Desktop on your machine.

### Changed

- [#7](https://github.com/jtdub/qgis-mcp/issues/7) - Prepare Release now runs the lint, the types, and both test suites before it opens the release pull request.
- [#7](https://github.com/jtdub/qgis-mcp/issues/7) - A `Publish to TestPyPI` workflow proves the whole publish chain before the first real release.

### Fixed

- [#7](https://github.com/jtdub/qgis-mcp/issues/7) - The Prepare Release workflow failed its own check after a version bump. It compared the bumped version against the one the editable install carried, which is not refreshed by a bump.

### Documentation

- [#4](https://github.com/jtdub/qgis-mcp/issues/4) - A `NOTICE` file carries the MIT copyright notice of BlenderMCP, the project this work derives from. Keep it with the work if you redistribute it.
- [#4](https://github.com/jtdub/qgis-mcp/issues/4) - `docs/dev/licensing.md` records why the project is Apache-2.0, and how that sits beside the GPL that QGIS uses.
- [#6](https://github.com/jtdub/qgis-mcp/issues/6) - A documentation site replaces `tools.md` and `CONTRIBUTING.md`. It holds a user guide, an administrator guide, and a developer guide.
- [#6](https://github.com/jtdub/qgis-mcp/issues/6) - The administrator guide covers the token, the `execute_code` gate, the environment variables, upgrading, and the QGIS and Python versions that are supported.
- [#7](https://github.com/jtdub/qgis-mcp/issues/7) - `docs/dev/release_checklist.md` describes how to cut a release, and what to set up once before the first one.
- [#9](https://github.com/jtdub/qgis-mcp/issues/9) - `docs/dev/ai_assisted_contributions.md` states what the project asks of a contributor who uses an AI assistant, and what a reviewer checks.
- [#9](https://github.com/jtdub/qgis-mcp/issues/9) - The pull request template asks you to disclose AI assistance, and which part of the change it wrote.
- [#14](https://github.com/jtdub/qgis-mcp/issues/14) - The release notes moved to `docs/admin/release_notes/`. `CHANGELOG.md` now points at them.
- [#14](https://github.com/jtdub/qgis-mcp/issues/14) - A change adds a file under `changes/` instead of editing a changelog. Read `docs/dev/changelog_fragments.md`.
