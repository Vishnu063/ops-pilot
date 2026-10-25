"""Optional, configured read-only collectors. No repair or arbitrary-command API."""
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
import uuid

from triage.evidence import annotate, deep_evidence, log_signals
from triage.health import check_health
from triage.integrations import ToolAdapter, redact
from triage.ecosystem import k8sgpt

TOOLS = frozenset(('kubernetes', 'jenkins', 'aws', 'helm', 'argocd', 'prometheus', 'grafana'))


def configuration(path):
    path = Path(path).expanduser()
    if path.is_symlink() or path.stat().st_size > 16384 or path.stat().st_mode & 0o077:
        raise ValueError('Diagnostics configuration must be a private regular file, at most 16 KiB')
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or set(value) != {'environment', 'tools'}:
        raise ValueError('Use environment and tools only; multi-user operation is disabled')
    environment = value['environment']
    if not isinstance(environment, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', environment):
        raise ValueError('Choose an explicit environment ID')
    if not isinstance(value['tools'], dict) or not value['tools'] or set(value['tools']) - TOOLS:
        raise ValueError('Select documented read-only diagnostic profiles')
    for tool, config in value['tools'].items():
        adapter = ToolAdapter(tool, config)
        for field in ('context', 'namespace', 'resource', 'profile', 'region'):
            if field in config and (not isinstance(config[field], str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,252}', config[field])):
                raise ValueError('Use exact diagnostic scope names without wildcards or command syntax')
        if tool == 'aws' and not re.fullmatch(r'i-[a-f0-9]{8,17}', config['resource']):
            raise ValueError('AWS diagnostics require one explicit EC2 instance ID')
        # Configuration is validated here; no connection or mutation during setup.
        del adapter
    return value


class Diagnostics:
    def __init__(self, config, directory):
        self.config = configuration(config)
        self.environment = self.config['environment']
        self.root = Path(directory) / 'diagnostics' / self.environment
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.root.chmod(0o700)
        self.path = self.root / 'reports.sqlite3'
        self.lock = threading.Lock()
        with self.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS reports(id TEXT PRIMARY KEY,tool TEXT,at REAL,payload TEXT);
            CREATE TABLE IF NOT EXISTS audit(seq INTEGER PRIMARY KEY,at REAL,action TEXT,report TEXT,previous TEXT,hash TEXT);
            CREATE TRIGGER IF NOT EXISTS immutable_audit_update BEFORE UPDATE ON audit BEGIN SELECT RAISE(ABORT,'append only'); END;
            CREATE TRIGGER IF NOT EXISTS immutable_audit_delete BEFORE DELETE ON audit BEGIN SELECT RAISE(ABORT,'append only'); END;''')
        self.path.chmod(0o600)

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def _save(self, tool, report):
        report.update(schema_version='1.0', id=uuid.uuid4().hex, environment=self.environment,
                      read_only=True, generated_at=time.time(), actions=[],
                      scope='Configured read-only evidence. Findings are hypotheses, not proof of root cause or recovery. Docker repair uses the separate exact-target owner approval workflow.')
        raw = json.dumps(report)
        if len(raw.encode()) > 262144:
            raise ValueError('Diagnostic report exceeds export bounds; narrow the configured scope')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT count(*) FROM reports').fetchone()[0] >= 2000:
                raise ValueError('Diagnostic retention limit reached; archive private evidence')
            db.execute('INSERT INTO reports VALUES (?,?,?,?)', (report['id'], tool, report['generated_at'], raw))
            previous = db.execute('SELECT hash FROM audit ORDER BY seq DESC LIMIT 1').fetchone()
            previous = previous[0] if previous else 'genesis'
            digest = hashlib.sha256((previous + raw).encode()).hexdigest()
            db.execute('INSERT INTO audit(at,action,report,previous,hash) VALUES (?,?,?,?,?)',
                       (report['generated_at'], 'read_only_collection', report['id'], previous, digest))
        return report

    def collect(self, tool):
        if tool not in self.config['tools']:
            raise ValueError('Collector is not configured for this environment')
        if not self.lock.acquire(blocking=False):
            raise ValueError('A diagnostic collection is already running')
        try:
            adapter = ToolAdapter(tool, self.config['tools'][tool])
            try:
                snapshot = adapter.collect()
                report = dict(tool=tool, target=adapter.target, snapshot=snapshot,
                              findings=adapter.findings(snapshot), deep_evidence=deep_evidence(adapter))
                report['findings'].extend(report['deep_evidence'].get('findings', []))
                if tool == 'aws' and 'impaired' in snapshot['observations'].get('instance_check', []):
                    report['findings'].append(dict(code='aws:instance-check', title='EC2 instance reachability check impaired',
                        evidence='AWS reports instance_check=impaired', likely_cause='Guest OS, networking or resource pressure may be involved.',
                        next_steps=['Inspect guest logs, EC2 events and CloudWatch metrics with read-only permissions; do not reboot automatically.']))
                if tool == 'helm':
                    try:
                        raw, _ = adapter.command(['helm','history','$resource','--namespace','$namespace','--kube-context','$context','--max','10','--output','json'])
                        history = json.loads(raw)
                        if not isinstance(history, list) or len(history) > 10:
                            raise ValueError('Invalid release history')
                        report['release_history'] = [{k: item.get(k) for k in ('revision','status','chart','app_version')} for item in history]
                        report['rollback_analysis'] = 'Review a retained deployed/superseded revision, workload compatibility and data migrations. No Helm rollback is executed or approved by this desk.'
                    except (ValueError, RuntimeError, OSError, TypeError, AttributeError):
                        report['deep_evidence']['errors'].append('Bounded Helm release history unavailable')
                if tool == 'jenkins':
                    # Read the numbered build collected above, not a moving lastBuild console.
                    number = snapshot['observations'].get('number', [None])[0]
                    if type(number) is not int or number < 1:
                        raise ValueError('Jenkins build identity is unavailable')
                    try:
                        raw, _ = adapter.request('/job/$resource/' + str(number) + '/logText/progressiveText?start=0')
                        report['deep_evidence'] = dict(supported=True, log_signals=log_signals(raw), errors=[],
                            scope='Bounded numbered-build console signature counts only; raw text is discarded. First failing stage is not inferred from signatures.')
                    except (ValueError, RuntimeError, OSError):
                        report['deep_evidence']['errors'].append('Numbered build log evidence unavailable or exceeds bounds')
                report['application_health'] = check_health(self.config['tools'][tool].get('application_health'))
                if report['application_health'].get('healthy') is False:
                    report['findings'].append(dict(code='application-health', title='Configured HTTP health policy failed', evidence='Configured endpoint did not satisfy its bounded policy', likely_cause='Application, routing, authentication or dependencies may be failing.', next_steps=['Check endpoint samples and dependencies before any repair.']))
                report['status'] = 'inconclusive' if snapshot.get('errors') or report['deep_evidence'].get('errors') else 'findings' if report['findings'] else 'no_findings_in_scope'
                if tool == 'kubernetes':
                    report['k8sgpt'] = k8sgpt(adapter.config['context'], adapter.config['namespace'], os.environ.get('OPS_PILOT_K8SGPT') == '1')
                annotate(report)
            except (ValueError, RuntimeError, OSError):
                report = dict(tool=tool, target=adapter.target, status='inconclusive', findings=[],
                              errors=['Read-only evidence unavailable; check scoped permissions, native tools and endpoint compatibility.'])
            # Never persist CLI stderr, raw manifests, console logs or credential configuration.
            return self._save(tool, redact(report))
        finally:
            self.lock.release()

    def trivy(self, value):
        if not isinstance(value, dict) or set(value) != {'artifact_digest', 'report'} or not re.fullmatch(r'sha256:[a-f0-9]{64}', str(value['artifact_digest'])):
            raise ValueError('Supply an exact artifact digest and a bounded Trivy JSON report')
        raw = value['report']
        if len(json.dumps(value).encode()) > 262144:
            raise ValueError('Scanner report exceeds input bounds')
        if not isinstance(raw, dict) or raw.get('SchemaVersion') != 2 or not isinstance(raw.get('Results'), list) or len(raw['Results']) > 100:
            raise ValueError('Use Trivy schema 2 with bounded results')
        findings = []
        counts = {s: 0 for s in ('UNKNOWN', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL')}
        for result in raw['Results']:
            if not isinstance(result, dict):
                raise ValueError('Invalid scanner result')
            vulnerabilities = result.get('Vulnerabilities') or []
            if not isinstance(vulnerabilities, list) or len(vulnerabilities) > 1000:
                raise ValueError('Scanner result exceeds bounds')
            for item in vulnerabilities:
                if not isinstance(item, dict):
                    raise ValueError('Invalid vulnerability entry')
                severity = item.get('Severity', 'UNKNOWN')
                if severity not in counts:
                    severity = 'UNKNOWN'
                counts[severity] += 1
                if len(findings) < 100:
                    findings.append({k: str(item.get(k, ''))[:200] for k in ('VulnerabilityID', 'PkgName', 'InstalledVersion', 'FixedVersion', 'Severity')})
        return self._save('trivy', dict(tool='trivy', artifact_digest=value['artifact_digest'], counts=counts,
            findings=redact(findings), truncated=sum(counts.values()) > len(findings),
            status='findings' if sum(counts.values()) else 'no_findings_in_supplied_report',
            provenance='Owner-supplied scanner output; artifact association is declared, not independently attested. No scan or mutation executed.'))

    def state(self):
        with self.connect() as db:
            rows = db.execute('SELECT payload FROM reports ORDER BY at DESC LIMIT 8').fetchall()
        return dict(environment=self.environment, tools=sorted(self.config['tools']), read_only=True, multi_user=False,
                    reports=[json.loads(r[0]) for r in rows], history_window=8)

    def report(self, ident):
        if not isinstance(ident, str) or not re.fullmatch(r'[a-f0-9]{32}', ident):
            raise ValueError('Select an existing diagnostic report')
        with self.connect() as db:
            row = db.execute('SELECT payload FROM reports WHERE id=?', (ident,)).fetchone()
        if not row:
            raise ValueError('Diagnostic report not found in this environment')
        return json.loads(row[0])
