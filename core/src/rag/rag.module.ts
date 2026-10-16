import { Module } from '@nestjs/common';
import { McpModule } from '../mcp/mcp.module';
import { RagService } from './rag.service';
import { RagController } from './rag.controller';
@Module({ imports:[McpModule],providers:[RagService],controllers:[RagController] })
export class RagModule {}
