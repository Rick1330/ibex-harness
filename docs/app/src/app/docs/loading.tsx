export default function DocsLoading() {
  return (
    <div
      className="docs-loading mx-auto w-full max-w-3xl px-6 py-10"
      aria-busy="true"
      aria-label="Loading page"
    >
      <div className="docs-loading-bar mb-3 h-9 w-2/3 rounded-[4px] bg-panel-raised" />
      <div className="docs-loading-bar mb-8 h-5 w-1/2 rounded-[4px] bg-panel-raised" />
      <div className="space-y-3">
        <div className="docs-loading-bar h-4 w-full rounded-[4px] bg-panel-raised" />
        <div className="docs-loading-bar h-4 w-full rounded-[4px] bg-panel-raised" />
        <div className="docs-loading-bar h-4 w-5/6 rounded-[4px] bg-panel-raised" />
        <div className="docs-loading-bar h-4 w-full rounded-[4px] bg-panel-raised" />
        <div className="docs-loading-bar h-4 w-4/6 rounded-[4px] bg-panel-raised" />
      </div>
    </div>
  );
}
