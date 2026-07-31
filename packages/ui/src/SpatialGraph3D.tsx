import { Canvas } from "@react-three/fiber";
import type { ThreeEvent } from "@react-three/fiber";
import { useThree } from "@react-three/fiber";
import { Line, OrbitControls, Text } from "@react-three/drei";
import type { SearchResultContract } from "@memory/types";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ComponentRef,
  type RefObject,
} from "react";
import { gsap } from "gsap";
import { prefersReducedMotion } from "./animations";
import { cameraFocusTarget, type CameraVector } from "./spatialCamera";

type OrbitControlsHandle = ComponentRef<typeof OrbitControls>;

export type SpatialPoint = {
  result: SearchResultContract;
  x: number;
  y: number;
  x3: number;
  y3: number;
  z3: number;
  radius: number;
  radius3: number;
  priority: number;
};

export type SpatialGraph3DProps = {
  points: SpatialPoint[];
  selectedId: string | null;
  hoveredId: string | null;
  setSelectedId: (id: string) => void;
  setHoveredId: (id: string | null) => void;
  resetSignal: number;
};

export default function SpatialGraph3D({
  points,
  selectedId,
  hoveredId,
  setSelectedId,
  setHoveredId,
  resetSignal,
}: SpatialGraph3DProps) {
  const controlsRef = useRef<OrbitControlsHandle | null>(null);
  const [contextGeneration, setContextGeneration] = useState(0);
  const [contextLost, setContextLost] = useState(false);
  const recoverContext = useCallback(() => {
    setContextLost(false);
    setContextGeneration((generation) => generation + 1);
  }, []);
  return (
    <div className="graph-canvas" aria-label="Spatial relationship map">
      <Canvas key={contextGeneration} camera={{ position: [0, 0, 9], fov: 48 }} dpr={[1, 1.6]}>
        <color attach="background" args={["#fbfaf7"]} />
        <ambientLight intensity={1.8} />
        <pointLight position={[3, 4, 6]} intensity={1.2} />
        <WebGLContextRecovery
          onContextLost={() => {
            setContextLost(true);
          }}
          onContextRestored={recoverContext}
        />
        <GraphScene
          points={points}
          selectedId={selectedId}
          hoveredId={hoveredId}
          setSelectedId={setSelectedId}
          setHoveredId={setHoveredId}
          controlsRef={controlsRef}
          resetSignal={resetSignal}
        />
        <OrbitControls
          ref={controlsRef}
          enableDamping
          dampingFactor={0.12}
          maxDistance={14}
          minDistance={4}
          maxPolarAngle={Math.PI / 2}
        />
      </Canvas>
      {contextLost ? (
        <div className="graph-canvas__status" role="status">
          Restoring spatial map
        </div>
      ) : null}
    </div>
  );
}

function WebGLContextRecovery({
  onContextLost,
  onContextRestored,
}: {
  onContextLost: () => void;
  onContextRestored: () => void;
}) {
  const { gl } = useThree();
  useEffect(() => {
    const canvas = gl.domElement;
    function handleContextLost(event: Event) {
      event.preventDefault();
      onContextLost();
    }
    canvas.addEventListener("webglcontextlost", handleContextLost);
    canvas.addEventListener("webglcontextrestored", onContextRestored);
    return () => {
      canvas.removeEventListener("webglcontextlost", handleContextLost);
      canvas.removeEventListener("webglcontextrestored", onContextRestored);
    };
  }, [gl, onContextLost, onContextRestored]);
  return null;
}

