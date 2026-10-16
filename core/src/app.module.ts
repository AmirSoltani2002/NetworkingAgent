import { IntegrationsModule } from './integrations/integrations.module';
import { FactoryModule } from './factory/factory.module';
import { TasksModule } from './tasks/tasks.module';
import { RagModule } from './rag/rag.module';
import { ConfigModule } from './config/config.module';
import { McpModule } from './mcp/mcp.module';
import { Module } from '@nestjs/common';
import { HealthModule } from './health/health.module';
import { DatabaseModule } from './database/database.module';
import { ChatsModule } from './chats/chats.module';
import { LlmModule } from './llm/llm.module';

@Module({ imports: [FactoryModule, IntegrationsModule, TasksModule, RagModule, ConfigModule, McpModule, DatabaseModule, HealthModule, ChatsModule, LlmModule] })
export class AppModule {}
