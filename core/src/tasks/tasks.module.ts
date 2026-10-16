import { Module } from '@nestjs/common';
import { LlmModule } from '../llm/llm.module';
import { McpModule } from '../mcp/mcp.module';
import { TasksController } from './tasks.controller';
import { TasksService } from './tasks.service';
import { TaskWorker } from './task-worker';
import { TaskSchedulesService } from './task-schedules.service';
import { ExecutionPolicy } from './execution-policy';
@Module({imports:[LlmModule,McpModule],controllers:[TasksController],providers:[TasksService,ExecutionPolicy,TaskWorker,TaskSchedulesService],exports:[TasksService]})
export class TasksModule{}