function GraphScene({
  points,
  selectedId,
  hoveredId,
  setSelectedId,
  setHoveredId,
  controlsRef,
  resetSignal,
}: SpatialGraph3DProps & {
  controlsRef: RefObject<OrbitControlsHandle | null>;
}) {
  const center = points[0];
  const selectedPoint = points.find((point) => point.result.document_id === selectedId) ?? center;
  const connectedIds = useMemo(() => {
    const ids = new Set<string>();
    if (center) ids.add(center.result.document_id);
    if (selectedId) ids.add(selectedId);
    return ids;
  }, [center, selectedId]);
  return (
    <group>
      <CameraFocus
        controlsRef={controlsRef}
        point={selectedPoint ?? null}
        resetSignal={resetSignal}
      />
      {center
        ? points.slice(1).map((point) => {
            const isSelectedEdge = point.result.document_id === selectedId;
            const unrelated = Boolean(selectedId && !isSelectedEdge);
            return (
              <Line
                color={isSelectedEdge ? "#274f49" : unrelated ? "#d7d2c8" : "#9eb8b2"}
                key={`${center.result.document_id}-${point.result.document_id}`}
                lineWidth={isSelectedEdge ? 2.4 : 1.1}
                opacity={isSelectedEdge ? 0.86 : unrelated ? 0.22 : 0.56}
                points={[
                  [center.x3, center.y3, center.z3],
                  [point.x3, point.y3, point.z3],
                ]}
                transparent
              />
            );
          })
        : null}
      {points.map((point) => {
        const isSelected = point.result.document_id === selectedId;
        const isHovered = point.result.document_id === hoveredId;
        const connected = connectedIds.has(point.result.document_id);
        const dimmed = Boolean(selectedId && !isSelected && !connected);
        const labelVisible = isSelected || isHovered || (!selectedId && point.priority < 0.14);
        const materialColor =
          point.result.source_metadata.kind === "google_drive" ? "#286f7a" : "#4f7660";
        return (
          <group
            key={point.result.document_id}
            position={[point.x3, point.y3, point.z3]}
            onClick={(event: ThreeEvent<MouseEvent>) => {
              event.stopPropagation();
              setSelectedId(point.result.document_id);
            }}
            onPointerEnter={(event: ThreeEvent<PointerEvent>) => {
              event.stopPropagation();
              setHoveredId(point.result.document_id);
              document.body.style.cursor = "pointer";
            }}
            onPointerLeave={() => {
              setHoveredId(null);
              document.body.style.cursor = "";
            }}
          >
            {isSelected ? (
              <mesh rotation={[Math.PI / 2, 0, 0]}>
                <torusGeometry args={[point.radius3 + 0.09, 0.012, 12, 56]} />
                <meshBasicMaterial color="#24231f" transparent opacity={0.88} />
              </mesh>
            ) : null}
            <mesh scale={isSelected ? 1.24 : isHovered ? 1.1 : 1}>
              <sphereGeometry args={[point.radius3, 28, 18]} />
              <meshStandardMaterial
                color={materialColor}
                emissive={isSelected || isHovered ? "#173f42" : "#000000"}
                emissiveIntensity={isSelected ? 0.2 : isHovered ? 0.09 : 0}
                opacity={dimmed ? 0.24 : connected ? 0.95 : 0.72}
                roughness={0.58}
                transparent
              />
            </mesh>
            {labelVisible ? (
              <Text
                anchorX="center"
                anchorY="middle"
                color={dimmed ? "#8c8981" : "#24231f"}
                fontSize={isSelected ? 0.15 : 0.125}
                maxWidth={1.7}
                position={[0, point.radius3 + (isSelected ? 0.3 : 0.22), 0]}
              >
                {truncate(point.result.title, 28)}
              </Text>
            ) : null}
          </group>
        );
      })}
    </group>
  );
}

function applyOrbitTarget(controls: OrbitControlsHandle | null, target: CameraVector) {
  controls?.target.set(target.x, target.y, target.z);
  controls?.update();
}

function CameraFocus({
  point,
  controlsRef,
  resetSignal,
}: {
  point: SpatialPoint | null;
  controlsRef: RefObject<OrbitControlsHandle | null>;
  resetSignal: number;
}) {
  const { camera } = useThree();
  const hasMountedRef = useRef(false);
  useEffect(() => {
    if (!point || prefersReducedMotion()) return;
    const focus = cameraFocusTarget(point);
    const tween = gsap.to(camera.position, {
      ...focus.position,
      duration: 0.52,
      ease: "power3.out",
      overwrite: true,
      onUpdate: () => {
        applyOrbitTarget(controlsRef.current, focus.target);
        camera.lookAt(focus.target.x, focus.target.y, focus.target.z);
      },
    });
    return () => {
      tween.kill();
    };
  }, [camera, controlsRef, point]);

  useEffect(() => {
    if (!hasMountedRef.current) {
      hasMountedRef.current = true;
      return;
    }
    const focus = cameraFocusTarget(null);
    camera.position.set(focus.position.x, focus.position.y, focus.position.z);
    applyOrbitTarget(controlsRef.current, focus.target);
    camera.lookAt(focus.target.x, focus.target.y, focus.target.z);
  }, [camera, controlsRef, resetSignal]);
  return null;
}

function truncate(value: string, length: number) {
  return value.length > length ? `${value.slice(0, length - 3)}...` : value;
}
