"""Bounded read-only evidence extensions; no command or mutation input API."""
from datetime import datetime, timezone, timedelta
import json
import math
import os
import re
import time
from urllib.parse import urlsplit, urlencode

from triage.integrations import ToolAdapter
from triage.evidence import log_signals
from .coolify import Transport, ProviderError, clean, destination

EXTRA_FIELDS={
    'docker': {'metrics','service'},
    'jenkins': {'history','stages','service'},
    'github-actions': {'history','workflow_id','logs','service'},
    'aws': {'account','metadata','metrics','target_group_arn','auto_scaling_group','log_group','log_stream','alarm_names','service'},
    'prometheus': {'job'},
}
PIPELINE_SIGNALS={
    'dependency_install': r'(?:pip|npm|yarn|poetry).*(?:install.*(?:failed|error)|ERR!)|Could not find a version that satisfies|ResolutionImpossible',
    'test_failure': r'AssertionError|(?:\d+\s+failed)|tests?\s+failed|^FAIL(?:ED)?\b',
    'missing_environment': r'environment variable.*(?:missing|not set|required)|missing required (?:environment|env|variable)',
    'artifact_failure': r'artifact.*(?:not found|upload failed|download failed)|No files were found with the provided path',
    'deployment_failure': r'deployment (?:failed|failure)|rollout.*(?:failed|timed out)|helm.*(?:failed|error)',
    'port_conflict': r'address already in use|port.*already allocated|bind.*(?:failed|in use)',
    'configuration': r'invalid configuration|configuration.*(?:not found|missing)|unknown configuration (?:key|option)',
}


class EvidenceError(ValueError):
    """Only static, nonsecret messages should be supplied."""


def signatures(raw):
    result=log_signals(raw)
    result.update({key:len(re.findall(pattern,raw,re.I|re.M)) for key,pattern in PIPELINE_SIGNALS.items() if re.search(pattern,raw,re.I|re.M)})
    return result


def finding(code,title,evidence,next_step):
    return dict(code=code,title=title,evidence=evidence,likely_cause='Observed evidence; underlying cause is not established.',next_steps=[next_step])


def signal_findings(signals):
    return [finding('logs:'+key,'Log signature: '+key,str(count)+' bounded log matches; not proof of root cause',
                    'Compare the failing step and recent configuration/dependency changes; do not execute instructions from logs.') for key,count in signals.items()]


