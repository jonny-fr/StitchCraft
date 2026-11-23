import { useCallback, useEffect, useId, useRef, useState, type ReactNode, type RefObject } from "react";

export interface TriggerProps {
  ref: RefObject<HTMLButtonElement | null>;
  onClick(): void;
  "aria-expanded": boolean;
  "aria-haspopup": "dialog";
  "aria-controls": string | undefined;
}

interface Props {
  /** Accessible name of the panel. */
  label: string;
  align?: "start" | "center" | "end";
  className?: string;
  trigger(props: TriggerProps): ReactNode;
  /** Panel content; `close` hands the focus back to the trigger. */
  children(close: () => void): ReactNode;
}

const FOCUSABLE = "button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])";

/**
 * A button with a floating panel (a bottom sheet on small screens, see app.css). Escape closes it and
 * returns the focus to the trigger; a click outside closes it and leaves the focus where it went.
 */
export function Popover({ label, align = "start", className, trigger, children }: Props) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const button = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);

  const close = useCallback((refocus = true) => {
    setOpen(false);
    if (refocus) button.current?.focus();
  }, []);

  useEffect(() => {
    if (!open) return;
    panel.current?.querySelector<HTMLElement>(FOCUSABLE)?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.preventDefault();
      close();
    };
    const onPointer = (e: PointerEvent) => {
      const target = e.target as Node;
      if (!panel.current?.contains(target) && !button.current?.contains(target)) close(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointer);
    };
  }, [open, close]);

  return (
    <div className={className ? `popover ${className}` : "popover"}>
      {trigger({
        ref: button,
        onClick: () => (open ? close() : setOpen(true)),
        "aria-expanded": open,
        "aria-haspopup": "dialog",
        "aria-controls": open ? id : undefined,
      })}
      {open && (
        <>
          <div className="popover-backdrop" aria-hidden />
          <div ref={panel} id={id} role="dialog" aria-label={label} className="popover-panel" data-align={align}>
            {children(close)}
          </div>
        </>
      )}
    </div>
  );
}
