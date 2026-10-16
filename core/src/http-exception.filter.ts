import { ArgumentsHost, Catch, HttpException, Logger, type ExceptionFilter } from '@nestjs/common';
import type { Response } from 'express';

@Catch()
export class HttpExceptionFilter implements ExceptionFilter {
  catch(error: unknown, host: ArgumentsHost) {
    const response = host.switchToHttp().getResponse<Response>();
    const status = error instanceof HttpException ? error.getStatus() : 500;
    const body = error instanceof HttpException ? error.getResponse() : null;
    let message = typeof body === 'string' ? body : body && 'message' in body
      ? body.message : 'Could not complete the request. Please try again.';
    if (typeof message === 'string' && /^(Unexpected token|Unexpected end of JSON|Expected .* in JSON|Unterminated string)/.test(message)) message = 'Invalid JSON request body.';
    // Parser/network/database stacks may contain submitted tokens or sensitive values.
    if (status >= 500) Logger.error(JSON.stringify({event:'http_error',status}), undefined, 'HTTP');
    response.status(status).json({ code: `HTTP_${status}`, message, field_errors: null });
  }
}
