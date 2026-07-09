import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/cn";

export type FeatureCard = {
  icon: LucideIcon;
  title: string;
  description: string;
};

type FeatureGridProps = Readonly<{
  features: FeatureCard[];
  className?: string;
}>;

export function FeatureGrid({ features, className }: FeatureGridProps) {
  return (
    <div
      className={cn(
        "feature-grid my-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3",
        className,
      )}
    >
      {features.map((feature) => {
        const Icon = feature.icon;

        return (
          <div
            key={feature.title}
            className="rounded-[4px] border border-border bg-panel p-5 transition-colors hover:bg-panel-raised"
            data-card
          >
            <div className="mb-3 flex items-center gap-3">
              <span className="flex size-10 shrink-0 items-center justify-center rounded-[4px] border border-border bg-panel-raised">
                <Icon className="size-5 text-text-primary" strokeWidth={2} />
              </span>
              <h4 className="text-base font-semibold text-text-primary">
                {feature.title}
              </h4>
            </div>
            <p className="text-sm leading-relaxed text-text-secondary">
              {feature.description}
            </p>
          </div>
        );
      })}
    </div>
  );
}
