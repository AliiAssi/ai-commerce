import { RowListSkeleton, Skeleton } from "@/components/ui/skeleton";

export default function CheckoutLoading() {
  return (
    <>
      <h1 className="mb-6 text-2xl font-bold">Checkout</h1>
      <div className="grid items-start gap-6 lg:grid-cols-[1fr_20rem]">
        <RowListSkeleton rows={3} label="Loading your order" />
        <aside className="space-y-4 rounded-card border border-border bg-surface p-5 shadow-card">
          <Skeleton className="h-5 w-24" />
          <div className="flex items-center justify-between border-t border-border pt-3">
            <Skeleton className="h-4 w-16" />
            <Skeleton className="h-6 w-20" />
          </div>
          <Skeleton className="h-10 w-full" />
        </aside>
      </div>
    </>
  );
}
