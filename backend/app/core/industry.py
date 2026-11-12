"""Industry Packs: the words (and, from step 1.4, the item attributes and rules) that make the same platform read
naturally in each industry. See docs/whitelabel/02_INDUSTRY_ANALYSIS.md.

The words are used everywhere a person reads text: screens (served by GET /api/config/public), notifications,
emails, delivery notes, Excel exports and error messages. Code, table names, API paths and enum values keep their
internal names (product, reseller, location) whatever the pack.

The `tyres` pack is the default and reproduces the reference customer's wording exactly ("tyre", "dealer", "shop").

Use in code:

    from app.core.industry import vocab
    f"{vocab.Items} sold by {vocab.aPartner}"      # "Tyres sold by a dealer"

A customer can rename single words without a new pack: TERMS_OVERRIDES='{"partner": "stockist",
"partners": "stockists"}'.
"""

from dataclasses import dataclass, field

# The words a pack defines: singular and plural of the stocked item, the partner holding consignment stock, and the
# partner's site (shop, theatre, branch…).
TERM_KEYS = ("item", "items", "partner", "partners", "site", "sites")


ATTRIBUTE_TYPES = ("text", "integer", "number", "boolean", "date", "choice")


@dataclass(frozen=True)
class AttributeDef:
    """One item attribute of an Industry Pack (e.g. medical "REF", tiles "Finish").

    Values are stored in `products.attributes` (JSONB) under `key`. The tyres pack's attributes are the original
    product columns instead (`column=True`): they keep their own validation and are shown here for the screens.
    """

    key: str
    label: str
    type: str = "text"                      # one of ATTRIBUTE_TYPES
    required: bool = False
    in_spec: bool = False                   # part of the short specification shown next to the name ("Size")
    options: tuple[str, ...] = ()           # for type "choice"
    unit: str = ""                          # shown after the label, e.g. "mm"
    help: str = ""
    example: str = ""
    column: bool = False                    # stored in its own products column (tyres pack only)


@dataclass(frozen=True)
class IndustryPack:
    code: str
    name: str
    description: str
    terms: dict[str, str]
    # Example search hint for the item picker ("e.g. 700001 or 205 55 16").
    search_example: str = "e.g. a SKU or name"
    tags: tuple[str, ...] = field(default_factory=tuple)
    attributes: tuple[AttributeDef, ...] = ()
    # Labels of the two fixed product fields: `brand` and `pattern` (pattern = model / product name).
    brand_label: str = "Brand"
    name_label: str = "Name"
    # Header for the short specification column ("Size" for tyres and tiles, "Spec" elsewhere).
    spec_label: str = "Spec"
    # The tyres pack keeps the original tyre columns, importer and size search.
    tyre_fields: bool = False

    def attribute(self, key: str) -> AttributeDef | None:
        return next((a for a in self.attributes if a.key == key), None)


def _terms(item: str, partner: str, site: str, items: str = "", partners: str = "", sites: str = "") -> dict[str, str]:
    return {"item": item, "items": items or item + "s", "partner": partner, "partners": partners or partner + "s",
            "site": site, "sites": sites or site + "s"}


A = AttributeDef
TYRE_ATTRIBUTES = (
    A("width", "Width", "integer", True, True, unit="mm", example="205", column=True),
    A("aspect_ratio", "Aspect ratio", "integer", True, True, example="55", column=True),
    A("rim_diameter", "Rim diameter", "number", True, True, unit="in", example="16", column=True),
    A("construction", "Construction", "text", False, True, example="R", column=True),
    A("load_index", "Load index", "text", True, example="91", column=True),
    A("speed_rating", "Speed rating", "text", True, example="H", column=True),
)

