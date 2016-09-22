# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Subprocess utilities.
"""
from subprocess import PIPE, STDOUT, CalledProcessError, Popen

from eliot import Message, start_action
from pyrsistent import PClass, field


class _CalledProcessError(CalledProcessError):
    """
    Just like ``CalledProcessError`` except output is included in the string
    representation.
    """
    def __str__(self):
        base = super(_CalledProcessError, self).__str__()
        lines = "\n".join("    |" + line for line in self.output.splitlines())
        return base + " and output:\n" + lines


class _ProcessResult(PClass):
    """
    The return type for ``run_process`` representing the outcome of the process
    that was run.
    """
    command = field(type=list, mandatory=True)
    output = field(type=bytes, mandatory=True)
    status = field(type=int, mandatory=True)


def run_process(command, *args, **kwargs):
    """
    Run a child process, capturing its stdout and stderr.

    :param list command: An argument list to use to launch the child process.

    :raise CalledProcessError: If the child process has a non-zero exit status.

    :return: A ``_ProcessResult`` instance describing the result of the child
         process.
    """
    kwargs["stdout"] = PIPE
    kwargs["stderr"] = STDOUT
    action = start_action(
        action_type="run_process", command=command, args=args, kwargs=kwargs)
    with action:
        process = Popen(command, *args, **kwargs)
        output = process.stdout.read()
        status = process.wait()
        result = _ProcessResult(command=command, output=output, status=status)
        # TODO: We should be using a specific logging type for this.
        Message.new(
            command=result.command,
            output=result.output,
            status=result.status,
        ).write()
        if result.status:
            raise _CalledProcessError(
                returncode=status, cmd=command, output=output,
            )
    return result
