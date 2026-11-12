"""Write a fictional sample catalogue for an Industry Pack, in that pack's import template layout (for demos).

    python -m scripts.make_sample_catalogue medical data/products/sample-medical-catalogue.xlsx

Brands, SKUs and references are invented. Nothing here is a real product or price.
"""

import argparse
import io

from openpyxl import load_workbook

from app.core.industry import PACKS
from app.modules.catalogue.generic_import import build_template, columns

SAMPLES: dict[str, list[dict[str, str]]] = {
    "medical": [
        {"sku": "ORX-100430", "pattern": "Cortical screw", "brand": "Orthex", "attr:ref": "CS-4530",
         "attr:size": "4.5 x 30 mm", "attr:device_class": "IIb", "attr:sterile": "Y", "attr:tracking": "Lot and expiry"},
        {"sku": "ORX-100432", "pattern": "Cortical screw", "brand": "Orthex", "attr:ref": "CS-4532",
         "attr:size": "4.5 x 32 mm", "attr:device_class": "IIb", "attr:sterile": "Y", "attr:tracking": "Lot and expiry"},
        {"sku": "ORX-200608", "pattern": "Locking plate", "brand": "Orthex", "attr:ref": "LP-0608",
         "attr:size": "6 hole", "attr:device_class": "IIb", "attr:sterile": "Y", "attr:tracking": "Serial"},
        {"sku": "VAL-310012", "pattern": "Knee tibial insert", "brand": "Valora", "attr:ref": "TI-12-3",
         "attr:size": "Size 3, 12 mm", "attr:device_class": "III", "attr:sterile": "Y", "attr:tracking": "Serial"},
        {"sku": "VAL-320040", "pattern": "Bone cement", "brand": "Valora", "attr:ref": "BC-40",
         "attr:size": "40 g", "attr:device_class": "III", "attr:sterile": "Y", "attr:tracking": "Lot and expiry"},
        {"sku": "SUT-400090", "pattern": "Drill bit", "brand": "Sutura", "attr:ref": "DB-32",
         "attr:size": "3.2 mm", "attr:device_class": "IIa", "attr:sterile": "N", "attr:tracking": "Lot"},
    ],
    "auto_parts": [
        {"sku": "BAT-55B24L", "pattern": "Car battery 45Ah", "brand": "Voltway", "attr:category": "Battery",
         "attr:oem_numbers": "55B24L, NS60L", "attr:fitment": "Toyota Corolla 2014-2019", "attr:warranty_months": "24",
         "attr:core_charge": "25.00"},
        {"sku": "BRK-DB1170", "pattern": "Front brake pads", "brand": "Stopline", "attr:category": "Brakes",
         "attr:oem_numbers": "04465-02220", "attr:fitment": "Toyota Corolla 2014-2019", "attr:warranty_months": "12"},
        {"sku": "FLT-Z418", "pattern": "Oil filter", "brand": "Purex", "attr:category": "Filters",
         "attr:oem_numbers": "90915-YZZE1", "attr:fitment": "Toyota, Lexus 2.0-3.5L"},
    ],
    "building": [
        {"sku": "TIL-CAR600M", "pattern": "Carrara porcelain", "brand": "Stonevale", "attr:size": "600 x 600 mm",
         "attr:finish": "Matt", "attr:coverage_per_box": "1.44", "attr:batch_matters": "Y"},
        {"sku": "TIL-CAR600P", "pattern": "Carrara porcelain", "brand": "Stonevale", "attr:size": "600 x 600 mm",
         "attr:finish": "Polished", "attr:coverage_per_box": "1.44", "attr:batch_matters": "Y"},
        {"sku": "TIL-SUB7515", "pattern": "Subway ceramic", "brand": "Claymark", "attr:size": "75 x 150 mm",
         "attr:finish": "Gloss", "attr:coverage_per_box": "1.0", "attr:batch_matters": "Y"},
    ],
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pack", choices=sorted(SAMPLES))
    parser.add_argument("out")
    args = parser.parse_args()
    pack = PACKS[args.pack]
    cols = columns(pack)
    wb = load_workbook(io.BytesIO(build_template(pack)))
    ws = wb["SKUs"]
    for r, item in enumerate(SAMPLES[args.pack], start=2):
        for c, col in enumerate(cols, start=1):
            ws.cell(row=r, column=c, value=item.get(col["key"]))
    wb.save(args.out)
    print(f"{len(SAMPLES[args.pack])} sample {pack.name.lower()} written to {args.out}")


if __name__ == "__main__":
    main()
