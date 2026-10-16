import { McpModule } from '../mcp/mcp.module';
import { Module } from '@nestjs/common';
import { ConfigModule } from '../config/config.module';
import { LlmController } from './llm.controller';
import { LlmService } from './llm.service';

@Module({ imports: [ConfigModule, McpModule], controllers: [LlmController], providers: [LlmService], exports: [LlmService] })
export class LlmModule {}
