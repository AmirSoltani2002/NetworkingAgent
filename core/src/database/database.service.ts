import { Injectable, Logger, type OnModuleInit, type OnModuleDestroy } from '@nestjs/common';
import { readFile, readdir } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { resolve } from 'node:path';
import { Pool, type PoolClient } from 'pg';
import { requiredSecret } from '../config/environment';

@Injectable()
export class DatabaseService implements OnModuleInit, OnModuleDestroy {
  readonly pool = new Pool({
    host: process.env.DB_HOST ?? '127.0.0.1',
    port: Number(process.env.DB_PORT ?? 5432),
    database: process.env.DB_NAME ?? 'meta_harness',
    user: process.env.DB_USER ?? 'meta_harness',
    password: requiredSecret('DB_PASSWORD'),
    max: 10,
    connectionTimeoutMillis: 5000,
  });

  constructor() {
    this.pool.on('error', () => Logger.error('Database connection interrupted.', undefined, 'Database'));
  }

  async onModuleInit() {
    const schema = await readFile(resolve(__dirname, '../../../database/schema.sql'), 'utf8');
    await this.transaction(async client => {
      await client.query('SELECT pg_advisory_xact_lock(7140826)');
      await client.query(schema);
      await client.query('CREATE TABLE IF NOT EXISTS schema_migrations(name text PRIMARY KEY, checksum text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())');
      const directory = resolve(__dirname, '../../../database/migrations');
      for (const name of (await readdir(directory)).filter(name => /^\d+_[a-z_]+\.sql$/.test(name)).sort()) {
        const sql = await readFile(resolve(directory,name),'utf8');
        const checksum = createHash('sha256').update(sql).digest('hex');
        const previous = (await client.query('SELECT checksum FROM schema_migrations WHERE name=$1',[name])).rows[0];
        if (previous && previous.checksum !== checksum) throw new Error('Applied database migration changed: '+name);
        if (!previous) {
          await client.query(sql);
          await client.query('INSERT INTO schema_migrations(name,checksum) VALUES($1,$2)',[name,checksum]);
        }
      }
    });
  }

  async transaction<T>(operation: (client: PoolClient) => Promise<T>): Promise<T> {
    const client = await this.pool.connect();
    try {
      await client.query('BEGIN');
      const result = await operation(client);
      await client.query('COMMIT');
      return result;
    } catch (error) {
      await client.query('ROLLBACK');
      throw error;
    } finally {
      client.release();
    }
  }

  async onModuleDestroy() {
    await this.pool.end();
  }
}
