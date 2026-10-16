import {Module} from '@nestjs/common';
import {ConfigModule} from '../config/config.module';
import {FactoryController} from './factory.controller';
import {FactoryService} from './factory.service';
@Module({imports:[ConfigModule],controllers:[FactoryController],providers:[FactoryService]})
export class FactoryModule{}
