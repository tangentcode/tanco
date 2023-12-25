#!/bin/env python
"""
command-line driver for rogo client.
"""
import sys, cmd, json


class RogoDriver(cmd.Cmd):
    prompt = ""

    def do_c(self, arg):
        """List challenges"""
        print(json.dumps(["rogo client test suite"]))

    def do_q(self, arg):
        """Run the test suite."""
        return True


if __name__ == '__main__':
    RogoDriver().cmdloop()
