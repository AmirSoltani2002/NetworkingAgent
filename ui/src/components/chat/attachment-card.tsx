import { Button } from '@/components/ui/button';
import { Icon } from './icon';

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

type FileMetadata = Pick<File, 'name' | 'size'>;

function FileDetails({ file }: { file: FileMetadata }) {
  return (
    <div className="attachment-details">
      <span className="attachment-name" title={file.name}>{file.name}</span>
      <span className="attachment-size">{formatSize(file.size)}</span>
    </div>
  );
}

export function AttachmentCard({ file, downloadUrl, onRemove }: {
  file: FileMetadata;
  downloadUrl?: string;
  onRemove?: () => void;
}) {
  if (downloadUrl) {
    return (
      <a className="attachment" href={downloadUrl} download={file.name}>
        <Icon name="file" /><FileDetails file={file} />
      </a>
    );
  }
  return (
    <div className="attachment">
      <Icon name="file" /><FileDetails file={file} />
      {onRemove && (
        <Button type="button" variant="ghost" size="icon" className="icon-button remove-attachment"
          aria-label={`Remove ${file.name}`} onClick={onRemove}>
          <Icon name="close" />
        </Button>
      )}
    </div>
  );
}
