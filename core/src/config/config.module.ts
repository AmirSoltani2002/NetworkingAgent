import { Global, Module } from '@nestjs/common';
import { EnvironmentStore } from './environment-store.service';

@Global()
@Module({ providers: [EnvironmentStore], exports: [EnvironmentStore] })
export class ConfigModule {}
