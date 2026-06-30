# styles/

## Responsibility

Global CSS for the OpenQMS "Precision Forge" industrial dark theme.
Defines the `--qf-*` design-token CSS variables (colours, fonts,
spacing, sizing, shadows, transitions), a small set of global
element rules (`html`, `body`, `#root`, the noise overlay), and imports
the web fonts used throughout the UI. Ant Design component tokens are
configured separately in `utils/darkTheme.ts` and must mirror the
values declared here.

## File Organisation

One file:

- `design-system.css` — the entire stylesheet. ~460 lines covering:
  - `@import` of Chakra Petch and JetBrains Mono (Google Fonts) and
    优设标题黑 (jsDelivr) for Chinese headings.
  - `:root` design-token declarations:
    `--qf-bg-*` (background layers), `--qf-border*`, `--qf-divider`,
    accent colours (`--qf-cyan`, `--qf-amber`, `--qf-red`,
    `--qf-green`, `--qf-blue`, `--qf-purple` with `*-dim` / `*-glow`
    variants), `--qf-text-*`, `--qf-font-display/body/mono`,
    `--qf-space-{xs,sm,md,lg,xl}`,
    `--qf-{header-height,sider-width,sider-collapsed}`,
    `--qf-radius-{sm,md,lg}`, `--qf-shadow-{sm,md,glow}`,
    `--qf-transition-{fast,base}`.
  - Global element rules (`html`, `body`, `#root` heights;
    `body` font, background, anti-aliasing).
  - The full-screen noise overlay (`#root::before` with an inline
    SVG `feTurbulence`).
  - Component-level rule overrides and utility classes after the
    token block.

## Public Interface

- **Imported once** by `frontend/src/main.tsx`:
  ```ts
  import "./styles/design-system.css";
  ```
  Nothing else in the codebase imports this file; tokens are
  consumed by everything indirectly through the cascade.
- **CSS variables** are the API. Components reference them with
  `var(--qf-bg-panel)`, `var(--qf-cyan)`, `var(--qf-radius-md)`,
  etc., either inline or via Ant Design `style` props.
- **No CSS Modules, no styled-components, no Tailwind.** Component
  styling is split between Ant Design's token system (configured in
  `utils/darkTheme.ts`) and inline `style` props that reference
  these variables.

## Conventions & Constraints

- **Keep this file and `utils/darkTheme.ts` in lock-step.** The Ant
  Design `ThemeConfig` declares the same colour palette, background
  layers, and radii as the `--qf-*` tokens here. Changing one
  without the other will cause subtle drift between native HTML
  elements and AntD components.
- **All tokens are prefixed `--qf-*`.** This is the "Precision Forge"
  namespace; do not add unprefixed globals.
- **Imports of web fonts stay at the top.** Some `@import` URLs
  (notably the Chinese display font on jsDelivr) carry visible
  latency on cold loads; consider self-hosting if these ever become
  a problem, but don't sprinkle additional `@import` URLs further
  down the file — keep the network surface auditable.
- **Dark theme only.** There is no light variant. The
  `prefers-color-scheme` media query is intentionally not honoured;
  this is an industrial-control aesthetic and downstream component
  styles assume a dark background.
- **Reduced motion** is honoured at the component level (see
  `utils/darkTheme.ts` reading `prefers-reduced-motion`), not via
  CSS overrides in this file.

## Dependencies

- **Depends on:** the three external font sources only.
- **Depended on by:** `main.tsx` (single import); every component
  transitively through the cascade and through the `var(--qf-*)`
  references in `utils/darkTheme.ts`.
