"use client";

import { useActionState } from "react";

import type { ProductFormState } from "@/lib/actions/admin";
import { Button, LinkButton } from "@/components/ui/button";
import { Field, SelectField, TextareaField } from "@/components/ui/field";
import type { Category, Product } from "@/lib/api/types";

interface Props {
  product?: Product;
  categories: Category[];
  action: (prev: ProductFormState, formData: FormData) => Promise<ProductFormState>;
}

export function ProductForm({ product, categories, action }: Props) {
  const [state, formAction, pending] = useActionState(action, {});
  const isEdit = Boolean(product);

  return (
    <form
      action={formAction}
      className="space-y-4 rounded-card border border-border bg-surface p-6 shadow-card"
    >
      {state.error && (
        <p
          role="alert"
          className="rounded-el border border-danger bg-danger-subtle px-3 py-2 text-sm text-danger"
        >
          {state.error}
        </p>
      )}

      <Field
        name="name"
        label="Name"
        required
        maxLength={200}
        defaultValue={product?.name ?? ""}
      />
      <SelectField
        name="category_id"
        label="Category"
        options={categories.map((c) => ({ value: c.id, text: c.name }))}
        defaultValue={product?.category_id}
      />

      <div className="grid gap-4 sm:grid-cols-2">
        <Field
          name="price"
          label="Price ($)"
          type="number"
          required
          min="0.01"
          step="0.01"
          defaultValue={product?.price ?? ""}
        />
        {/* Stock is only set at creation; afterwards it moves through the audited +/- controls
            on the product list, so every change leaves a trail. */}
        {!isEdit && (
          <Field
            name="stock"
            label="Initial stock"
            type="number"
            required
            min="0"
            step="1"
            defaultValue="0"
          />
        )}
      </div>

      <Field
        name="origin"
        label="Origin"
        placeholder="e.g. Koura, North Lebanon"
        maxLength={80}
        defaultValue={product?.origin ?? ""}
      />
      <Field
        name="image_url"
        label="Image URL"
        placeholder="https://…"
        maxLength={500}
        defaultValue={product?.image_url ?? ""}
      />
      <TextareaField
        name="description"
        label="Description"
        rows={5}
        required
        defaultValue={product?.description ?? ""}
      />

      <div className="flex items-center gap-3">
        <Button type="submit" disabled={pending}>
          {pending ? "Saving…" : "Save product"}
        </Button>
        <LinkButton href="/admin/products" variant="secondary">
          Cancel
        </LinkButton>
      </div>

      {isEdit && (
        <p className="text-xs text-ink-faint">
          Stock is adjusted from the product list, so every change is audited.
        </p>
      )}
    </form>
  );
}
