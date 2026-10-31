"""Audit coverage tests: no package silently disappears from the inventory."""
import importlib.util
import json
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('dependency_audit',Path(__file__).resolve().parents[1]/'scripts/dependency_audit.py')
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
URL='https://github.com/Vishnu063/devops-triage-assistant/archive/'+'a'*40+'.zip'
PROJECT={'version':'0.2.0','dependencies':['devops-triage-assistant @ '+URL]}

class Distribution:
    def __init__(self,name,version='1.0',requires=None,url=None):
        self.metadata={'Name':name};self.version=version;self.requires=requires;self.url=url
    def read_text(self,name):
        return json.dumps({'url':self.url}) if self.url is not None else None

class DependencyAuditTests(unittest.TestCase):
    def packages(self):
        return [Distribution('ops-pilot','0.2.0',['devops-triage-assistant@ '+URL]),Distribution('devops-triage-assistant','0.4.0',url=URL),Distribution('pip','25.3')]
    def test_all_indexed_packages_including_bootstrap_are_audited(self):
        result=audit.inventory(self.packages()+[Distribution('Example_Package','2.0')],PROJECT)
        self.assertEqual(result['third_party_requirements'],['example-package==2.0','pip==25.3'])
        self.assertEqual(len(result['first_party_source_review']),2)
        self.assertTrue(all('not public-CVE clearance' in p['coverage'] for p in result['first_party_source_review']))
    def test_native_provenance_cannot_be_silently_excluded(self):
        for value in [None,'https://evil.example/engine.zip',URL+'?token=private']:
            packages=self.packages();packages[1].url=value
            with self.assertRaises(ValueError):audit.inventory(packages,PROJECT)
    def test_missing_packages_fail_closed(self):
        for index in (0,1):
            packages=self.packages();packages.pop(index)
            with self.assertRaises(ValueError):audit.inventory(packages,PROJECT)
    def test_duplicate_normalized_packages_fail_closed(self):
        with self.assertRaises(ValueError):audit.inventory(self.packages()+[Distribution('PIP','25.3')],PROJECT)
    def test_name_or_version_cannot_inject_a_requirement_option(self):
        for name,version in [('bad\n--index-url','1.0'),('bad','1.0\n--trusted-host evil')]:
            with self.assertRaises(ValueError):audit.inventory(self.packages()+[Distribution(name,version)],PROJECT)
    def test_project_and_installed_dependency_contract_must_match(self):
        packages=self.packages();packages[0].requires=['unreviewed @ https://evil.example']
        with self.assertRaises(ValueError):audit.inventory(packages,PROJECT)
        with self.assertRaises(ValueError):audit.inventory(self.packages(),dict(PROJECT,dependencies=[]))
    def test_wrong_installed_project_version_fails(self):
        packages=self.packages();packages[0].version='99.0'
        with self.assertRaises(ValueError):audit.inventory(packages,PROJECT)
    def test_empty_indexed_inventory_cannot_appear_as_success(self):
        with self.assertRaises(ValueError):audit.inventory(self.packages()[:2],PROJECT)
