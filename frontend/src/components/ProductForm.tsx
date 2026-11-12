"use client";

import { useState, type FormEvent } from "react";
import { invalidateReference } from "@/components/pickers";
import { api } from "@/lib/api";
import { useItemSchema, type ItemAttribute } from "@/lib/config";
import { useAction } from "@/lib/hooks";
import type { Product } from "@/lib/types";
import { Alert, Button, Field, Input, Modal, Select, Textarea } from "./ui";

const EMPTY = { sku: "", brand: "", pattern: "", width: "", aspect_ratio: "", rim_diameter: "", load_index: "", speed_rating: "",
  description: "", barcode: "", is_active: "true" };

const attrKey = (a: ItemAttribute) => `attr:${a.key}`;

function initialForm(product: Product | "new", attributes: ItemAttribute[]): Record<string, string> {
  const base: Record<string, string> = product === "new" ? { ...EMPTY }
    : Object.fromEntries(Object.keys(EMPTY).map((k) => [k, String((product as unknown as Record<string, unknown>)[k] ?? "")]));
  for (const a of attributes) {
    const v = product === "new" ? undefined : product.attributes?.[a.key];
    base[attrKey(a)] = v === undefined || v === null ? "" : a.type === "boolean" ? (v ? "Y" : "N") : String(v);
  }
  return base;
}

/** Create or edit a catalogue product. The fields follow the Industry Pack: tyre size fields, or the pack's attributes. */
export function ProductFormModal({ product, onClose, onSaved }: { product: Product | "new"; onClose: () => void; onSaved: (p: Product) => void }) {
  const schema = useItemSchema();
  const [form, setForm] = useState<Record<string, string>>(() => initialForm(product, schema.attributes));
  const action = useAction();
  const set = (k: string) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const isNew = product === "new";

  async function save(e: FormEvent) {
    e.preventDefault();
    const nullable = (v: string) => (v.trim() === "" ? null : v.trim());
    const shared = { brand: form.brand, pattern: form.pattern, description: nullable(form.description), barcode: nullable(form.barcode),
      is_active: form.is_active === "true" };   // no prices: they are managed in the accounting system
    let body: Record<string, unknown>;
    if (schema.tyreFields) {
      body = { ...shared, load_index: form.load_index, speed_rating: form.speed_rating };
      if (isNew) body = { ...body, width: Number(form.width), aspect_ratio: Number(form.aspect_ratio), rim_diameter: form.rim_diameter };
    } else {
      const attributes = Object.fromEntries(schema.attributes.map((a) => [a.key, form[attrKey(a)] ?? ""]).filter(([, v]) => v !== ""));
      body = { ...shared, attributes };
    }
    const saved = await action.run(() => isNew
      ? api.post<Product>("/products", { ...body, sku: form.sku })
      : api.patch<Product>(`/products/${product.id}`, body));
    if (saved) { invalidateReference(); onSaved(saved); }
  }

  function attributeField(a: ItemAttribute) {
    const label = a.unit ? `${a.label} (${a.unit})` : a.label;
    const k = attrKey(a);
    return (
      <Field key={k} label={label} required={a.required} hint={a.help || undefined}>
        {(id) => a.type === "boolean"
          ? <Select id={id} value={form[k]} onChange={set(k)} options={[{ value: "", label: "—" }, { value: "Y", label: "Yes" }, { value: "N", label: "No" }]} />
          : a.type === "choice"
            ? <Select id={id} value={form[k]} onChange={set(k)} required={a.required}
                options={[{ value: "", label: "—" }, ...a.options.map((o) => ({ value: o, label: o }))]} />
            : <Input id={id} value={form[k]} onChange={set(k)} required={a.required} placeholder={a.example ? `e.g. ${a.example}` : undefined}
                type={a.type === "date" ? "date" : a.type === "integer" || a.type === "number" ? "number" : "text"}
                step={a.type === "number" ? "any" : undefined} />}
      </Field>
    );
  }

  return (
    <Modal open wide title={isNew ? "New product" : `Edit ${product.sku}`} description="Products are matched by exact SKU — similar items are never interchangeable." onClose={onClose}>
      <form onSubmit={save} className="space-y-4">
        <Alert>{action.error}</Alert>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Field label="SKU" required>{(id) => <Input id={id} value={form.sku} onChange={set("sku")} required disabled={!isNew} />}</Field>
          <Field label={schema.brandLabel} required>{(id) => <Input id={id} value={form.brand} onChange={set("brand")} required />}</Field>
          <Field label={schema.tyreFields ? "Pattern / model" : schema.nameLabel} required>{(id) => <Input id={id} value={form.pattern} onChange={set("pattern")} required />}</Field>
          {schema.tyreFields ? <>
            <Field label="Width (mm)" required>{(id) => <Input id={id} type="number" min={1} value={form.width} onChange={set("width")} required disabled={!isNew} />}</Field>
            <Field label="Aspect ratio" required>{(id) => <Input id={id} type="number" min={1} value={form.aspect_ratio} onChange={set("aspect_ratio")} required disabled={!isNew} />}</Field>
            <Field label="Rim diameter (in)" required>{(id) => <Input id={id} type="number" step="0.5" min={1} value={form.rim_diameter} onChange={set("rim_diameter")} required disabled={!isNew} />}</Field>
            <Field label="Load index" required>{(id) => <Input id={id} value={form.load_index} onChange={set("load_index")} required />}</Field>
            <Field label="Speed rating" required>{(id) => <Input id={id} value={form.speed_rating} onChange={set("speed_rating")} required maxLength={3} />}</Field>
          </> : schema.attributes.map(attributeField)}
          <Field label="Barcode">{(id) => <Input id={id} value={form.barcode} onChange={set("barcode")} />}</Field>
          <Field label="Status">{(id) => <Select id={id} value={form.is_active} onChange={set("is_active")} options={[{ value: "true", label: "Active" }, { value: "false", label: "Inactive" }]} />}</Field>
        </div>
        <Field label="Description">{(id) => <Textarea id={id} value={form.description} onChange={set("description")} />}</Field>
        <div className="flex justify-end gap-2 border-t border-line pt-4">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" disabled={action.busy}>{action.busy ? "Saving…" : "Save product"}</Button>
        </div>
      </form>
    </Modal>
  );
}
