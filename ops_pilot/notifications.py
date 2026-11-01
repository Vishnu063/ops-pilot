"""Minimal Telegram adapter. Never includes logs, targets, credentials or login URLs."""
import json
import os
import re
from .coolify import Transport, ProviderError

EVENTS=frozenset(('incident_detected','recovery_approval_required','recovery_completed','recovery_failed','application_restored','monitoring_connection_lost'))


def telegram(config,event,transport=None):
    if event not in EVENTS: raise ValueError('Unsupported notification event')
    token=os.environ.get(config['token_env'],'')
    if not re.fullmatch(r'[0-9]{5,20}:[A-Za-z0-9_-]{20,100}',token): raise ValueError('Configure a private Telegram bot token')
    body=json.dumps(dict(chat_id=config['chat_id'],text='Ops Pilot: '+event.replace('_',' ')+'. Open the private owner dashboard for details.')).encode()
    # No retry after a transport failure: delivery may have succeeded remotely.
    for attempt in range(2):
        status,headers,raw=(transport or Transport()).request('POST','https://api.telegram.org/bot'+token+'/sendMessage',{'Content-Type':'application/json'},body,3)
        if status==429 and attempt==0:
            try: wait=json.loads(raw)['parameters']['retry_after']
            except (ValueError,TypeError,KeyError): return False
            if type(wait) is not int or not 0<=wait<=2: return False
            import time
            time.sleep(wait);continue
        if status!=200: return False
        try:
            data=json.loads(raw)
            return data.get('ok') is True and isinstance(data.get('result'),dict) and type(data['result'].get('message_id')) is int
        except (ValueError,AttributeError): return False
    return False
