import { useCallback, useRef, useState } from "react";

import type { Copy } from "../i18n";

export interface ManualRegion {
  x: number;
  y: number;
  width: number;
  height: number;
}

interface ManualMaskEditorProps {
  image: string;
  filename: string;
  regions: ManualRegion[];
  onChange: (regions: ManualRegion[]) => void;
  copy: Pick<Copy, "manualHint" | "manualRegionCount">;
}

interface DragOrigin {
  pointerId: number;
  x: number;
  y: number;
}

const minimumRegionSize = 0.005;

function clamp(value: number) {
  return Math.max(0, Math.min(1, value));
}

function regionStyle(region: ManualRegion) {
  return {
    left: `${region.x * 100}%`,
    top: `${region.y * 100}%`,
    width: `${region.width * 100}%`,
    height: `${region.height * 100}%`,
  };
}

export function ManualMaskEditor({
  image,
  filename,
  regions,
  onChange,
  copy,
}: ManualMaskEditorProps) {
  const surfaceRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<DragOrigin | null>(null);
  const [draft, setDraft] = useState<ManualRegion | null>(null);

  const pointFromEvent = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    const bounds = surfaceRef.current?.getBoundingClientRect();
    if (!bounds) return null;
    return {
      x: clamp((event.clientX - bounds.left) / bounds.width),
      y: clamp((event.clientY - bounds.top) / bounds.height),
    };
  }, []);

  const updateDraft = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      const origin = dragRef.current;
      const point = pointFromEvent(event);
      if (!origin || !point || origin.pointerId !== event.pointerId) return;
      setDraft({
        x: Math.min(origin.x, point.x),
        y: Math.min(origin.y, point.y),
        width: Math.abs(point.x - origin.x),
        height: Math.abs(point.y - origin.y),
      });
    },
    [pointFromEvent],
  );

  const handlePointerDown = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (regions.length >= 8) return;
      const point = pointFromEvent(event);
      if (!point) return;
      event.preventDefault();
      event.currentTarget.setPointerCapture(event.pointerId);
      dragRef.current = { pointerId: event.pointerId, ...point };
      setDraft({ x: point.x, y: point.y, width: 0, height: 0 });
    },
    [pointFromEvent, regions.length],
  );

  const finishDraft = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      updateDraft(event);
      const origin = dragRef.current;
      const point = pointFromEvent(event);
      dragRef.current = null;
      setDraft(null);
      if (!origin || !point || origin.pointerId !== event.pointerId) return;
      const region = {
        x: Math.min(origin.x, point.x),
        y: Math.min(origin.y, point.y),
        width: Math.abs(point.x - origin.x),
        height: Math.abs(point.y - origin.y),
      };
      if (region.width >= minimumRegionSize && region.height >= minimumRegionSize) {
        onChange([...regions, region]);
      }
    },
    [onChange, pointFromEvent, regions, updateDraft],
  );

  return (
    <div className="rounded-[1.75rem] bg-[var(--paper-deep)] p-3">
      <div className="flex min-h-[360px] items-center justify-center sm:min-h-[460px]">
        <div className="relative inline-block max-w-full touch-none select-none">
          <img
            src={image}
            alt={filename}
            className="block max-h-[62vh] max-w-full rounded-2xl object-contain"
            draggable={false}
          />
          <div
            ref={surfaceRef}
            className="absolute inset-0 cursor-crosshair overflow-hidden rounded-2xl"
            onPointerDown={handlePointerDown}
            onPointerMove={updateDraft}
            onPointerUp={finishDraft}
            onPointerCancel={() => {
              dragRef.current = null;
              setDraft(null);
            }}
            role="application"
            aria-label={copy.manualHint}
          >
            {regions.map((region, index) => (
              <span
                key={`${region.x}-${region.y}-${index}`}
                className="pointer-events-none absolute border-2 border-[var(--accent)] bg-[rgba(20,184,166,0.2)] shadow-[0_0_0_9999px_rgba(20,24,22,0.06)]"
                style={regionStyle(region)}
              >
                <span className="absolute -left-0.5 -top-6 rounded-md bg-[var(--accent-strong)] px-1.5 py-0.5 font-mono text-[9px] text-white">
                  {index + 1}
                </span>
              </span>
            ))}
            {draft && (
              <span
                className="pointer-events-none absolute border-2 border-dashed border-white bg-[rgba(20,184,166,0.22)]"
                style={regionStyle(draft)}
              />
            )}
          </div>
        </div>
      </div>
      <div className="flex items-center justify-between gap-4 px-2 pb-1 pt-3 text-xs text-[var(--ink-muted)]">
        <span>{copy.manualHint}</span>
        <span className="shrink-0 font-mono text-[10px] uppercase tracking-[0.12em]">
          {copy.manualRegionCount(regions.length)}
        </span>
      </div>
    </div>
  );
}
