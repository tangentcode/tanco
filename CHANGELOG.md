# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
