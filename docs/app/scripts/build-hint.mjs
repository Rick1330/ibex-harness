console.log(`
[build] Expected phases (silent gaps are normal on Windows):

  1. [MDX] updated map file                    ~30ms
  2. Creating an optimized production build    45–90s, no output
  3. Linting and checking validity of types
  4. Generating static pages (276)             progress shown
  5. Collecting build traces                   30s–3min, no output
  6. Finishing writing to cache                1–5min, no output

Do NOT run \`pnpm start\` until the build exits with code 0.
If cache write loops, try: pnpm build:fast
`);
