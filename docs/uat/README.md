# UAT journey maps

Reference and checklist for user acceptance testing, written for non-technical testers.

| File | For |
|---|---|
| `TyreGrow-UAT-Journey-Maps.pdf` | Everyone: all 12 journeys, every step |
| `TyreGrow-UAT-Journey-Maps-<Role>.pdf` | One role (Administrator, Relationship Manager, Warehouse Manager, Finance Manager, Sales Representative, Dealer): same diagrams, checklist rows only for that role's steps |

Each PDF is fillable on screen (Works / Issue per step, comments, journey sign-off, tester details) and prints cleanly
for pen ticking. Step numbers match the numbered boxes in each journey's diagram.

To update after the app changes: edit `journeys.py` (content), then

```bash
pip install reportlab
python docs/uat/build_journey_maps.py
```
