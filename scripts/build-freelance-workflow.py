"""Generate a credential-free, importable n8n canvas. No third-party code is bundled."""
import json
from pathlib import Path
import uuid

ROOT = Path(__file__).resolve().parents[1]
NODES=[]; CONNECTIONS={}

def node(name, kind, params, xy, version=1, **extra):
    n=dict(id=str(uuid.uuid5(uuid.NAMESPACE_URL, 'ops-pilot/'+name)), name=name, type='n8n-nodes-base.'+kind,
           typeVersion=version, position=xy, parameters=params, **extra)
    NODES.append(n); return name

def link(a,b,port=0):
    ports=CONNECTIONS.setdefault(a, {'main':[]})['main']
    while len(ports)<=port: ports.append([])
    ports[port].append(dict(node=b,type='main',index=0))

def credential(role):
    return {'httpHeaderAuth': {'id':'CONFIGURE_'+role.upper()+'_CREDENTIAL', 'name':'Ops Pilot '+role.title()}}

def http(name, xy, body=None, path='/bridge/action', role='workflow', download=False):
    params=dict(method='POST' if body else 'GET', url='http://127.0.0.1:8767'+path,
                authentication='genericCredentialType',genericAuthType='httpHeaderAuth',options={'timeout':10000})
    if body: params.update(sendBody=True,specifyBody='json',jsonBody='={{ '+body+' }}')
    if download: params['options']['response']={'response':{'responseFormat':'file','outputPropertyName':'data'}}
    return node(name,'httpRequest',params,xy,4.2,credentials=credential(role),retryOnFail=False)

def agent(name,action,xy):
    return http(name,xy,"{ action: '"+action+"', job_id: $json.job.id, revision: $json.job.revision }")

def field(label,kind='text',**kw): return dict(fieldLabel=label,fieldType=kind,**kw)

def dropdown(label,values):return field(label,'dropdown',fieldOptions={'values':[{'option':s} for s in values]},requiredField=label=='Task')

F="$('Freelance control centre').first().json"
fields=[dropdown('Task',['View board','Import listing','Generate starter files','Owner decision','Download handover']),
        field('Project title'),field('Requirements','textarea'),field('Source',placeholder='Upwork, Fiverr or direct client'),
        field('Listing URL'),field('Budget',placeholder='0.00'),dropdown('Currency',['USD','INR','EUR','GBP']),
        field('Job ID',placeholder='Copy from the board'),field('Revision','number',placeholder='Copy current revision from the board'),
        dropdown('Decision',['approve_proposal','accept','approve_work','sign_off','delivery','earnings','payment','reject','edit_proposal','brief','task','scope_change','invoice','expense','time_entry','validation','customer_acceptance','offboard','close','quote','intake_check','draft_message']),
        field('Confirm job ID',placeholder='Type the ID for acceptance, work approval or sign-off'),
        field('Application image',placeholder='Existing trusted image, for starter files only'),
        field('Internal port','number',placeholder='8000'),field('Health path',placeholder='/health'),
        field('Record JSON','textarea',placeholder='For business records only: JSON object matching the owner desk schema'),field('Edited proposal','textarea'),field('Payment amount'),field('Platform fee'),field('Payment reference')]
node('Freelance control centre','formTrigger',dict(authentication='basicAuth',formTitle='Ops Pilot · Freelance control centre',
     formDescription='View all nine roles, project outputs and earnings. Choose a task. For View board, other fields can stay empty/default. Import needs title and requirements. Generate needs job ID, revision and image. Owner decisions need current job ID and revision; confirm the ID when requested. No live deployment or client submission.',
     formFields={'values':fields},responseMode='lastNode',options={}),[0,400],2.2,
     webhookId='ops-pilot-freelance-control',credentials={'httpBasicAuth':{'id':'CONFIGURE_FORM_LOGIN','name':'Ops Pilot Form Login'}})
values=[]
for task in ['Import listing','Generate starter files','Owner decision','View board','Download handover']:
    values.append(dict(conditions={'options':{'caseSensitive':True,'leftValue':'','typeValidation':'strict','version':2},
                                  'conditions':[{'id':str(uuid.uuid5(uuid.NAMESPACE_URL,task)),'leftValue':'={{ $json.Task }}','rightValue':task,'operator':{'type':'string','operation':'equals'}}], 'combinator':'and'},
                      renameOutput=True,outputKey=task))
node('Manager · route owner request','switch',{'rules':{'values':values},'options':{}},[270,400],3.2)
link('Freelance control centre','Manager · route owner request')
intake=http('Import owner-provided listing',[560,0],"{ action:'import', data:{ title:$json['Project title'], description:$json.Requirements, platform:$json.Source || 'manual', url:$json['Listing URL'] || '', budget:String($json.Budget || '0'), currency:$json.Currency || 'USD' } }")
link('Manager · route owner request',intake,0)
last=intake
for i,(name,action) in enumerate([('01 · Scout','scout'),('02 · Evaluator','evaluator'),('03 · Manager','manager'),('04 · Client assistant','client'),('05 · Proposal writer','proposal')]):
    nxt=agent(name,action,[790+230*i,0]);link(last,nxt);last=nxt
