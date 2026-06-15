import {
  Children,
  cloneElement,
  isValidElement,
  type ReactElement,
  type ReactNode,
} from "react";

import { cn } from "@/lib/cn";

type StepsProps = Readonly<{
  children: ReactNode;
}>;

type StepProps = Readonly<{
  title?: string;
  children: ReactNode;
  index?: number;
  isLast?: boolean;
}>;

export function Step({ title, children, index = 1, isLast = false }: StepProps) {
  return (
    <div
      className={cn("nd-step process-step relative flex gap-4", !isLast && "pb-8")}
      data-step
    >
      {!isLast ? (
        <span
          aria-hidden
          className="absolute bottom-0 left-4 top-8 w-px bg-border"
        />
      ) : null}
      <span
        aria-hidden
        className="nd-step-number relative z-[1] flex size-8 shrink-0 items-center justify-center rounded-full border border-border bg-muted font-mono text-[0.8125rem] font-semibold text-foreground"
        data-step-number
      >
        {index}
      </span>
      <div className="min-w-0 flex-1 pt-1">
        {title ? (
          <h3 className="mb-2 text-base font-semibold text-text-primary">
            {title}
          </h3>
        ) : null}
        <div className="text-[0.9375rem] leading-[1.65] text-text-secondary [&_p:first-child]:mt-0 [&_p:last-child]:mb-0">
          {children}
        </div>
      </div>
    </div>
  );
}

export function Steps({ children }: StepsProps) {
  const steps = Children.toArray(children).filter(isValidElement) as ReactElement<
    StepProps
  >[];

  return (
    <div className="nd-steps process-steps my-8" data-steps>
      {steps.map((step, index) =>
        cloneElement(step, {
          index: index + 1,
          isLast: index === steps.length - 1,
          key: index,
        }),
      )}
    </div>
  );
}
