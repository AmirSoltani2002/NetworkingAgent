import {Module} from '@nestjs/common';
import {TasksModule} from '../tasks/tasks.module';
import {ConfigModule} from '../config/config.module';
import {IntegrationsController} from './integrations.controller';
@Module({imports:[TasksModule,ConfigModule],controllers:[IntegrationsController]})
export class IntegrationsModule{}
