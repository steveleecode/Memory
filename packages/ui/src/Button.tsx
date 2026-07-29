import type { ButtonHTMLAttributes, ReactNode } from "react";

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  icon?: ReactNode;
  variant?: "primary" | "secondary" | "ghost";
};

export function Button({
  children,
  icon,
  variant = "secondary",
  type = "button",
  ...props
}: ButtonProps) {
  return (
    <button className={`memory-button memory-button--${variant}`} type={type} {...props}>
      {icon ? <span className="memory-button__icon">{icon}</span> : null}
      {children ? <span>{children}</span> : null}
    </button>
  );
}
