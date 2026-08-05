# 04 — UI/UX Brief: Ethara Seat Allocation & Project Mapping System

The visual language. Lock it in once so every screen feels like the same product.

## Aesthetic

Clean, dense, trustworthy enterprise dashboard — "operations console, not a toy". Light-first, calm neutrals with one confident indigo accent, data-forward tables and charts, generous whitespace around dense data. Think Linear's precision + a facilities-ops tool's clarity. Not flashy, not generic-Bootstrap.

## Reference apps

- Linear (typographic precision, restraint, keyboard-first)
- Vercel dashboard (calm neutrals, crisp cards, clear hierarchy)
- Retool / internal-tool dashboards (data density done tastefully)

## Core palette

| Role | Light | Dark |
|---|---|---|
| Background | `#F8FAFC` (slate-50) | `#0B1120` |
| Surface | `#FFFFFF` | `#111827` |
| Text primary | `#0F172A` (slate-900) | `#F1F5F9` |
| Text muted | `#64748B` (slate-500) | `#94A3B8` |
| Primary / CTA | `#4F46E5` (indigo-600) | `#6366F1` |
| Border | `#E2E8F0` (slate-200) | `#1F2937` |
| Danger | `#DC2626` (red-600) | `#F87171` |

### Extended palette

| Role | Light | Dark |
|---|---|---|
| Surface elevated | `#FFFFFF` + shadow | `#1E293B` |
| Primary hover | `#4338CA` | `#4F46E5` |
| Accent | `#0EA5E9` (sky-500) | `#38BDF8` |
| Success | `#16A34A` (green-600) | `#4ADE80` |
| Warning | `#D97706` (amber-600) | `#FBBF24` |

**Seat-status colors** (used consistently in tables, chips, charts):
- Available → green `#16A34A`
- Occupied → slate `#64748B`
- Reserved → amber `#D97706`
- Maintenance → red `#DC2626`

## Typography

- **UI font**: Inter (system-ui fallback)
- **Mono font**: JetBrains Mono (seat codes like `B4-23`, employee codes)
- **Heading scale**: 30 / 24 / 20 / 16
- **Body**: 14 (default), 16 (emphasis)
- **Caption**: 12
- **Line height**: 1.5 body, 1.25 headings
- **Numerals**: tabular-nums in all tables and metric tiles

## Shape language

- **Border radius**: 8px default, 12px cards, 9999px pills/status chips
- **Shadows**: `0 1px 2px rgba(15,23,42,.06), 0 1px 3px rgba(15,23,42,.10)` for cards; elevated modals get a larger soft shadow
- **Borders**: 1px hairline `#E2E8F0`

## Density

Balanced-to-dense. Tables are the primary surface: 40px rows, comfortable padding, sticky header, zebra optional. Metric tiles are airy to stay scannable.

## Mode

- **Default**: light
- **User can toggle**: yes (light/dark toggle in top bar; persisted). Dark mode is fully specified above but light is the primary target for QA.

## Components

### Buttons
- **Variants**: primary (indigo), secondary (surface + border), ghost, destructive (red), link
- **Sizes**: sm (28px) / md (36px) / lg (44px)
- **Hover**: subtle bg shift + 100ms
- **Disabled**: 50% opacity, no pointer

### Forms
- **Input**: 1px border, 8px radius, focus ring 2px indigo
- **Label**: above input, 13px medium, muted
- **Error**: below input, danger color, 12px
- **Select/date**: native-friendly, consistent height with inputs

### Cards / lists / tables
- **Cards**: surface bg, 1px border, 12px radius, p-4/p-6
- **Metric tile**: big tabular number (30px), label (12px muted), optional delta/subtext, status color where relevant
- **Tables**: sticky header, 40px rows, hover highlight, status rendered as colored pill, seat/employee codes in mono
- **Lists**: divided by 1px hairline

### Feedback
- **Toast**: top-right, 4s auto-dismiss, color-coded (success/danger/info)
- **Modal**: centered, backdrop blur, Escape closes, confirm-destroy for releases

### Charts (dashboard)
- Recharts: horizontal bar for project-wise allocation, stacked/segmented bar for floor-wise occupancy (Occupied/Available/Reserved/Maintenance), donut for overall seat-status split. Use the seat-status colors above. Always show a legend + tooltips; never rely on color alone (label values).

## Motion

- **Duration**: 150ms standard, 250ms entering
- **Easing**: `cubic-bezier(0.16, 1, 0.3, 1)` (easeOutExpo) — corporate-calm, no bounce
- **Reduce-motion**: respect `prefers-reduced-motion` (disable non-essential transitions)

## Mobile

- **Breakpoints**: 640 / 768 / 1024 / 1280
- **Touch targets**: minimum 44×44
- **Navigation pattern**: hamburger drawer; tables → scrollable or card layout; charts stack vertically

## Accessibility

- **WCAG target**: AA
- **Contrast**: ≥ 4.5:1 body text, ≥ 3:1 large; status never conveyed by color alone (always paired with text label)
- **Keyboard nav**: full — every interactive element reachable; command/search focus shortcut
- **Focus visible**: yes, never `outline: none` without a replacement ring
- **Screen reader**: meaningful labels on icon buttons; charts have text summaries / accessible tables as fallback
