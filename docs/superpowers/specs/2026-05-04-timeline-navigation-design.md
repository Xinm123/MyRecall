# Timeline Navigation Buttons — Design Spec

## Context

The timeline view (`/timeline`) displays frames from a single day as a slider-based viewer. Users can already:

- Drag the slider to seek
- Press `ArrowLeft` / `ArrowRight` to navigate
- Click play button for auto-playback

There is no visible UI affordance for prev/next navigation. This spec adds carousel-style arrow buttons on the image.

## Goal

Add "previous frame" and "next frame" buttons on the left and right sides of the timeline image, making navigation discoverable for mouse/touch users without interfering with existing keyboard or playback functionality.

## Decision

Adopt **carousel-style overlay buttons** (centered vertically on each side of the image).

- Most intuitive for image browsing.
- Consistent with macOS Preview, Google Photos, and other image viewers.
- Does not compete with playback controls for space.

## Visual Design

### Button Appearance

| Property       | Value                                      |
|----------------|--------------------------------------------|
| Shape          | 40 × 40 px circle                          |
| Position       | Vertical center of image container         |
| Left button    | `left: 12px`                               |
| Right button   | `right: 12px`                              |
| Default state  | `background: rgba(0,0,0,0.35)`             |
| Icon           | White SVG chevron (`stroke="white"`)       |
| Hover          | `background: rgba(0,0,0,0.6)`              |
| Focus          | Same as hover (visible focus ring for keyboard tab users) |
| Boundary (first/last) | Hidden (`x-show` / `display: none`) |

### Layout (within `.image-container`)

```
┌──────────────────────────────────────┐
│  [◀]                    🗑️ [▶]      │
│   prev                 next          │
│                                      │
│           [  frame image  ]          │
│                                      │
└──────────────────────────────────────┘
```

- Delete button (`top: 12px; right: 12px`) remains untouched.
- Navigation arrows sit in the side margins, overlapping the image only if the viewport is narrow.

## Behavior

| Trigger              | Action                                   |
|----------------------|------------------------------------------|
| Click Prev (`◀`)     | `currentIndex -= 1`; stop playback       |
| Click Next (`▶`)     | `currentIndex += 1`; stop playback       |
| Prev at first frame  | Button hidden                            |
| Next at last frame   | Button hidden                            |
| Playback active      | Buttons still visible, click stops it    |
| Frame deleted        | Recalculate visibility after array splice|

## Keyboard

Existing keyboard shortcuts remain unchanged:

| Key           | Action                          |
|---------------|---------------------------------|
| `ArrowLeft`   | Previous frame                  |
| `ArrowRight`  | Next frame                      |
| `Space`       | Toggle playback                 |

## Implementation Scope

### Files to Modify

1. `openrecall/client/web/templates/timeline.html`
   - Add CSS classes `.nav-arrow`, `.nav-arrow-left`, `.nav-arrow-right`
   - Add two `<button>` elements inside `.image-container`
   - Add `goPrev()` and `goNext()` methods in Alpine.js component

## Testing Checklist

- [ ] Prev button hides on first frame, shows on frame 2+
- [ ] Next button hides on last frame, shows on frames < last
- [ ] Clicking either button stops active playback
- [ ] After deleting the last frame, Next disappears
- [ ] After deleting frame 0 with only 2 frames, Prev disappears
- [ ] Buttons visible in both light and dark mode
- [ ] Buttons do not overlap delete button at any window width
