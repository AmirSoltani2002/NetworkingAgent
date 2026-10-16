import { Module } from '@nestjs/common';
import { ChatsController } from './chats.controller';
import { ChatsService } from './chats.service';
import { LlmModule } from '../llm/llm.module';

@Module({ imports: [LlmModule], controllers: [ChatsController], providers: [ChatsService] })
export class ChatsModule {}
