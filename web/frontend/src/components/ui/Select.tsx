"use client";

import {
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
} from "react";
import { createPortal } from "react-dom";
import { Check, ChevronDown } from "lucide-react";

export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

interface Props {
  value: string;
  options: SelectOption[];
  onChange: (value: string) => void;
  disabled?: boolean;
  ariaLabel?: string;
  className?: string;
  size?: "sm" | "md";
  monospace?: boolean;
}

type MenuPosition = {
  left: number;
  width: number;
  maxHeight: number;
  top?: number;
  bottom?: number;
};

const VIEWPORT_GAP = 8;
const MENU_GAP = 4;
const MAX_MENU_HEIGHT = 240;

export default function Select({
  value,
  options,
  onChange,
  disabled = false,
  ariaLabel,
  className = "",
  size = "md",
  monospace = false,
}: Props) {
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [menuPosition, setMenuPosition] = useState<MenuPosition | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const typeaheadRef = useRef("");
  const typeaheadTimerRef = useRef<number | null>(null);
  const listboxId = useId();

  const selectedIndex = options.findIndex((option) => option.value === value);
  const selectedOption = selectedIndex >= 0 ? options[selectedIndex] : undefined;
  const enabledIndexes = options.flatMap((option, index) => option.disabled ? [] : [index]);

  const openMenu = (preferredIndex = selectedIndex) => {
    if (disabled || enabledIndexes.length === 0) return;
    const nextIndex = options[preferredIndex]?.disabled
      ? enabledIndexes[0]
      : (preferredIndex >= 0 ? preferredIndex : enabledIndexes[0]);
    setActiveIndex(nextIndex);
    setOpen(true);
  };

  const closeMenu = () => {
    setOpen(false);
    setMenuPosition(null);
  };

  const choose = (index: number) => {
    const option = options[index];
    if (!option || option.disabled) return;
    onChange(option.value);
    closeMenu();
    triggerRef.current?.focus();
  };

  const moveActive = (step: number) => {
    if (enabledIndexes.length === 0) return;
    const current = enabledIndexes.indexOf(activeIndex);
    const next = current < 0
      ? (step > 0 ? 0 : enabledIndexes.length - 1)
      : (current + step + enabledIndexes.length) % enabledIndexes.length;
    setActiveIndex(enabledIndexes[next]);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (disabled) return;

    if (!open) {
      if (["Enter", " ", "ArrowDown", "ArrowUp"].includes(event.key)) {
        event.preventDefault();
        const preferred = event.key === "ArrowUp"
          ? enabledIndexes[enabledIndexes.length - 1]
          : selectedIndex;
        openMenu(preferred);
      }
      return;
    }

    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      event.nativeEvent.stopImmediatePropagation();
      closeMenu();
    } else if (event.key === "Tab") {
      closeMenu();
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      moveActive(1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      moveActive(-1);
    } else if (event.key === "Home") {
      event.preventDefault();
      setActiveIndex(enabledIndexes[0]);
    } else if (event.key === "End") {
      event.preventDefault();
      setActiveIndex(enabledIndexes[enabledIndexes.length - 1]);
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      choose(activeIndex);
    } else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
      typeaheadRef.current += event.key.toLocaleLowerCase();
      if (typeaheadTimerRef.current !== null) window.clearTimeout(typeaheadTimerRef.current);
      typeaheadTimerRef.current = window.setTimeout(() => { typeaheadRef.current = ""; }, 500);
      const match = options.findIndex((option) => (
        !option.disabled && option.label.toLocaleLowerCase().startsWith(typeaheadRef.current)
      ));
      if (match >= 0) setActiveIndex(match);
    }
  };

  useLayoutEffect(() => {
    if (!open) return;

    const updatePosition = () => {
      const trigger = triggerRef.current;
      if (!trigger) return;
      const rect = trigger.getBoundingClientRect();
      const width = Math.min(Math.max(rect.width, 128), window.innerWidth - VIEWPORT_GAP * 2);
      const spaceBelow = window.innerHeight - rect.bottom - MENU_GAP - VIEWPORT_GAP;
      const spaceAbove = rect.top - MENU_GAP - VIEWPORT_GAP;
      const openAbove = spaceBelow < 144 && spaceAbove > spaceBelow;
      const available = Math.max(80, openAbove ? spaceAbove : spaceBelow);
      const left = Math.min(
        Math.max(VIEWPORT_GAP, rect.left),
        window.innerWidth - width - VIEWPORT_GAP,
      );
      const position: MenuPosition = {
        left,
        width,
        maxHeight: Math.min(MAX_MENU_HEIGHT, available),
      };
      if (openAbove) position.bottom = window.innerHeight - rect.top + MENU_GAP;
      else position.top = rect.bottom + MENU_GAP;
      setMenuPosition(position);
    };

    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!triggerRef.current?.contains(target) && !menuRef.current?.contains(target)) closeMenu();
    };
    document.addEventListener("pointerdown", handlePointerDown, true);
    return () => document.removeEventListener("pointerdown", handlePointerDown, true);
  }, [open]);

  useEffect(() => {
    if (!open || activeIndex < 0) return;
    document.getElementById(`${listboxId}-option-${activeIndex}`)?.scrollIntoView({ block: "nearest" });
  }, [activeIndex, listboxId, open]);

  useEffect(() => () => {
    if (typeaheadTimerRef.current !== null) window.clearTimeout(typeaheadTimerRef.current);
  }, []);

  const sizeClass = size === "sm"
    ? "rounded-md py-1 pl-2 pr-7 text-[12px]"
    : "rounded-lg py-1.5 pl-3 pr-8 text-[13px]";

  const menuStyle: CSSProperties | undefined = menuPosition ? {
    left: menuPosition.left,
    width: menuPosition.width,
    maxHeight: menuPosition.maxHeight,
    top: menuPosition.top,
    bottom: menuPosition.bottom,
  } : undefined;

  return (
    <span className={`relative inline-flex min-w-0 ${className}`}>
      <button
        ref={triggerRef}
        type="button"
        disabled={disabled}
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open && !disabled}
        aria-controls={open && !disabled ? listboxId : undefined}
        aria-activedescendant={open && !disabled && activeIndex >= 0 ? `${listboxId}-option-${activeIndex}` : undefined}
        onClick={() => open ? closeMenu() : openMenu()}
        onKeyDown={handleKeyDown}
        className={`surface flex min-w-0 flex-1 items-center text-left text-ink outline-none transition-colors hover:border-line-strong focus-visible:border-accent disabled:cursor-not-allowed disabled:opacity-40 ${sizeClass} ${monospace ? "font-mono" : ""}`}
      >
        <span className={`min-w-0 flex-1 truncate ${selectedOption ? "" : "text-ink-faint"}`} title={selectedOption?.label}>
          {selectedOption?.label ?? "Select"}
        </span>
        <ChevronDown
          size={size === "sm" ? 12 : 14}
          className={`absolute right-2 shrink-0 text-ink-faint transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && !disabled && menuPosition && createPortal(
        <div
          ref={menuRef}
          id={listboxId}
          role="listbox"
          aria-label={ariaLabel}
          style={menuStyle}
          className="fade-in fixed z-[100] overflow-y-auto rounded-lg border border-line bg-surface p-1 shadow-[0_12px_32px_rgba(15,23,42,0.18)]"
        >
          {options.map((option, index) => {
            const selected = option.value === value;
            const active = index === activeIndex;
            return (
              <div
                key={option.value}
                id={`${listboxId}-option-${index}`}
                role="option"
                aria-selected={selected}
                aria-disabled={option.disabled || undefined}
                onMouseEnter={() => { if (!option.disabled) setActiveIndex(index); }}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => choose(index)}
                className={`flex min-h-8 items-center gap-2 rounded-md px-2 py-1.5 text-[12.5px] transition-colors ${
                  option.disabled
                    ? "cursor-not-allowed text-ink-faint opacity-50"
                    : active
                      ? "cursor-pointer bg-clay text-accent-ink"
                      : "cursor-pointer text-ink-dim"
                }`}
              >
                <span className={`min-w-0 flex-1 truncate ${monospace ? "font-mono" : ""}`} title={option.label}>
                  {option.label}
                </span>
                {selected && <Check size={13} className="shrink-0 text-accent" />}
              </div>
            );
          })}
        </div>,
        document.body,
      )}
    </span>
  );
}
