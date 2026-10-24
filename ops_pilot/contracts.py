"""Versioned wire projections over existing engine reports; no second engine."""
from datetime import datetime, timezone
from triage.ecosystem import diagnosis


def stamp(value=None):
    return datetime.fromtimestamp(value, timezone.utc).isoformat() if isinstance(value, (int, float)) else datetime.now(timezone.utc).isoformat()


def project(state):
    report = state.get('report')
    if not report:
        return []
    incident_id = (state.get('plan') or {}).get('incident_id') or report['incident_id']
    def envelope(kind, suffix, **fields):
        return dict(schema_version=1, kind=kind, id=incident_id+':'+suffix,
                    source='ops-pilot', timestamp=stamp(), correlation_id=incident_id, **fields)
    evidence = [envelope('Evidence', 'evidence', incident_id=incident_id,
                         observation={'snapshot': report.get('snapshot'), 'deep_evidence': report.get('deep_evidence'), 'application_health': report.get('application_health')},
                         scope='Configured Docker application; filtered runtime metadata and bounded log signatures')]
    plan, result = state.get('plan'), state.get('result')
    status = 'investigating'
    if plan and plan['status'] == 'pending': status = 'awaiting_approval'
    if result: status = 'verified' if result.get('status') == 'verified' else 'failed'
    incident = envelope('Incident', 'incident', service=state['container'], status=status, evidence_refs=[evidence[0]['id']])
    records = [incident, *evidence, diagnosis(dict(report, incident_id=incident_id))]
    if plan:
        records.append(envelope('RemediationProposal', 'proposal', incident_id=plan['incident_id'],
            action=plan['action'], parameters={'command': plan.get('command', [])}, risk=plan['risk'],
            expected_impact=plan.get('preview', {}).get('expected_effect', 'Review the exact configured operation'),
            rollback_strategy=plan['rollback'], verification_criteria={'container_identity': 'unchanged', 'application_health': plan.get('application_health')}, expires_at=stamp(plan['expires_at'])))
        for row in state.get('event_audit', []):
            if row['event_id'] == plan['id'] and row['operation'] in {'approve', 'cancel'} and row['outcome']=='completed':
                decision = envelope('ApprovalDecision', 'decision:'+str(row['sequence']), incident_id=plan['incident_id'], proposal_id=incident_id+':proposal', actor=row['actor'],
                    decision='approved' if row['operation']=='approve' else 'rejected', expires_at=stamp(plan['expires_at']))
                decision['timestamp'] = stamp(row['timestamp']); records.append(decision)
    verification = {}
    if result and plan:
        health = result.get('application_health', {})
        verification = envelope('VerificationResult', 'verification', incident_id=plan['incident_id'],
            status='verified' if result.get('status')=='verified' else 'failed' if health.get('healthy') is False else 'inconclusive',
            criteria={'container_identity': 'unchanged', 'endpoint': state['health_url']},
            observations=[health, {'infrastructure_status': result.get('infrastructure_status')}], recovery_seconds=None)
        records.extend([envelope('ExecutionResult', 'execution', incident_id=plan['incident_id'], proposal_id=incident_id+':proposal',
            actor='local-owner', action=plan['action'], parameters={'command':plan.get('command',[])},
            status='executed' if result.get('infrastructure_status')=='verified' else 'unknown', error=None if result.get('status')=='verified' else 'Recovery not verified'), verification])
    records.append(envelope('IncidentReport', 'report', incident_id=incident_id,
        timeline=state.get('incident_timeline', []) + state.get('event_audit', []) + state.get('incoming_events', []), evidence=evidence,
        actions=state.get('history', []), verification=verification,
        unresolved_issues=[] if status=='verified' else ['Recovery has not been verified']))
    return records
