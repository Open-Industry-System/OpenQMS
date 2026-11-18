#!/usr/bin/env python3
"""Durable scheduler for the one shared test slot.

The caller supplies reviewed, eligible release identities. It performs deployment
and cleanup outside the database transaction and acknowledges each by lease ID.
"""
import argparse
import json
import re
import sqlite3
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4


IDENTITY_FIELDS = ('pr', 'head', 'merge', 'plan')


def identity(payload):
    if not isinstance(payload, dict) or set(payload) != set(IDENTITY_FIELDS):
        raise ValueError('expected PR number, head, merge and plan digest')
    if type(payload['pr']) is not int or not 0 < payload['pr'] < 10**9:
        raise ValueError('invalid PR number')
    for field, digits in [('head', 40), ('merge', 40), ('plan', 64)]:
        if not isinstance(payload[field], str) or not re.fullmatch(
            f'[0-9a-f]{{{digits}}}', payload[field]
        ):
            raise ValueError(f'invalid {field}')
    return json.dumps(payload, sort_keys=True, separators=(',', ':'))


class Queue:
    def __init__(self, database):
        self.database = database

    @contextmanager
    def transaction(self):
        connection = sqlite3.connect(self.database, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute('BEGIN IMMEDIATE')
            connection.execute('''CREATE TABLE IF NOT EXISTS slot (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                lease TEXT NOT NULL UNIQUE, release TEXT NOT NULL,
                phase TEXT NOT NULL, expires_at INTEGER, outcome TEXT
            )''')
            connection.execute('''CREATE TABLE IF NOT EXISTS completed (
                release TEXT PRIMARY KEY, outcome TEXT NOT NULL
            )''')
            yield connection
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def slot(connection):
        return connection.execute('SELECT * FROM slot WHERE singleton = 1').fetchone()

    @staticmethod
    def describe(slot):
        if slot is None:
            return {'phase': 'idle'}
        return {
            **json.loads(slot['release']), 'phase': slot['phase'],
            'lease': slot['lease'], 'expires_at': slot['expires_at'],
            'outcome': slot['outcome'],
        }

    @staticmethod
    def snapshot(eligible):
        if not isinstance(eligible, list):
            raise ValueError('expected eligible release list')
        releases = {}
        for release in eligible:
            encoded = identity(release)
            pr = release['pr']
            if pr in releases:
                raise ValueError('multiple versions for one PR in eligibility snapshot')
            releases[pr] = encoded
        return releases

    def tick(self, eligible, now):
        releases = self.snapshot(eligible)
        current = set(releases.values())
        with self.transaction() as connection:
            slot = self.slot(connection)
            if slot:
                if slot['phase'] == 'testing':
                    obsolete = slot['release'] not in current
                    if obsolete or now >= slot['expires_at']:
                        self.release(connection, 'superseded' if obsolete else 'expired')
                return self.describe(self.slot(connection))

            for pr in sorted(releases):
                release = releases[pr]
                if connection.execute(
                    'SELECT 1 FROM completed WHERE release = ?', (release,)
                ).fetchone():
                    continue
                connection.execute(
                    "INSERT INTO slot VALUES (1, ?, ?, 'deploying', NULL, NULL)",
                    (uuid4().hex, release),
                )
                break
            return self.describe(self.slot(connection))

    def acknowledge(self, lease, event, now, ttl_seconds=None, eligible=None):
        with self.transaction() as connection:
            slot = self.slot(connection)
            if not slot or slot['lease'] != lease:
                raise ValueError('stale or unknown slot lease')

            phase = slot['phase']
            if event in {'ready', 'passed', 'failed'}:
                current = set(self.snapshot(eligible).values())
                if slot['release'] not in current:
                    raise ValueError('release is no longer eligible')

            if event == 'ready' and phase == 'deploying':
                if type(ttl_seconds) is not int or not 0 < ttl_seconds <= 24 * 3600:
                    raise ValueError('acceptance window must be between 1 and 86400 seconds')
                connection.execute(
                    "UPDATE slot SET phase = 'testing', expires_at = ? WHERE singleton = 1",
                    (now + ttl_seconds,),
                )
            elif event == 'deploy-failed' and phase == 'deploying':
                self.release(connection, event)
            elif event in {'passed', 'failed'} and phase == 'testing':
                if now >= slot['expires_at']:
                    raise ValueError('acceptance window expired')
                self.release(connection, event)
            elif event == 'released' and phase == 'releasing':
                connection.execute(
                    'INSERT INTO completed VALUES (?, ?)', (slot['release'], slot['outcome'])
                )
                connection.execute('DELETE FROM slot WHERE singleton = 1')
            else:
                raise ValueError('event does not match slot phase')
            return self.describe(self.slot(connection))

    @staticmethod
    def release(connection, outcome):
        connection.execute(
            "UPDATE slot SET phase = 'releasing', outcome = ? WHERE singleton = 1",
            (outcome,),
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    subcommands = parser.add_subparsers(dest='command', required=True)
    subcommands.add_parser('tick', help='read the current eligible release list from stdin')
    acknowledge = subcommands.add_parser('acknowledge')
    acknowledge.add_argument('lease')
    acknowledge.add_argument('event', choices=['ready', 'deploy-failed', 'passed', 'failed', 'released'])
    acknowledge.add_argument('--ttl-seconds', type=int)
    args = parser.parse_args()
    queue = Queue(args.database)
    now = int(time.time())
    if args.command == 'tick':
        result = queue.tick(json.load(sys.stdin), now)
    else:
        current = json.load(sys.stdin) if args.event in {'ready', 'passed', 'failed'} else None
        result = queue.acknowledge(args.lease, args.event, now, args.ttl_seconds, current)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
