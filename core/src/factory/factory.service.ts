import { BadRequestException, Injectable, ServiceUnavailableException, type OnApplicationBootstrap,type OnModuleDestroy } from '@nestjs/common';
import { HttpAdapterHost } from '@nestjs/core';
import { lookup } from 'node:dns';
import { WebSocket,WebSocketServer } from 'ws';
import type { Server } from 'node:http';
import { EnvironmentStore } from '../config/environment-store.service';
import { requireLocalOrigin } from '../config/local-origin';
import { approvedUrl,guardedFetch,safeAddress } from '../mcp/network-policy';
@Injectable()
export class FactoryService implements OnApplicationBootstrap,OnModuleDestroy {
 private wss?:WebSocketServer;
 constructor(private readonly environment:EnvironmentStore,private readonly adapter:HttpAdapterHost){}
 async connection(){
  const env=await this.environment.read();
  if(!env.FACTORY_API_URL||!env.FACTORY_API_TOKEN)throw new ServiceUnavailableException('Factory is not configured. See factory-service/README.md.');
  const origins=env.FACTORY_ALLOWED_ORIGINS??'http://factory:8110,http://127.0.0.1:8110';
  const url=approvedUrl(env.FACTORY_API_URL,origins);
  if(url.pathname!=='/')throw new BadRequestException('Factory URL must be an origin.');
  return{url,token:env.FACTORY_API_TOKEN,origins};
 }
 async request(path:string,method='GET',body?:unknown){
  const {url,token,origins}=await this.connection();
  try{
   const response=await guardedFetch(url.href,origins)(new URL('/api/'+path,url),{method,headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(20000)});
   const result=await response.json();
   if(!response.ok)throw new BadRequestException('Factory rejected this request. Check current state, identifiers and simulation policy.');
   return result;
  }catch(e){if(e instanceof BadRequestException)throw e;throw new ServiceUnavailableException('Factory temporarily unavailable; reconnect to inspect saved state.');}
 }
 onApplicationBootstrap(){
  this.wss=new WebSocketServer({noServer:true,maxPayload:1024,perMessageDeflate:false});
  const server=this.adapter.httpAdapter.getHttpServer() as Server;
  server.on('upgrade',(req,socket,head)=>{
   if(req.url!=='/api/factory/ws'){socket.destroy();return;}
   try{requireLocalOrigin(req.headers.origin);}catch{socket.destroy();return;}
   void this.connection().then(({url,token})=>{
    this.wss!.handleUpgrade(req,socket,head,client=>{
     const target=new URL('/ws',url);target.protocol=url.protocol==='https:'?'wss:':'ws:';
     const upstream=new WebSocket(target,{headers:{Authorization:'Bearer '+token},handshakeTimeout:10000,maxPayload:1048576,followRedirects:false,perMessageDeflate:false,lookup:(host,options,callback)=>lookup(host,{all:true,verbatim:true},(error,addresses)=>{
      if(error||!addresses.length||addresses.some(a=>!safeAddress(a.address))){callback(new Error('Factory resolution failed'),'',4);return;}
      if(options.all)(callback as unknown as (e:null,a:typeof addresses)=>void)(null,addresses);else callback(null,addresses[0].address,addresses[0].family);
     })});
     upstream.on('message',(data,binary)=>{if(client.readyState===WebSocket.OPEN){if(client.bufferedAmount>1048576){client.close(1013);return;}client.send(data,{binary});}});
     upstream.on('error',()=>client.close(1011,'Factory unavailable'));upstream.on('close',()=>client.close());
     client.on('close',()=>upstream.close());client.on('error',()=>upstream.close());
     // Browser is a renderer. Commands use validated REST routes, never WS messages.
     client.on('message',()=>client.close(1008,'Use simulation controls'));
    });
   }).catch(()=>socket.destroy());
  });
 }
 onModuleDestroy(){this.wss?.clients.forEach(c=>c.terminate());this.wss?.close();}
}
