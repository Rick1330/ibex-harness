
export type ParamRow = {
  name: string;
  type: string;
  required?: boolean;
  description: string;
  defaultValue?: string;
};

type ParamTableProps = Readonly<{
  params: ParamRow[];
}>;

export function ParamTable({ params }: ParamTableProps) {
  return (
    <div className="my-6 overflow-x-auto rounded-md border border-border">
      <table className="w-full text-sm">
        <thead className="border-b border-border bg-panel-raised">
          <tr>
            <th className="px-4 py-3 text-start font-medium text-text-primary">
              Parameter
            </th>
            <th className="px-4 py-3 text-start font-medium text-text-primary">
              Type
            </th>
            <th className="px-4 py-3 text-start font-medium text-text-primary">
              Description
            </th>
          </tr>
        </thead>
        <tbody>
          {params.map((param) => (
            <tr className="border-t border-border" key={param.name}>
              <td className="px-4 py-3 align-top">
                <code className="font-mono text-xs text-text-primary">
                  {param.name}
                </code>
                {param.required ? (
                  <span className="ms-2 rounded-[4px] border border-danger/40 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-danger">
                    Required
                  </span>
                ) : null}
              </td>
              <td className="px-4 py-3 align-top">
                <code className="font-mono text-xs text-info">{param.type}</code>
              </td>
              <td className="px-4 py-3 align-top text-text-secondary">
                <div>{param.description}</div>
                {param.defaultValue ? (
                  <div className="mt-1 font-mono text-xs text-text-tertiary">
                    Default: {param.defaultValue}
                  </div>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