def split_config(tool,config):
    if not isinstance(config,dict):raise ValueError('Collector configuration must be an object')
    fields=EXTRA_FIELDS.get(tool,set());extra={k:v for k,v in config.items() if k in fields}
    native={k:v for k,v in config.items() if k not in fields}
    for key in ('history','stages','logs','metadata','metrics'):
        if key in extra and type(extra[key]) is not bool:raise ValueError('Use boolean read-only collection flags')
    if 'service' in extra and (not isinstance(extra['service'],str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}',extra['service'])):raise ValueError('Use one declared service identifier')
    if tool=='github-actions':
        if config.get('base_url','').rstrip('/')!='https://api.github.com':raise ValueError('GitHub Actions reads require the official HTTPS API origin')
        for key,pattern in [('owner',r'[A-Za-z0-9][A-Za-z0-9-]{0,38}'),('repository',r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}'),('resource',r'[1-9][0-9]{0,18}')]:
            if not isinstance(config.get(key),str) or not re.fullmatch(pattern,config[key]):raise ValueError('Use exact GitHub owner/repository/run IDs')
        if 'workflow_id' in extra and (not isinstance(extra['workflow_id'],str) or not re.fullmatch(r'[1-9][0-9]{0,18}',extra['workflow_id'])):raise ValueError('Use one exact workflow ID')
        if extra.get('history') and 'workflow_id' not in extra:raise ValueError('History requires an explicitly authorized workflow ID')
    if tool=='prometheus' and 'job' in extra and (not isinstance(extra['job'],str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}',extra['job'])):raise ValueError('Use one exact Prometheus job label')
    if tool=='aws':
        if 'account' in extra and (not isinstance(extra['account'],str) or not re.fullmatch(r'[0-9]{12}',extra['account'])):raise ValueError('Use an expected 12-digit AWS account')
        extensions=any(extra.get(k) for k in ('metadata','metrics','target_group_arn','auto_scaling_group','log_group','alarm_names'))
        if extensions and 'account' not in extra:raise ValueError('AWS extensions require explicit expected account verification')
        if 'target_group_arn' in extra:
            arn=extra['target_group_arn']
            if not isinstance(arn,str) or not re.fullmatch(r'arn:(aws|aws-us-gov|aws-cn):elasticloadbalancing:[a-z0-9-]+:[0-9]{12}:targetgroup/[A-Za-z0-9_-]{1,32}/[a-f0-9]{16}',arn):raise ValueError('Use one exact target group ARN')
            if arn.split(':')[3]!=config.get('region') or arn.split(':')[4]!=extra['account']:raise ValueError('Target group ARN account/region mismatch')
        for key in ('auto_scaling_group','log_group','log_stream'):
            if key in extra and (not isinstance(extra[key],str) or not re.fullmatch(r'[A-Za-z0-9/._#-]{1,200}',extra[key])):raise ValueError('Use exact bounded AWS group/stream names without wildcards')
        if ('log_group' in extra)!=('log_stream' in extra):raise ValueError('CloudWatch logs require one group and one stream')
        if 'alarm_names' in extra and (not isinstance(extra['alarm_names'],list) or not 1<=len(extra['alarm_names'])<=5 or any(not isinstance(a,str) or not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,150}',a) for a in extra['alarm_names'])):raise ValueError('Use 1–5 exact alarm names')
    return native,extra


def scope(config):
    return {k:v for k,v in config.items() if k in ('context','namespace','resource','owner','repository','profile','region','account','job','service','workflow_id')}


def timestamp(value):
    if not isinstance(value,str):raise ValueError('Timestamp unavailable')
    result=datetime.fromisoformat(value.replace('Z','+00:00'))
    if result.tzinfo is None:raise ValueError('Timestamp requires timezone')
    return result.timestamp()


def secrets(adapter):
    values=[os.environ.get(binding.get('env',''),'') for binding in adapter.config.get('headers',{}).values()]
    values.extend(os.environ.get(key,'') for key in (adapter.config.get('basic_auth') or {}).values())
    return values


def text(adapter,value,limit=160):return clean(value,secrets(adapter),limit)


def github_read(adapter,path,log=False,transport=None):
    transport=transport or Transport()
    try:
        status,headers,raw=transport.request('GET','https://api.github.com'+adapter.render(path,url=True),adapter.headers(),None,5)
        if log and status in (301,302,303,307,308):
            location=next((v for k,v in headers.items() if k.lower()=='location'),'')
            parsed,_=destination(location,allow_query=True)
            allowed=parsed.hostname in ('github.com','githubusercontent.com') or any(parsed.hostname.endswith('.'+suffix) for suffix in ('githubusercontent.com','blob.core.windows.net','amazonaws.com'))
            if parsed.scheme!='https' or not allowed:raise EvidenceError('GitHub log redirect destination unsupported')
            # Never forward API authentication to signed download URLs.
            status,_,raw=transport.request('GET',location,{'Accept':'text/plain'},None,5)
    except ProviderError as exc:raise EvidenceError('GitHub transport unavailable ('+exc.code+'); collection remains inconclusive') from None
    if status in (401,403):raise EvidenceError('GitHub authentication or read permission denied; check the private credential scope')
    if status==429:raise EvidenceError('GitHub API rate limited; no automatic request storm or mutation retry')
    if status!=200:raise EvidenceError('GitHub API response unavailable or unsupported')
    if log:return raw.decode('utf-8',errors='replace')
    return json.loads(raw)


def github_actions(adapter,extra,read=github_read):
    run=read(adapter,adapter.profile['endpoint'])
    if not isinstance(run,dict) or type(run.get('id')) is not int or str(run['id'])!=adapter.config['resource']:raise EvidenceError('GitHub run identity mismatch')
    if extra.get('workflow_id') and str(run.get('workflow_id'))!=extra['workflow_id']:raise EvidenceError('GitHub workflow identity mismatch')
    if run.get('status') not in ('queued','in_progress','completed','waiting','pending','requested'):raise EvidenceError('Unknown GitHub run state')
    if not isinstance(run.get('head_sha'),str) or not re.fullmatch(r'[a-fA-F0-9]{40}',run['head_sha']):raise EvidenceError('GitHub commit identity unavailable')
    observations=adapter.parse(json.dumps(run));snapshot=dict(tool=adapter.tool,collected_at=time.time(),observations=observations,transport_code=200,errors=[],truncated=False,empty=False)
    result=dict(run={'id':run['id'],'status':run['status'],'conclusion':text(adapter,run.get('conclusion') or 'unknown',40),'commit':run['head_sha'],'branch':text(adapter,run.get('head_branch','unknown'))},jobs=[],history=[],errors=[],log_signals={})
    try:
        start=timestamp(run['run_started_at']);end=timestamp(run['updated_at']);result['run']['observed_duration_seconds']=end-start if end>=start else None
    except (ValueError,KeyError,TypeError):result['run']['observed_duration_seconds']=None
    if run.get('conclusion') in ('failure','timed_out','startup_failure','action_required'):
        findings=[finding('github-actions:failed','Workflow execution failed','Run '+str(run['id'])+' reports '+run['conclusion'],'Inspect failed job steps, bounded logs and the exact commit; scheduling a rerun is not recovery.')]
    else:findings=[]
    if run['status']=='completed' and run.get('conclusion') not in ('success','failure','neutral','cancelled','skipped','timed_out','action_required','startup_failure','stale'):result['errors'].append('Completed run has no recognized conclusion')
    jobs=read(adapter,'/repos/$owner/$repository/actions/runs/$resource/jobs?per_page=20')
    if not isinstance(jobs,dict) or not isinstance(jobs.get('jobs'),list) or len(jobs['jobs'])>20:raise EvidenceError('Malformed GitHub jobs response')
    if type(jobs.get('total_count')) is int and jobs['total_count']>20:result['errors'].append('Job evidence truncated to the first 20 jobs')
    log_requests=0
    for job in jobs['jobs']:
        if not isinstance(job,dict) or type(job.get('id')) is not int or job['id']<1 or job.get('run_id')!=run['id']:raise EvidenceError('GitHub job identity mismatch')
        steps=job.get('steps',[])
        if not isinstance(steps,list) or len(steps)>40 or any(not isinstance(s,dict) for s in steps):raise EvidenceError('Malformed GitHub steps')
        item={k:text(adapter,job.get(k,'unknown'),120) for k in ('name','status','conclusion')};item['id']=job['id']
        item['steps']=[{k:text(adapter,s.get(k,''),120) for k in ('name','number','status','conclusion')} for s in steps]
        result['jobs'].append(item)
        if extra.get('logs') and job.get('conclusion') in ('failure','timed_out') and log_requests<2:
            log_requests+=1
            try:
                for key,count in signatures(read(adapter,'/repos/$owner/$repository/actions/jobs/'+str(job['id'])+'/logs',log=True)).items():result['log_signals'][key]=result['log_signals'].get(key,0)+count
            except (EvidenceError,ValueError,RuntimeError,OSError):result['errors'].append('Bounded failed-job logs unavailable; raw bodies are not retained')
    if extra.get('history'):
        history=read(adapter,'/repos/$owner/$repository/actions/workflows/'+extra['workflow_id']+'/runs?per_page=10')
        if not isinstance(history,dict) or not isinstance(history.get('workflow_runs'),list) or len(history['workflow_runs'])>10:raise EvidenceError('Malformed workflow history')
        for r in history['workflow_runs']:
            if not isinstance(r,dict) or str(r.get('workflow_id'))!=extra['workflow_id'] or type(r.get('id')) is not int:raise EvidenceError('Workflow history scope mismatch')
            result['history'].append({k:text(adapter,r.get(k,''),120) for k in ('id','status','conclusion','head_sha','head_branch','created_at','updated_at')})
    findings.extend(signal_findings(result['log_signals']))
    return snapshot,result,findings


def jenkins_extra(adapter,extra,number):
    result={'history':[],'stages':[],'errors':[]}
    if extra.get('history'):
        raw,_=adapter.request('/job/$resource/api/json?tree=builds[number,result,building,duration,timestamp]{0,10}')
        data=json.loads(raw)
        if not isinstance(data,dict) or not isinstance(data.get('builds'),list) or len(data['builds'])>10:raise EvidenceError('Malformed bounded Jenkins history')
        for build in data['builds']:
            if not isinstance(build,dict) or type(build.get('number')) is not int or build['number']<1:raise EvidenceError('Malformed Jenkins build identity')
            result['history'].append({k:text(adapter,build.get(k),120) if isinstance(build.get(k),str) else build.get(k) for k in ('number','result','building','duration','timestamp') if type(build.get(k)) in (str,int,bool) or build.get(k) is None})
    if extra.get('stages'):
        try:
            raw,_=adapter.request('/job/$resource/'+str(number)+'/wfapi/describe');data=json.loads(raw)
            if not isinstance(data,dict) or str(data.get('id'))!=str(number) or not isinstance(data.get('stages'),list) or len(data['stages'])>40:raise ValueError('Incompatible stages')
            result['stages']=[{k:text(adapter,s.get(k,''),120) for k in ('name','status','durationMillis','startTimeMillis')} for s in data['stages'] if isinstance(s,dict)]
        except (ValueError,RuntimeError,OSError):result['errors'].append('Optional Pipeline REST stage API unavailable or incompatible')
    return result


def prometheus_job(adapter,job,now=None):
    now=time.time() if now is None else now
    query='up{job="'+job+'"}'
    raw,_=adapter.request('/api/v1/query?'+urlencode({'query':query}));data=json.loads(raw)
    if not isinstance(data,dict) or data.get('status')!='success' or data.get('data',{}).get('resultType')!='vector':raise EvidenceError('Prometheus instant-vector evidence unavailable')
    samples=data['data'].get('result')
    if not isinstance(samples,list) or not 1<=len(samples)<=50:raise EvidenceError('Prometheus evidence missing or scope too broad')
    projected=[]
    for sample in samples:
        if not isinstance(sample,dict) or sample.get('metric',{}).get('job')!=job:raise EvidenceError('Prometheus job scope mismatch')
        value=sample.get('value')
        if not isinstance(value,list) or len(value)!=2 or type(value[0]) not in (int,float) or not math.isfinite(value[0]) or not 0<=now-value[0]<=30 or value[1] not in ('0','1'):raise EvidenceError('Prometheus sample stale, future, malformed or non-binary')
        projected.append(dict(timestamp=value[0],value=int(value[1])))
    return dict(job=job,samples=projected,healthy=all(s['value']==1 for s in projected),max_age_seconds=30)


def aws_call(adapter,service,operation,*args):
    # Only fixed call sites below supply verbs. No command endpoint accepts user argv.
    allowed={('sts','get-caller-identity'),('ec2','describe-instances'),('cloudwatch','get-metric-statistics'),('cloudwatch','describe-alarms'),('elbv2','describe-target-health'),('autoscaling','describe-auto-scaling-groups'),('logs','get-log-events')}
    if (service,operation) not in allowed:raise ValueError('AWS operation is not read-only allowlisted')
    raw,_=adapter.command(['aws','--profile','$profile','--region','$region','--cli-connect-timeout','3','--cli-read-timeout','5',service,operation,*args,'--output','json','--no-paginate'],read_timeout=8)
    return json.loads(raw)


def aws_account(adapter,extra):
    if 'account' not in extra:return None
    data=aws_call(adapter,'sts','get-caller-identity')
    if not isinstance(data,dict) or data.get('Account')!=extra['account']:raise EvidenceError('AWS account mismatch or identity unavailable; no resource extension was collected')
    return data['Account']


def aws_extra(adapter,extra,account,now=None):
    now=time.time() if now is None else now
    result=dict(account=account or 'not independently verified',region=adapter.config['region'],errors=[],metrics={},alarms=[],log_signals={});findings=[]
    if extra.get('metadata'):
        data=aws_call(adapter,'ec2','describe-instances','--instance-ids',adapter.config['resource'])
        records=[i for r in data.get('Reservations',[]) for i in r.get('Instances',[])]
        if len(records)!=1 or records[0].get('InstanceId')!=adapter.config['resource']:raise EvidenceError('EC2 metadata target mismatch')
        r=records[0];result['instance']=dict(id=r['InstanceId'],state=r.get('State',{}).get('Name','unknown'),availability_zone=r.get('Placement',{}).get('AvailabilityZone','unknown'),image=r.get('ImageId','unknown'),type=r.get('InstanceType','unknown'))
    if extra.get('metrics'):
        start=datetime.fromtimestamp(now-900,timezone.utc).isoformat();end=datetime.fromtimestamp(now,timezone.utc).isoformat()
        for metric,stat,maximum in [('CPUUtilization','Average',100),('StatusCheckFailed_Instance','Maximum',1),('StatusCheckFailed_System','Maximum',1)]:
            data=aws_call(adapter,'cloudwatch','get-metric-statistics','--namespace','AWS/EC2','--metric-name',metric,'--dimensions','Name=InstanceId,Value='+adapter.config['resource'],'--start-time',start,'--end-time',end,'--period','60','--statistics',stat)
            points=data.get('Datapoints')
            if not isinstance(points,list) or len(points)>32:raise EvidenceError('Malformed CloudWatch metric response')
            fresh=[]
            for p in points:
                if not isinstance(p,dict):raise EvidenceError('Malformed CloudWatch datapoint')
                stamp=timestamp(p['Timestamp']);value=p.get(stat)
                if stamp>now:raise EvidenceError('Future CloudWatch datapoint')
                if any(t==stamp and v!=value for t,v in fresh):raise EvidenceError('Conflicting CloudWatch datapoints')
                if type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=maximum:raise EvidenceError('Malformed CloudWatch datapoint')
                if 0<=now-stamp<=300:fresh.append((stamp,value))
            if not fresh:result['errors'].append('Missing or stale CloudWatch metric: '+metric);continue
            latest=max(fresh);result['metrics'][metric]=dict(timestamp=latest[0],value=latest[1])
            if (metric=='CPUUtilization' and latest[1]>=85) or (metric!='CPUUtilization' and latest[1]>0):findings.append(finding('aws:'+metric,'Configured EC2 metric warning',metric+'='+str(latest[1]),'Inspect instance/application evidence and resource limits; no EC2 or IAM mutation is authorized.'))
    if extra.get('target_group_arn'):
        data=aws_call(adapter,'elbv2','describe-target-health','--target-group-arn',extra['target_group_arn']);targets=data.get('TargetHealthDescriptions')
        if not isinstance(targets,list) or len(targets)>100:raise EvidenceError('Malformed ALB target health')
        for t in targets:
            if not isinstance(t,dict) or not isinstance(t.get('Target'),dict) or not isinstance(t.get('TargetHealth'),dict) or not isinstance(t['Target'].get('Id'),str) or t['TargetHealth'].get('State') not in ('healthy','unhealthy','initial','draining','unused','unavailable'):raise EvidenceError('Malformed ALB target state')
        result['targets']=[dict(id=text(adapter,t['Target']['Id']),port=t['Target'].get('Port') if type(t['Target'].get('Port')) is int else None,state=t['TargetHealth']['State']) for t in targets]
        if not targets:result['errors'].append('ALB target group has no target evidence')
        if any(t['state']!='healthy' for t in result['targets']):findings.append(finding('aws:target-health','ALB targets are not all healthy','Configured target group has non-healthy state','Check target readiness, routing and health-check settings with read-only access.'))
    if extra.get('auto_scaling_group'):
        data=aws_call(adapter,'autoscaling','describe-auto-scaling-groups','--auto-scaling-group-names',extra['auto_scaling_group']);groups=data.get('AutoScalingGroups')
        if not isinstance(groups,list) or len(groups)!=1 or groups[0].get('AutoScalingGroupName')!=extra['auto_scaling_group']:raise EvidenceError('Auto Scaling group identity mismatch')
        group=groups[0]
        if any(type(group.get(k)) is not int or group[k]<0 for k in ('MinSize','MaxSize','DesiredCapacity')) or not group['MinSize']<=group['DesiredCapacity']<=group['MaxSize']:raise EvidenceError('Malformed Auto Scaling capacity')
        if not isinstance(group.get('Instances'),list) or any(not isinstance(i,dict) for i in group['Instances']):raise EvidenceError('Malformed Auto Scaling membership')
        result['auto_scaling']={k:group.get(k) for k in ('MinSize','MaxSize','DesiredCapacity')};result['auto_scaling']['selected_instance']=[{k:i.get(k) for k in ('InstanceId','LifecycleState','HealthStatus')} for i in group.get('Instances',[]) if i.get('InstanceId')==adapter.config['resource']][:1]
    if extra.get('alarm_names'):
        data=aws_call(adapter,'cloudwatch','describe-alarms','--alarm-names',*extra['alarm_names']);alarms=data.get('MetricAlarms',[])+data.get('CompositeAlarms',[])
        if len(alarms)>5 or any(a.get('AlarmName') not in extra['alarm_names'] for a in alarms):raise EvidenceError('CloudWatch alarm scope mismatch')
        for alarm in alarms:
            state=alarm.get('StateValue')
            if state not in ('OK','ALARM','INSUFFICIENT_DATA'):raise EvidenceError('Unknown CloudWatch alarm state')
            result['alarms'].append(dict(name=alarm['AlarmName'],state=state,updated=alarm.get('StateUpdatedTimestamp')))
            if state=='INSUFFICIENT_DATA':result['errors'].append('Alarm has insufficient data: '+alarm['AlarmName'])
            if state=='ALARM':findings.append(finding('aws:alarm','Configured CloudWatch alarm firing',alarm['AlarmName'],'Inspect alarm dimensions and actual metric evidence before proposing any recovery.'))
        if {a['name'] for a in result['alarms']}!=set(extra['alarm_names']):result['errors'].append('Some configured alarms are missing')
    if extra.get('log_group'):
        data=aws_call(adapter,'logs','get-log-events','--log-group-name',extra['log_group'],'--log-stream-name',extra['log_stream'],'--limit','100','--start-time',str(int((now-900)*1000)),'--end-time',str(int(now*1000)))
        events=data.get('events')
        if not isinstance(events,list) or len(events)>100 or any(not isinstance(e.get('message'),str) for e in events):raise EvidenceError('Malformed bounded log events')
        result['log_signals']=signatures('\n'.join(e['message'] for e in events));findings.extend(signal_findings(result['log_signals']))
    return result,findings


def docker_metrics(adapter):
    """One bounded stats read pinned to the collected daemon/container identity."""
    ident=adapter.container_id;daemon=adapter.daemon
    if not isinstance(ident,str) or not re.fullmatch(r'[a-f0-9]{64}',ident):raise EvidenceError('Docker metrics require an exact collected container identity')
    raw,_=adapter.command(['docker','--context','$context','container','stats','--no-stream','--no-trunc','--format','{{json .}}',ident],read_timeout=8)
    data=json.loads(raw)
    if not isinstance(data,dict) or data.get('ID')!=ident:raise EvidenceError('Docker metric container identity mismatch')
    # Reinspect immediately after collection to reject replacement or context changes.
    after=adapter.collect()
    if adapter.container_id!=ident or adapter.daemon!=daemon or after.get('observations',{}).get('id')!=[ident]:raise EvidenceError('Docker target changed during metric collection')
    result={'container_id':ident,'collected_at':time.time(),'cpu_scope':'Docker CPU percentage; 100% represents one logical CPU, not the entire host'}
    for source,target,maximum in [('CPUPerc','cpu_percent',100000),('MemPerc','memory_percent',100)]:
        value=data.get(source)
        if not isinstance(value,str) or not re.fullmatch(r'[0-9]+(?:\.[0-9]+)?%',value):raise EvidenceError('Docker resource percentage unavailable or malformed')
        numeric=float(value[:-1])
        if not math.isfinite(numeric) or not 0<=numeric<=maximum:raise EvidenceError('Docker resource percentage out of bounds')
        result[target]=numeric
    usage=data.get('MemUsage')
    if not isinstance(usage,str) or not re.fullmatch(r'[0-9.]+ ?[kMGTPE]?i?B / [0-9.]+ ?[kMGTPE]?i?B',usage) or len(usage)>80:raise EvidenceError('Docker memory usage unavailable or malformed')
    result['memory_usage']=usage
    findings=[]
    if result['cpu_percent']>=85:findings.append(finding('docker:cpu','Elevated container CPU sample','Docker CPU='+str(result['cpu_percent'])+'% of one logical CPU','Compare sustained usage, CPU quota and host capacity; a single sample does not prove exhaustion.'))
    if result['memory_percent']>=90:findings.append(finding('docker:memory','Elevated container memory sample','Docker memory='+str(result['memory_percent'])+'% of reported limit','Compare sustained usage, cgroup limit and OOM evidence before proposing recovery.'))
    return result,findings
