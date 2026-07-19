# PhotoFold Demo Script

**Target length:** 2:20 to 2:40  
**Purpose:** Product demonstration only. This file is not an implementation specification.

---

## 0:00 to 0:15 - Problem

Show a phone-storage warning, followed by a rapid sequence of similar photos.

On-screen text:

> I took 14 photos to get one moment right.

Then:

> They use 62 MB, even though most of every photo is the same.

---

## 0:15 to 0:25 - Product reveal

On-screen text:

> Meet PhotoFold.

Subtext:

> Keep every shot. Store the scene once.

---

## 0:25 to 0:50 - Upload and analysis

Upload the photo set.

Show real analysis results such as:

- Photos detected from the same moment
- Shared-scene percentage
- Pose or expression changes
- One unique visual event
- Recommended reference frame

Show one short GPT-5.6 observation that explains a meaningful difference.

---

## 0:50 to 1:20 - Fold the moment

Animate the images aligning.

Visually separate:

- Shared scene
- Meaningful subject changes
- Residual corrections

Select:

> Fold this moment

Animate the assets collapsing into one PhotoFold package.

---

## 1:20 to 1:45 - Show the result

Display real measured values:

- Original size
- PhotoFold package size
- Storage percentage saved
- Photos reconstructed
- Mean quality score

Do not use hard-coded example values in the working product.

---

## 1:45 to 2:15 - Prove reconstruction

- Swipe through reconstructed frames
- Use the original-versus-reconstruction slider
- Zoom into a face or clothing detail
- Show a difference heatmap
- Export one reconstructed frame as a standard image

---

## 2:15 to 2:30 - Explain the architecture

Show:

```text
Similar photos
→ GPT-5.6 semantic preservation
→ OpenCV alignment
→ shared scene plus frame differences
→ reconstructable PhotoFold package
```

Clarify:

- GPT-5.6 identifies meaningful visual changes
- Deterministic computer vision performs alignment, encoding, reconstruction, and measurement
- Codex was used to build, test, and debug the pipeline

---

## 2:30 to 2:40 - Close

On-screen text:

> Your memories are not duplicates.

Then:

> But their backgrounds often are.

Final screen:

> PhotoFold  
> Keep every shot. Store the scene once.
