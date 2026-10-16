import { Body, Controller, Get, Header, Headers, Put } from '@nestjs/common';
import { requireLocalOrigin } from '../config/local-origin';
import { LlmService } from './llm.service';

@Controller('llm')
export class LlmController {
  constructor(private readonly llm: LlmService) {}

  @Get()
  @Header('Cache-Control', 'no-store')
  configuration() { return this.llm.configuration(); }

  @Get('models')
  @Header('Cache-Control', 'no-store')
  models() { return this.llm.models(); }

  @Put()
  @Header('Cache-Control', 'no-store')
  save(@Body() body: unknown, @Headers('origin') origin?: string) {
    requireLocalOrigin(origin);
    return this.llm.save(body);
  }
}
