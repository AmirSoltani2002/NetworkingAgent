"""Operator-run local setup. No secrets printed or passed as command arguments."""
import argparse,json,re,secrets,urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def read_env():
    values={}
    for line in (ROOT/'.env').read_text().splitlines():
        m=re.match(r'^([A-Z][A-Z0-9_]*)=(.*)$',line)
        if m:
            raw=m[2].strip()
            if raw.startswith('"'):
                try:raw=json.loads(raw)
                except ValueError:raw=raw.strip('"')
            values[m[1]]=raw
    return values

def write_env(changes):
    p=ROOT/'.env';s=p.read_text()
    for k,v in changes.items():
        line=k+'='+str(v)
        if re.search(r'^'+k+r'=.*$',s,re.M):s=re.sub(r'^'+k+r'=.*$',lambda m:line,s,flags=re.M)
        else:s+='\n'+line+'\n'
    with p.open('r+') as f:f.write(s);f.truncate()
    p.chmod(0o600)

def request(base,path,body=None,method=None,token=None):
    headers={'Content-Type':'application/json'}
    if token:headers['Authorization']='Bearer '+token
    req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers,method=method or ('POST' if body is not None else 'GET'))
    with urllib.request.urlopen(req,timeout=30) as r:return json.load(r)

def main():
    parser=argparse.ArgumentParser(description='Configure simulation-only factory integration and explicit diagnostic task grants')
    parser.add_argument('--core-url',default='http://127.0.0.1:8000/api');parser.add_argument('--factory-url',default='http://factory:8110')
    parser.add_argument('--rag-device-id',required=True,help='Explicit existing RAG device UUID, simulation mapping only')
    parser.add_argument('--demo-stop',action='store_true',help='Explicitly authorize automatic SIMULATED stops; restart/maintenance remain disabled')
    args=parser.parse_args();from uuid import UUID;UUID(args.rag_device_id)
    env=read_env();changes={}
    for key in ('FACTORY_API_TOKEN','FACTORY_MCP_AUTH_TOKEN','TASK_INTEGRATION_TOKEN'):
        if not env.get(key):changes[key]=secrets.token_urlsafe(36)
    origins=env.get('MCP_ALLOWED_ORIGINS','http://rag-api:8090,http://manufacturing-ml:8000').split(',')
    if args.factory_url not in origins:origins.append(args.factory_url)
    changes.update(FACTORY_API_URL=args.factory_url,FACTORY_ALLOWED_ORIGINS=args.factory_url+',http://127.0.0.1:8110',MCP_ALLOWED_ORIGINS=','.join(origins))
    write_env(changes);env=read_env()
    profiles=request(args.core_url,'/mcp/servers')
    factory=next((p for p in profiles if p['url']==args.factory_url+'/mcp'),None)
    if not factory:factory=request(args.core_url,'/mcp/servers',{'name':'Simulation-only ZSK Factory','url':args.factory_url+'/mcp','authEnvVar':'FACTORY_MCP_AUTH_TOKEN'})
    discovered=request(args.core_url,'/mcp/servers/'+factory['id']+'/discover',{})
    allowed=[t['name'] for t in discovered['tools'] if t['readOnly']]+['move_character','inspect_component','assign_maintenance_task','acknowledge_alarm']
    if args.demo_stop:allowed+=['stop_manufacturing_line','pause_manufacturing_line']
    request(args.core_url,'/mcp/servers/'+factory['id']+'/permissions',{'allowedTools':allowed,'enabled':True},'PUT')
    rag=[p for p in profiles if p['enabled'] and p['agentEnabled'] and 'search_knowledge' in p['allowedTools']]
    if len(rag)!=1:raise RuntimeError('Exactly one enabled/allowlisted RAG knowledge profile is required; configure it in the existing UI first')
    ml=[p for p in profiles if 'get_zsk_model_metrics' in p['allowedTools'] and p['enabled'] and p['agentEnabled']]
    if len(ml)==1:
        latest=request(args.core_url,'/mcp/servers/'+ml[0]['id']+'/discover',{})
        forecast_tools=[t['name'] for t in latest['tools'] if t['name'] in ('get_zsk_forecast_metrics','predict_zsk_future_failure') and t['readOnly']]
        request(args.core_url,'/mcp/servers/'+ml[0]['id']+'/permissions',{'allowedTools':list(dict.fromkeys(ml[0]['allowedTools']+forecast_tools)),'enabled':True},'PUT')
    controlled=set(filter(None,env.get('TASK_CONTROLLED_MCP_TOOLS','').split(',')))
    controlled.update(factory['id']+':'+tool for tool in allowed if not next(t['readOnly'] for t in discovered['tools'] if t['name']==tool))
    write_env(dict(FACTORY_SERVER_ID=factory['id'],FACTORY_RAG_SERVER_ID=rag[0]['id'],FACTORY_RAG_DEVICE_ID=args.rag_device_id,
     FACTORY_TASK_TEMPLATE='factory-stop-demo' if args.demo_stop else 'manufacturing-alert',TASK_CONTROLLED_MCP_TOOLS=','.join(sorted(controlled)),
     SIMULATION_AUTO_STOP_ALLOWED='true' if args.demo_stop else 'false',SIMULATION_AUTO_RESTART_ALLOWED='false',SIMULATION_AUTO_MAINTENANCE_ALLOWED='false'))
    print('Factory profile:',factory['id']);print('Diagnostic grants configured. Simulated auto-stop:',args.demo_stop)
    print('Recreate core and factory to load task policy/environment; tokens remain only in root .env.')
if __name__=='__main__':main()
