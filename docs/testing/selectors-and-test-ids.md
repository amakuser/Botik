# Selectors and Test IDs

This document defines the selector contract for UI automation and future feature development.

## Selector Priority

Use selectors in this order:

1. role
2. label
3. stable semantic text
4. data-testid

## Why This Order

- role and label improve accessibility and testability together;
- semantic selectors survive styling changes;
- explicit test ids remain available for complex widgets and non-semantic structures.

## data-testid Naming Standard

Format:

`screen.entity.action`

Rules:

- use lowercase;
- use stable domain terms;
- avoid styling, layout, or visual naming;
- avoid raw positional names;
- include a stable domain identifier for repeated rows when needed.

## Examples

Good:

- `jobs.start-button`
- `jobs.stop-button`
- `jobs.log-panel`
- `telegram.refresh-status`
- `models.row.futures-champion`

Bad:

- `blue-button`
- `left-tab`
- `button-3`
- `logs-div-2`

## When data-testid Is Required

Use `data-testid` when:

- the element is not semantically exposed in a stable way;
- text is dynamic or localized in a way that would make the selector fragile;
- the widget is complex enough that role/label alone is ambiguous.

## Tabs, Rows, Dialogs, and Lists

Recommended patterns:

- tabs: `screen.tab.name`
- rows: `screen.row.<stable-id>`
- dialogs: `screen.dialog.name`
- status cards: `screen.status.name`
- log panes: `screen.log-pane.name`

## Review Rule

If a new screen cannot be tested cleanly with this selector model, the product implementation should be questioned before the test is weakened.
