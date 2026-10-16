const shapes = {
  panel: <><rect x="3" y="4.5" width="18" height="15" rx="3" /><path d="M14 5v14" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
  send: <path d="M12 19V5m-6 6 6-6 6 6" />,
  file: <path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9zM14 3v6h6" />,
  close: <path d="m6 6 12 12M18 6 6 18" />,
  chevron: <path d="m6 9 6 6 6-6" />,
};

export function Icon({ name }: { name: keyof typeof shapes }) {
  return <svg viewBox="0 0 24 24" aria-hidden="true">{shapes[name]}</svg>;
}
