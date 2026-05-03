---
name: stank-frontend-patterns
description: Enforces stank-bot's SvelteKit frontend conventions — component hierarchy, store barrel, shared utilities, testing patterns. Trigger when editing any file under src/stankbot/web/frontend/src/ or creating new Svelte/TS modules there.
---

# StankBot frontend conventions

## Architecture

- **SvelteKit 2** with `@sveltejs/adapter-static` (SPA mode, no SSR).
- **Svelte 5 runes** (`$state`, `$derived`, `$effect`) in `.svelte` files. Traditional `writable` stores from `svelte/store` for cross-component state.
- **Route pages are thin shells.** The root `+page.svelte` delegates to `<WelcomePage>` (unauthenticated) or `<Dashboard>` (authenticated). Do not inline view logic in route files.

## Component hierarchy

`+layout.svelte` owns the shell: header, nav skeleton, WS lifecycle, `<ToastContainer>`. It hydrates auth stores from load data. Child routes render inside `<main>`.

`+page.svelte` → `<WelcomePage>` or `<Dashboard>`
Admin routes share `admin/+layout.svelte` (sidebar + auth guard).

## Reusable components (`$lib/components/`)

Always check existing components before creating new ones:

| Component | Purpose | Key props |
|-----------|---------|-----------|
| `Button` | Action button | `variant`, `loading`, `disabled`, `testId` |
| `Input` | Text input | `type`, `placeholder`, `bind:value` |
| `Toggle` | Boolean toggle | `checked`, `label`, `onchange` |
| `Select` | Dropdown select | `options`, `bind:value` |
| `Textarea` | Multi-line input | `rows`, `bind:value` |
| `Dropdown` | Popover menu | `align`, `bind:open`, `trigger` snippet, `children` |
| `DropdownItem` | Menu item | `href`, `active`, `danger` |
| `Modal` | Dialog overlay | `bind:open`, `title`, `children` |
| `ConfirmDialog` | Confirmation prompt | `bind:open`, `title`, `body`, `confirmLabel`, `danger`, `onconfirm` |
| `Tabs` | Tab switcher | `tabs`, `bind:active` |
| `Avatar` | User/guild icon | `src`, `name`, `userId`, `size` |
| `StatTile` | Labeled stat display | `value`, `label`, `color`, `flash`, `testId`, `valueTestId` |
| `RemovableItem` | List item with Remove | `onremove`, `children` snippet |
| `ToastContainer` | Toast + update banner | `updateToast`, `onreload` |
| `GuildSwitcher` | Guild list picker | `guilds`, `activeGuildId`, `switchingTo`, `onswitch`, `ontoggle`, `open` |
| `Card` | Section container | `title`, `footer` snippet, `children` snippet |
| `PageHeader` | Page title bar | `title`, `subtitle`, `actions` snippet |
| `ChainBreakOverlay` | Chain break animation | reads `$activeChainBreak` |
| `LiveBadge` | WS connection indicator | `disabled` |
| `EmptyState` | Empty/zero state | `icon`, `title`, `message` |
| `ErrorState` | Load error display | `title`, `message`, `onretry` |
| `Skeleton` | Loading placeholder | `width`, `height`, `rounded` |
| `NavSkeleton` | Full-page nav loading | `isAdminRoute` |
| `Sparkline` | Mini line chart | `values`, `ariaLabel` |
| `LeaderboardRow` | Single leaderboard row | `rank`, `row`, `isMe`, `context` |
| `Chart` | Chart.js wrapper (line/bar) — dark-theme aware; also handles media compare overlays via stacked datasets | `type`, `data`, `options` |
| `RelativeTime` | Live "N min ago" label that auto-ticks | `iso`, `fallback` |
| `SelectDropdown` | Icon-prefixed select (interval / metric pickers) | `options`, `bind:value` |
| `Tooltip` | Hover tooltip primitive — accepts `useNativeTooltip` to opt out of custom rendering | `text`, `useNativeTooltip` |
| `Duration` | Human duration (`XhYm`, max 2 units) | `seconds`, `useNativeTooltip` |
| `OnlineBadge` | Admin online-users popover | reads `$onlineUsers` |

Every component should use `data-testid` attributes for stable E2E queries. The `StatTile` component also accepts `valueTestId` when the inner value `<div>` needs its own test ID (e.g. `valueTestId="chain-counter"`).

## Store barrel (`$lib/stores/`)

The barrel at `src/lib/stores/index.ts` exports only what's consumed:

- `boardState` — leaderboard rankings, chain state, reactions
- `connectionStatus` / `wsLatency` — WS connection state
- `lastWsEvent` / `emitWsEvent` / `WsEvent` — side-channel events
- `toasts` / `addToast` / `removeToast` — notification queue
- `activeChainBreak` / `ChainBreakInfo` — chain break overlay state
- `guildId` / `user` / `guilds` — auth state
- `adminSidebarOpen` — admin sidebar toggle

**Deleted stores (do not use, do not import):**
- `loading.ts` — removed v2.29.2. Use local `$state` for loading flags.
- `player.ts` — removed v2.29.2. Player data loads per-page via `+page.ts`.
- `cache.ts` — removed v2.29.2. SessionStorage caching was unused.

When adding a new store, export it from `src/lib/stores/index.ts` so `$lib/stores` resolves it.

## Shared utilities

- **`$lib/format.ts`** — `formatNumber(n)` for M/K suffix display. Import instead of redefining.
- **`$lib/api-utils.ts`** — `toErrorMessage(err, fallback)` for standardized error extraction; `loadWithFallback(fetcher, options)` for page load error resilience.
- **`$lib/datetime.ts`** — `formatDateTime(isoStr, fallback)`, `formatResetTime(isoStr)`.
- **`$lib/api.ts`** — `apiFetch`, `apiPost`, `apiDelete`, `FetchError`. API calls MUST use these, never raw `fetch`.

## Testing conventions

- Use `data-testid` selectors in Playwright tests.
- `StatTile` exposes the value via `valueTestId` for precise assertions (e.g. `data-testid="chain-counter"`).
- E2E fixtures in `e2e/fixtures.ts`: `mockLogin`, `mockBotGuilds`, `newSession`, `injectStank`, `injectBreak`, `injectReaction`, `startRandomEvents`, `stopRandomEvents`.
- For WS frame interception in E2E: use `'framereceived'` event, not `'frames'`.
