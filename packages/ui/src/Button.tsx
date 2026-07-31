import type { ButtonHTMLAttributes, ReactNode } from "react";
import { pressElement } from "./animations";

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  icon?: ReactNode;
  variant?: "primary" | "secondary" | "ghost";
};

export function Button({
  children,
  icon,
  onPointerDown,
  variant = "secondary",
  type = "button",
  ...props
}: ButtonProps) {
  return (
    <button
      className={`memory-button memory-button--${variant}`}
      type={type}
      onPointerDown={(event) => {
        onPointerDown?.(event);
        if (!event.defaultPrevented && !props.disabled) {
          pressElement(event.currentTarget);
        }
      }}
      {...props}
    >
      {icon ? <span className="memory-button__icon">{icon}</span> : null}
      {children ? <span>{children}</span> : null}
    </button>
  );
}
