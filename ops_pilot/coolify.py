"""Optional documented Coolify v4 API. Credentials and raw errors never enter evidence."""
import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
import time
from urllib.parse import urlsplit

SUPPORTED_VERSIONS = frozenset({'4.5.3'})
MAX_RESPONSE = 262144


class ProviderError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__({'authentication': 'Coolify rejected the configured credential or permission',
                          'timeout': 'Coolify connection timed out; mutation outcome may be unknown',
                          'tls': 'TLS validation failed', 'dns': 'Destination resolution failed',
                          'destination': 'Destination is outside the explicit network policy',
                          'rate_limit': 'Coolify rate limit reached; try after the polling interval',
                          'unreachable': 'Coolify connection unavailable',
                          'response': 'Unexpected or oversized Coolify response',
                          'unsupported': 'Operation unsupported for this version or configuration',
                          'api': 'Coolify API rejected the operation; inspect locally without exposing credentials'}[code])


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', value):
        raise ValueError('Use one exact identifier without paths, wildcards or query syntax')
    return value


def clean(value, secrets=(), limit=4096):
    """Redact before truncation; projections still must avoid collecting unnecessary secrets."""
    text = str(value)
    for secret in sorted((s for s in secrets if s), key=len, reverse=True):
        text = text.replace(secret, '[redacted]')
    text = re.sub(r'(?im)^\s*(authorization|proxy-authorization|cookie|set-cookie|x-api-key)\s*:[^\r\n]*', r'\1: [redacted]', text)
    text = re.sub(r'(?i)\b(bearer|basic)\s+[^\s,;]+', r'\1 [redacted]', text)
    text = re.sub(r'(?i)([\w.-]*(?:token|password|passwd|secret|api[_-]?key|credential)[\w.-]*[\s"\x27]*[:=][\s"\x27]*)([^\s,;"\x27}]+)', r'\1[redacted]', text)
    text = re.sub(r'(?i)(https?://)[^/\s:@]+:[^/\s@]+@', r'\1[redacted]@', text)
    text = re.sub(r'-----BEGIN [^-]*PRIVATE KEY-----[\s\S]*?(?:-----END [^-]*PRIVATE KEY-----|$)', '[redacted private key]', text)
    text = ''.join(c if c in '\n\t' or ord(c) >= 32 and ord(c) != 127 else '?' for c in text)
    return text[:limit] + ('\n[truncated]' if len(text) > limit else '')


def destination(url, private_ips=(), loopback=False, allow_query=False):
    if not isinstance(url,str): raise ValueError('Destination must be a URL string')
    p = urlsplit(url)
    if (p.scheme not in ('https', 'http') or not p.hostname or p.username or p.password
            or p.fragment or (p.query and not allow_query) or len(url) > 2000 or any(ord(c) < 33 for c in url)):
        raise ValueError('Use an explicit HTTP(S) URL without credentials, query or fragment')
    try:
        port = p.port
        if port is not None and not 1<=port<=65535: raise ValueError('Invalid destination port')
    except ValueError:
        raise ValueError('Invalid destination port') from None
    if p.scheme != 'https' and not (loopback and p.hostname in ('127.0.0.1', '::1', 'localhost')):
        raise ValueError('Remote connections require HTTPS with certificate validation')
    for value in private_ips:
        addr = ipaddress.ip_address(value)
        private_networks=('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16','fc00::/7')
        if not any(addr in ipaddress.ip_network(network) for network in private_networks) or str(addr)=='fd00:ec2::254':
            raise ValueError('Private IP exceptions must be exact non-loopback RFC1918/ULA addresses')
    return p, port or (443 if p.scheme == 'https' else 80)


