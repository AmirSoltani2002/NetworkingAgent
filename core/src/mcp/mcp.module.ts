import { Module } from '@nestjs/common';
import { ConfigModule } from '../config/config.module';
import { McpController } from './mcp.controller';
import { McpService } from './mcp.service';
@Module({ imports: [ConfigModule], controllers: [McpController], providers: [McpService], exports: [McpService] })
export class McpModule {}
