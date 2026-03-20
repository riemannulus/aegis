<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-20 | Updated: 2026-03-20 -->

# components

## Purpose
Reusable Streamlit UI components shared across backoffice pages. Provides chart builders and filter widgets.

## Key Files

| File | Description |
|------|-------------|
| `charts.py` | Chart visualization utilities using Plotly (equity curves, candle charts, metric plots) |
| `filters.py` | Filter UI components (date range pickers, symbol selectors, status filters) |

## For AI Agents

### Working In This Directory
- Components are imported by page modules in `backoffice/pages/`
- Use Plotly for all chart types — consistent with the rest of the dashboard
- Keep components stateless where possible (let pages manage state)

### Common Patterns
- `from backoffice.components.charts import plot_equity_curve`
- `from backoffice.components.filters import date_range_filter`

## Dependencies

### External
- `plotly` — Chart library
- `streamlit` — UI framework

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
