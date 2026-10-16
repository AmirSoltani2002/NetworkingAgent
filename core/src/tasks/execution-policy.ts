import { BadRequestException, Injectable } from '@nestjs/common';
import { spawn } from 'node:child_process';
import { constants } from 'node:fs';
import { lstat, mkdir, open, realpath, rename, unlink, readdir } from 'node:fs/promises';
import { dirname, isAbsolute, relative, resolve, sep } from 'node:path';
import { randomUUID } from 'node:crypto';
import { EnvironmentStore } from '../config/environment-store.service';
import { McpService } from '../mcp/mcp.service';
import { digest, object, text, type Action } from './task-contract';

const forbidden=/[\r\n;&|<>`$\\]/;
const secretPath=/(^|\/)\.env(?:\.|$)|(^|\/)(?:\.git|\.ssh|\.aws|\.codex)(\/|$)|(?:credential|secret|private[_-]?key)/i;
@Injectable()
export class ExecutionPolicy{
 constructor(private readonly env:EnvironmentStore,private readonly mcp:McpService){}
 async workspacePath(input:string,write=false){
  if(!process.env.TASK_WORKSPACE_ROOT)throw new BadRequestException('Set TASK_WORKSPACE_ROOT to enable local workspace tools.');
  if(input.includes(String.fromCharCode(0))||forbidden.test(input)||secretPath.test(input)||input.length>1000)throw new BadRequestException('Workspace path is not permitted.');
  const root=await realpath(process.env.TASK_WORKSPACE_ROOT);const path=resolve(root,input);const inside=(p:string)=>{const r=relative(root,p);return r!==''&&!r.startsWith('..'+sep)&&r!=='..'&&!isAbsolute(r);};
  if(!inside(path))throw new BadRequestException('Path must be inside the approved workspace and cannot be its root.');
  let checked:string;try{checked=await realpath(path);}catch{if(!write)throw new BadRequestException('Workspace file does not exist.');checked=await realpath(dirname(path));}
  if(secretPath.test(relative(root,checked))||(checked!==root&&!inside(checked)))throw new BadRequestException('Symlink escapes the approved workspace.');
  if(write){try{if((await lstat(path)).isSymbolicLink())throw new BadRequestException('Writing through symlinks is not permitted.');}catch(e){if(e instanceof BadRequestException)throw e;}}
  return path;
 }
 async grant(serverId:string,tool:string){
  const row=await this.mcp.get(serverId);const descriptor=row.tools.find(t=>t.name===tool);
  if(!row.enabled||!row.agent_enabled||row.disconnected||row.status!=='connected'||!descriptor||!row.allowed_tools.includes(tool))throw new BadRequestException('Only currently enabled and allowlisted tools can receive task grants.');
  if((process.env.TASK_DANGEROUS_MCP_TOOLS??'').split(',').includes(serverId+':'+tool)||(!descriptor.readOnly&&!(process.env.TASK_CONTROLLED_MCP_TOOLS??'').split(',').includes(serverId+':'+tool)))throw new BadRequestException('This tool requires exact action approval. An operator must classify it in TASK_CONTROLLED_MCP_TOOLS before granting task-wide write authority.');
  return {serverId,tool,policyDigest:digest([row.url,row.auth_env_var,row.allowed_tools,descriptor])};
 }
 async prepare(action:Action){
  object(action);
  if(action.kind==='mcp'){
   text(action.tool,200);text(action.serverId,36);object(action.arguments);
   const prepared=await this.mcp.prepareCall(action.serverId!,action.tool!,action.arguments);
   const row=await this.mcp.get(action.serverId!);const descriptor=row.tools.find(t=>t.name===action.tool)!;
   const policyDigest=digest([row.url,row.auth_env_var,row.allowed_tools,descriptor]);
   const explicitlyControlled=(process.env.TASK_CONTROLLED_MCP_TOOLS??'').split(',').includes(action.serverId+':'+action.tool);
   const dangerous=(process.env.TASK_DANGEROUS_MCP_TOOLS??'').split(',').includes(action.serverId+':'+action.tool)||(!prepared.readOnly&&!explicitlyControlled);
   return{readOnly:prepared.readOnly&&!dangerous,level:dangerous?'dangerous':prepared.readOnly?'safe':'controlled',policyDigest,confirmation:{configurationDigest:prepared.configurationDigest,argumentsDigest:prepared.argumentsDigest}};
  }
  if(action.kind==='workspace'){
   if(!['read','list','exists','write','delete'].includes(action.operation??''))throw new BadRequestException('Unsupported workspace operation.');
   text(action.path,1000);await this.workspacePath(action.path!,action.operation==='write'||action.operation==='exists');
   if(action.operation==='write'&&(typeof action.content!=='string'||Buffer.byteLength(action.content)>262144))throw new BadRequestException('File content is required and limited to 256 KiB.');
   const readOnly=!['write','delete'].includes(action.operation!);
   return{readOnly,level:action.operation==='delete'?'dangerous':readOnly?'safe':'controlled',policyDigest:digest([process.env.TASK_WORKSPACE_ROOT,action])};
  }
  if(action.kind!=='command'||!Array.isArray(action.args)||action.args.length>32||action.args.some(x=>typeof x!=='string'||x.length>1000||x.includes(String.fromCharCode(0))||forbidden.test(x))||typeof action.executable!=='string')throw new BadRequestException('Use a supported executable and structured arguments; shell syntax is forbidden.');
  const command=action.executable,args=action.args;const root=process.env.TASK_WORKSPACE_ROOT;
  if(!root)throw new BadRequestException('Configure TASK_WORKSPACE_ROOT before running commands.');await realpath(root);
  // Parse exact argument grammars; never delegate classification to model text.
  if(command==='pwd'&&args.length===0){/* Fixed executable, no arguments. */}
  else if(command==='ls'&&args.length===1&&!args[0].startsWith('-'))await this.workspacePath(args[0]);
  else if(command==='cat'&&args.length===1&&!args[0].startsWith('-'))await this.workspacePath(args[0]);
  else if(command==='grep'&&args.length===3&&args[0]==='-F'&&!args[1].startsWith('-')&&!args[2].startsWith('-'))await this.workspacePath(args[2]);
  else if(command==='find'&&args.length===3&&args[1]==='-maxdepth'&&/^[1-3]$/.test(args[2])&&!args[0].startsWith('-'))await this.workspacePath(args[0]);
  else if(command==='git'&&(JSON.stringify(args)==='["status","--short"]'||JSON.stringify(args)==='["diff","--stat"]')){const git=await realpath(resolve(root,'.git'));if(git!==resolve(await realpath(root),'.git')||!(await lstat(git)).isDirectory())throw new BadRequestException('Git inspection requires an ordinary repository inside the approved workspace.');}
  else throw new BadRequestException('Command or arguments are outside the approved execution policy.');

  return{readOnly:true,level:'safe',policyDigest:digest([root,action])};
 }
 async execute(action:Action,signal:AbortSignal){
  if(action.kind==='workspace'){
   const path=await this.workspacePath(action.path!,action.operation==='write'||action.operation==='exists');
   if(action.operation==='exists'){try{return{exists:(await lstat(path)).isFile(),path:action.path};}catch{return{exists:false,path:action.path};}}
   if(action.operation==='list'){const entries=await readdir(path,{withFileTypes:true});return{entries:entries.filter(e=>!secretPath.test(e.name)).slice(0,200).map(e=>({name:e.name,directory:e.isDirectory()}))};}
   if(action.operation==='delete'){if(!(await lstat(path)).isFile())throw new BadRequestException('Only an explicitly approved regular file can be deleted.');await unlink(path);return{deleted:true,path:action.path};}
   if(action.operation==='write'){
    const temp=resolve(dirname(path),'.task-'+randomUUID());await mkdir(dirname(path),{recursive:true});const handle=await open(temp,constants.O_WRONLY|constants.O_CREAT|constants.O_EXCL|constants.O_NOFOLLOW,0o600);
    try{await handle.writeFile(action.content!);await handle.sync();}finally{await handle.close();}if(signal.aborted){await unlink(temp);throw signal.reason;}await rename(temp,path);return{written:true,path:action.path,bytes:Buffer.byteLength(action.content!),sha256:digest(action.content)};
   }
   const handle=await open(path,constants.O_RDONLY|constants.O_NOFOLLOW);try{if((await handle.stat()).size>262144)throw new BadRequestException('File exceeds the 256 KiB read limit.');return{content:await handle.readFile('utf8'),path:action.path};}finally{await handle.close();}
  }
  const fixed:Record<string,string>={pwd:'/bin/pwd',cat:'/bin/cat',grep:'/bin/grep',git:'/usr/bin/git',ls:'/bin/ls',find:'/usr/bin/find'};
  const executable=fixed[action.executable!];if(!executable)throw new BadRequestException('Unsupported executable.');
  const args=[...(action.args??[])];
  if(action.executable==='ls'||action.executable==='find'){const list=async(path:string,depth:number):Promise<string[]>=>{const full=await this.workspacePath(path);const entries=await readdir(full,{withFileTypes:true});const results:string[]=[];for(const entry of entries.slice(0,200)){if(secretPath.test(entry.name)||entry.isSymbolicLink())continue;const child=path+'/'+entry.name;results.push(child);if(entry.isDirectory()&&depth>1)results.push(...await list(child,depth-1));if(results.length>=200)break;}return results.slice(0,200);};return{exitCode:0,stdout:(await list(args[0],action.executable==='find'?Number(args[2]):1)).join('\n'),stderr:''};}
  if(action.executable==='git')args.unshift('-c','core.fsmonitor=false','-c','core.hooksPath=/dev/null','-c','diff.external=','--no-optional-locks',...(args[0]==='diff'?['--no-pager']:[]));
  if(action.executable==='git'&&args.includes('diff'))args.push('--no-ext-diff','--no-textconv');
  if(action.executable==='cat'||action.executable==='grep'){const file=action.executable==='cat'?args[0]:args[2];const result=await this.execute({kind:'workspace',operation:'read',path:file},signal) as {content:string};const stdout=action.executable==='cat'?result.content:result.content.split('\n').filter(line=>line.includes(args[1])).join('\n');return{exitCode:action.executable==='grep'&&!stdout?1:0,stdout,stderr:''};}
if(action.executable==='cat')args[0]=await this.workspacePath(args[0]);if(action.executable==='grep')args[2]=await this.workspacePath(args[2]);
  return new Promise<Record<string,unknown>>((done,reject)=>{
   const child=spawn(executable,args,{cwd:process.env.TASK_WORKSPACE_ROOT,shell:false,env:{PATH:'/usr/bin:/bin',LANG:'C.UTF-8',GIT_CONFIG_NOSYSTEM:'1',GIT_CONFIG_GLOBAL:'/dev/null',GIT_ATTR_NOSYSTEM:'1',GIT_NO_REPLACE_OBJECTS:'1',GIT_TERMINAL_PROMPT:'0'},stdio:['ignore','pipe','pipe'],signal,timeout:10000});let bytes=0,stdout='',stderr='';
   const capture=(chunk:Buffer,err=false)=>{bytes+=chunk.length;if(bytes>262144){child.kill('SIGKILL');return;}if(err)stderr+=chunk.toString();else stdout+=chunk.toString();};child.stdout.on('data',chunk=>capture(chunk));child.stderr.on('data',chunk=>capture(chunk,true));child.on('error',reject);child.on('close',code=>bytes>262144?reject(new BadRequestException('Command output exceeded the limit.')):done({exitCode:code,stdout:action.executable==='git'?stdout.split('\n').filter(line=>!secretPath.test(line)).join('\n'):stdout,stderr}));
  });
 }
}
