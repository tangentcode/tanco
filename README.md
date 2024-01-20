# tanco

A test-driven teaching environment for programmers.


This is a work in progress. There are videos about it on:

https://www.youtube.com/@tangentstream

If your goal is to work through a coding challenge,
detailed setup instructions are here:

https://tangentcode.com/setup

## Installation

```bash
# eventually:
# pip install tanco

# but for now, this is still very alpha stage, so:
git clone https://github.com/tangentcode/tanco.git
cd tanco
pip install -e .
```


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
