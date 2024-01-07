# rogo

A test-driven teaching environment for programmers.

## Installation (TODO)

## Using the Client

## Running the Server (TODO)

## Private Key

The `rogo login` command lets the command-line client
log into the server in a multi-user setup.

In this setup, the server uses a private key to sign
a [json web token](https://jwt.io/).

To set up the private key, do this:

```bash
$ cd /path/to/rogo-server
$ ssh-keygen -t rsa -b 4096 -m PEM -f rogo_auth_key.pem
```

This will also create a public key in `rogo_auth_key.pem.pub`.
This is not currently used for anything.
