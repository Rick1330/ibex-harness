"use client";

import type { ReactNode } from "react";

import { useReveal } from "@/hooks/use-reveal";

type RevealProps = Readonly<{
  children: ReactNode;
  delay?: number;
  className?: string;
}>;

export function Reveal({ children, delay = 0, className = "" }: RevealProps) {
  const { ref, shown } = useReveal<HTMLDivElement>();

  return (
    <div
      ref={ref}
      className={className}
      style={{
        opacity: shown ? 1 : 0,
        transform: shown ? "translateY(0)" : "translateY(22px)",
        transition: `opacity 0.6s ease ${delay}ms, transform 0.6s cubic-bezier(0.16,1,0.3,1) ${delay}ms`,
      }}
    >
      {children}
    </div>
  );
}
