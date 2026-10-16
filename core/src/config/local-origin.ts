import { ForbiddenException } from '@nestjs/common';

export function requireLocalOrigin(origin?: string) {
  if (!origin) return;
  try {
    const url = new URL(origin);
    if (url.protocol !== 'http:' || !['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)
      || !['8080', process.env.CORE_PORT ?? '8000'].includes(url.port)) throw new Error();
  } catch {
    throw new ForbiddenException('Use the local application to perform this action.');
  }
}
