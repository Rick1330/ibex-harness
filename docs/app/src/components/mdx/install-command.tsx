"use client";

import { useEffect, useMemo, useState } from "react";

import { CodeTab, CodeTabs } from "@/components/mdx/code-tabs";
import { ShellBlock } from "@/components/mdx/shell-block";

type PackageManager = "npm" | "pnpm" | "yarn" | "bun";

const STORAGE_KEY = "ibex-docs-preferred-pm";
const MANAGERS: PackageManager[] = ["npm", "pnpm", "yarn", "bun"];

type InstallCommandProps = Readonly<{
  packages: string;
  dev?: boolean;
}>;

type CommandMap = ReturnType<typeof buildCommands>;

function buildCommands(packages: string, dev: boolean) {
  return {
    npm: `npm install ${dev ? "-D " : ""}${packages}`,
    pnpm: `pnpm add ${dev ? "-D " : ""}${packages}`,
    yarn: `yarn add ${dev ? "-D " : ""}${packages}`,
    bun: `bun add ${dev ? "-d " : ""}${packages}`,
  } as const;
}

function commandForManager(commands: CommandMap, manager: PackageManager): string {
  switch (manager) {
    case "npm":
      return commands.npm;
    case "pnpm":
      return commands.pnpm;
    case "yarn":
      return commands.yarn;
    case "bun":
      return commands.bun;
  }
}

export function InstallCommand({ packages, dev = false }: InstallCommandProps) {
  const commands = useMemo(
    () => buildCommands(packages, dev),
    [packages, dev],
  );
  const [manager, setManager] = useState<PackageManager>("pnpm");

  useEffect(() => {
    const saved = localStorage.getItem(STORAGE_KEY) as PackageManager | null;
    if (saved && MANAGERS.includes(saved)) setManager(saved);
  }, []);

  const onManagerChange = (value: string) => {
    const next = value as PackageManager;
    setManager(next);
    localStorage.setItem(STORAGE_KEY, next);
  };

  return (
    <CodeTabs onValueChange={onManagerChange} value={manager}>
      {MANAGERS.map((pm) => (
        <CodeTab key={pm} label={pm} value={pm}>
          <ShellBlock
            className="my-0 rounded-t-none border-t-0"
            command={commandForManager(commands, pm)}
          />
        </CodeTab>
      ))}
    </CodeTabs>
  );
}
