import {
  Children,
  cloneElement,
  isValidElement,
  type ReactElement,
  type ReactNode,
} from "react";

import { cn } from "@/lib/cn";

type StepsProps = {
  children: ReactNode;
};

type StepProps = {
  title?: string;
  children: ReactNode;
  index?: number;
  isLast?: boolean;
};

export function Step({ title, children, index = 1, isLast = false }: StepProps) {
  return (
    <div className={cn("relative flex gap-4", !isLast && "pb-8")}>
      {!isLast ? (
        <span
          aria-hidden
          className="absolute bottom-0 left-[13px] top-7 w-px bg-border"
        />
      ) : null}
      <span
        aria-hidden
        className="relative z-[1] flex size-7 shrink-0 items-center justify-center rounded-[4px] border border-border bg-panel-raised text-xs font-medium text-text-primary"
      >
        {index}
      </span>
      <div className="min-w-0 flex-1 pt-0.5">
        {title ? (
          <p className="mb-2 font-medium text-text-primary">{title}</p>
        ) : null}
        <div className="text-text-secondary [&_p:first-child]:mt-0 [&_p:last-child]:mb-0">
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
    <div className="my-6">
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
