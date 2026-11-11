/** Who and where a stock check is (finding 27): the dealer and the shop by name, with the address and the rep. */
import { Store } from "lucide-react";
import type { ReactNode } from "react";
import { Card, DefinitionList } from "./ui";
import { vocab } from "@/lib/terms";

export function StocktakeHeader({ dealer, accountRef, shop, code, address, city, rep }: {
  dealer?: ReactNode; accountRef?: string | null; shop?: string | null; code?: string | null;
  address?: string | null; city?: string | null; rep?: string | null;
}) {
  return (
    <Card className="mb-4" icon={Store} title={<>{dealer ?? "—"} {accountRef && <span className="sku text-label text-ink-secondary">{accountRef}</span>}</>}
      subtitle={<>{shop ?? code}{code && shop ? <span className="sku text-label"> · {code}</span> : null}</>}>
      <DefinitionList columns={2} items={[[vocab.Site, shop ?? code], ["Address", address], ["City", city], ["Sales rep", rep ?? "Not assigned"]]} />
    </Card>
  );
}
