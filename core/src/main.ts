import 'reflect-metadata';
import { Logger } from '@nestjs/common';
import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';
import { HttpExceptionFilter } from './http-exception.filter';
import { loadCoreEnvironment, requiredSecret } from './config/environment';

async function bootstrap() {
  loadCoreEnvironment();
  requiredSecret('DB_PASSWORD');
  const port = Number(process.env.CORE_PORT ?? 8000);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error('CORE_PORT must be an integer between 1 and 65535.');
  }

  const app = await NestFactory.create(AppModule);
  app.setGlobalPrefix('api');
  app.useGlobalFilters(new HttpExceptionFilter());
  app.enableShutdownHooks();
  await app.listen(port, process.env.CORE_HOST ?? '127.0.0.1');
  Logger.log(`Core available at http://127.0.0.1:${port}/api`, 'Bootstrap');
}

void bootstrap().catch((error: unknown) => {
  Logger.error(error instanceof Error ? error.message : 'Core failed to start.', undefined, 'Bootstrap');
  process.exitCode = 1;
});
