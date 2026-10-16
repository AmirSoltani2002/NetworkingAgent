import Ajv from 'ajv';
import { taskDecisionSchema } from './task-prompt';
import { digest, TransientTaskError, validateDecision, type Decision } from './task-contract';

const validSchema = new Ajv({ strict: false, validateFormats: false }).compile(taskDecisionSchema);
const maxResponseCharacters = 262144;

/** Extract JSON without interpreting prose, repairing syntax, or evaluating code. */
function extractDecision(source: string): Record<string, unknown> {
  if (source.length > maxResponseCharacters) throw new TransientTaskError('The model decision exceeded the permitted response size.');
  const starts: number[] = [];
  const candidates: Record<string, unknown>[] = [];
  let quoted = false;
  let escaped = false;
  let objectCount = 0;
  for (let index = 0; index < source.length; index++) {
    const char = source[index];
    if (quoted) {
      if (escaped) escaped = false;
      else if (char === '\\') escaped = true;
      else if (char === '"') quoted = false;
      continue;
    }
    if (starts.length && char === '"') { quoted = true; continue; }
    if (char === '{') { starts.push(index); continue; }
    if (char !== '}' || !starts.length) continue;
    const start = starts.pop()!;
    if (++objectCount > 512) throw new TransientTaskError('The model response contained too many JSON objects.');
    let value: unknown;
    try { value = JSON.parse(source.slice(start, index + 1)); } catch { continue; }
    if (value && typeof value === 'object' && !Array.isArray(value) && Object.hasOwn(value, 'goal') && Object.hasOwn(value, 'plan') && Object.hasOwn(value, 'kind')) candidates.push(value as Record<string, unknown>);
  }
  if (!candidates.length) throw new TransientTaskError('The model returned no valid decision JSON. I’ll request another decision before executing tools.');
  const unique = new Map<string, Record<string, unknown>>();
  for (const candidate of candidates) {
    if (!validSchema(candidate)) throw new TransientTaskError('The model decision does not match the required task schema.');
    // Execute/wait labels are explanatory; every operational field must still match.
    const operational = Object.fromEntries(Object.entries(candidate).filter(([key]) => key !== 'step' && key !== 'summary'));
    const identity = digest(['execute', 'wait'].includes(String(candidate.kind)) ? operational : candidate);
    unique.set(identity, candidate);
  }
  if (unique.size !== 1) throw new TransientTaskError('The model returned conflicting task decisions. I’ll request one unambiguous decision before executing tools.');
  return unique.values().next().value!;
}

function jsonField(value: string, field: string, fallback?: string): unknown {
  try { return JSON.parse(value.trim() || fallback || ''); }
  catch { throw new TransientTaskError(`The model supplied invalid ${field}. I’ll request another decision before executing tools.`); }
}

export function parseTaskDecision(source: string): Decision {
  const raw = extractDecision(source);
  if (!validSchema(raw)) throw new TransientTaskError('The model decision does not match the required task schema. I’ll request another decision before executing tools.');
  const criteria = (raw.criteria as Record<string, unknown>[]).map(criterion => ({
    ...criterion,
    match: jsonField(criterion.matchJson as string, 'completion filter JSON', '{}'),
    expected: jsonField(criterion.expectedJson as string, 'completion value JSON', 'null'),
  }));
  const action = raw.action as Record<string, unknown> | null;
  if (raw.kind === 'execute' && !action) throw new TransientTaskError('The model execution decision omitted its action.');
  try {
    return validateDecision({ ...raw, criteria, action: raw.kind === 'execute' && action ? {
      ...action,
      arguments: ['mcp','evidence'].includes(String(action.kind)) ? jsonField(action.argumentsJson as string, 'tool arguments JSON', '{}') : {},
    } : null });
  } catch (error) {
    if (error instanceof TransientTaskError) throw error;
    throw new TransientTaskError('The model supplied an invalid task action or completion check. I’ll request another decision before executing tools.');
  }
}
