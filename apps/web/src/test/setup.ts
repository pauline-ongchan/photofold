import "@testing-library/jest-dom/vitest";

import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

Object.defineProperty(URL, "createObjectURL", {
  configurable: true,
  value: vi.fn((file: File) => `blob:${file.name}`),
});
Object.defineProperty(URL, "revokeObjectURL", {
  configurable: true,
  value: vi.fn(),
});

class LoadedImage {
  naturalWidth = 1600;
  naturalHeight = 1200;
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;

  set src(_value: string) {
    queueMicrotask(() => this.onload?.());
  }
}

vi.stubGlobal("Image", LoadedImage);
