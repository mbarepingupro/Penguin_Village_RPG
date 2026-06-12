# Penguin Wearing Sprites

Items as they appear ON the penguin sprite. Layered on top of the base penguin.

## Shape-specific paths (preferred)

Each cosmetic should have two versions:

```
static/penguin_wearing/normal/<slot>/<item_id>.png
static/penguin_wearing/tall/<slot>/<item_id>.png
```

The village map will load the shape-specific version first and fall back to the
legacy flat path below.

## Legacy flat path (fallback)

```
static/penguin_wearing/<slot>/<item_id>.png
```

## Canvas size

- 64x40 pixels — two 32x40 frames side-by-side (matching penguin_normal.png / penguin_tall.png)
- Legacy sprites may still use 64x32 until migrated

## Format

- PNG with transparent background — ONLY the item, no penguin body
- No anti-aliasing — pixel art only
- Frame 1: pixels 0–31, Frame 2: pixels 32–63

## Slots

- `hats/`        — positioned on top of penguin head
- `outfits/`     — positioned on penguin body
- `footwear/`    — positioned at penguin feet
- `accessories/` — positioned on penguin face/side

Naming: must match item_id exactly