class Transport:
    """Resolve, validate every result, pin the chosen IP, retain TLS hostname validation.

    No redirects, ambient proxy credentials, metadata/link-local addresses or URL discovery.
    Explicit private-IP exceptions support owner-configured private networks, not web input.
    """
    def __init__(self, private_ips=(), loopback=False):
        self.private_ips, self.loopback = tuple(private_ips), loopback

    def request(self, method, url, headers, body, timeout):
        p, port = destination(url, self.private_ips, self.loopback, allow_query=True)
        try:
            addresses = list(dict.fromkeys(a[4][0] for a in socket.getaddrinfo(p.hostname, port, type=socket.SOCK_STREAM)))
        except socket.gaierror:
            raise ProviderError('dns') from None
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if str(ip)=='fd00:ec2::254': raise ProviderError('destination')
            allowed = ip.is_global and not ip.is_multicast
            allowed |= ip.is_private and address in self.private_ips and not (ip.is_link_local or ip.is_loopback)
            allowed |= self.loopback and ip.is_loopback and p.hostname in ('localhost', '127.0.0.1', '::1')
            if not allowed:
                raise ProviderError('destination')
        if not addresses:
            raise ProviderError('dns')
        connection = http.client.HTTPConnection(p.hostname, port, timeout=timeout)
        try:
            connection.sock = socket.create_connection((addresses[0], port), timeout)
            if p.scheme == 'https':
                connection.sock = ssl.create_default_context().wrap_socket(connection.sock, server_hostname=p.hostname)
            connection.request(method, (p.path or '/') + ('?' + p.query if p.query else ''), body=body, headers=headers)
            response = connection.getresponse()
            chunks=[];size=0;deadline=time.monotonic()+timeout
            while True:
                remaining=deadline-time.monotonic()
                if remaining<=0: raise ProviderError('timeout')
                if connection.sock is not None: connection.sock.settimeout(remaining)
                chunk=response.read1(min(8192,MAX_RESPONSE+1-size))
                if not chunk: break
                size+=len(chunk)
                if size>MAX_RESPONSE: raise ProviderError('response')
                chunks.append(chunk)
            raw=b''.join(chunks)
            return response.status, dict(response.getheaders()), raw
        except (TimeoutError, socket.timeout):
            raise ProviderError('timeout') from None
        except ssl.SSLError:
            raise ProviderError('tls') from None
        except (OSError, http.client.HTTPException):
            raise ProviderError('unreachable') from None
        finally:
            connection.close()


