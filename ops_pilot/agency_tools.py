"""Deterministic estimates, intake inspection and message drafts. No external actions."""
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
import re

IMAGE = r'[A-Za-z0-9][A-Za-z0-9._/:-]*@sha256:[a-f0-9]{64}'
BRIEF_FIELDS = ('client_alias', 'target', 'access_reference', 'access_expires', 'image', 'port',
    'health_path', 'expected_status', 'rollback_image', 'rollback_reference', 'first_deployment',
    'runtime_assumptions', 'environment', 'stateless', 'persistent_storage', 'private_network',
    'configuration', 'constraints', 'scope', 'agreement_reference', 'quote', 'milestones',
    'revisions', 'support_hours', 'support_days', 'response_expectation', 'retention_days', 'deadline')


def quote(data, currency):
    from .agency import checked
    from .freelance import money
    fields = ('hours', 'hourly_rate', 'complexity', 'hosting', 'tools', 'platform_fees', 'contingency')
    values = checked(data, fields, ('hours', 'hourly_rate'))
    # Reuse the ledger's decimal parser; all quantities have at most two decimals.
    hours = Decimal(money(values['hours'])) / 100
    complexity = Decimal(money(values.get('complexity', '1.00'))) / 100
    if not 0 < hours <= 240 or not 0 < complexity <= 5:
        raise ValueError('Quote hours must be 0–240 exclusive of zero; complexity must be 0–5 exclusive of zero')
    labor = int((hours * money(values['hourly_rate']) * complexity).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    extras = {name: money(values.get(name, '0')) for name in fields[3:]}
    total = labor + sum(extras.values())
    if total > 10_000_000_000:
        raise ValueError('Quote exceeds the supported amount limit')
    return dict(inputs=values, currency=currency, labor_cents=labor, extras_cents=extras,
        total_cents=total, method='hours × hourly rate × complexity + fixed estimated costs; labor rounded half-up to cents',
        source='owner estimate; not customer-agreed', customer_agreed=False, sent=False)


def unsupported_configuration(brief, require_flags=False):
    blockers = []
    if brief.get('expected_status') and brief['expected_status'] != '200':
        blockers.append('The first practice worker supports HTTP 200 readiness only')
    if brief.get('configuration') and brief['configuration'].lower() not in ('none', 'no configuration'):
        blockers.append('Custom application configuration is outside the first worker')
    for field, expected in (('stateless', 'yes'), ('persistent_storage', 'no'), ('private_network', 'no')):
        if (require_flags or field in brief) and brief.get(field) != expected:
            blockers.append(field+' must be explicitly '+expected+' for the first service')
    return blockers


def intake_check(brief, at=None):
    at = at or datetime.now(timezone.utc)
    blockers = []
    required = ('client_alias', 'target', 'scope', 'constraints', 'runtime_assumptions', 'environment',
                'access_reference', 'access_expires', 'agreement_reference', 'image', 'port',
                'health_path', 'expected_status', 'configuration', 'rollback_reference')
    missing = [name for name in required if not brief.get(name)]
    blockers.extend('Missing: '+name for name in missing)
    for name in ('image', 'rollback_image'):
        if brief.get(name) and not re.fullmatch(IMAGE, brief[name]):
            blockers.append(name+' must name an immutable image digest')
    if brief.get('first_deployment') not in ('yes', 'no'):
        blockers.append('Confirm first_deployment as yes or no')
    if brief.get('first_deployment') == 'no' and not brief.get('rollback_image'):
        blockers.append('Previous immutable rollback_image required for an existing deployment')
    if brief.get('first_deployment') == 'yes' and brief.get('rollback_image'):
        blockers.append('First deployment cannot also claim a previous rollback image')
    port = brief.get('port', '')
    if port and (not re.fullmatch(r'[1-9][0-9]{0,4}', port) or int(port) > 65535):
        blockers.append('Port must be a canonical integer from 1 to 65535')
    if brief.get('health_path') and not re.fullmatch(r'/(?!/)[A-Za-z0-9_./-]*', brief['health_path']):
        blockers.append('Use a simple absolute health path without a remote URL or query')
    blockers.extend(unsupported_configuration(brief, require_flags=True))
    expires = brief.get('access_expires')
    if expires:
        try:
            expiration = datetime.fromisoformat(expires)
            if expiration.tzinfo is None:
                raise ValueError('timezone required')
            if expiration <= at:
                blockers.append('Access authorization reference has expired; renew it before customer work')
        except ValueError:
            blockers.append('access_expires must be an ISO timestamp with an explicit timezone')
    return dict(missing=missing, blockers=blockers, ready_for_manual_review=not blockers,
        authorized_to_deploy=False, customer_runtime_verified=False,
        checked_at=at.isoformat(), valid_until=expires or None,
        brief_digest=hashlib.sha256(json.dumps(brief, sort_keys=True).encode()).hexdigest(),
        source='Owner-recorded requirements only; references and permissions are not independently verified',
        next_action='Review actual authorization, image trust and recovery evidence before any customer action')


def draft_message(job, data, balance):
    from .agency import checked, records
    item = checked(data, ('kind', 'details'), ('kind',))
    kind = item['kind']
    a = records(job)
    if kind == 'requirements':
        inspection = intake_check(a['brief'])
        questions = inspection['blockers'] or ['Please confirm the recorded image, readiness response, access window and recovery plan are accurate.']
        body = 'Please confirm these requirements for '+job['title']+':\n'+ '\n'.join('- '+q for q in questions)
    elif kind == 'progress':
        done = [t['title'][:200] for t in a['tasks'].values() if t['status']=='done'][:10]
        blocked = [t.get('blocker') or t['title'] for t in a['tasks'].values() if t['status']=='blocked'][:10]
        body = (f"Project: {job['title']}\nInternal workflow state: {job['state']}\n"
                +'Owner-recorded completed tasks: '+('; '.join(done) or 'none recorded')+'\n'
                +'Blockers: '+('; '.join(b[:200] for b in blocked) or 'none recorded; confirm current conditions')+'\n'
                +'Customer runtime validation and acceptance must be checked separately. No new infrastructure change is authorized by this update.')
    elif kind == 'incident':
        if not item.get('details'):
            raise ValueError('Incident drafts require owner-supplied observations')
        body = ('Owner-reported observations (verify before sending): '+item['details']+'\n'
                'Please confirm the observed time, impact and agreed escalation contact. Pause further changes until the recovery plan and approval are reviewed. No recovery or response deadline is promised by this draft.')
    elif kind == 'overdue':
        amount = Decimal(balance['outstanding_cents']) / 100
        body = (f"Our owner-maintained project records show {job['currency']} {amount:.2f} outstanding for {job['title']}. "
                'Please confirm your payment reference or any discrepancy. Invoice-level payment allocation is manual: verify which milestone is overdue before sending. This record does not independently verify payment.')
    elif kind == 'follow_up':
        body = ('Please review the agreed handover and let us know any outstanding concerns for '+job['title']+'. '
                'Confirm the agreed support window and acceptance checks before committing to additional work.')
    else:
        raise ValueError('Choose requirements, progress, incident, overdue or follow_up')
    return dict(kind=kind, text=body, sent=False, approved_to_send=False,
        source_revision=job['revision'], source='deterministic draft using owner records; verify every claim')
