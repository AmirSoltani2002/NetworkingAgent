import { BadRequestException, Body, Controller, Get, Header, Headers, Param, ParseUUIDPipe, Post, StreamableFile, UploadedFiles, UseInterceptors } from '@nestjs/common';
import { FilesInterceptor } from '@nestjs/platform-express';
import type { Express } from 'express';
import { ChatsService } from './chats.service';
import { requireLocalOrigin } from '../config/local-origin';

@Controller('chats')
export class ChatsController {
  constructor(private readonly chats: ChatsService) {}

  @Get()
  list() { return this.chats.list(); }

  @Post()
  create() { return this.chats.create(); }

  @Get(':id')
  get(@Param('id', new ParseUUIDPipe()) id: string) { return this.chats.get(id); }

  @Post(':id/messages')
  @UseInterceptors(FilesInterceptor('files', 10, { limits: { fileSize: 10 * 1024 * 1024, files: 10, fields: 2, fieldSize: 100000, parts: 12 } }))
  addMessage(@Param('id', new ParseUUIDPipe()) id: string,
    @Body('text') text: unknown,
    @Body('clientMessageId', new ParseUUIDPipe({ version: '4' })) clientMessageId: string,
    @UploadedFiles() files: Express.Multer.File[] = []) {
    if (typeof text !== 'string') throw new BadRequestException('Message text must be a string.');
    return this.chats.addMessage(id, text, clientMessageId, files);
  }

  @Get(':id/attachments/:attachmentId')
  async download(@Param('id', new ParseUUIDPipe()) id: string,
    @Param('attachmentId', new ParseUUIDPipe()) attachmentId: string) {
    const file = await this.chats.download(id, attachmentId);
    return new StreamableFile(file.content, {
      type: 'application/octet-stream',
      disposition: `attachment; filename*=UTF-8''${encodeURIComponent(file.name).replace(/'/g, '%27')}`,
      length: file.content.length,
    });
  }

  @Post(':id/messages/:messageId/response')
  @Header('Cache-Control', 'no-store')
  respond(@Param('id', new ParseUUIDPipe()) id: string,
    @Param('messageId', new ParseUUIDPipe()) messageId: string,
    @Headers('origin') origin?: string) {
    requireLocalOrigin(origin);
    return this.chats.respond(id, messageId);
  }

  @Post(':id/messages/:messageId/confirmation')
  @Header('Cache-Control', 'no-store')
  confirm(@Param('id',new ParseUUIDPipe()) id:string,@Param('messageId',new ParseUUIDPipe()) messageId:string,
    @Body() body:unknown,@Headers('origin') origin?:string) {
    requireLocalOrigin(origin);
    const value=body as {id?:unknown;approved?:unknown};
    if (!value || typeof value.id!=='string' || !/^[0-9a-f-]{36}$/i.test(value.id) || typeof value.approved!=='boolean' || Object.keys(value).some(key=>!['id','approved'].includes(key))) throw new BadRequestException('Confirm or decline the current tool invocation.');
    return this.chats.respond(id,messageId,{id:value.id,approved:value.approved});
  }
}
