"""Optional, configured read-only collectors. No repair or arbitrary-command API."""
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import threading
import time
import uuid

from triage.evidence import annotate, deep_evidence, log_signals
from triage.health import check_health
from triage.integrations import ToolAdapter, redact
from triage.ecosystem import k8sgpt
from .storage import private_database, PrivateConnection
from .read_diagnostics import (split_config, scope, signatures, signal_findings, github_actions, jenkins_extra, aws_account, aws_extra, prometheus_job, EvidenceError, finding, docker_metrics)

TOOLS = frozenset(('docker', 'kubernetes', 'jenkins', 'github-actions', 'aws', 'helm', 'argocd', 'prometheus', 'grafana'))


def optional_analysis(context, namespace, enabled):
    try:
        result=k8sgpt(context,namespace,enabled)
        if not isinstance(result,dict):raise ValueError('Incompatible optional analyzer response')
        return result
    except (ValueError,RuntimeError,OSError,TypeError):
        return {'status':'inconclusive','executable':False,'untrusted':True,
                'explanation':'Optional analyzer unavailable or incompatible; native evidence is retained. No provider inference or generated command is executed.'}


def wizard(path):
    """Create a new private profile without credentials, network access or overwrite."""
    path = Path(path).expanduser()
    if path.exists() or path.is_symlink():
        raise ValueError('Diagnostics configuration already exists; review it locally rather than overwrite it')
    print('Read-only diagnostics: configure only an environment you are authorized to inspect. No connection runs now.')
    environment = input('Environment ID: ').strip()
    tool = input('Collector (docker, kubernetes, jenkins, github-actions, aws, helm, argocd, prometheus, grafana): ').strip()
    fields = {'docker':('context','resource'), 'kubernetes':('context','namespace','resource'), 'jenkins':('base_url','resource'),
              'github-actions':('owner','repository','resource','base_url'), 'aws':('profile','region','resource'), 'helm':('context','namespace','resource'),
              'argocd':('server','resource'), 'prometheus':('base_url',), 'grafana':('base_url',)}
    if tool not in fields:
        raise ValueError('Choose a documented read-only collector')
    config = {name:input(name + ' (exact configured scope): ').strip() for name in fields[tool]}
    print('Credentials use native CLI profiles or documented environment bindings; never paste tokens into this wizard.')
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    import tempfile
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix='.diagnostics-')
    try:
        with os.fdopen(descriptor,'w') as stream:
            os.fchmod(stream.fileno(),0o600)
            json.dump({'environment':environment,'tools':{tool:config}},stream,indent=2)
        configuration(temporary)
        # Hard-link creation is atomic and refuses a concurrent existing destination.
        os.link(temporary,path)
    finally:
        os.unlink(temporary)
    print('Saved privately. Add environment credential bindings if needed; then run diagnostics with --tool ' + tool)


