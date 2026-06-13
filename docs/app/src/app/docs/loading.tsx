export default function DocsLoading() {
  return (
    <div className="mx-auto w-full max-w-3xl animate-pulse px-6 py-10">
      <div className="mb-3 h-9 w-2/3 rounded-[4px] bg-panel-raised" />
      <div className="mb-8 h-5 w-1/2 rounded-[4px] bg-panel-raised" />
      <div className="space-y-3">
        <div className="h-4 w-full rounded-[4px] bg-panel-raised" />
        <div className="h-4 w-full rounded-[4px] bg-panel-raised" />
        <div className="h-4 w-5/6 rounded-[4px] bg-panel-raised" />
        <div className="h-4 w-full rounded-[4px] bg-panel-raised" />
        <div className="h-4 w-4/6 rounded-[4px] bg-panel-raised" />
      </div>
    </div>
  );
}
