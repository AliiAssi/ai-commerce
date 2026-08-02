import { RowListSkeleton } from "@/components/ui/skeleton";

export default function OrdersLoading() {
  return (
    <>
      <h1 className="mb-6 text-2xl font-bold">My orders</h1>
      <RowListSkeleton rows={4} label="Loading your orders" />
    </>
  );
}
