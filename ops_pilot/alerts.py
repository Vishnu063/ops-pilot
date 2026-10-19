"""Optional, explicit webhook delivery; no logs, credentials or login URLs sent."""
import json
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def deliver(url, event):
    request = Request(url, data=json.dumps({'source': 'ops-pilot', 'event': event}).encode(),
                      headers={'Content-Type': 'application/json'}, method='POST')
    # Explicit destination only: no proxy inheritance and no redirect forwarding.
    with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=3) as response:
        if not 200 <= response.status < 300:
            raise OSError('Webhook rejected the event')
