import { RowListSkeleton, Skeleton } from "@/components/ui/skeleton";

export default function AdminLoading() {
  return (
    <>
      <Skeleton className="mb-6 h-7 w-48" />
      <RowListSkeleton rows={6} label="Loading" />
    </>
  );
}
