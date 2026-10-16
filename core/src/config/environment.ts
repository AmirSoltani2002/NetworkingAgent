import { loadEnvFile } from 'node:process';
import { resolve } from 'node:path';

export function environmentFilePath() {
  return resolve(__dirname, '../../../.env');
}

export function loadCoreEnvironment() {
  try {
    loadEnvFile(environmentFilePath());
  } catch (error) {
    if (!(error instanceof Error && 'code' in error && error.code === 'ENOENT')) {
      // Do not retain a file-loader error that could disclose confidential input.
      // eslint-disable-next-line preserve-caught-error
      throw new Error('Could not read the project .env file.');
    }
  }
}

export function requiredSecret(name: string): string {
  const value = process.env[name];
  if (!value?.trim()) {
    throw new Error(`${name} must be configured in the project .env or supplied by the container environment.`);
  }
  return value;
}