def configuration(path):
    path = Path(path).expanduser()
    if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode) or path.stat().st_size > 16384 or path.stat().st_mode & 0o077:
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
        native, extra = split_config(tool, config)
        adapter = ToolAdapter(tool, native)
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
        self.path = self.root / 'reports.sqlite3'
        self.lock = threading.Lock()
        with self.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS reports(id TEXT PRIMARY KEY,tool TEXT,at REAL,payload TEXT);
            CREATE TABLE IF NOT EXISTS audit(seq INTEGER PRIMARY KEY,at REAL,action TEXT,report TEXT,previous TEXT,hash TEXT);
            CREATE TRIGGER IF NOT EXISTS immutable_audit_update BEFORE UPDATE ON audit BEGIN SELECT RAISE(ABORT,'append only'); END;
            CREATE TRIGGER IF NOT EXISTS immutable_audit_delete BEFORE DELETE ON audit BEGIN SELECT RAISE(ABORT,'append only'); END;''')
        self.path.chmod(0o600)

    def connect(self):
        return sqlite3.connect(private_database(self.path), timeout=10, factory=PrivateConnection)

    def _save(self, tool, report):
        report.update(schema_version='1.0', id=uuid.uuid4().hex, environment=self.environment,
                      read_only=True, generated_at=time.time(), actions=[], read_scope=scope(self.config['tools'].get(tool,{})),
                      data_origin='owner-supplied scanner metadata' if tool=='trivy' else 'configured collector; live only when actually invoked',
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
            native, extra = split_config(tool,self.config['tools'][tool])
            if tool=='docker':
                from .service import DockerAdapter
                adapter=DockerAdapter(native)
            else:adapter = ToolAdapter(tool, native)
            try:
                account=aws_account(adapter,extra) if tool=='aws' else None
                github=None;prometheus=None
                if tool=='github-actions':
                    snapshot,github,findings=github_actions(adapter,extra)
                elif tool=='prometheus' and extra.get('job'):
                    prometheus=prometheus_job(adapter,extra['job'])
                    snapshot=dict(tool=tool,collected_at=time.time(),observations={'status':['success'],'job':[extra['job']],'target_health':['up' if prometheus['healthy'] else 'down']},errors=[],truncated=False,empty=False)
                    findings=adapter.findings(snapshot)
                    if not prometheus['healthy']:findings.append(finding('prometheus:down','Configured Prometheus job has down targets','Fresh scoped up sample is zero','Inspect the configured scrape targets and application endpoint; missing samples cannot establish recovery.'))
                else:
                    snapshot=adapter.collect();findings=adapter.findings(snapshot)
                report = dict(tool=tool, target=adapter.target, snapshot=snapshot,
                              findings=findings, deep_evidence=deep_evidence(adapter))
                if tool=='docker' and extra.get('metrics'):
                    report['resources'],resource_findings=docker_metrics(adapter)
                    report['findings'].extend(resource_findings)
                if github is not None:
                    report['ci']=github;report['deep_evidence']['errors'].extend(github['errors'])
                if prometheus is not None:report['monitoring']=prometheus
                if tool=='aws':
                    report['aws_evidence'],extra_findings=aws_extra(adapter,extra,account)
                    report['findings'].extend(extra_findings)
                    report['deep_evidence']['errors'].extend(report['aws_evidence']['errors'])
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
                    number = (snapshot['observations'].get('number') or [None])[0]
                    if type(number) is not int or number < 1:
                        raise ValueError('Jenkins build identity is unavailable')
                    try:
                        raw, _ = adapter.request('/job/$resource/' + str(number) + '/logText/progressiveText?start=0')
                        report['deep_evidence'] = dict(supported=True, log_signals=signatures(raw), errors=[],
                            scope='Bounded numbered-build console signature counts only; raw text is discarded. First failing stage is not inferred from signatures.')
                    except (ValueError, RuntimeError, OSError):
                        report['deep_evidence']['errors'].append('Numbered build log evidence unavailable or exceeds bounds')
                    report['findings'].extend(signal_findings(report['deep_evidence'].get('log_signals',{})))
                    if extra.get('history') or extra.get('stages'):
                        report['ci']=jenkins_extra(adapter,extra,number)
                        report['deep_evidence']['errors'].extend(report['ci']['errors'])
                report['application_health'] = check_health(self.config['tools'][tool].get('application_health'))
                if report['application_health'].get('healthy') is False:
                    report['findings'].append(dict(code='application-health', title='Configured HTTP health policy failed', evidence='Configured endpoint did not satisfy its bounded policy', likely_cause='Application, routing, authentication or dependencies may be failing.', next_steps=['Check endpoint samples and dependencies before any repair.']))
                report['status'] = 'inconclusive' if snapshot.get('errors') or report['deep_evidence'].get('errors') else 'findings' if report['findings'] else 'no_findings_in_scope'
                if tool == 'kubernetes':
                    report['k8sgpt'] = optional_analysis(adapter.config['context'], adapter.config['namespace'], os.environ.get('OPS_PILOT_K8SGPT') == '1')
                annotate(report)
            except EvidenceError as exc:
                report=dict(tool=tool,target=adapter.target,status='inconclusive',findings=[],errors=[str(exc)])
            except (ValueError, RuntimeError, OSError, TypeError, KeyError, IndexError, AttributeError):
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
            if any(result.get(field) for field in ('Misconfigurations','Secrets','Licenses')):
                raise ValueError('Import vulnerability-only reports; other scanner findings must not be silently discarded')
            vulnerabilities = result.get('Vulnerabilities', [])
            if vulnerabilities is None:vulnerabilities=[]
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
            attempts={};successes={}
            for tool,at,payload in db.execute('SELECT tool,at,payload FROM reports ORDER BY at DESC LIMIT 2000'):
                if tool not in self.config['tools']:continue
                attempts.setdefault(tool,{'at':at,'status':json.loads(payload).get('status','unknown')})
                if tool not in successes and json.loads(payload).get('status') not in ('inconclusive',None):successes[tool]=at
                if len(successes)==len(self.config['tools']):break
        return dict(environment=self.environment, tools=sorted(self.config['tools']), read_only=True, multi_user=False,
                    collectors=[dict(tool=tool,scope=scope(config),last_attempt=attempts.get(tool),last_successful_collection=successes.get(tool)) for tool,config in self.config['tools'].items()],
                    reports=[json.loads(r[0]) for r in rows], history_window=8)

    def report(self, ident):
        if not isinstance(ident, str) or not re.fullmatch(r'[a-f0-9]{32}', ident):
            raise ValueError('Select an existing diagnostic report')
        with self.connect() as db:
            row = db.execute('SELECT payload FROM reports WHERE id=?', (ident,)).fetchone()
        if not row:
            raise ValueError('Diagnostic report not found in this environment')
        return json.loads(row[0])
