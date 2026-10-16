import asyncio,json,time,os
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

async def main():
    read=os.environ['ZSK_API_KEY'];admin=os.environ['ZSK_ADMIN_API_KEY'];base='http://127.0.0.1:8000'
    with httpx.Client(base_url=base,trust_env=False,headers={'Authorization':'Bearer '+read}) as client:
        assert client.get('/ready').status_code==200
        assert client.get('/api/model/status').json()['counts']=={'labeled':0,'unlabeled':1000}
        assert client.post('/api/model/train',json={'idempotency_key':'unauthorized-test-v1'}).status_code==403
        assert client.post('/api/model/predict',json={'measurement_id':1000}).status_code==200
        assert client.get('/api/measurements?page=10&page_size=100').status_code==200
        assert client.get('/api/measurements?page_size=101').status_code==422
        assert httpx.get(base+'/api/model/status',trust_env=False).status_code==401
    async with streamable_http_client(base+'/mcp',http_client=httpx.AsyncClient(headers={'Authorization':'Bearer '+admin},trust_env=False,timeout=20)) as (r,w,_):
        async with ClientSession(r,w) as session:
            await session.initialize();tools=await session.list_tools()
            names=[t.name for t in tools.tools];assert len(names)==8
            predicted=await session.call_tool('predict_zsk_health',{'measurement_id':1000})
            assert not predicted.isError
            batch=await session.call_tool('batch_predict_zsk_health',{'idempotency_key':'zsk-initial-inference-v1','page_size':37})
            assert not batch.isError
            content=batch.structuredContent
            if set(content)=={'result'}:content=content['result']
            job_id=content['job_id']
            for _ in range(100):
                status=await session.call_tool('get_zsk_training_status',{'job_id':job_id})
                assert not status.isError, status.content
                body=status.structuredContent
                if set(body)=={'result'}:body=body['result']
                if body['status'] in ('completed','failed'):break
                await asyncio.sleep(.2)
            assert body['status']=='completed',body
            result=await session.call_tool('get_zsk_predictions',{'job_id':job_id,'page_size':5})
            outputs=result.structuredContent
            if set(outputs)=={'result'}:outputs=outputs['result']
            assert outputs['total']==1000
            repeated=await session.call_tool('batch_predict_zsk_health',{'idempotency_key':'zsk-initial-inference-v1','page_size':37})
            repeat=repeated.structuredContent
            if set(repeat)=={'result'}:repeat=repeat['result']
            assert repeat['job_id']==job_id
            print(json.dumps({'mcp_tools':names,'job_id':job_id,'stored_predictions':1000,'prediction':predicted.structuredContent,'auth_checks':'passed','batch_idempotency':'passed'},default=str))
asyncio.run(main())
