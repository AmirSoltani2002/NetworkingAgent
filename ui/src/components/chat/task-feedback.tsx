import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { tasksApi } from '@/lib/tasks-api';
import type { TaskDetail } from '@/types/tasks';

const outcomes = {
  PENDING: 'Your task is queued. I’ll post progress here.',
  RUNNING: 'I’m working on your task.',
  RETRYING: 'A service is temporarily unavailable. I’m retrying; saved work is preserved.',
  WAITING_APPROVAL: 'Your approval is needed before the next action. Open task details to review it.',
  PAUSED: 'Your task is paused. Open task details to review what is needed next.',
  FAILED: 'I couldn’t complete this task. No successful completion has been recorded. Open task details to review or retry it.',
  CANCELLED: 'Your task was cancelled. Previously executed actions remain recorded.',
  COMPLETED: 'Your task completed and its checks passed.',
};

export function TaskFeedback({ taskId, revision, hasReply, onOpen }: {
  taskId: string; revision: number; hasReply: boolean; onOpen: () => void;
}) {
  const [task, setTask] = useState<TaskDetail | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function refresh() {
      try {
        const next = await tasksApi.get(taskId);
        if (disposed) return;
        setTask(next);
        setUnavailable(false);
        if (!['COMPLETED', 'FAILED', 'CANCELLED'].includes(next.status)) timer = setTimeout(() => void refresh(), 3000);
      } catch {
        if (!disposed) { setUnavailable(true); timer = setTimeout(() => void refresh(), 5000); }
      }
    }
    void refresh();
    return () => { disposed = true; clearTimeout(timer); };
  }, [taskId, revision]);
  return <article className="assistant-message task-feedback" aria-label="Task response">
    <p className="task-feedback-title">{task?.user_request ?? 'Task received'}</p>
    <p className="message-text" role="status">{unavailable ? 'I can’t fetch the latest task update right now. I’ll reconnect automatically; you can also open task details.' : task ? (task.status==='COMPLETED'&&task.criteria.length>0&&task.criteria.every(c=>c.kind==='response')?'Your response is ready. No external operation was verified.':outcomes[task.status]) : 'Your task is saved. Checking its progress…'}</p>
    {task?.last_error && <p className="message-text">{task.last_error.includes('invalid structured task decision') ? 'I couldn’t interpret the model’s response safely. Open task details to review or retry this request.' : task.last_error}</p>}
    {task?.next_action?.summary && !task.last_error && <p>{task.next_action.summary}</p>}
    {task?.result && !hasReply && <p className="message-text">{task.result}</p>}
    {!!task?.operations.length && <details className="tool-trace"><summary>Requests and outputs · {task.operations.length}</summary>{task.operations.map(op=><div key={op.id}><p>{op.kind} · {op.status.replaceAll('_',' ')}</p><pre>{JSON.stringify({request:op.action,output:op.result??op.last_error??'Awaiting output'},null,2)}</pre></div>)}</details>}
    {!!task?.events.some(event=>event.type==='model_output') && <details className="tool-trace"><summary>Model request outputs</summary>{task.events.filter(event=>event.type==='model_output').slice().reverse().map(event=><pre key={event.sequence}>{JSON.stringify(event.data,null,2)}</pre>)}</details>}
    <Button variant="ghost" onClick={onOpen}>View task details</Button>
  </article>;
}