PACKS: dict[str, IndustryPack] = {p.code: p for p in (
    IndustryPack("tyres", "Tyres and wheels", "Tyre distributors supplying dealers on consignment.",
                 _terms("tyre", "dealer", "shop"), "e.g. 700001 or 205 55 16", attributes=TYRE_ATTRIBUTES,
                 name_label="Pattern", spec_label="Size", tyre_fields=True),
    IndustryPack("generic", "General consignment", "Neutral wording for any industry.",
                 _terms("item", "partner", "site"),
                 attributes=(A("variant", "Variant", in_spec=True, example="Blue / Large"),)),
    IndustryPack("auto_parts", "Auto parts and batteries", "Parts and battery suppliers stocking workshops.",
                 _terms("part", "workshop", "branch", sites="branches"), "e.g. a part number or name",
                 attributes=(
                     A("category", "Category", "choice", True, True,
                       options=("Battery", "Brakes", "Filters", "Suspension", "Electrical", "Engine", "Other"),
                       example="Battery"),
                     A("oem_numbers", "OEM numbers", help="Cross-references, separated by commas.",
                       example="31500-SR1-A01, 12V45AH"),
                     A("fitment", "Fitment", help="Makes and models it fits.", example="Toyota Corolla 2014-2019"),
                     A("warranty_months", "Warranty", "integer", unit="months", example="24"),
                     A("core_charge", "Core charge", "number", help="Deposit refunded when the old unit is returned.",
                       example="25.00"),
                 ), brand_label="Brand", name_label="Part name"),
    IndustryPack("medical", "Medical devices and implants", "Device suppliers holding consigned stock at hospitals.",
                 _terms("device", "hospital", "location"), "e.g. a REF, GTIN or name",
                 attributes=(
                     A("ref", "REF", required=True, in_spec=True, help="Manufacturer catalogue number.",
                       example="71933215"),
                     A("size", "Size", in_spec=True, example="4.5 x 30 mm"),
                     A("device_class", "Class", "choice", options=("I", "IIa", "IIb", "III"), example="IIb"),
                     A("sterile", "Sterile", "boolean", example="Y"),
                     A("tracking", "Tracking", "choice", options=("None", "Lot", "Serial", "Lot and expiry"),
                       help="How each unit is identified (lot / serial tracking arrives in a later release).",
                       example="Lot and expiry"),
                 ), brand_label="Manufacturer", name_label="Device"),
    IndustryPack("industrial", "Industrial spares and tools", "MRO and tool suppliers stocking customer stores.",
                 _terms("part", "customer", "store"), "e.g. a part number or name",
                 attributes=(
                     A("manufacturer_part", "Manufacturer part no.", in_spec=True, example="6205-2RS"),
                     A("specification", "Specification", in_spec=True, example="25 x 52 x 15 mm, sealed"),
                     A("serialised", "Serialised", "boolean", example="N"),
                 ), brand_label="Manufacturer", name_label="Part name"),
    IndustryPack("agri", "Agricultural inputs and parts", "Agri suppliers stocking rural merchants.",
                 _terms("product", "merchant", "store"),
                 attributes=(
                     A("pack_size", "Pack size", required=True, in_spec=True, example="20 L"),
                     A("registration_no", "Registration no.", help="Agrichemical / fertiliser registration.",
                       example="P009876"),
                     A("hazard_class", "Hazard class", example="9"),
                 ), name_label="Product"),
    IndustryPack("fmcg", "Retail and FMCG vendor stock", "Brands and wholesalers with stock in retail stores.",
                 _terms("product", "retailer", "store"),
                 attributes=(
                     A("variant", "Variant", in_spec=True, example="500 g"),
                     A("case_pack", "Case pack", "integer", unit="units", example="12"),
                 ), name_label="Product"),
    IndustryPack("building", "Building materials and tiles", "Suppliers stocking stockists and showrooms.",
                 _terms("product", "stockist", "showroom"),
                 attributes=(
                     A("size", "Size", required=True, in_spec=True, example="600 x 600 mm"),
                     A("finish", "Finish", in_spec=True, example="Matt"),
                     A("coverage_per_box", "Coverage per box", "number", unit="m²", example="1.44"),
                     A("batch_matters", "Shade / batch matters", "boolean",
                       help="Supply one job from a single batch (batch tracking arrives in a later release).",
                       example="Y"),
                 ), name_label="Range", spec_label="Size"),
    IndustryPack("furniture", "Furniture showrooms", "Furniture makers with floor stock in showrooms.",
                 _terms("piece", "retailer", "showroom"),
                 attributes=(
                     A("variant", "Fabric / finish", in_spec=True, example="Oak, charcoal linen"),
                     A("dimensions", "Dimensions", example="2100 x 950 x 820 mm"),
                 ), brand_label="Collection", name_label="Model"),
)}

DEFAULT_PACK = "tyres"


def _article(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"


class Vocabulary:
    """The current deployment's words, read live from settings (so tests and tenants can switch packs).

    Attributes: item, items, partner, partners, site, sites; capitalised forms Item, Items, Partner…; and with an
    article: aItem / AItem ("a tyre" / "An item"), aPartner / APartner, aSite / ASite.
    """

    def as_dict(self) -> dict[str, str]:
        from app.core.config import get_settings

        settings = get_settings()
        words = dict(PACKS[settings.industry_pack].terms)
        words.update({k: v for k, v in settings.terms_overrides.items() if k in TERM_KEYS and v.strip()})
        return words

    def __getattr__(self, name: str) -> str:
        words = self.as_dict()
        if name in words:
            return words[name]
        if name[:1].isupper() and name.lower() in words:
            return words[name.lower()].capitalize()
        if name.startswith(("a", "A")) and name[1:].lower() in words:
            word = words[name[1:].lower()]
            art = _article(word)
            return f"{art.capitalize() if name[0] == 'A' else art} {word}"
        raise AttributeError(name)


vocab = Vocabulary()


def current_pack() -> IndustryPack:
    from app.core.config import get_settings

    return PACKS[get_settings().industry_pack]
