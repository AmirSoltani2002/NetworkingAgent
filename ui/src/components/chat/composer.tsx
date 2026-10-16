import { useLayoutEffect, useRef, useState, type ChangeEvent, type FormEvent } from 'react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import type { PendingAttachment } from '@/types/chat';
import { AttachmentCard } from './attachment-card';
import { Icon } from './icon';

export function Composer({ onSend, busy }: {
  onSend: (text: string, files: PendingAttachment[], clientMessageId: string) => Promise<boolean>;
  busy: boolean;
}) {
  const [text, setText] = useState('');
  const [files, setFiles] = useState<PendingAttachment[]>([]);
  const picker = useRef<HTMLInputElement>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const addButton = useRef<HTMLButtonElement>(null);
  const requestId = useRef<string | null>(null);
  const submitting = useRef(false);
  const [fileError, setFileError] = useState<string | null>(null);
  const canSend = Boolean(text.trim() || files.length) && !busy;

  useLayoutEffect(() => {
    if (!textarea.current) return;
    textarea.current.style.height = '40px';
    textarea.current.style.height = `${Math.min(180, textarea.current.scrollHeight)}px`;
  }, [text]);

  function selectFiles(event: ChangeEvent<HTMLInputElement>) {
    const selected = Array.from(event.currentTarget.files ?? []);
    const next = [...files];
    for (const file of selected) {
      if (!next.some(item => item.file.name === file.name && item.file.size === file.size
        && item.file.lastModified === file.lastModified)) next.push({ id: crypto.randomUUID(), file });
    }
    event.currentTarget.value = '';
    if (next.length > 10 || next.some(item => item.file.size > 10 * 1024 * 1024)
      || next.reduce((sum, item) => sum + item.file.size, 0) > 25 * 1024 * 1024) {
      setFileError('Attach up to 10 files, 10 MB each and 25 MB total.');
      return;
    }
    requestId.current = null;
    setFileError(null);
    setFiles(next);
  }

  async function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSend || submitting.current) return;
    submitting.current = true;
    requestId.current ??= crypto.randomUUID();
    try {
      if (await onSend(text.trim(), files, requestId.current)) {
        setText('');
        setFiles([]);
        requestId.current = null;
        textarea.current?.focus();
      }
    } finally {
      submitting.current = false;
    }
  }

  return (
    <div className="composer-area">
      <p className="disclaimer">AI can make mistakes. Check important information.</p>
      {fileError && <p className="chat-error" role="alert">{fileError}</p>}
      <form className="composer" aria-label="Message composer" onSubmit={send}>
        <ul className="attachments" aria-label="Attached files" hidden={!files.length}>
          {files.map(attachment => (
            <li key={attachment.id}>
              <AttachmentCard file={attachment.file} onRemove={busy ? undefined : () => {
                setFiles(current => current.filter(item => item.id !== attachment.id));
                requestId.current = null;
                setFileError(null);
                addButton.current?.focus();
              }} />
            </li>
          ))}
        </ul>
        {files.length > 0 && <p className="attachment-context-note">Files are saved locally; their contents are not sent to the model.</p>}
        <div className="composer-controls">
          <Button ref={addButton} type="button" variant="ghost" size="icon"
            className="icon-button add-attachment" aria-label="Add files" title="Add files"
            disabled={busy}
            onClick={() => picker.current?.click()}><Icon name="plus" /></Button>
          <input ref={picker} type="file" id="file-picker" multiple hidden onChange={selectFiles} />
          <Textarea ref={textarea} aria-label="Message" rows={1} placeholder="Ask anything"
            spellCheck value={text} maxLength={20000} readOnly={busy} onChange={event => {
              setText(event.target.value);
              requestId.current = null;
            }}
            onKeyDown={event => {
              if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                if (canSend) event.currentTarget.form?.requestSubmit();
              }
            }} />
          <Button type="submit" size="icon" className="send-button" aria-label="Send message"
            title="Send message" disabled={!canSend}><Icon name="send" /></Button>
        </div>
      </form>
    </div>
  );
}
