# PhotoFold

**Keep every shot. Store the shared scene once.**

PhotoFold helps people keep every photo from a moment without storing the same background again and again. It turns a burst of similar photos into one smaller, reconstructable `.photofold` collection while preserving every frame.

## Why PhotoFold

People often take several photos to capture the right smile, gesture, or expression. Existing photo cleaners solve the resulting storage problem by asking users to delete most of those photos. PhotoFold takes a different approach: keep every version, identify what the photos share, and store the differences that make each frame unique.

The prototype is local-first. Personal photos stay on the user’s computer, and a downloaded collection can be opened and reconstructed without a network connection.

## Product experience

1. **Choose** 5–20 JPEG, PNG, or WebP photos from the same moment.
2. **Check** which photos can safely share storage.
3. **Create** one collection that preserves every compatible or independently stored frame.
4. **Compare and export** rebuilt photos, inspect visual differences, save an individual image, or download the complete archive.

PhotoFold reports the real size of the finished archive and measures how closely every rebuilt photo matches its original. If a photo is not a safe match, PhotoFold keeps it whole instead of forcing it into the shared representation.

## What makes it different

Traditional image formats compress each photo independently. Duplicate cleaners find similar photos so users can delete them. PhotoFold preserves every frame while encoding the shared visual relationship across one moment.

This creates a practical balance between storage, quality, and trust: users keep every photo, uncertain frames remain protected, and the product explains what happened instead of hiding failed quality checks.

## Measured evidence

Every evaluated `.photofold` archive reconstructed every frame from the archive alone.

On the seven-photo reference burst:

- Original photos: **4,408,395 bytes**
- PhotoFold archive: **677,744 bytes**
- Independently compressed WebP comparison at equal or better measured quality: **725,126 bytes**
- PhotoFold relational advantage: **47,382 bytes**
- Mean visual-similarity score: **0.851131**
- Lowest per-photo score: **0.826471**

Three additional real-world bursts contained **42 photos** and **98,292,352 source bytes**, producing **26,297,683 PhotoFold bytes**. Results varied with camera movement, lighting, and scene stability, showing where shared storage works best and where keeping a frame independent is the safer choice.

## Run the demo

### Requirements

- Python 3.12
- Node.js 20.9 or newer
- npm 10 or newer
- macOS or another Unix-like environment

### Install

From the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install \
  --constraint services/processor/requirements.lock \
  -e 'services/processor[dev]'
npm ci
```

### Start

```bash
make human-verify-gate3 DATASET=data/demo/hdrplus-static
```

Open <http://127.0.0.1:3000>, upload the seven images from `data/demo/hdrplus-static/`, and follow the four on-screen steps. Stop the demo with `Ctrl-C`.

## Sample data

`data/demo/hdrplus-static/` contains seven checksum-verified 1600×1200 JPEG frames derived from one Google HDR+ mobile-camera burst. The images are licensed CC BY-SA 4.0; provenance, attribution, source URLs, conversion settings, and checksums are documented in [`data/demo/README.md`](data/demo/README.md).

Three additional bursts covering handheld capture, moving subjects, and camera or lighting changes are available under `data/real-bursts/`.

## Technology

The processor uses Python, OpenCV, Pillow/WebP, NumPy, scikit-image, and Pydantic. The product experience uses Next.js, React, TypeScript, Tailwind CSS, Vitest, and Playwright.

Under the hood, PhotoFold aligns compatible photos, stores one shared scene with the information needed to recover each frame, validates the finished archive, and reconstructs every photo without reading the original upload directory.

## How Codex and GPT-5.6 were used

We began with a product hypothesis and used Codex with GPT-5.6 to turn it into a measurable system. Codex accelerated implementation across the Python pipeline, Next.js interface, archive format, typed contracts, and automated tests.

GPT-5.6 helped challenge assumptions and shape key product decisions: measure the complete finished archive, compare against independently compressed photos at matched quality, reconstruct without the original uploads, preserve uncertain frames independently, and explain quality failures clearly.

The result was an iterative loop of **hypothesis → implementation → test → failure analysis → revised design → measured evidence**. GPT-5.6 shaped the engineering and evaluation process while the codec remained deterministic, private, and locally reconstructable.

Detailed requirements, experiment methodology, and technical contracts are available in [`docs/`](docs/).
