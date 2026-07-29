import { Canvas } from "@react-three/fiber";
import type { ThreeEvent } from "@react-three/fiber";
import { useThree } from "@react-three/fiber";
import { Line, OrbitControls, Text } from "@react-three/drei";
import type { SearchResultContract } from "@memory/types";
import { useEffect, useMemo, type ReactNode } from "react";
import { gsap } from "gsap";
import { prefersReducedMotion } from "./animations";

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
  fallback: ReactNode;
};

export default function SpatialGraph3D({
  points,
  selectedId,
  hoveredId,
  setSelectedId,
  setHoveredId,
  fallback,
}: SpatialGraph3DProps) {
  return (
    <div className="graph-canvas" aria-label="Spatial relationship map">
      <Canvas camera={{ position: [0, 0, 9], fov: 48 }} dpr={[1, 1.6]} fallback={fallback}>
        <color attach="background" args={["#fbfaf7"]} />
        <ambientLight intensity={1.8} />
        <pointLight position={[3, 4, 6]} intensity={1.2} />
        <GraphScene
          points={points}
          selectedId={selectedId}
          hoveredId={hoveredId}
          setSelectedId={setSelectedId}
          setHoveredId={setHoveredId}
        />
        <OrbitControls
          enableDamping
          dampingFactor={0.12}
          maxDistance={14}
          minDistance={4}
          maxPolarAngle={Math.PI / 2}
        />
      </Canvas>
    </div>
  );
}

function GraphScene({
  points,
  selectedId,
  hoveredId,
  setSelectedId,
  setHoveredId,
}: Omit<SpatialGraph3DProps, "fallback">) {
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
      <CameraFocus point={selectedPoint ?? null} />
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

function CameraFocus({ point }: { point: SpatialPoint | null }) {
  const { camera } = useThree();
  useEffect(() => {
    if (!point || prefersReducedMotion()) return;
    gsap.to(camera.position, {
      x: point.x3 * 0.28,
      y: point.y3 * 0.28,
      z: 8.2,
      duration: 0.52,
      ease: "power3.out",
      overwrite: true,
      onUpdate: () => {
        camera.lookAt(point.x3 * 0.18, point.y3 * 0.18, point.z3);
      },
    });
  }, [camera, point]);
  return null;
}

function truncate(value: string, length: number) {
  return value.length > length ? `${value.slice(0, length - 3)}...` : value;
}
