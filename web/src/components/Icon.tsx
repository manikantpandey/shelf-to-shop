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
