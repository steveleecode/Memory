export const DEFAULT_CAMERA_POSITION = { x: 0, y: 0, z: 9 };
export const DEFAULT_CAMERA_TARGET = { x: 0, y: 0, z: 0 };

export type CameraVector = typeof DEFAULT_CAMERA_POSITION;
export type CameraFocusPoint = {
  x3: number;
  y3: number;
  z3: number;
};

export function cameraFocusTarget(point: CameraFocusPoint | null) {
  if (!point) {
    return {
      position: DEFAULT_CAMERA_POSITION,
      target: DEFAULT_CAMERA_TARGET,
    };
  }
  return {
    position: {
      x: point.x3 * 0.28,
      y: point.y3 * 0.28,
      z: 8.2,
    },
    target: {
      x: point.x3 * 0.18,
      y: point.y3 * 0.18,
      z: point.z3,
    },
  };
}
