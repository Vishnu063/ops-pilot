"""Produce an explicit audit inventory from the isolated installed runtime.

Only the two verified first-party distributions are separated from public CVE
lookup. Every other installed distribution is pinned for strict pip-audit input.
"""
import argparse
from importlib import metadata
import json
from pathlib import Path
import re
import tomllib


def canonical(name):
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,199}', name):
        raise ValueError('Invalid installed distribution name')
    return re.sub(r'[-_.]+', '-', name).lower()


def inventory(distributions, project):
    dependencies = project.get('dependencies')
    if not isinstance(dependencies, list) or len(dependencies) != 1:
        raise ValueError('Review changed runtime dependency contract before auditing')
    match = re.fullmatch(r'devops-triage-assistant\s*@\s*(https://github.com/Vishnu063/devops-triage-assistant/archive/[0-9a-f]{40}\.zip)', dependencies[0])
    if not match:
        raise ValueError('Native engine must use its exact immutable approved source URL')
    expected_url = match[1]
    own = {'ops-pilot', 'devops-triage-assistant'}
    seen = set(); requirements = []; first_party = []
    for distribution in distributions:
        name = canonical(distribution.metadata.get('Name'))
        version = distribution.version
        if not isinstance(version, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.!+_-]{0,99}', version):
            raise ValueError('Invalid installed distribution version')
        if name in seen:
            raise ValueError('Duplicate installed distribution; use a fresh isolated runtime')
        seen.add(name)
        if name not in own:
            requirements.append(name + '==' + version)
            continue
        if name == 'ops-pilot':
            if version != project.get('version'):
                raise ValueError('Installed Ops Pilot version differs from reviewed project')
            declared = distribution.requires or []
            if len(declared) != 1 or not re.fullmatch(r'devops-triage-assistant\s*@\s*' + re.escape(expected_url), declared[0]):
                raise ValueError('Installed Ops Pilot dependency differs from reviewed project')
        else:
            raw = distribution.read_text('direct_url.json')
            direct = json.loads(raw) if raw else None
            if not isinstance(direct, dict) or direct.get('url') != expected_url:
                raise ValueError('Installed native engine provenance differs from immutable pin')
        first_party.append({'name':name, 'version':version,
                            'source':expected_url if name == 'devops-triage-assistant' else 'checked-out project',
                            'coverage':'First-party source review/Bandit; not public-CVE clearance'})
    if not own.issubset(seen):
        raise ValueError('Audit runtime must contain both installed first-party packages')
    if not requirements:
        raise ValueError('No indexed audit inputs; audit result must not be an empty success')
    return {'third_party_requirements':sorted(requirements),
            'first_party_source_review':sorted(first_party, key=lambda p:p['name']),
            'scope':'All installed runtime distributions, including bootstrap tools. First-party packages are explicitly reported separately; build-isolation and CI tooling are outside this runtime inventory.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-directory', type=Path, required=True)
    args = parser.parse_args()
    project = tomllib.loads((Path(__file__).resolve().parents[1] / 'pyproject.toml').read_text())['project']
    result = inventory(metadata.distributions(), project)
    args.output_directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    (args.output_directory / 'inventory.json').write_text(json.dumps(result, indent=2) + '\n')
    (args.output_directory / 'requirements.txt').write_text('\n'.join(result['third_party_requirements']) + '\n')
    print('Recorded explicit source-review scope and ' + str(len(result['third_party_requirements'])) + ' indexed distributions for strict vulnerability audit.')


if __name__ == '__main__':
    main()
