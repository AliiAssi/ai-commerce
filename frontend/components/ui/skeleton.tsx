import { cn } from "@/lib/cn";

/** The catalog grid, shared so a skeleton cannot drift from the real thing. */
export const PLATE_GRID = "grid grid-cols-1 gap-x-7 gap-y-10 sm:grid-cols-2 xl:grid-cols-3";

export function Skeleton({ className }: { className?: string }) {
  return <span className={cn("skeleton block rounded-el bg-surface-sunk", className)} />;
}

export function TextSkeleton({ lines = 1, className }: { lines?: number; className?: string }) {
  return (
    <div className={cn("flex flex-col gap-2.5", className)}>
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton key={i} className={cn("h-3", i === lines - 1 && lines > 1 && "w-3/5")} />
      ))}
    </div>
  );
}

/** Mirrors <Plate>'s box model, so nothing shifts when the real grid replaces this. */
export function PlateSkeleton() {
  return (
    <div className="flex flex-col gap-3.5">
      <Skeleton className="aspect-[4/5] rounded-card" />
      <Skeleton className="h-5 w-3/4" />
      <Skeleton className="h-3 w-24" />
      <div className="mt-auto flex items-baseline justify-between gap-3 pt-1">
        <Skeleton className="h-3 w-20" />
        <Skeleton className="h-5 w-14" />
      </div>
    </div>
  );
}

export function PlateGridSkeleton({ count = 12 }: { count?: number }) {
  return (
    <div role="status" aria-label="Loading products" data-testid="plate-grid-skeleton">
      <div className={PLATE_GRID} aria-hidden="true">
        {Array.from({ length: count }, (_, i) => (
          <PlateSkeleton key={i} />
        ))}
      </div>
    </div>
  );
}

export function FilterRailSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div
      className="flex flex-col gap-2.5"
      aria-hidden="true"
      data-testid="filter-rail-skeleton"
    >
      <Skeleton className="h-3 w-20" />
      <div className="flex flex-col gap-3.5 pt-1.5">
        {Array.from({ length: rows }, (_, i) => (
          <div key={i} className="flex items-baseline justify-between gap-3">
            <Skeleton className="h-3.5 w-28" />
            <Skeleton className="h-3 w-5" />
          </div>
        ))}
      </div>
    </div>
  );
}

export function RowSkeleton() {
  return (
    <div className="flex flex-wrap items-center gap-3 p-4">
      <Skeleton className="h-4 w-24" />
      <Skeleton className="h-4 w-32" />
      <Skeleton className="h-5 w-16" />
      <Skeleton className="ms-auto h-4 w-20" />
    </div>
  );
}

/** The panel shape used by the order list and the admin tables. */
export function RowListSkeleton({
  rows = 4,
  label = "Loading",
}: {
  rows?: number;
  label?: string;
}) {
  return (
    <div
      role="status"
      aria-label={label}
      data-testid="row-list-skeleton"
      className="divide-y divide-border rounded-card border border-border bg-surface shadow-card"
    >
      {Array.from({ length: rows }, (_, i) => (
        <RowSkeleton key={i} />
      ))}
    </div>
  );
}
