type BenchmarkPageHeaderProps = Readonly<{
  title: string;
  subtitle: string;
}>;

export function BenchmarkPageHeader({ title, subtitle }: BenchmarkPageHeaderProps) {
  return (
    <header className="mb-8">
      <p className="mb-2 text-xs font-semibold uppercase tracking-widest text-muted-foreground">
        Performance
      </p>
      <h1 className="text-3xl font-bold tracking-tight text-foreground md:text-4xl">{title}</h1>
      <p className="mt-2 max-w-2xl text-sm text-muted-foreground">{subtitle}</p>
    </header>
  );
}
