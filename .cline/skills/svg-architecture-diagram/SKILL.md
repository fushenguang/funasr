---
name: svg-architecture-diagram
description: Draw polished, self-contained SVG architecture diagrams for the TheFoolAI wiki (flowchart / structural / illustrative / comparison), using a standardized warm/muted design system. This skill is self-contained — the full design system ships alongside it in reference/design-system.md; read that file first, then draw.
---

# SVG Architecture Diagram Skill (Claude Code entry point)

**Design system (read this first)**: `reference/design-system.md` (relative to this SKILL.md).

This skill is **self-contained and hub-portable**: the complete design system and example
diagrams live inside this skill directory, so publishing to a skill hub never breaks a link.
The authoritative source of `reference/design-system.md` and `examples/` is the `.cline`
copy of this skill; they are synced here by `pnpm skill:sync:svg` (see "Sync mechanism"
below). Do not hand-edit the synced files here — edit the `.cline` source and re-run sync.

---

## Invocation

```
/svg-architecture-diagram Draw an Electron process-model architecture diagram (structural)
```

## Workflow (5 steps, in order)

1. **Read** `reference/design-system.md` (relative to this file — do NOT reach into `.cline/…`).
2. **Diagnose** the diagram type: flowchart / structural / illustrative / comparison.
3. **Plan coordinates** using the "Coordinate planning template" at the end of the design
   system (box width via the formula, row width ≤560, viewBox H = last y+h+40).
4. **Generate** the SVG from the design system's self-contained template (4-section `<style>`
   theming, arrow marker in `<defs>`, `fill="var(--svg-canvas)"` backdrop rect, warm/muted
   palette, ≤3 color scales).
5. **Self-check** against the design system's "Mandatory pre-output checklist", then save to
   `apps/wiki/content/docs/diagrams/<kebab-case>.svg` and output the embed snippet.

## Quick reference

**Canvas**: `viewBox="0 0 680 H"` (H explicitly calculated)
**Type sizes**: 14px (`th`/`t`) / 12px (`ts`)
**Palette**: warm/muted — peach `#FADADD` (core), butter `#F9EDD6` (middleware), sage
`#DDE4D6` (infra), deep warm brown text `#5C4B3A`, warm gray-brown arrows `#C4B5A0`; ≤3
scales per diagram
**Backdrop**: `fill="var(--svg-canvas)"` (themed — never hardcode `#FDF9F2`)
**Save to**: `apps/wiki/content/docs/diagrams/<topic>.svg`
**Banned**: high-saturation purple `#7C3AED` / deep green `#064E3B`, pure black, `onclick`,
bare `<text>`, estimated coordinates, >3 color scales, missing `<style>` theming block

## Examples

See `examples/` in this skill directory: `structural-three-tier-app.svg` and
`flowchart-ci-pipeline.svg`, both using the current warm/muted palette.

## Sync mechanism (single source of truth)

- **Truth source**: `.cline/skills/svg-architecture-diagram/reference/design-system.md` and
  `.cline/skills/svg-architecture-diagram/examples/*.svg`.
- **Publish copy**: this directory's `reference/` and `examples/` are copies synced from the
  truth source, so this skill is self-contained for hub publishing.
- **Sync**: `pnpm skill:sync:svg` (copies truth → here). CI/verification:
  `pnpm skill:sync:svg:check` fails if the copies drift from the source.
- Never hand-edit `reference/design-system.md` or `examples/` here — edit the `.cline` source
  and re-run the sync.
