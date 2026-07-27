import { EmptyState } from "@/components/ui/panel";

export default function NotFound() {
  return (
    <main className="mx-auto w-full max-w-shell flex-1 px-4 py-24">
      <EmptyState
        title="Not found"
        body="That page or product isn't on our shelves."
        ctaLabel="Browse the catalog"
        ctaHref="/catalog"
      />
    </main>
  );
}
