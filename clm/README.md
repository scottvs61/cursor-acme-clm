# Certificate Lifecycle Manager (CLM)

Backend API and optional React GUI for certificate lifecycle management. This document describes **GUI color and layout customization** for the web interface.

---

## Where the GUI Lives

The CLM web UI is a React (Vite) app in the repo at **`frontend/`**, not under `clm/`. The CLM server serves the built static files from `frontend/dist` when you run the CLM (e.g. `uvicorn clm.app.main:app`). To change the GUI’s look and feel, edit files in **`frontend/src/`** and then rebuild.

---

## Color Modifications

All global colors are defined in **one place**: CSS custom properties in **`frontend/src/index.css`**, inside the **`:root`** block at the top of the file.

### Theme Variables

| Variable | Purpose | Example (current light theme) |
|----------|---------|-------------------------------|
| `--bg` | Page background | `#f5f6f8` |
| `--surface` | Cards, sidebar background | `#ffffff` |
| `--surface-hover` | Hover state for rows, nav items | `#eef0f3` |
| `--border` | Borders, dividers | `#d1d5db` |
| `--text` | Primary text | `#1f2937` |
| `--text-muted` | Labels, secondary text | `#6b7280` |
| `--accent` | Primary buttons, links, active nav | `#2563eb` |
| `--accent-dim` | Accent hover (if used) | `#1d4ed8` |
| `--success` | Success alerts, success buttons | `#059669` |
| `--warning` | Warning state | `#d97706` |
| `--error` | Error alerts, revoke button | `#dc2626` |
| `--on-accent` | Text on accent buttons (e.g. white) | `#ffffff` |
| `--on-success` | Text on success buttons | `#ffffff` |
| `--radius` | Border radius for cards/inputs | `8px` |
| `--font` | Font family | `'IBM Plex Sans', system-ui, ...` |

To change the overall look (e.g. to your corporate palette), edit the hex values (or units) in that **`:root`** block. The rest of the UI uses these variables, so one edit updates the whole app.

### Applying Color Changes

1. Edit **`frontend/src/index.css`** (`:root` block).
2. From the **repo root** run:
   ```bash
   cd frontend && npm run build && cd ..
   ```
3. Restart the CLM server if it is already running, then reload the app in the browser.

---

## Layout Modifications

Layout is controlled by the same **`frontend/src/index.css`** and by the React components under **`frontend/src/`**.

### Main structure

- **`.app`** — Flex container: sidebar + main content.
- **`.sidebar`** — Fixed-width left column (nav: Certificates, Enroll, Bulk Enroll, SCEP). Width, padding, and borders are set in `index.css` (e.g. `width: 220px`).
- **`.main`** — Main content area; flexes to fill remaining space. Padding is set in `index.css` (e.g. `padding: 1.5rem 2rem`).

Navigation and which page is shown are defined in **`frontend/src/App.jsx`** (`PAGES` array and sidebar `<nav>`).

### Page-level layout

- **`.page-title`** — Large heading on each page.
- **`.card`** / **`.card-header`** / **`.card-body`** — Card containers and sections.
- **`.form-group`** — Form fields (label + input/textarea); spacing and input styles in `index.css`.
- **Tables** — `.table-wrap`, `table`, `th`, `td` for list/detail tables.

To change layout (e.g. sidebar width, main padding, card spacing), edit the corresponding class in **`frontend/src/index.css`**. To change structure or navigation, edit **`frontend/src/App.jsx`** and the page components (e.g. **`Certificates.jsx`**, **`Enroll.jsx`**, **`BulkEnroll.jsx`**, **`SCEP.jsx`**).

### Applying layout changes

Same as for colors: edit **`frontend/src/index.css`** and/or the **`frontend/src/*.jsx`** files, then from repo root run **`cd frontend && npm run build && cd ..`**, and restart/refresh the CLM app.

---

## Optional: Dark theme

To support both light and dark themes:

1. In **`frontend/src/index.css`**, keep the current **`:root`** as the default (e.g. light) theme.
2. Add a second block, e.g. **`.theme-dark`**, with the same variable names but dark values (e.g. `--bg: #0d1117`, `--surface: #161b22`, `--text: #e6edf3`, etc.).
3. In **`frontend/index.html`** or your root React component, set the theme by adding/removing a class on `<html>` (e.g. `document.documentElement.classList.add('theme-dark')` when the user selects dark mode).

Components already use the CSS variables, so they will follow whichever theme class is applied.

---

## Quick reference

| Goal | File(s) to edit |
|------|------------------|
| Change colors (whole app) | `frontend/src/index.css` (`:root`) |
| Change sidebar width, main padding, card/table styles | `frontend/src/index.css` (`.sidebar`, `.main`, `.card`, etc.) |
| Change nav items or page set | `frontend/src/App.jsx` |
| Change content or forms on a page | `frontend/src/Certificates.jsx`, `Enroll.jsx`, `BulkEnroll.jsx`, `SCEP.jsx` |

After any change to the frontend, run **`cd frontend && npm run build && cd ..`** from the repo root so the CLM serves the updated GUI.
