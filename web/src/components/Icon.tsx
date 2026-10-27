/** Small line icons drawn inline (no icon font or library). Decorative unless labelled. */
const PATHS: Record<string, string> = {
  home: "M3 10.5 12 3l9 7.5V21h-6v-6H9v6H3z",
  items: "M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z",
  videos: "M3 6h13v12H3zM16 10l5-3v10l-5-3",
  settings: "M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0M14 4v4M8 10v4M16 16v4",
  record: "M12 4a8 8 0 1 0 0 16a8 8 0 1 0 0-16z",
  share: "M12 3v12M7 8l5-5 5 5M5 13v7h14v-7",
  copy: "M8 8h12v12H8zM4 16V4h12",
  search: "M10.5 4a6.5 6.5 0 1 0 0 13a6.5 6.5 0 1 0 0-13zM15.5 15.5 21 21",
  camera: "M3 7h4l2-3h6l2 3h4v13H3zM12 10a3.5 3.5 0 1 0 0 7a3.5 3.5 0 1 0 0-7z",
  frame: "M3 5h18v14H3zM3 9h18M7 5v4M12 5v4M17 5v4",
  pack: "M4 7l8-4 8 4v10l-8 4-8-4zM4 7l8 4 8-4M12 11v10",
  check: "M4 12.5 9.5 18 20 6",
  alert: "M12 3 2 21h20zM12 10v5M12 18v.5",
  back: "M15 4 7 12l8 8",
  close: "M5 5l14 14M19 5 5 19",
  next: "M9 4l8 8-8 8",
  open: "M14 4h6v6M20 4l-9 9M18 14v6H4V6h6",
  download: "M12 3v12M7 10l5 5 5-5M4 20h16",
  chat: "M4 4h16v12H9l-5 4z",
  barcode: "M4 5v14M7 5v14M10 5v14M14 5v14M16 5v14M20 5v14",
  orders: "M6 3h12v18l-3-2-3 2-3-2-3 2zM9 8h6M9 12h6M9 16h3",
  more: "M5 12h.01M12 12h.01M19 12h.01",
  store: "M3 9l1.5-5h15L21 9M3 9h18M3 9v11h18V9M9 20v-6h6v6",
  qr: "M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h2v2h-2zM18 14h2M14 18h2v2M18 18h2v2",
  star: "M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z",
  hide: "M3 3l18 18M10.6 6.1A9 9 0 0 1 21 12a14 14 0 0 1-2.3 3.1M6.6 6.6A14 14 0 0 0 3 12s3 6 9 6a9 9 0 0 0 4.3-1.1",
  plus: "M12 5v14M5 12h14",
  minus: "M5 12h14",
  trash: "M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3",
  up: "M6 15l6-6 6 6",
  down: "M6 9l6 6 6-6",
  sections: "M4 6h16M4 12h10M4 18h13",
  basket: "M3 9h18l-2 11H5zM8 9l4-6 4 6",
  print: "M7 9V3h10v6M7 18H4v-8h16v8h-3M7 14h10v7H7z",
  check2: "M4 12.5 9.5 18 20 6",
};

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 22, label }: { name: IconName; size?: number; label?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      focusable="false"
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
