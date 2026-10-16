import { Body, Controller, Delete, Get, Header, Headers, Param, ParseUUIDPipe, Post, Put } from '@nestjs/common';
import { requireLocalOrigin } from '../config/local-origin';
import { McpService } from './mcp.service';

@Controller('mcp/servers')
export class McpController {
  constructor(private readonly mcp: McpService) {}
  @Get() @Header('Cache-Control', 'no-store') list() { return this.mcp.list(); }
  @Get('managed') @Header('Cache-Control', 'no-store') managedList() { return this.mcp.managedList(); }
  @Post('managed') managedCreate(@Body() body: unknown,@Headers('origin') origin?:string) { requireLocalOrigin(origin); return this.mcp.managedSave(body); }
  @Post('test') testDraft(@Body() body:unknown,@Headers('origin') origin?:string) { requireLocalOrigin(origin); return this.mcp.managedTest(body); }
  @Put(':id/configuration') configure(@Param('id',ParseUUIDPipe) id:string,@Body() body:unknown,@Headers('origin') origin?:string) { requireLocalOrigin(origin); return this.mcp.managedSave(body,id); }
  @Post(':id/test') testSaved(@Param('id',ParseUUIDPipe) id:string,@Body() body:unknown,@Headers('origin') origin?:string) { requireLocalOrigin(origin); return this.mcp.managedTest(body,id); }
  @Put(':id/permissions') permissions(@Param('id',ParseUUIDPipe) id:string,@Body() body:unknown,@Headers('origin') origin?:string) { requireLocalOrigin(origin); return this.mcp.permissions(id,body); }
  @Post(':id/disconnect') disconnect(@Param('id',ParseUUIDPipe) id:string,@Headers('origin') origin?:string) { requireLocalOrigin(origin); return this.mcp.disconnect(id); }
  @Post() create(@Body() body: unknown, @Headers('origin') origin?: string) { requireLocalOrigin(origin); return this.mcp.save(body); }
  @Put(':id') update(@Param('id', ParseUUIDPipe) id: string, @Body() body: unknown, @Headers('origin') origin?: string) { requireLocalOrigin(origin); return this.mcp.save(body, id); }
  @Delete(':id') remove(@Param('id', ParseUUIDPipe) id: string, @Headers('origin') origin?: string) { requireLocalOrigin(origin); return this.mcp.remove(id); }
  @Post(':id/discover') discover(@Param('id', ParseUUIDPipe) id: string, @Headers('origin') origin?: string) { requireLocalOrigin(origin); return this.mcp.discover(id); }
  @Put(':id/allowlist') allow(@Param('id', ParseUUIDPipe) id: string, @Body() body: unknown, @Headers('origin') origin?: string) { requireLocalOrigin(origin); return this.mcp.allow(id, body); }
}
