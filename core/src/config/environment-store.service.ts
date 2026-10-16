import { ConflictException, Injectable, ServiceUnavailableException } from '@nestjs/common';
import { open, readFile } from 'node:fs/promises';
import { parseEnv } from 'node:util';
import { environmentFilePath } from './environment';

export type LlmEnvironmentName = 'OPENAI_API_KEY' | 'LLM_PROVIDER' | 'LLM_MODEL' | 'LLM_THINKING';
const allowedNames = new Set<LlmEnvironmentName>(['OPENAI_API_KEY', 'LLM_PROVIDER', 'LLM_MODEL', 'LLM_THINKING']);

@Injectable()
export class EnvironmentStore {
  private pending: Promise<void> = Promise.resolve();

  private serialize<T>(operation: () => Promise<T>): Promise<T> {
    const result = this.pending.then(operation);
    this.pending = result.then(() => undefined, () => undefined);
    return result;
  }

  private async contents() {
    try {
      return await readFile(environmentFilePath(), 'utf8');
    } catch (error) {
      if (error instanceof Error && 'code' in error && error.code === 'ENOENT') return '';
      throw new ServiceUnavailableException('Could not read local configuration.');
    }
  }

  read() {
    return this.serialize(async () => {
      try {
        return parseEnv(await this.contents());
      } catch {
        throw new ServiceUnavailableException('Could not read local configuration.');
      }
    });
  }

  saveMcpToken(id: string, token: string) {
    if (!/^[a-f0-9-]{36}$/i.test(id) || !/^[\x21-\x7e]{1,2048}$/.test(token)) throw new ServiceUnavailableException('Invalid connection credential.');
    const name = `MCP_TOKEN_${id.replaceAll('-', '').toUpperCase()}`;
    return this.writeValues({ [name]: token }).then(() => name);
  }

  update(values: Partial<Record<LlmEnvironmentName, string>>, expectedApiKey: string | null) {
    if (Object.keys(values).some(name => !allowedNames.has(name as LlmEnvironmentName))) throw new ServiceUnavailableException('Unsupported configuration update.');
    return this.writeValues(values, expectedApiKey);
  }

  private writeValues(values: Record<string, string>, expectedApiKey?: string | null) {
    return this.serialize(async () => {
      const original = await this.contents();
      if (expectedApiKey !== undefined && (parseEnv(original).OPENAI_API_KEY ?? null) !== expectedApiKey) {
        throw new ConflictException('The API key changed while saving. Reload LLM settings and try again.');
      }
      const remaining = new Map(Object.entries(values));
      const lines = original.split(/\r?\n/).flatMap(line => {
        const match = line.match(/^[\t ]*(?:export[\t ]+)?([A-Z][A-Z0-9_]*)[\t ]*=/);
        const name = match?.[1] as LlmEnvironmentName | undefined;
        if (!name || !(name in values)) return [line];
        const value = remaining.get(name);
        remaining.delete(name);
        return value === undefined ? [] : [`${name}=${JSON.stringify(value)}`];
      });
      for (const [name, value] of remaining) lines.push(`${name}=${JSON.stringify(value)}`);
      const updated = lines.join('\n').replace(/\n*$/, '\n');
      try {
        const file = await open(environmentFilePath(), 'r+').catch(async error => {
          if (error instanceof Error && 'code' in error && error.code === 'ENOENT') {
            return open(environmentFilePath(), 'wx+', 0o600);
          }
          throw error;
        });
        const write = async (content: string) => {
          const data = Buffer.from(content);
          let offset = 0;
          while (offset < data.length) {
            const { bytesWritten } = await file.write(data, offset, data.length - offset, offset);
            if (!bytesWritten) throw new Error('Configuration write interrupted.');
            offset += bytesWritten;
          }
          await file.truncate(data.length);
          await file.sync();
        };
        try {
          await file.chmod(0o600);
          try {
            await write(updated);
          } catch {
            await write(original).catch(() => undefined);
            throw new Error('Configuration write failed.');
          }
        } finally {
          await file.close();
        }
      } catch {
        throw new ServiceUnavailableException('Could not save local configuration. Check the local .env permissions.');
      }
      for (const [name, value] of Object.entries(values)) process.env[name] = value;
      return parseEnv(updated);
    });
  }
}
