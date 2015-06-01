#!/usr/bin/env python

from __future__ import print_function

import json

from sys import argv, stdin, stdout

# Lines look like
# Jun 01 18:40:15 acceptance-test-jpxrichardx1925xtesting-1 flocker-dataset-agent[7010]: {...


def main(input_stream):
    stacks = {}
    for line in open(input_stream):
        _, _, _, host, service, rest = line.strip().split(None, 5)
        key = (host, service)
        if service.startswith(b"flocker-"):
            # Weak heuristic
            stacks.setdefault(key, []).append(rest)
            starting = rest.startswith(b"{")
            continuing = len(stacks[key]) > 1
            if rest.endswith(b"}"):
                if starting and continuing:
                    # It starts a message but a message is started
                    # already.  Throw out the stack because it's
                    # incomplete.
                    stacks[key] = [rest]

                elif not starting and not continuing:
                    # It doesn't start a message but there's nothing
                    # on the stack already started.  We're hosed.
                    # Toss it all out.
                    del stacks[key][:]
                    continue

                try:
                    event = json.loads(b"".join(stacks[key]))
                except Exception as e:
                    print(e, stacks[key])
                    import pdb; pdb.set_trace()

                if "action_type" not in event:
                    event["action_type"] = "SIMULATION"
                    event["action_status"] = "SIMULATION"
                del stacks[key][:]
                print(json.dumps(event), file=stdout)

if __name__ == '__main__':
    main(*argv[1:])
