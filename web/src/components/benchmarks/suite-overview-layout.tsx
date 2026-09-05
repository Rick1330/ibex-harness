import type { ReactNode } from "react";

type SuiteOverviewLayoutProps = Readonly<{
  status: ReactNode;
  kpis: ReactNode;
  sla?: ReactNode;
  trend: ReactNode;
  extras?: ReactNode;
}>;

export function SuiteOverviewLayout({
  status,
  kpis,
  sla,
  trend,
  extras,
}: SuiteOverviewLayoutProps) {
  return (
    <div className="min-w-0 space-y-8">
      {status}
      {kpis}
      <section
        className={
          sla ? "grid min-w-0 gap-4 lg:grid-cols-3" : "min-w-0"
        }
      >
        <div className={sla ? "min-w-0 lg:col-span-2" : "min-w-0"}>{trend}</div>
        {sla ? <div className="min-w-0">{sla}</div> : null}
      </section>
      {extras}
    </div>
  );
}
