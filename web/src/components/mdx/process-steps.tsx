import { cn } from "@/lib/cn";

export type ProcessStep = {
  title: string;
  description: string;
};

type ProcessStepsProps = Readonly<{
  steps: ProcessStep[];
}>;

export function ProcessSteps({ steps }: ProcessStepsProps) {
  return (
    <div className="nd-steps process-steps my-10" data-steps>
      {steps.map((step, index) => {
        const isLast = index === steps.length - 1;

        return (
          <div
            key={step.title}
            className={cn(
              "nd-step process-step relative flex gap-4",
              !isLast && "pb-8",
            )}
            data-step
          >
            {isLast ? null : (
              <span
                aria-hidden
                className="absolute bottom-0 left-4 top-8 w-px bg-border"
              />
            )}
            <div className="relative z-10 flex shrink-0">
              <span
                className="nd-step-number flex size-8 items-center justify-center rounded-full border border-border bg-muted font-mono text-[0.8125rem] font-semibold text-foreground"
                data-step-number
              >
                {index + 1}
              </span>
            </div>
            <div className="min-w-0 flex-1 pt-1">
              <h3 className="mb-2 text-base font-semibold text-text-primary">
                {step.title}
              </h3>
              <p className="m-0 text-[0.9375rem] leading-[1.65] text-text-secondary">
                {step.description}
              </p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
