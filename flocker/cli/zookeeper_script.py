# Copyright (C) 2017 Nokia Corporation and/or its subsidiary(-ies). See LICENSE file for details.

"""
Command line tool for manipulating ZooKeeper-held Flocker control data.
"""

from argparse import ArgumentParser, RawDescriptionHelpFormatter
from contextlib import contextmanager
import logging
import datetime
import sys

from kazoo.client import KazooClient
from kazoo.exceptions import NoNodeError

ZK_CONFIG_PATH = '/flocker/configuration'
ZOOKEEPER_HOSTS = 'localhost:2181'
MIGRATE_FROM = '/var/lib/flocker/current_configuration.json'
EPILOG = '''get:
  Print ZooKeeper node contents to stdout.

put:
  Pipe from stdin to ZooKeeper.

migrate:
  Store %s in ZooKeeper.
''' % MIGRATE_FROM


class ScriptError(RuntimeError):
    '''Known errors we want to catch'''

@contextmanager
def zk_client(zkhosts):
    '''Minimal ZooKeeper client'''
    _client = KazooClient(
        hosts=zkhosts,
        connection_retry={'max_tries': 4, 'delay': 1},
        command_retry={'max_tries': 4, 'delay': 1}
        )
    try:
        _client.start()
        yield _client
    finally:
        _client.stop()

def get(zkhosts, node):
    '''Get node contents from ZooKeeper'''
    with zk_client(zkhosts) as client:
        try:
            content, stat = client.get(node)
        except NoNodeError:
            raise ScriptError, 'No such node %s' % node
        mtime = datetime.datetime.fromtimestamp(stat.mtime / 1000).isoformat()
        logging.info(
            'Fetched node. Version:%s, mtime:%s, size:%s',
            stat.version, mtime, len(content))
        return content

def put(zkhosts, node, content):
    '''Store something to a ZooKeeper node'''
    with zk_client(zkhosts) as client:
        client.ensure_path(node)
        stat = client.set(node, content)
        mtime = datetime.datetime.fromtimestamp(stat.mtime / 1000).isoformat()
        logging.info(
            'Stored node. Version:%s, mtime:%s, size:%s',
            stat.version, mtime, len(content))
        return stat.version


def main():
    '''Entrypoint for the command line tool'''
    parser = ArgumentParser(
        description=__doc__, epilog=EPILOG, formatter_class=RawDescriptionHelpFormatter)
    parser.add_argument('action', nargs='?', choices=['put', 'get', 'migrate'], default='get',
                        help='default: get; see below for details')
    parser.add_argument('--zookeeper-hosts', '-z', help='default: %s' % ZOOKEEPER_HOSTS)
    parser.add_argument('--node', '-n', help='default: %s' % ZK_CONFIG_PATH)
    parser.add_argument('-v', dest='verbose', action='count', default=0, help='increase verbosity')
    parser.add_argument('-q', dest='quiet', action='count', default=0, help='decrease verbosity')
    parser.set_defaults(zookeeper_hosts=ZOOKEEPER_HOSTS, node=ZK_CONFIG_PATH)
    args = parser.parse_args()
    log_level = logging.WARNING - (args.verbose * 10) + (args.quiet * 10)
    logging.basicConfig(
        level=log_level,
        format='%(message)s',
        handlers=[logging.StreamHandler(sys.stderr)])
    try:
        if args.action == 'get':
            sys.stdout.write(get(args.zookeeper_hosts, args.node))
        elif args.action == 'put':
            print put(args.zookeeper_hosts, args.node, sys.stdin.read())
        elif args.action == 'migrate':
            with open(MIGRATE_FROM, 'rb') as dir_cfg_store:
                content = dir_cfg_store.read()
                print put(args.zookeeper_hosts, args.node, content)
    except ScriptError, exc:
        logging.error(str(exc))
        sys.exit(2)
    except Exception, exc:  # pylint: disable=broad-except
        if log_level <= logging.DEBUG:
            raise
        else:
            logging.error(str(exc))
            sys.exit(3)

if __name__ == '__main__':
    main()
