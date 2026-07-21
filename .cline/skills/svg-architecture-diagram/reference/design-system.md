# SVG Architecture Diagram Design System

**Single source of truth**: `.cline/skills/svg-architecture-diagram/reference/design-system.md`
Other entry points (`.claude/skills/svg-architecture-diagram/`, the wiki writing-standard quick
reference) link to this file — they do not duplicate it. `.claude`'s copy is a build-time sync
of this file (see the skill's `SKILL.md` §Sync mechanism); this file is the one you edit.

> **Design origin — v5 "Claude Editorial".** This system is modeled directly on the reference
> diagram exported from the Claude desktop app (`apify_mcp_server_architecture.svg`). Its whole
> character is: **flat solid pastel fills · 1px hairline same-hue borders · neutral warm-gray
> container bands · two text tiers · no fill-opacity, no gradients, no drop-shadows.** The calm,
> "comfortable to look at" feel comes from restraint — thin borders and soft fills, not effects.
> The earlier v4 (peach/sage warm palette with 1.5px borders + fill-opacity + gradients/shadows)
> is **retired**; do not reintroduce opacity, gradients, shadows, or heavy borders.

---

## Canvas & coordinate system

- `viewBox` must be `"0 0 680 H"` — 680px width is a fixed payload, never change it
- H = the (y + height) of the bottom-most element + 40px; **must be calculated, never estimated**
- Safe area: x=40..640, y=40..(H-40); no element may exceed it; no negative coordinates

Top-level structure:

```svg
<svg width="100%" viewBox="0 0 680 [H]" role="img" xmlns="http://www.w3.org/2000/svg">
  <title>[diagram title]</title>
  <desc>[one-sentence description of what this diagram shows]</desc>
  <style>/* self-contained v5 theming block — see "Self-contained theming" below */</style>
  <defs><!-- arrow marker — must come after <style>, before any content --></defs>
  <rect x="0" y="0" width="680" height="[H]" fill="var(--svg-canvas)"/><!-- theme-aware backdrop -->
  <!-- diagram content -->
</svg>
```

---

## Arrow marker (required)

Every diagram with connectors declares this marker in `<defs>`, right after `<style>`:

```svg
<defs>
  <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5"
          markerWidth="6" markerHeight="6" orient="auto-start-reverse">
    <path d="M2 1L8 5L2 9" fill="none" stroke="context-stroke"
          stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
  </marker>
</defs>
```

Connector reference: `class="arr" marker-end="url(#arrow)"`. Every connector `<line>`/`<path>`
carries `class="arr"` (stroke `#898781`, 1.5px). Dashed leader lines use `class="leader"`.
Every connector `<path>` must have `fill="none"`.

---

## Typography

| Class | Size | Weight | Use |
|-------|------|--------|-----|
| `t`   | 14px | 400    | body text |
| `th`  | 14px | 500    | node title (inside a colored box → same-hue dark heading) |
| `ts`  | 12px | 400    | subtitle / annotation |
| `band-label` | 12px | 400 | group label on a container band (neutral gray) |

Rules:
- **Only these two sizes (14/12) and two weights (400/500)** — never 600/700
- Every `<text>` carries a class — no bare `<text>`
- Text inside a box gets `dominant-baseline="central"` + `text-anchor="middle"`
- Font stack leads with `"Anthropic Sans"` then system fallbacks; it degrades gracefully where
  Anthropic Sans is unavailable
- Sentence case; never all-caps or title-case
- No text wraps automatically; use a second `<text class="ts">` line for a subtitle

**Width estimation**: 14px ≈ 8px/char, 12px ≈ 7px/char.
Box min width = max(title_chars × 8, subtitle_chars × 7) + 32px padding.

---

## Color system (v5 Claude Editorial)

Two structural rules mirror the reference exactly:

1. **Color lives on leaf boxes, never on bands.** A leaf box = a soft pastel `fill` + a **1px
   same-hue border** (`stroke`) + **same-hue dark text**. Bands (grouping containers) are always
   the neutral warm-gray `--band-*` tokens — they organize space, they do not carry category.
2. **Flat only.** Solid fills (no `fill-opacity`), 1px borders, no gradients, no drop-shadows.

Category classes are applied to the `<g>` wrapping shape+text. **Never apply to a `<path>`.**
**Use at most 3 category scales per diagram.** Color encodes category, never sequence.

### Category scales (light — exact reference values)

| Class | Semantic use | fill | stroke (1px border) | th (title) | ts (subtitle) |
|-------|--------------|------|---------------------|------------|---------------|
| `c-purple` | core / entry point (indigo) | `#EEEDFE` | `#534AB7` | `#3C3489` | `#534AB7` |
| `c-teal`   | infrastructure / data (green) | `#E1F5EE` | `#0F6E56` | `#085041` | `#0F6E56` |
| `c-blue`   | process / information | `#E6F1FB` | `#185FA5` | `#0C447C` | `#185FA5` |
| `c-coral`  | tool / tech (terracotta) | `#FAECE7` | `#993C1D` | `#712B13` | `#993C1D` |
| `c-amber`  | external / warning (gold) | `#FAEEDA` | `#854F0B` | `#633806` | `#854F0B` |
| `c-gray`   | neutral leaf | `#F1EFE8` | `#A8A69E` | `#4A4945` | `#6B6A66` |
| `c-green`  | success / result | `#E7F4E4` | `#3B8A44` | `#245C2A` | `#3B8A44` |
| `c-pink`   | auxiliary category | `#FCE9F1` | `#B84A7D` | `#83224F` | `#B84A7D` |
| `c-red`    | error / danger | `#FBE9E7` | `#C0392B` | `#7E2018` | `#C0392B` |

### Structure & global tokens (light)

| Token | Value | Note |
|-------|-------|------|
| `--svg-canvas` | `#FCFAF5` | theme-aware backdrop rect (dark `#1A1815`) |
| `--svg-text-primary` | `#3D3B37` | titles / body outside boxes — **never pure black** |
| `--svg-text-secondary` | `#6B6A66` | annotations / band labels |
| `--svg-arr` | `#898781` | connectors, 1.5px |
| `--band-fill` / `--band-stroke` | `#F1EFE8` / `#5F5E5A` | neutral container band (dark `#232019` / `#8A8880`) |

Each scale also has derived **dark-mode** values (deep tinted fill + lighter stroke + light text);
they ship inside every SVG's `<style>` block (below). The `-fill/-stroke/-th/-ts` variables also
have `-bg/-bd/-h/-s` aliases so older markup keeps resolving.

### Guardrails

- Text-to-background contrast as high as practical; the `th`/`ts` tokens are deliberately dark
  against their pastel `fill`.
- **Every `<svg>` includes a `fill="var(--svg-canvas)"` backdrop `rect`** so it never renders on a
  transparent background against a mismatched page. Use the variable — **never hardcode** the hex,
  or dark mode shows a light rectangle.
- No pure black (`#000000`), no high-saturation jewel tones (`#7C3AED`, `#064E3B`), no
  `fill-opacity`, no `<linearGradient>`/`feDropShadow` on boxes.

---

## Self-contained theming (core)

Every SVG **inlines this exact `<style>` block** — light default + system-dark + wiki-dark-toggle
+ wiki-light-override (4 sections). Paste it verbatim; it is generated from this file's tokens.

```svg
<style>
/* ── v5 Claude Editorial · light (flat solid fills · 1px hairline borders · no opacity/gradient/shadow) ── */
:root, :host {
  --svg-font: "Anthropic Sans", -apple-system, "system-ui", "Segoe UI", Arial, sans-serif;
  --svg-text-primary: #3D3B37; --svg-text-secondary: #6B6A66; --svg-arr: #898781; --svg-canvas: #FCFAF5;
  --band-fill: #F1EFE8; --band-stroke: #5F5E5A;
  --c-purple-fill: #EEEDFE; --c-purple-stroke: #534AB7; --c-purple-th: #3C3489; --c-purple-ts: #534AB7;
  --c-teal-fill: #E1F5EE; --c-teal-stroke: #0F6E56; --c-teal-th: #085041; --c-teal-ts: #0F6E56;
  --c-blue-fill: #E6F1FB; --c-blue-stroke: #185FA5; --c-blue-th: #0C447C; --c-blue-ts: #185FA5;
  --c-coral-fill: #FAECE7; --c-coral-stroke: #993C1D; --c-coral-th: #712B13; --c-coral-ts: #993C1D;
  --c-amber-fill: #FAEEDA; --c-amber-stroke: #854F0B; --c-amber-th: #633806; --c-amber-ts: #854F0B;
  --c-gray-fill: #F1EFE8; --c-gray-stroke: #A8A69E; --c-gray-th: #4A4945; --c-gray-ts: #6B6A66;
  --c-green-fill: #E7F4E4; --c-green-stroke: #3B8A44; --c-green-th: #245C2A; --c-green-ts: #3B8A44;
  --c-pink-fill: #FCE9F1; --c-pink-stroke: #B84A7D; --c-pink-th: #83224F; --c-pink-ts: #B84A7D;
  --c-red-fill: #FBE9E7; --c-red-stroke: #C0392B; --c-red-th: #7E2018; --c-red-ts: #C0392B;
}
/* dark: standalone .svg viewing */
@media (prefers-color-scheme: dark) { :root, :host {
  --svg-text-primary: #E8E4DC; --svg-text-secondary: #A8A49C; --svg-arr: #7C7A74; --svg-canvas: #1A1815;
  --band-fill: #232019; --band-stroke: #8A8880;
  --c-purple-fill: #23213A; --c-purple-stroke: #8B82D6; --c-purple-th: #CFCBF5; --c-purple-ts: #A9A2E6;
  --c-teal-fill: #17302A; --c-teal-stroke: #4FA98E; --c-teal-th: #B6E4D3; --c-teal-ts: #6FC0A6;
  --c-blue-fill: #162A3A; --c-blue-stroke: #5A93C8; --c-blue-th: #BEDAF0; --c-blue-ts: #7FB0DC;
  --c-coral-fill: #3A241A; --c-coral-stroke: #C87551; --c-coral-th: #F0C4AE; --c-coral-ts: #D89675;
  --c-amber-fill: #352915; --c-amber-stroke: #C79A4C; --c-amber-th: #EBD6A0; --c-amber-ts: #D4B472;
  --c-gray-fill: #26241E; --c-gray-stroke: #8A8880; --c-gray-th: #DAD6CC; --c-gray-ts: #A8A49C;
  --c-green-fill: #1E3320; --c-green-stroke: #5AA860; --c-green-th: #C0E4C0; --c-green-ts: #7FC084;
  --c-pink-fill: #34202B; --c-pink-stroke: #C86F98; --c-pink-th: #F0C6DA; --c-pink-ts: #D897B4;
  --c-red-fill: #3A211D; --c-red-stroke: #C56A5D; --c-red-th: #F0C2BA; --c-red-ts: #D8938A;
} }
/* dark: wiki in-site theme toggle (html.dark) — same values as @media dark */
/* light override: html:not(.dark) — same values as :root */
text { font-family: var(--svg-font); }
text.t  { font-size: 14px; font-weight: 400; fill: var(--svg-text-primary); }
text.th { font-size: 14px; font-weight: 500; fill: var(--svg-text-primary); }
text.ts { font-size: 12px; font-weight: 400; fill: var(--svg-text-secondary); }
.band-label { font-family: var(--svg-font); font-size: 12px; font-weight: 400; fill: var(--svg-text-secondary); }
.arr    { stroke: var(--svg-arr); stroke-width: 1.5px; fill: none; }
.leader { stroke: var(--svg-arr); stroke-width: 1px; stroke-dasharray: 4 3; fill: none; }
rect.band { fill: var(--band-fill); stroke: var(--band-stroke); stroke-width: 1px; }
.c-purple rect, .c-purple circle, .c-purple ellipse { fill: var(--c-purple-fill); stroke: var(--c-purple-stroke); stroke-width: 1px; }
.c-purple text.th, .c-purple text.t { fill: var(--c-purple-th); } .c-purple text.ts { fill: var(--c-purple-ts); }
/* …repeat one rule-triple per remaining scale (teal/blue/coral/amber/gray/green/pink/red)… */
</style>
```

> **Generation note.** The full block that ships in each SVG duplicates the light values into an
> `html.dark { … }` (= @media dark) and an `html:not(.dark) { … }` (= :root) section — the wiki
> theme toggle stamps `.dark` on `<html>`, and the explicit override wins over `@media` so the
> "system-dark + wiki-light" conflict is resolved. It also emits `-bg/-bd/-h/-s` aliases and
> `-band/-ring` (neutral) aliases. Regenerate all diagrams' blocks with the skill's sync/apply
> step rather than hand-editing 4 sections.

---

## Box & band patterns

### Single-line box (44px tall)
```svg
<g class="c-blue">
  <rect x="100" y="40" width="180" height="44" rx="8"/>
  <text class="th" x="190" y="62" text-anchor="middle" dominant-baseline="central">Label</text>
</g>
```

### Two-line box (60px tall)
```svg
<g class="c-teal">
  <rect x="100" y="40" width="200" height="60" rx="8"/>
  <text class="th" x="200" y="62" text-anchor="middle" dominant-baseline="central">Title</text>
  <text class="ts" x="200" y="82" text-anchor="middle" dominant-baseline="central">Subtitle</text>
</g>
```

### Container band (neutral grouping boundary)

Bands are **always neutral gray** (`class="band"`), never a category color. Corner radius `rx=12`.

> **⚠️ Label spacing law**:
> - Band label centered at top: `y = band.y + 22`, `text-anchor="middle"`, `class="band-label"`
>   (matches the reference), OR top-left `y = band.y + 8` with `dominant-baseline="hanging"`.
> - First inner element `y ≥ band.y + 30`.
> - Band height = `30 + content_height + 12`.

```svg
<rect x="40" y="40" width="600" height="80" rx="12" class="band"/>
<text class="band-label" x="340" y="62" text-anchor="middle">Transport 层</text>
<!-- inner colored leaf boxes drawn AFTER the band, on top -->
<g class="c-purple">
  <rect x="60" y="72" width="160" height="36" rx="6"/>
  <text class="th" x="140" y="90" text-anchor="middle" dominant-baseline="central">Streamable HTTP</text>
</g>
```

### Connectors
```svg
<line x1="340" y1="124" x2="340" y2="140" class="arr" marker-end="url(#arrow)"/>
```
**L-shaped polyline** (route around an obstacle):
```svg
<path d="M200 96 L200 120 L350 120 L350 140" class="arr" marker-end="url(#arrow)"/>
```

---

## Layout rules

1. Box spacing ≥16px; arrow gap between adjacent bands ≥14px
2. Total row width = (n × box_w) + ((n-1) × gap) ≤ 560px
3. No overlap: left box right edge + 16 ≤ right box left edge in the same row
4. All single-line boxes share height 44px; all two-line boxes 60px
5. Arrows never cross an unrelated box; use an L-shaped polyline if needed
6. Band label law (above): content y ≥ band.y + 30, band.h = 30 + content + 12

---

## Diagram type selection

| User intent keywords | Type | Layout direction |
|-----------------------|------|-------------------|
| steps / process / pipeline / workflow | **flowchart** | top-to-bottom or left-to-right |
| architecture / components / internal structure | **structural** | neutral bands + colored leaf boxes |
| how it works / explain / principle | **illustrative** | free-space metaphor |
| comparison / vs / difference / selection | **comparison** | parallel columns |

---

## Mandatory pre-output checklist

- [ ] `viewBox` is `"0 0 680 H"`, H explicitly calculated (not estimated)
- [ ] `<style>` is the v5 self-contained block with 4 theme sections
- [ ] Box style is v5: **solid fill + 1px same-hue border + same-hue dark text** — no
      `fill-opacity`, no gradient, no drop-shadow, no border > 1px
- [ ] Bands use `class="band"` (neutral gray) — color only on leaf boxes
- [ ] Colors from the v5 scales — **no `#7C3AED`/`#064E3B`, no pure black**
- [ ] `<svg>` has a `fill="var(--svg-canvas)"` backdrop rect (variable, not hardcoded)
- [ ] `<defs>` arrow marker present, before content
- [ ] Every `<text>` carries a class; every connector has `class="arr"`/`"leader"` + `fill="none"`
- [ ] Band label law respected (content y ≥ band.y+30)
- [ ] No box overlap; all text fits its box (width formula); arrows cross nothing
- [ ] ≤3 category scales, assigned semantically
- [ ] Output path: `apps/wiki/content/docs/diagrams/<kebab-case>.svg`

---

## Coordinate planning template (fill in before generating)

```
Diagram type: [flowchart / structural / illustrative / comparison]
Total nodes: [N]      Nodes per row: [n]
Box width: max([title_chars]×8, [subtitle_chars]×7) + 32 = [W]px
Row total: [n]×[W] + ([n]-1)×[gap] = [?]px  ← must be ≤560
viewBox H: [last element y+h] + 40 = [H]px
Band (structural): band.y=[Y]; label y=Y+22 (middle); content start y=Y+30; band.h=30+[content_h]+12
Per-box coordinates: row1 y=[?] x=[?] gap=[?]; row2 …
```

**Column-count quick reference** (gap=18, band width 600, margin=40):

| Columns | box_w | row total | first x |
|---------|-------|-----------|---------|
| 2 | 260 | 538 | 71 |
| 3 | 168 | 540 | 70 |
| 4 | 120 | 534 | 73 |
| 5 | 98  | 562 | 59 |
