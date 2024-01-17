# tanco

A test-driven teaching environment for programmers.


This is a work in progress. There are videos about it on:

https://www.youtube.com/@tangentstream

## Installation

```bash
# eventually:
# pip install tanco

# but for now, this is still very alpha stage, so:
git clone https://github.com/tangentstorm/tanco.git
cd tanco
pip install -e .
```

## setting up the database

Currently expects `tanco.sdb` in the current directory.

You need one copy for the server, and one copy for each challenge attempt.
(So these should run in separate directories.)

(Eventually on the client side, there will only be one global database
shared by all attempts on your machine, but because tanco still expects
the database to be in the current directory, you need multiple copies.)

For now, you have to do this manually, by running the following commands:

```bash
cd /path/to/tanco-repo
echo '.read tanco/sql/init.sql' | sqlite3 tanco.sdb 
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

## Running the Server

First set up a private key, then run quart.

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

### Quart server

``bash
QUART_APP=tanco.app:app quart run # --reload
``

Note that the above runs the standard asgiref server, and as the message will say:

```
Please use an ASGI server (e.g. Hypercorn) directly in production 
```
