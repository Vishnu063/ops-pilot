"""Version 1 ingestion contracts and durable receipts. No execution capability."""
import hashlib
import json
import re
import time
from datetime import datetime

IDENTIFIER = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:/-]{0,159}\Z')
DEPLOYMENT_STATES = {'started', 'succeeded', 'failed', 'rollback_started', 'rollback_succeeded', 'rollback_failed'}


def identifier(value):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ValueError('Invalid identifier')
    return value


def timestamp(value):
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError('Expected an RFC3339 timestamp')
    if 'T' not in value:
        raise ValueError('Expected an RFC3339 timestamp')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Timestamp must include timezone')
    return value


def normalize(value, service):
    """Project onto known fields; remote annotations/URLs/commands are never used."""
    if not isinstance(value, dict):
        raise ValueError('Expected an object')
    if 'alerts' in value:
        if value.get('version') != '4' or not isinstance(value['alerts'], list) or not 1 <= len(value['alerts']) <= 50:
            raise ValueError('Expected 1–50 Alertmanager v4 alerts')
        result = []
        for alert in value['alerts']:
            if not isinstance(alert, dict) or alert.get('status') not in {'firing', 'resolved'}:
                raise ValueError('Invalid alert status')
            labels = alert.get('labels')
            if not isinstance(labels, dict) or labels.get('service') != service:
                raise ValueError('Alert does not match the configured service')
            fingerprint = identifier(alert.get('fingerprint'))
            start = timestamp(alert.get('startsAt'))
            status = alert['status']
            key = hashlib.sha256(json.dumps([fingerprint, start, status]).encode()).hexdigest()
            result.append(dict(schema_version=1, kind='MonitoringAlert', id=key,
                source='alertmanager', service=service, timestamp=start,
                correlation_id=fingerprint, status=status,
                alertname=identifier(labels.get('alertname')), fingerprint=fingerprint))
        return result
    required = {'schema_version', 'kind', 'id', 'source', 'service', 'timestamp', 'correlation_id', 'status', 'release_id'}
    if set(value) != required or type(value.get('schema_version')) is not int or value['schema_version'] != 1 or value.get('kind') != 'DeploymentEvent':
        raise ValueError('Expected a version 1 DeploymentEvent')
    for key in required - {'schema_version', 'timestamp'}:
        identifier(value[key])
    timestamp(value['timestamp'])
    if value['service'] != service or value['status'] not in DEPLOYMENT_STATES:
        raise ValueError('Deployment does not match the service or status contract')
    return [dict(value)]


class EventStore:
    def __init__(self, runtime):
        self.runtime = runtime
        with runtime.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS incoming_events (target TEXT, id TEXT, received REAL, payload TEXT, incident TEXT, PRIMARY KEY(target,id))')
            db.execute('CREATE TABLE IF NOT EXISTS event_audit (seq INTEGER PRIMARY KEY, target TEXT, time REAL, event_id TEXT, actor TEXT, operation TEXT, outcome TEXT)')

    def receive(self, events):
        receipts = []
        with self.runtime.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            for event in events:
                raw = json.dumps(event, sort_keys=True)
                row = db.execute('SELECT payload,incident FROM incoming_events WHERE target=? AND id=?', (self.runtime.key, event['id'])).fetchone()
                if row:
                    if row[0] != raw:
                        raise ValueError('Event ID conflicts with an earlier payload')
                    receipts.append(dict(id=event['id'], duplicate=True, incident_id=row[1]))
                    continue
                db.execute('INSERT INTO incoming_events VALUES (?,?,?,?,?)', (self.runtime.key, event['id'], time.time(), raw, None))
                db.execute('INSERT INTO event_audit(target,time,event_id,actor,operation,outcome) VALUES (?,?,?,?,?,?)',
                           (self.runtime.key, time.time(), event['id'], 'ingest-token', 'receive', event['status']))
                receipts.append(dict(id=event['id'], duplicate=False, incident_id=None))
        return receipts

    def link(self, event_ids, incident):
        with self.runtime.connect() as db:
            for event_id in event_ids:
                db.execute('UPDATE incoming_events SET incident=? WHERE target=? AND id=?', (incident, self.runtime.key, event_id))

    def related_incident(self, event):
        # Alert lifecycle identity includes startsAt, so a new outage with the
        # same fingerprint is never hidden. Deployment bursts correlate for 5m.
        cutoff = 0 if event["kind"] == "MonitoringAlert" else time.time() - 300
        with self.runtime.connect() as db:
            rows = db.execute('SELECT payload,incident FROM incoming_events WHERE target=? AND received>=? AND incident IS NOT NULL ORDER BY received DESC LIMIT 500', (self.runtime.key, cutoff))
            for raw, incident in rows:
                prior = json.loads(raw)
                if prior['source'] == event['source'] and prior['correlation_id'] == event['correlation_id'] and prior['kind'] == event['kind']:
                    if event['kind'] != 'MonitoringAlert' or prior['timestamp'] == event['timestamp']:
                        return incident
        return None

    def record_action(self, operation, plan_id, outcome):
        with self.runtime.connect() as db:
            db.execute('INSERT INTO event_audit(target,time,event_id,actor,operation,outcome) VALUES (?,?,?,?,?,?)',
                       (self.runtime.key, time.time(), plan_id, 'local-owner', operation, outcome))

    def history(self):
        with self.runtime.connect() as db:
            return [dict(received_at=t, event=json.loads(p), incident_id=i) for t,p,i in db.execute(
                'SELECT received,payload,incident FROM incoming_events WHERE target=? ORDER BY received DESC LIMIT 100', (self.runtime.key,))]

    def audit(self):
        with self.runtime.connect() as db:
            return [dict(sequence=s, timestamp=t, event_id=e, actor=a, operation=o, outcome=r) for s,t,e,a,o,r in db.execute(
                'SELECT seq,time,event_id,actor,operation,outcome FROM event_audit WHERE target=? ORDER BY seq DESC LIMIT 200', (self.runtime.key,))]
