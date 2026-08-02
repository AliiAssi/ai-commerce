import { RowListSkeleton, Skeleton } from "@/components/ui/skeleton";

export default function OrderDetailLoading() {
  return (
    <div className="mx-auto max-w-2xl" role="status" aria-label="Loading order">
      <Skeleton className="h-3 w-24" />
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <Skeleton className="h-7 w-40" />
        <Skeleton className="h-5 w-16" />
      </div>
      <div className="mt-6">
        <RowListSkeleton rows={3} label="Loading order items" />
      </div>
    </div>
  );
}
