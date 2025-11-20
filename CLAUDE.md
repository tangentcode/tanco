# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Tanco is a test-driven teaching environment for programmers. It consists of:
- A command-line **client** for students to work through coding challenges
- A **server** (Quart/hypercorn) that manages challenges, tests, and student progress
- A **test runner** that executes programs and validates output
- Support for both **online mode** (syncing with server) and **offline mode** (running tests from `.org` files)

## Architecture

### Core Components

**driver.py** - CLI entry point (`tanco` command)
- Implements a cmd.Cmd-based interactive shell
- Routes subcommands like `login`, `init`, `test`, `next`, `show`, etc.
- Contains the `TancoDriver` class that orchestrates all operations

**runner.py** - Test execution engine
- `spawn()`: Launches student programs as subprocesses with proper platform handling (Windows/POSIX)
- `run_test()`: Sends input to programs, captures output, validates results
- `check_output()`: Compares actual vs expected output (local validation or server-based)
- Handles configuration from `.tanco` files and environment variables

**client.py** - Server API client (`TancoClient`)
- Communicates with remote tanco server via REST API
- Manages authentication (JWT tokens), challenge fetching, and result submission
- Default server: https://tanco.tangentcode.com/ (override via `TANCO_SERVER` env var)

**app.py** - Quart web server
- REST API endpoints for challenges, attempts, authentication
- WebSocket support (`/a/<code>/live`, `/a/<code>/share`) for real-time collaboration
- "Platonic" framework: endpoints serve both HTML (htmx) and JSON (`.json` suffix)
- JWT authentication with RSA signing (requires `tanco_auth_key.pem`)

**database.py** - SQLite persistence layer
- Default location: `~/.tanco.sdb` (override via `TANCO_SDB_PATH`)
- Schema initialized from `tanco/sql/init.sql`
- Tracks: servers, users, challenges, attempts, tests, progress, tokens
- `set_attempt_state()`: Implements state machine (Start → Build → Fix/Change → Done)

**model.py** - Data models and validation
- `TestDescription`: Input lines (`ilines`), expected output (`olines`), metadata
- `Challenge`: Collection of tests with metadata
- `Config`: Runtime configuration (program args, shell mode, skip lines, etc.)
- `TestResult`: Pass/Fail/AskServer with validation rules (currently `LineDiffRule`)
- Attempt state machine: Start → Build → Change ↔ Fix → Done

**orgtest.py** - Org-mode file parser
- Reads test definitions from `.org` files (Emacs org-mode format)
- Supports two format versions (auto-detected):

**Format v0.2 (current)** - Uses org-native TEST headlines:
```org
#+tanco-format: 0.2

** TEST testname : title
#+begin_src
> input line
expected output
#+end_src

Description text goes here as plain body text.
```

**Format v0.1 (legacy)** - Uses `#+name:` directives with inline metadata:
```org
#+name: testname
#+begin_src
> input line
expected output
= title
: description line
#+end_src
```

Line prefixes (both formats):
  - `>` = input line to send to program
  - `#` = comment (shown to user, not expected output)
  - Everything else = expected output

Use `tanco migrate` to convert v0.1 files to v0.2 format.

## Common Development Tasks

### Running Tests

```bash
# Run tests from database (requires `tanco init` first)
tanco test

# Run tests from org file (local/offline mode)
tanco run --tests path/to/tests.org [program_and_args...]

# With shell invocation (for interpreted languages)
tanco run --tests tests.org -c 'python my_script.py'
tanco run --tests tests.org -c 'node my_script.js'

# Direct executables
tanco run --tests tests.org ./my_program arg1 arg2

# Verbose mode (show config)
tanco run -v --tests tests.org ...

# Check that program launches correctly
tanco check [program_args...]
```

### Running the Server

```bash
# Development server (Quart)
QUART_APP=tanco.app:app quart run

# Production server (hypercorn)
hypercorn tanco.app:app

# Note: Requires tanco_auth_key.pem for JWT signing
ssh-keygen -t rsa -b 4096 -m PEM -f tanco_auth_key.pem
```

### Development Installation

```bash
# Editable install (links to source code)
pip install -e .

# Regular install from PyPI
pip install tanco
```

### Code Quality

```bash
# Linting (configured in pyproject.toml)
ruff check .

# Format (configured for single quotes, 120 char lines)
ruff format .
```

## Configuration

### .tanco File Format

Student projects contain a `.tanco` file (JSON):

```json
{
  "targets": {
    "main": {
      "args": ["./my-program"],
      "shell": false
    }
  },
  "attempt": "unique-attempt-code",
  "input_path": "",
  "skip_lines": 0
}
```

### Environment Variables

- `TANCO_SERVER`: Server URL (default: https://tanco.tangentcode.com/)
- `TANCO_SDB_PATH`: Database path (default: `~/.tanco.sdb`)
- `INPUT_PATH`: Write input to file instead of stdin (for non-interactive programs)
- `SKIP_LINES`: Skip N lines of output (for languages with unavoidable headers)
- `TEST_PLAN`: Path to org file for test definitions

## Key Implementation Details

### Test Validation Flow

1. Student runs `tanco test`
2. `runner.run_tests()` iterates through tests for current attempt
3. For each test: `spawn()` program → `send_cmds()` → `communicate()` → `clean_output()`
4. `local_check_output()` compares against cached rules or asks server
5. On first pass, server validates and returns rule; client caches to database
6. On subsequent runs, local validation uses cached rule
7. Pass → notify server, advance state; Fail → show diff, stop testing

### State Machine (Attempts)

States: `Start` → `Build` → `Change` ↔ `Fix` → `Done`

- **Start**: No tests fetched yet
- **Build**: Working on new test (first time seeing it)
- **Change**: All current tests pass, ready for `tanco next`
- **Fix**: Regression (previously passing test now fails)
- **Done**: All tests complete

Transitions in `database.set_attempt_state()` based on `Transition` enum (Pass/Next/Fail).

### Platform Handling (Windows/POSIX)

- `runner.spawn()` handles executable resolution, PATHEXT on Windows
- `-c` flag forces shell mode: `'python script.py'` instead of `['./script']`
- Path normalization: forward slashes → backslashes on Windows when using shell

### WebSocket Collaboration

- `tanco share`: Student shares terminal control with server
- `tanco bind <port>`: Opens local WebSocket for testing
- Teachers can send commands through `/a/<code>/shell` endpoint
- Real-time updates via `/a/<code>/live` websocket (htmx OOB swaps)

## Testing Approach

Self-testing: Tanco includes `tanco/testplan.org` for testing itself. Run via:

```bash
tanco run --tests tanco/testplan.org -c 'tanco shell'
```

Tests use org-mode format. See `orgtest.py` for parser implementation.
