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


@dataclass(frozen=True)
class IndustryPack:
    code: str
    name: str
    description: str
    terms: dict[str, str]
    # Example search hint for the item picker ("e.g. 700001 or 205 55 16").
    search_example: str = "e.g. a SKU or name"
    tags: tuple[str, ...] = field(default_factory=tuple)


def _terms(item: str, partner: str, site: str, items: str = "", partners: str = "", sites: str = "") -> dict[str, str]:
    return {"item": item, "items": items or item + "s", "partner": partner, "partners": partners or partner + "s",
            "site": site, "sites": sites or site + "s"}


PACKS: dict[str, IndustryPack] = {p.code: p for p in (
    IndustryPack("tyres", "Tyres and wheels", "Tyre distributors supplying dealers on consignment.",
                 _terms("tyre", "dealer", "shop"), "e.g. 700001 or 205 55 16"),
    IndustryPack("generic", "General consignment", "Neutral wording for any industry.",
                 _terms("item", "partner", "site")),
    IndustryPack("auto_parts", "Auto parts and batteries", "Parts and battery suppliers stocking workshops.",
                 _terms("part", "workshop", "branch", sites="branches"), "e.g. a part number or name"),
    IndustryPack("medical", "Medical devices and implants", "Device suppliers holding consigned stock at hospitals.",
                 _terms("device", "hospital", "location"), "e.g. a REF, GTIN or name"),
    IndustryPack("industrial", "Industrial spares and tools", "MRO and tool suppliers stocking customer stores.",
                 _terms("part", "customer", "store"), "e.g. a part number or name"),
    IndustryPack("agri", "Agricultural inputs and parts", "Agri suppliers stocking rural merchants.",
                 _terms("product", "merchant", "store")),
    IndustryPack("fmcg", "Retail and FMCG vendor stock", "Brands and wholesalers with stock in retail stores.",
                 _terms("product", "retailer", "store")),
    IndustryPack("building", "Building materials and tiles", "Suppliers stocking stockists and showrooms.",
                 _terms("product", "stockist", "showroom")),
    IndustryPack("furniture", "Furniture showrooms", "Furniture makers with floor stock in showrooms.",
                 _terms("piece", "retailer", "showroom")),
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
