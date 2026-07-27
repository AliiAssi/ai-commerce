"use client";

import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/panel";

export default function ErrorBoundary({ reset }: { error: Error; reset: () => void }) {
  return (
    <main className="mx-auto w-full max-w-shell flex-1 px-4 py-24">
      <EmptyState
        title="Something went wrong"
        body="The store had trouble loading that. It may just be waking up, try again in a moment."
      />
      <div className="mt-6 flex justify-center">
        <Button onClick={reset}>Try again</Button>
      </div>
    </main>
  );
}