class Coolify:
    def __init__(self, config, transport=None, sleep=time.sleep):
        self.config = config
        if not isinstance(config.get('base_url'),str): raise ValueError('Coolify base_url is required')
        self.base = config['base_url'].rstrip('/')
        p, _ = destination(self.base, config.get('private_ips', ()), config.get('allow_loopback', False))
        if p.path not in ('', '/'):
            raise ValueError('Coolify base_url must be the origin, without /api/v1')
        self.transport = transport or Transport(config.get('private_ips', ()), config.get('allow_loopback', False))
        self.sleep = sleep
        self.version = None

    def token(self, repair=False):
        key = self.config.get('repair_token_env') if repair else self.config['token_env']
        value = os.environ.get(key or '', '')
        if not 16 <= len(value) <= 4096 or any(ord(c) < 33 or ord(c) > 126 for c in value):
            raise ProviderError('authentication')
        return value

    def request(self, path, method='GET', body=None):
        token = self.token(method != 'GET')
        headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/json', 'Content-Type': 'application/json'}
        # Only idempotent reads retry. Never retry mutations, including ambiguous timeouts/429s.
        for attempt in range(3 if method == 'GET' else 1):
            try:
                status, response_headers, raw = self.transport.request(method, self.base + '/api/v1' + path,
                    headers, json.dumps(body).encode() if body is not None else None, self.config.get('timeout', 3))
            except ProviderError as exc:
                if method == 'GET' and exc.code in ('timeout', 'unreachable') and attempt < 2:
                    self.sleep(0.25 * 2**attempt)
                    continue
                raise
            if status in (401, 403):
                raise ProviderError('authentication')
            if status == 429 or 500 <= status <= 599:
                if method == 'GET' and attempt < 2:
                    retry = next((v for k,v in response_headers.items() if k.lower() == 'retry-after'), '')
                    if status == 429 and (not retry.isdigit() or int(retry) > 2):
                        raise ProviderError('rate_limit')
                    self.sleep(min(2, max(0.25 * 2**attempt, int(retry) if retry.isdigit() else 0)))
                    continue
                raise ProviderError('rate_limit' if status == 429 else 'api')
            if not 200 <= status < 300:
                raise ProviderError('unsupported' if status in (404, 405) else 'api')
            if not isinstance(raw, bytes) or len(raw) > MAX_RESPONSE:
                raise ProviderError('response')
            try:
                text = raw.decode('utf-8')
                return text.strip().strip('"') if path == '/version' else json.loads(text)
            except (UnicodeError, ValueError):
                raise ProviderError('response') from None
        raise ProviderError('api')

    def connection(self):
        version = self.request('/version')
        if not isinstance(version, str) or not re.fullmatch(r'v?[0-9][A-Za-z0-9.+-]{0,60}', version):
            raise ProviderError('response')
        self.version = version.removeprefix('v')
        return dict(version=self.version, documented_contract=self.version in SUPPORTED_VERSIONS,
                    actions=['restart', 'redeploy'] if self.version in SUPPORTED_VERSIONS and self.config.get('repair_token_env') else [],
                    runtime_acceptance=False)

    def project(self, raw):
        if not isinstance(raw, dict):
            raise ProviderError('response')
        try:
            target = identifier(raw.get('uuid'))
        except ValueError:
            raise ProviderError('response') from None
        status = raw.get('status', 'unknown')
        if not isinstance(status, str):
            raise ProviderError('response')
        runtime = status.split(':', 1)[0]
        runtime = runtime if runtime in ('running', 'stopped', 'exited', 'restarting', 'starting') else 'unknown'
        # Provider health is separate from the owner's configured readiness endpoint.
        provider_health = 'unhealthy' if 'unhealthy' in status else 'healthy' if status.endswith(':healthy') else 'unknown'
        server = raw.get('destination', {}) or {}
        server = server.get('server', {}) if isinstance(server, dict) else {}
        server = server.get('uuid', 'unknown') if isinstance(server, dict) else 'unknown'
        identity = {k:raw.get(k) for k in ('uuid','updated_at','destination_id','git_repository','git_branch',
                                        'git_commit_sha','docker_registry_image_name','docker_registry_image_tag','build_pack')}
        import hashlib
        return dict(uuid=target, application_id=self.numeric_id(raw.get('id')), name=clean(raw.get('name', target), self.secrets(), 120),
                    server=clean(server, self.secrets(), 100), runtime=runtime, provider_health=provider_health,
                    revision=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest(),
                    pinned_release=bool(re.fullmatch(r'[a-fA-F0-9]{40}',str(raw.get('git_commit_sha','')))))

    @staticmethod
    def numeric_id(value):
        if type(value) is int and value>0: return str(value)
        if isinstance(value,str) and re.fullmatch(r'[1-9][0-9]{0,19}',value): return value
        return None

    def secrets(self):
        return tuple(os.environ.get(self.config.get(key, ''), '') for key in ('token_env', 'repair_token_env'))

    def discover(self):
        raw = self.request('/applications')
        if not isinstance(raw, list) or len(raw) > 200:
            raise ProviderError('response')
        apps = [self.project(item) for item in raw]
        if len({a['uuid'] for a in apps}) != len(apps):
            raise ProviderError('response')
        return apps

    def servers(self):
        raw = self.request('/servers')
        if not isinstance(raw, list) or len(raw) > 200:
            raise ProviderError('response')
        return [dict(uuid=identifier(r.get('uuid')), name=clean(r.get('name',''),self.secrets(),120)) for r in raw if isinstance(r,dict)]

    def inspect(self, target):
        app = self.project(self.request('/applications/' + identifier(target)))
        if app['uuid'] != target:
            raise ProviderError('response')
        return app

    def deployments(self, target):
        # The official schema says array; release controller returns {count, deployments}.
        raw = self.request('/deployments/applications/' + identifier(target) + '?take=5&skip=0')
        raw = raw.get('deployments') if isinstance(raw, dict) else raw
        if not isinstance(raw, list) or len(raw) > 5 or any(not isinstance(r,dict) for r in raw):
            raise ProviderError('response')
        return [dict(uuid=identifier(r.get('deployment_uuid')), status=clean(r.get('status','unknown'),self.secrets(),60),
                     created_at=clean(r.get('created_at',''),self.secrets(),60)) for r in raw]

    def deployment(self, deployment_id, target):
        raw = self.request('/deployments/' + identifier(deployment_id))
        if not isinstance(raw, dict) or raw.get('deployment_uuid') != deployment_id:
            raise ProviderError('response')
        # Coolify scopes this endpoint to the team, not the requested application.
        app=self.inspect(identifier(target))
        if app['application_id'] is None or self.numeric_id(raw.get('application_id'))!=app['application_id']:
            raise ProviderError('response')
        return dict(uuid=deployment_id,application_uuid=target,status=clean(raw.get('status','unknown'),self.secrets(),60))

    def logs(self, target):
        raw = self.request('/applications/' + identifier(target) + '/logs?lines=' + str(self.config.get('log_lines',100)))
        if not isinstance(raw, dict) or not isinstance(raw.get('logs'), str):
            raise ProviderError('response')
        return clean(raw['logs'], self.secrets(), 8192)

    def execute(self, target, action):
        if self.version not in SUPPORTED_VERSIONS or action not in ('restart', 'redeploy') or not self.config.get('repair_token_env'):
            raise ProviderError('unsupported')
        target = identifier(target)
        path = '/applications/' + target + '/restart' if action == 'restart' else '/deploy'
        raw = self.request(path, 'POST', {'uuid':target} if action == 'redeploy' else {})
        if action == 'redeploy':
            values = raw.get('deployments') if isinstance(raw,dict) else None
            if not isinstance(values,list) or len(values)!=1 or not isinstance(values[0],dict) or values[0].get('resource_uuid')!=target:
                raise ProviderError('response')
            raw=values[0]
        if not isinstance(raw,dict):
            raise ProviderError('response')
        try:
            return dict(deployment_uuid=identifier(raw.get('deployment_uuid')), status='queued')
        except ValueError:
            raise ProviderError('response') from None
