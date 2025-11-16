# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Org file format v0.2**: New org-native format using TEST headlines instead of `#+name:` directives, with cleaner syntax and better org-mode integration.
- **Migration tool**: New `tanco migrate` command to convert v0.1 org files to v0.2 format, with `--check` option for previewing changes before applying. Preserves original headline text when no `=` title line exists, and saves conflicting headlines as comments.
- **Format auto-detection**: Parser automatically detects org file format version based on `#+tanco-format:` directive.
- **Test file override**: `tanco test` now supports `-t/--tests` flag to override test file, matching the behavior of `tanco run` for consistency.

### Changed
- **Org file syntax**: Test definitions now use `** TEST name : title` headlines instead of separate `#+name:` directives.
- **Test metadata**: Test titles and descriptions moved from inline `=` and `:` prefixes to headline and post-src-block body text.
- **Test headlines**: TODO/DONE keywords removed from test headlines; TEST keyword now identifies tests vs. section headers.

### Documentation
- Updated CLAUDE.md with comprehensive org file format documentation, including examples of both v0.1 and v0.2 formats.
- Added migration instructions and process description.

## [0.1.0] - 2025-11-12

### Fixed
- **Cross-platform shell handling**: `shell: false` now works correctly on all platforms (Windows, Mac, Linux) by searching PATH for executables like `node`, `python`, etc. This eliminates the need to toggle `shell` settings based on operating system.
- **POSIX shell argument passing**: When using `shell: true` on POSIX systems, arguments are now properly passed to the command instead of to the shell itself.
- **orgtest**: Fixed issue where first test was incorrectly skipped in local mode.

### Changed
- Generated `.tanco` config files now omit `"shell": false` (the default), only including `"shell": true` when explicitly needed.
- Updated to new PyPI license specifier format in `pyproject.toml`.

### Documentation
- Added note about `tanco run` command to README.

## [0.0.10] - 2025-01-XX

Previous releases not documented in changelog.
