from uuid import uuid4
from fastapi.testclient import TestClient
from factory.api import create_app
from test_database import store


def test_rest_mcp_auth_ws_and_confirmed_actions(store):
    with TestClient(create_app(store.settings),base_url="http://127.0.0.1:8110") as client:
        assert client.get('/api/state').status_code==401
        api={'Authorization':'Bearer '+store.settings.api_token.get_secret_value()}
        mcp={'Authorization':'Bearer '+store.settings.mcp_auth_token.get_secret_value(),'Accept':'application/json, text/event-stream'}
        assert client.get('/api/state',headers=mcp).status_code==401
        state=client.get('/api/state',headers=api).json()
        assert state['machine_id']=='ZSK-SIM-01'
        init={'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'factory-test','version':'1'}}}
        assert client.post('/mcp',headers=api,json=init).status_code==401
        response=client.post('/mcp',headers=mcp,json=init);assert response.status_code==200,response.text
        tools=client.post('/mcp',headers=mcp,json={'jsonrpc':'2.0','id':2,'method':'tools/list','params':{}}).json()['result']['tools']
        assert len(tools)==17
        stop=next(t for t in tools if t['name']=='stop_manufacturing_line');assert not stop['annotations']['readOnlyHint']
        assert all(t['inputSchema']['additionalProperties'] is False for t in tools)
        result=client.post('/mcp',headers=mcp,json={'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'get_machine_state','arguments':{'machine_id':'ZSK-SIM-01'}}}).json()['result']
        assert result['structuredContent']['machine_id']=='ZSK-SIM-01'
        assert result['structuredContent']['latest_measurement']==state['latest_measurement']
        assert 'actions' not in result['structuredContent']
        denied=client.post('/mcp',headers=mcp|{'Idempotency-Key':str(uuid4())},json={'jsonrpc':'2.0','id':4,'method':'tools/call','params':{'name':'start_manufacturing_line','arguments':{'machine_id':'ZSK-SIM-01','epoch':state['epoch']}}}).json()['result']
        assert denied['isError']
        # Distinct harness operations must not collide when a model reuses its
        # optional key. Re-delivery of one harness operation stays idempotent.
        shared=str(uuid4());operation=str(uuid4())
        body={'jsonrpc':'2.0','id':5,'method':'tools/call','params':{'name':'inspect_component','arguments':{'component_id':'gearbox','epoch':state['epoch'],'idempotency_key':shared}}}
        first=client.post('/mcp',headers=mcp|{'Idempotency-Key':operation},json=body).json()['result']
        assert not first.get('isError'),first
        again=client.post('/mcp',headers=mcp|{'Idempotency-Key':operation},json=body).json()['result']
        assert first['structuredContent']==again['structuredContent']
        client.app.state.store.settings.auto_stop_allowed=True
        body['params']={'name':'stop_manufacturing_line','arguments':{'machine_id':'ZSK-SIM-01','epoch':state['epoch'],'idempotency_key':shared}}
        stopped=client.post('/mcp',headers=mcp|{'Idempotency-Key':str(uuid4())},json=body).json()['result']
        assert not stopped.get('isError'),stopped
        assert stopped['structuredContent']['action_id']!=first['structuredContent']['action_id']
        body['params']={'name':'acknowledge_alarm','arguments':{'alarm_id':str(uuid4()),'idempotency_key':shared}}
        absent=client.post('/mcp',headers=mcp|{'Idempotency-Key':str(uuid4())},json=body).json()['result']
        assert absent.get('isError') # unknown alarm, never falsely acknowledged
        stale=client.post('/mcp',headers=mcp,json={'jsonrpc':'2.0','id':6,'method':'tools/call','params':{'name':'get_machine_state','arguments':{'machine_id':'ZSK-SIM-01','epoch':str(uuid4())}}}).json()['result']
        assert stale.get('isError')
        with client.websocket_connect('/ws',headers=api) as ws:
            snap=ws.receive_json();assert snap['type']=='factory.snapshot' and snap['version']>0
            key=str(uuid4());action={'kind':'clock','arguments':{'paused':True},'idempotency_key':key}
            first=client.post('/api/actions',headers=api,json=action).json()
            second=client.post('/api/actions',headers=api,json=action).json();assert first==second
            newer=ws.receive_json();assert newer['version']>snap['version'] and newer['state']['clock']['paused']
        client.app.state.store.action('clock',{'paused':False},str(uuid4()),operator=True)
        client.app.state.worker.tick(100)
        client.post('/api/actions',headers=api,json={'kind':'reset','arguments':{},'idempotency_key':str(uuid4())}).raise_for_status()
        client.post('/api/actions',headers=api,json={'kind':'clock','arguments':{'paused':False},'idempotency_key':str(uuid4())}).raise_for_status()
