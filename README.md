# tanco

A test-driven teaching environment for programmers.


This is a work in progress. There are videos about it on:

https://www.youtube.com/@tangentstream

If your goal is to work through a coding challenge,
detailed setup instructions are here:

https://tangentcode.com/setup

## Installation

There are two main ways to install Tanco:

**1. From PyPI (Recommended for users):**

If you just want to use Tanco to follow a course or run tests, you can install it directly from the Python Package Index (PyPI):

```bash
pip install tanco
```

You can find the package details on [PyPI](https://pypi.org/project/tanco).

**2. Editable Install (Recommended for developers):**

If you plan to contribute to Tanco development or want the latest changes, clone the repository and install it in editable mode:

```bash
git clone https://github.com/tangentcode/tanco.git
cd tanco
pip install -e .
```

This command links the installed package to your local source code, so any changes you make are immediately effective.

## Using the Client

```bash
tanco login
cd /path/to/your/project
tanco init
tanco test     # keep doing this until it passes
git commit    # once the test passes
tanco next     # to fetch the next test
```

## inspecting the database

Tanco (both the client and server) creates a sqlite database in `~/.tanco.sdb`.

You can override this location by setting the `TANCO_SDB` environment
variable to a different path.

You can inspect the database with the `sqlite3` command-line tool.

```bash
sqlite3 ~/.tanco.sdb
.schema
```


## Running the Server

First set up a private key, then run quart or hypercorn.

### Private Key

The `tanco login` command lets the command-line client
log into the server in a multi-user setup.

In this setup, the server uses a private key to sign
a [json web token](https://jwt.io/).

To set up the private key, do this:

```bash
cd /path/to/tanco-server
ssh-keygen -t rsa -b 4096 -m PEM -f tanco_auth_key.pem
```

This will also create a public key in `tanco_auth_key.pem.pub`.
This is not currently used for anything.

### Running the server

You can run the development server like so:

``bash
QUART_APP=tanco.app:app quart run # --reload
``

Or (on platforms that support it) use hypercorn:

```bash
hypercorn tanco.app:app # --reload
```

## Local Usage

Tanco is primarily used via its command-line interface.

**Running Local Tests from Org Files:**

Tanco can now run tests defined directly within an `.org` file, independent of the server. This is useful for local development, testing, and creating new challenges.

Use the `run` command with the `--tests` flag:

```bash
tanco run --tests path/to/your/tests.org [program_and_args...]
```

*   `--tests path/to/your/tests.org`: Specifies the org file containing the test definitions (using `#+name:`, `#+begin_src`, etc.).
*   `[program_and_args...]`: The command and arguments needed to execute the program being tested.
    *   If your program needs to be run via the shell (e.g., using interpreters like `node` or `python`), prefix the command with `-c`. For example:
        ```bash
        tanco run --tests tests.org -c 'node your_script.js'
        tanco run --tests tests.org -c 'python your_script.py arg1'
        ```
    *   If your program is a direct executable (like `myprogram.exe` on Windows or `./myprogram` on Linux), just provide the path and arguments:
        ```bash
        tanco run --tests tests.org path/to/your_program arg1 arg2
        ```

**Verbose Output:**

You can add the `-v` or `--verbose` flag to the `run` command to print the configuration Tanco is using before executing the tests. This is helpful for debugging paths and arguments:

```bash
tanco run -v --tests tests.org ...
```
