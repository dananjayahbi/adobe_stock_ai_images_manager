import type { HTMLAttributes, ReactNode } from "react";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  /** Renders the ticket-stub dashed divider under the header, if given. */
  header?: ReactNode;
}

/** The framed paper card — double hairline, warm shadow, ticket header. */
export default function Card({
  children,
  header,
  className = "",
  ...rest
}: CardProps) {
  return (
    <div className={`frame-card animate-fade-up ${className}`} {...rest}>
      {header && (
        <div className="border-b border-dashed border-parchment-400 px-5 pb-3 pt-4">
          {header}
        </div>
      )}
      <div className="px-5 py-4">{children}</div>
    </div>
  );
}
