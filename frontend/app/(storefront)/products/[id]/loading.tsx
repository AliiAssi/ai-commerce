import { Skeleton, TextSkeleton } from "@/components/ui/skeleton";

export default function ProductLoading() {
  return (
    <div role="status" aria-label="Loading product">
      <Skeleton className="mb-8 h-3 w-56" />

      <div className="grid gap-14 lg:grid-cols-[1.05fr_0.95fr] lg:items-start">
        <Skeleton className="aspect-square w-full rounded-card" />

        <div className="flex flex-col gap-6">
          <div className="flex flex-col gap-3">
            <Skeleton className="h-3 w-32" />
            <Skeleton className="h-10 w-4/5" />
            <Skeleton className="h-4 w-28" />
          </div>
          <Skeleton className="h-8 w-28" />
          <TextSkeleton lines={4} className="max-w-[60ch]" />
          <Skeleton className="h-12 w-52" />
        </div>
      </div>
    </div>
  );
}
