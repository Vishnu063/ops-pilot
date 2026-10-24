"""Optional stdlib producer client; no Triage, Docker or AI imports required."""
import argparse
from datetime import datetime, timezone
import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def send(url, token, event):
    parsed = urlsplit(url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path != '/api/events':
        raise ValueError('Use the exact ingestion URL without credentials, query or fragment')
    if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in {'127.0.0.1', 'localhost', '::1'}):
        raise ValueError('HTTPS required except on loopback')
    if not token or len(token) < 32:
        raise ValueError('OPS_PILOT_INGEST_TOKEN is missing or too short')
    body = json.dumps(event).encode()
    if len(body) > 65536:
        raise ValueError('Event exceeds 64 KiB')
    for attempt in range(3):
        try:
            request = Request(url, data=body, headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token})
            with build_opener(NoRedirect()).open(request, timeout=20) as response:
                if response.status != 200:
                    raise ValueError('Ingestion did not acknowledge the event')
                return json.loads(response.read(65537))
        except HTTPError as error:
            if error.code not in {429, 502, 503, 504}:
                raise ValueError('Ingestion rejected the event') from None
        except (URLError, TimeoutError, OSError):
            pass
        if attempt < 2:
            time.sleep(attempt + 1)
    raise RuntimeError('Delivery unconfirmed after three attempts; retry the same event ID')


def main():
    parser = argparse.ArgumentParser(description='Send one immutable deployment fact to Ops Pilot')
    parser.add_argument('--service', required=True)
    parser.add_argument('--release-id', required=True)
    parser.add_argument('--status', required=True, choices=['started', 'succeeded', 'failed', 'rollback_started', 'rollback_succeeded', 'rollback_failed'])
    parser.add_argument('--event-id', required=True, help='Stable across retries')
    parser.add_argument('--correlation-id', required=True)
    parser.add_argument('--timestamp', required=True, help='Stable RFC3339 timestamp across retries')
    parser.add_argument('--audit-file', help='Append this non-secret deployment fact as JSONL before sending')
    args = parser.parse_args()
    event = dict(schema_version=1, kind='DeploymentEvent', id=args.event_id, source='cloudlaunch', service=args.service,
                 timestamp=args.timestamp, correlation_id=args.correlation_id, status=args.status, release_id=args.release_id)
    # Validate locally using only the producer fields; the server is authoritative.
    if args.audit_file:
        fd = os.open(args.audit_file, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write(json.dumps(event) + '\n')
    url = os.environ.get('OPS_PILOT_EVENTS_URL')
    if not url:
        print('Recorded locally; Ops Pilot integration disabled')
        return 0
    try:
        receipt = send(url, os.environ.get('OPS_PILOT_INGEST_TOKEN'), event)
        print(json.dumps(receipt))
        return 0
    except (ValueError, RuntimeError):
        print('Event delivery unconfirmed; inspect local audit and retry the same ID')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
