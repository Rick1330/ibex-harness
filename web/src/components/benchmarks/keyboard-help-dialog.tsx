"use client";

import { useEffect, useRef } from "react";

type KeyboardHelpDialogProps = Readonly<{
  open: boolean;
  onClose: () => void;
}>;

const SHORTCUTS = [
  { keys: "j / k", action: "Move selection down / up" },
  { keys: "Enter", action: "Open run detail" },
  { keys: "c", action: "Toggle compare selection (max 2)" },
  { keys: "/", action: "Focus status filter" },
  { keys: "?", action: "Show this help" },
  { keys: "Escape", action: "Close help" },
] as const;

export function KeyboardHelpDialog({ open, onClose }: KeyboardHelpDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) {
      return;
    }

    if (open && !dialog.open) {
      dialog.showModal();
      return;
    }

    if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby="benchmark-keyboard-help-title"
      className="benchmark-keyboard-dialog w-full max-w-md rounded-md border border-border bg-panel p-5 text-foreground shadow-lg"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClose={onClose}
    >
      <h2 id="benchmark-keyboard-help-title" className="text-sm font-semibold text-foreground">
        Keyboard shortcuts
      </h2>
      <table className="mt-4 w-full text-sm">
        <tbody>
          {SHORTCUTS.map((entry) => (
            <tr key={entry.keys} className="border-b border-border/60 last:border-0">
              <td className="py-2 pe-4 font-mono text-xs text-muted-foreground">{entry.keys}</td>
              <td className="py-2 text-foreground">{entry.action}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <button
        type="button"
        onClick={onClose}
        className="mt-4 rounded-md border border-border px-3 py-1.5 text-sm hover:bg-panel-raised"
      >
        Close
      </button>
    </dialog>
  );
}
