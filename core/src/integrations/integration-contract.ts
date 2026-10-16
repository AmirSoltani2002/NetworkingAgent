import { BadRequestException, UnauthorizedException } from '@nestjs/common';
import { timingSafeEqual } from 'node:crypto';
import { object, text, uuid } from '../tasks/task-contract';
export function authenticate(header: string | undefined, secret: string | undefined) {
 if (!secret || secret.length < 24) throw new UnauthorizedException('Integration is not configured.');
 const expected=Buffer.from('Bearer '+secret),given=Buffer.from(header??'');
 if(given.length!==expected.length||!timingSafeEqual(given,expected))throw new UnauthorizedException('Service authentication required.');
}
export function eventInput(raw:unknown){const b=object(raw);if(Object.keys(b).some(k=>!['template','eventId','variables'].includes(k)))throw new BadRequestException('Unknown integration field.');const variables=object(b.variables);if(JSON.stringify(variables).length>16000)throw new BadRequestException('Event payload exceeds limit.');return{template:text(b.template,100),eventId:uuid(b.eventId),variables};}
export function expand(value:unknown,env:Record<string,string|undefined>,variables:Record<string,unknown>,allowVariables=true):unknown{
 if(Array.isArray(value))return value.map(v=>expand(v,env,variables,allowVariables));
 if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).map(([k,v])=>[k,expand(v,env,variables,allowVariables)]));
 if(typeof value!=='string')return value;
 const resolved=value.replace(/\$\{([A-Z][A-Z0-9_]*)\}/g,(_,k:string)=>{if(!env[k])throw new BadRequestException('Required integration configuration is missing.');return env[k]!;});
 if(!allowVariables)return resolved;
 return resolved.replace(/\{\{([a-z_]+)\}\}/g,(_,k:string)=>{if(!Object.hasOwn(variables,k))throw new BadRequestException('Required event variable missing.');return typeof variables[k]==='string'?String(variables[k]):JSON.stringify(variables[k]);});
}
