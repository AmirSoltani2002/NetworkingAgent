import { BadRequestException, Body, Controller, Get, Header, Headers, Param, ParseUUIDPipe, Post, Put, UploadedFile, UseInterceptors } from '@nestjs/common';
import { FileInterceptor } from '@nestjs/platform-express';
import type { Express } from 'express';
import { requireLocalOrigin } from '../config/local-origin';
import { RagService } from './rag.service';

const uuid = '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}';
export function validateOperation(body: unknown) {
  const input = body as { path?: unknown; method?: unknown; data?: unknown };
  if (!input || typeof input.path !== 'string' || Object.keys(input).some(key=>!['path','method','data'].includes(key))) throw new BadRequestException('Invalid RAG operation.');
  const method = input.method ?? 'GET';
  if (typeof method !== 'string' || !['GET','POST','PUT','DELETE'].includes(method) || !input.path.startsWith('api/') || input.path.includes('%') || input.path.includes('\\') || input.path.length > 4000) throw new BadRequestException('Invalid RAG operation.');
  const url = new URL(input.path,'http://internal/'); const path = url.pathname.slice(1);
  const patterns: Record<string,RegExp[]> = {
    GET: [/^api\/(devices|issues|documents)$/,new RegExp(`^api/(devices|issues|documents)/${uuid}$`),new RegExp(`^api/documents/${uuid}/(status|chunks)$`),new RegExp(`^api/issues/${uuid}/evidence$`)],
    POST:[/^api\/(devices|issues|retrieval\/search)$/,new RegExp(`^api/issues/${uuid}/evidence$`),new RegExp(`^api/documents/${uuid}/reprocess$`)],
    PUT:[new RegExp(`^api/(devices|issues|documents)/${uuid}$`)],
    DELETE:[new RegExp(`^api/(devices|issues|documents)/${uuid}$`),new RegExp(`^api/issues/${uuid}/evidence/${uuid}$`)],
  };
  if (!patterns[method].some(pattern=>pattern.test(path))) throw new BadRequestException('This RAG operation is not supported.');
  const queryNames = ['offset','limit','name','model','manufacturer','device_id','category','symptoms','document_type','status'];
  for (const [key,value] of url.searchParams) if (method !== 'GET' || !queryNames.includes(key) || value.length > 300 || (['offset','limit'].includes(key) && !/^\d{1,5}$/.test(value))) throw new BadRequestException('Invalid RAG filter.');
  if (input.data !== undefined && (!input.data || typeof input.data !== 'object' || Array.isArray(input.data) || Buffer.byteLength(JSON.stringify(input.data)) > 65536)) throw new BadRequestException('Invalid or oversized RAG request fields.');
  if (['GET','DELETE'].includes(method) && input.data !== undefined) throw new BadRequestException('This operation does not accept fields.');
  return { path:path+url.search,method,data:input.data };
}
@Controller('rag/connections')
export class RagController {
  constructor(private readonly rag: RagService) {}
  @Get() @Header('Cache-Control','no-store') list() { return this.rag.list(); }
  @Post() save(@Body() body: unknown,@Headers('origin') origin?:string) { requireLocalOrigin(origin); return this.rag.save(body); }
  @Put(':id') update(@Param('id',ParseUUIDPipe) id:string,@Body() body:unknown,@Headers('origin') origin?:string) { requireLocalOrigin(origin); return this.rag.save(body,id); }
  @Post('test') test(@Body() body:unknown,@Headers('origin') origin?:string) { requireLocalOrigin(origin); return this.rag.test(body); }
  @Post(':id/test') testSaved(@Param('id',ParseUUIDPipe) id:string,@Body() body:unknown,@Headers('origin') origin?:string) { requireLocalOrigin(origin); return this.rag.test(body,id); }
  @Post(':id/disconnect') disconnect(@Param('id',ParseUUIDPipe) id:string,@Headers('origin') origin?:string) { requireLocalOrigin(origin); return this.rag.disconnect(id); }
  @Put(':id/permissions') permissions(@Param('id',ParseUUIDPipe) id:string,@Body() body:unknown,@Headers('origin') origin?:string) { requireLocalOrigin(origin); return this.rag.permissions(id,body); }
  @Post(':id/request') @Header('Cache-Control','no-store') request(@Param('id',ParseUUIDPipe) id:string,@Body() body:unknown,@Headers('origin') origin?:string) { requireLocalOrigin(origin); const value=validateOperation(body); return this.rag.request(id,value.path,value.method,value.data); }
  @Post(':id/upload') @UseInterceptors(FileInterceptor('file',{ limits:{fileSize:25*1024*1024,files:1,fields:5,fieldSize:65536} })) upload(@Param('id',ParseUUIDPipe) id:string,@UploadedFile() file:Express.Multer.File,@Body() body:Record<string,string>,@Headers('origin') origin?:string) { requireLocalOrigin(origin); return this.rag.upload(id,file,body); }
}
