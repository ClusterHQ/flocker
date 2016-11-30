#!/usr/bin/env python2
#
# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Run a build step.

Travis calls this during the `script` phase of its build lifecycle.
 * https://docs.travis-ci.com/user/customizing-the-build

Set ``FLOCKER_BUILDER`` environment variable before calling this script.
"""
import os
from subprocess import call

from .common import BuildHandler


def tox(tox_env):
    return call(["tox", "-e", tox_env])


def docs(build_type):
    return tox("docs-" + build_type)


def lint():
    return tox("lint")


def acceptance(provider, distribution, dataset_backend):
    build_dir = "/".join([
        os.environ["TRAVIS_BUILD_DIR"],
        "build",
        os.environ["FLOCKER_BUILDER"]
    ])
    os.makedirs(build_dir)
    command = [
        os.environ["TRAVIS_BUILD_DIR"] + "/admin/run-acceptance-tests",
        "--provider", provider,
        "--distribution", distribution,
        "--dataset-backend", dataset_backend,
        "--config-file",
        os.environ["TRAVIS_BUILD_DIR"] + "/.travis/secrets/acceptance.yml",
        "--",
        "flocker.acceptance.endtoend.test_diagnostics",
    ]
    return call(command, cwd=build_dir)


main = BuildHandler(
    handlers={
        "acceptance": acceptance,
        "lint": lint,
        "docs": docs,
    }
).main
