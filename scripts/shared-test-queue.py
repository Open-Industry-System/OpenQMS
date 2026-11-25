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
            connection.execute('''CREATE TABLE IF NOT EXISTS switch_requests (
                comment_id INTEGER PRIMARY KEY, release TEXT NOT NULL, pending INTEGER NOT NULL
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

    def request_switch(self, comment_id, release, eligible):
        if type(comment_id) is not int or not 0 < comment_id < 2**63:
            raise ValueError('invalid switch comment ID')
        requested = identity(release)
        if self.snapshot(eligible).get(release['pr']) != requested:
            raise ValueError('switch target is not currently eligible')
        with self.transaction() as connection:
            replay = connection.execute(
                'SELECT release FROM switch_requests WHERE comment_id = ?', (comment_id,)
            ).fetchone()
            if replay:
                if replay['release'] != requested:
                    raise ValueError('switch comment is already bound to a different version')
                return self.describe(self.slot(connection))
            if connection.execute('SELECT 1 FROM switch_requests WHERE pending = 1').fetchone():
                raise ValueError('another switch is already pending')
            outcome = connection.execute('SELECT outcome FROM completed WHERE release = ?', (requested,)).fetchone()
            if outcome and outcome['outcome'] == 'passed':
                raise ValueError('switch target already passed acceptance')
            slot = self.slot(connection)
            pending = slot is None or slot['release'] != requested or slot['phase'] == 'releasing'
            connection.execute('INSERT INTO switch_requests VALUES (?, ?, ?)', (comment_id, requested, pending))
            return self.describe(slot)

    def tick(self, eligible):
        releases = self.snapshot(eligible)
        current = set(releases.values())
        with self.transaction() as connection:
            request = connection.execute(
                'SELECT comment_id, release FROM switch_requests WHERE pending = 1'
            ).fetchone()
            if request and request['release'] not in current:
                connection.execute('UPDATE switch_requests SET pending = 0 WHERE comment_id = ?',
                                   (request['comment_id'],))
                request = None
            slot = self.slot(connection)
            if slot:
                if slot['phase'] == 'testing':
                    obsolete = slot['release'] not in current
                    if obsolete:
                        self.release(connection, 'superseded')
                    elif request and request['release'] != slot['release']:
                        self.release(connection, 'switched')
                return self.describe(self.slot(connection))

            if request:
                preferred = request['release']
                connection.execute('UPDATE switch_requests SET pending = 0 WHERE comment_id = ?',
                                   (request['comment_id'],))
                connection.execute("DELETE FROM completed WHERE release = ? AND outcome != 'passed'", (preferred,))
                ordered = [preferred, *(releases[pr] for pr in sorted(releases) if releases[pr] != preferred)]
            else:
                ordered = [releases[pr] for pr in sorted(releases)]
            for release in ordered:
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

    def retry_failed(self, release):
        encoded = identity(release)
        with self.transaction() as connection:
            if self.slot(connection):
                raise ValueError('retry requires an idle shared test slot')
            result = connection.execute(
                'DELETE FROM completed WHERE release = ? AND outcome = ?', (encoded, 'deploy-failed')
            )
            if result.rowcount != 1:
                raise ValueError('only an exact deployment failure may be retried')
            return {'phase': 'idle'}

    def acknowledge(self, lease, event, eligible=None):
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
                connection.execute("UPDATE slot SET phase = 'testing', expires_at = NULL WHERE singleton = 1")
            elif event == 'deploy-failed' and phase == 'deploying':
                self.release(connection, event)
            elif event in {'passed', 'failed'} and phase == 'testing':
                self.release(connection, event)
            elif event == 'released' and phase == 'releasing':
                if slot['outcome'] != 'switched':
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
    args = parser.parse_args()
    queue = Queue(args.database)
    if args.command == 'tick':
        result = queue.tick(json.load(sys.stdin))
    else:
        current = json.load(sys.stdin) if args.event in {'ready', 'passed', 'failed'} else None
        result = queue.acknowledge(args.lease, args.event, eligible=current)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
