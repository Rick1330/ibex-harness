import { readFileSync } from "node:fs";
import { rename } from "node:fs/promises";

/** True when a Node fs error indicates a missing path. */
export function isEnoent(error) {
  return error?.code === "ENOENT";
}

/** Renames a path and ignores ENOENT so idempotent stash/restore is safe. */
export async function renameIgnoreMissing(from, to, logMessage) {
  try {
    await rename(from, to);
    if (logMessage) {
      console.log(logMessage);
    }
  } catch (error) {
    if (isEnoent(error)) {
      return;
    }
    throw error;
  }
}

function stripBom(content) {
  if (content.codePointAt(0) === 0xfeff) {
    return content.slice(1);
  }
  return content;
}

function trimCr(value) {
  return value.endsWith("\r") ? value.slice(0, -1) : value;
}

function unquoteDoubleQuoted(value) {
  if (value.startsWith('"') && value.endsWith('"')) {
    return value.slice(1, -1);
  }
  return value;
}

function unquoteSingleQuoted(value) {
  if (value.startsWith("'") && value.endsWith("'")) {
    return value.slice(1, -1);
  }
  return value;
}

function unquoteEnvValue(value) {
  return unquoteSingleQuoted(unquoteDoubleQuoted(value));
}

/** Load KEY=VALUE pairs from a dotenv file into process.env. */
export function loadEnvFile(filePath) {
  let content = readFileSync(filePath, "utf8");
  content = stripBom(content);

  for (const rawLine of content.split("\n")) {
    const line = trimCr(rawLine);
    const match = line.match(/^([^#=]+)=(.*)$/);
    if (!match) {
      continue;
    }

    const key = trimCr(match[1].trim());
    const value = unquoteEnvValue(trimCr(match[2].trim()));
    process.env[key] = value;
  }
}
