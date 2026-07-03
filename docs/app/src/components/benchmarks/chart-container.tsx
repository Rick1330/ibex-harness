import { forwardRef } from "react";

import { cn } from "@/lib/cn";

type ChartContainerProps = Readonly<{
  label: string;
  className?: string;
}>;

export const ChartContainer = forwardRef<HTMLDivElement, ChartContainerProps>(
  function ChartContainer({ label, className }, ref) {
    return (
      <figure className={cn("w-full", className)}>
        <figcaption className="sr-only">{label}</figcaption>
        <div ref={ref} className="chart-container w-full" />
      </figure>
    );
  },
);
