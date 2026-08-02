import { RowListSkeleton } from "@/components/ui/skeleton";

export default function CartLoading() {
  return (
    <>
      <h1 className="mb-6 text-2xl font-bold">Your cart</h1>
      <RowListSkeleton rows={3} label="Loading your cart" />
    </>
  );
}