end=node('All projects and outputs','form',dict(operation='completion',respondWith='showText',responseText='={{ $json.summary_html }}'),[2210,400])
link(last,end)
worker=http('06 · DevOps worker',[560,240],"{action:'worker',job_id:$json['Job ID'],revision:Number($json.Revision),data:{image:$json['Application image'],port:Number($json['Internal port'] || 8000),health_path:$json['Health path'] || '/health'} }")
link('Manager · route owner request',worker,1)
reviewer=agent('07 · Reviewer','reviewer',[820,240]);link(worker,reviewer);link(reviewer,end)
owner=http('Owner decision · explicit review',[560,480],"{action:$json.Decision,job_id:$json['Job ID'],revision:Number($json.Revision),data: ($json['Record JSON'] ? JSON.parse($json['Record JSON']) : {confirmation:$json['Confirm job ID'] || '',draft:$json['Edited proposal'] || '',amount:$json['Payment amount'] || '0',fee:$json['Platform fee'] || '0',reference:$json['Payment reference'] || ''})}",role='owner')

# Delivery is a distinct worker node: choose delivery in the owner form, route to it, never pretend it ran otherwise.
node('Delivery requested?','if',{'conditions':{'options':{'caseSensitive':True,'leftValue':'','typeValidation':'strict','version':2},
     'conditions':[{'id':'delivery-condition','leftValue':'={{ '+F+'.Decision }}','rightValue':'delivery','operator':{'type':'string','operation':'equals'}}],'combinator':'and'},'options':{}},[820,480],2.2)
# Delivery executes with the workflow credential only after stored owner sign-off.
http('08 · Delivery assistant',[1080,430],"{action:'delivery',job_id:$json['Job ID'],revision:Number($json.Revision)}")
link('Manager · route owner request','Delivery requested?',2);link('Delivery requested?','08 · Delivery assistant',0);link('Delivery requested?',owner,1)
earnings=agent('09 · Earnings tracker','earnings',[1370,480]);link('08 · Delivery assistant',earnings);link(owner,earnings);link(earnings,end)
board=http('Refresh full board',[560,740],path='/bridge/board');link('Manager · route owner request',board,3);link(board,end)
download=http('Download reviewed ZIP',[560,980],path="/bridge/package?job_id={{ encodeURIComponent($json['Job ID']) }}",download=True)
# URL expressions must start with '=' when mixing literal text and expressions.
NODES[-1]['parameters']['url']='=http://127.0.0.1:8767/bridge/package?job_id={{ encodeURIComponent($json["Job ID"]) }}'
link('Manager · route owner request',download,4)
file_end=node('Handover ZIP','form',dict(operation='completion',respondWith='returnBinary',inputDataFieldName='data',completionTitle='Reviewed starter bundle',completionMessage='Generated files only. No live deployment or client submission.'),[900,980]);link(download,file_end)
for name,content,xy,w,h,color in [
 ('Start here','## FREELANCE STUDIO\nOne control form · five routes · nine bounded local roles\nConfigure Form Login + Workflow + Owner credentials. Use Execute Workflow, then submit the form. No credentials are included.',[-30,-390],650,240,6),
 ('Intake lane','## 01 / DISCOVER & PLAN\nOwner-provided text → skill match → questions → proposal. No scraping or auto-bidding.',[550,-220],1600,180,4),
 ('Work lane','## 02 / BUILD & CHECK\nRequires recorded client acceptance + separate work approval. Existing Docker image only. Static review, not live validation.',[550,110],1080,100,5),
 ('Owner lane','## 03 / YOU DECIDE\nApprove proposal → accept → approve work → generate → review → sign off → package. Use current revision. Owner credential belongs only on this lane.',[550,590],1080,100,3),
 ('View lane','## 04 / YOUR BOARD\nAll job outputs, artifact contents, statuses and earnings. Download packaged files using the fifth route.',[1130,810],750,180,6)]:
 node(name,'stickyNote',dict(content=content,width=w,height=h,color=color),xy)
workflow=dict(name='Ops Pilot · Freelance Agency · 9 roles',nodes=NODES,connections=CONNECTIONS,active=False,
              settings={'executionOrder':'v1','saveDataErrorExecution':'all','saveDataSuccessExecution':'all','saveManualExecutions':True},
              pinData={},tags=[],versionId=str(uuid.uuid5(uuid.NAMESPACE_URL,'ops-pilot-freelance-v1')))
(ROOT/'n8n/freelance-agency.json').write_text(json.dumps(workflow,indent=2)+'\n')
print('Generated',len(NODES),'nodes with',len(CONNECTIONS),'connections')
