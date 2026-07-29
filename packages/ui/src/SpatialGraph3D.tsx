import { Canvas } from "@react-three/fiber";
import type { ThreeEvent } from "@react-three/fiber";
import { Line, OrbitControls, Text } from "@react-three/drei";
import type { SearchResultContract } from "@memory/types";

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
};

export default function SpatialGraph3D({
  points,
  selectedId,
  hoveredId,
  setSelectedId,
  setHoveredId,
}: SpatialGraph3DProps) {
  return (
    <div className="graph-canvas" aria-label="Spatial relationship map">
      <Canvas camera={{ position: [0, 0, 9], fov: 48 }} dpr={[1, 1.6]}>
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
  return (
    <group>
      {center
        ? points.slice(1).map((point) => {
            const unrelated = selectedId && point.result.document_id !== selectedId;
            return (
              <Line
                color={unrelated ? "#d9d5cc" : "#aebfbb"}
                key={`${center.result.document_id}-${point.result.document_id}`}
                lineWidth={1.2}
                opacity={unrelated ? 0.34 : 0.7}
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
        const dimmed = Boolean(selectedId && !isSelected);
        const labelVisible = isSelected || isHovered || point.priority < 0.22;
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
            <mesh scale={isSelected ? 1.22 : 1}>
              <sphereGeometry args={[point.radius3, 28, 18]} />
              <meshStandardMaterial
                color={point.result.source_metadata.kind === "google_drive" ? "#286f7a" : "#4f7660"}
                emissive={isSelected ? "#173f42" : "#000000"}
                emissiveIntensity={isSelected ? 0.18 : 0}
                opacity={dimmed ? 0.28 : 0.94}
                roughness={0.58}
                transparent
              />
            </mesh>
            {labelVisible ? (
              <Text
                anchorX="center"
                anchorY="middle"
                color={dimmed ? "#8c8981" : "#24231f"}
                fontSize={0.13}
                maxWidth={1.8}
                position={[0, point.radius3 + 0.22, 0]}
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

function truncate(value: string, length: number) {
  return value.length > length ? `${value.slice(0, length - 3)}...` : value;
}
