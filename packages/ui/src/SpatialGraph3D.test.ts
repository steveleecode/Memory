import { describe, expect, it } from "vitest";
import {
  cameraFocusTarget,
  DEFAULT_CAMERA_POSITION,
  DEFAULT_CAMERA_TARGET,
  type CameraFocusPoint,
} from "./spatialCamera";

describe("cameraFocusTarget", () => {
  it("returns the default graph view when no point is selected", () => {
    expect(cameraFocusTarget(null)).toEqual({
      position: DEFAULT_CAMERA_POSITION,
      target: DEFAULT_CAMERA_TARGET,
    });
  });

  it("derives synchronized camera and orbit target coordinates from a selected point", () => {
    expect(cameraFocusTarget(pointFixture({ x3: 4, y3: -2, z3: 0.5 }))).toEqual({
      position: { x: 1.12, y: -0.56, z: 8.2 },
      target: { x: 0.72, y: -0.36, z: 0.5 },
    });
  });
});

function pointFixture(overrides: Partial<CameraFocusPoint> = {}): CameraFocusPoint {
  return {
    x3: 0,
    y3: 0,
    z3: 0,
    ...overrides,
  };
}
