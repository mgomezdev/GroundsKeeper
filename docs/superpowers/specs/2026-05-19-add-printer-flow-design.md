# Add Printer Flow — Type-Driven Form Design

**Goal:** Replace the hardcoded Bambu-only add-printer form with a two-step flow where each concrete printer client advertises the connection fields it needs, so adding a new printer type requires no frontend changes.

**Architecture:** The concrete client class owns a `connection_fields()` classmethod that returns an ordered list of field descriptors. A new API endpoint collects these from a central registry and serves them to the frontend. The add-printer modal fetches this endpoint, renders a type-picker in step 1, then renders common + connection fields dynamically in step 2.

**Tech Stack:** Python dataclasses (backend field descriptors), FastAPI (new endpoint), React + TanStack Query (frontend fetch + form render)

---

## Backend

### `ConnectionField` dataclass — `abstract_printer_client.py`

```python
@dataclass
class ConnectionField:
    name: str          # API payload key (e.g. "serial_number")
    label: str         # Display label (e.g. "Serial Number")
    field_type: str    # "text" | "password" | "number"
    required: bool = True
    default: Any = None
    placeholder: str = ""
    help_text: str = ""
```

Added to `abstract_printer_client.py` alongside the existing `PrinterCapabilities` dataclass.

### `connection_fields()` classmethod — `AbstractPrinterClient`

```python
@classmethod
def connection_fields(cls) -> list[ConnectionField]:
    return []
```

Default returns empty list. Each concrete client overrides it:

| Client | Fields returned |
|---|---|
| `BambuMQTTClient` | `serial_number` (text, required), `access_code` (password, required) |
| `ElegooCentauriClient` | `port` (number, required, default=3030) |
| `MoonrakerClient` | `port` (number, required, default=7125), `api_key` (text, required=False) |
| `SnapmakerU1Client` | `port` (number, required, default=7125), `api_key` (text, required=False) |

### Registry — `backend/app/services/printer_registry.py` (new file)

```python
PRINTER_CLIENT_REGISTRY: dict[str, tuple[str, type[AbstractPrinterClient]]] = {
    "bambu":           ("Bambu Lab",          BambuMQTTClient),
    "elegoo_centauri": ("Elegoo Centauri",    ElegooCentauriClient),
    "moonraker":       ("Moonraker / Klipper", MoonrakerClient),
    "snapmaker_u1":    ("Snapmaker U1",        SnapmakerU1Client),
}
```

Importing this file is the single place to register a new printer type. `PrinterManager` imports from here instead of hardcoding its own type map.

### New API endpoint — `GET /api/v1/printer-types`

Added to `backend/app/api/routes/printers.py`. No DB reads — reads directly from the registry.

Response (no auth required — same as the existing discovery endpoints):

```json
[
  {
    "printer_type": "bambu",
    "display_name": "Bambu Lab",
    "connection_fields": [
      {
        "name": "serial_number",
        "label": "Serial Number",
        "field_type": "text",
        "required": true,
        "default": null,
        "placeholder": "01P00A000000000",
        "help_text": ""
      },
      {
        "name": "access_code",
        "label": "Access Code",
        "field_type": "password",
        "required": true,
        "default": null,
        "placeholder": "From printer LAN settings",
        "help_text": ""
      }
    ]
  },
  {
    "printer_type": "elegoo_centauri",
    "display_name": "Elegoo Centauri",
    "connection_fields": [
      {
        "name": "port",
        "label": "Port",
        "field_type": "number",
        "required": true,
        "default": 3030,
        "placeholder": "3030",
        "help_text": "SDCP WebSocket port (default 3030)"
      }
    ]
  }
]
```

---

## Frontend

### New types — `frontend/src/api/client.ts`

```typescript
export interface PrinterConnectionField {
  name: string;
  label: string;
  field_type: 'text' | 'password' | 'number';
  required: boolean;
  default: string | number | null;
  placeholder: string;
  help_text: string;
}

export interface PrinterTypeInfo {
  printer_type: string;
  display_name: string;
  connection_fields: PrinterConnectionField[];
}
```

New API call added to the `api` object:

```typescript
getPrinterTypes: (): Promise<PrinterTypeInfo[]> =>
  fetch('/api/v1/printer-types').then(r => r.json()),
```

### Modal step 1 — Type picker

The `AddPrinterModal` component opens on step 1. It fetches `/api/v1/printer-types` via `useQuery` on mount. Results are rendered as a vertical list (same card style as the discovered-printer list already in the modal). Clicking a type card advances to step 2.

Step 1 has no "Back" target — closing the modal dismisses.

### Modal step 2 — Connection form

State: `{ step: 1 | 2, selectedType: PrinterTypeInfo | null, form: Record<string, string | number> }`

The form renders in two sections:

**Common fields** (always present, same as today):
- Name (text, required)
- IP Address (text, required, same pattern validation)
- Model (text, optional free-text)
- Location (text, optional)
- Auto-archive (checkbox)

The **network discovery** scan button appears between IP and Model, same as today. Selecting a discovered printer pre-fills Name, IP, and Model.

**Connection fields** (dynamic, from `selectedType.connection_fields`):
Rendered after the common fields. For each field:
- `"text"` → `<input type="text">`
- `"password"` → `<input type="password">`  
- `"number"` → `<input type="number">`
- `required` → HTML `required` attribute + asterisk on label
- `default` → initialises the form state value for that field
- `placeholder` → input placeholder
- `help_text` → `<p className="text-xs text-bambu-gray mt-1">` below the input

**Back button** in step 2 returns to step 1 and resets the form (connection field values only; name/IP/model/location are preserved so the user doesn't have to re-type after changing type).

### Submit

On submit, the form assembles the payload:

```typescript
{
  name,
  ip_address,
  printer_type: selectedType.printer_type,
  model: model || undefined,
  location: location || undefined,
  auto_archive,
  // connection field values spread in from form state:
  serial_number: form.serial_number,   // Bambu only
  access_code: form.access_code,       // Bambu only
  port: form.port,                     // Moonraker/Elegoo only
  api_key: form.api_key || undefined,  // Moonraker/Elegoo only
}
```

This is the same `PrinterCreate` shape the existing `POST /api/v1/printers` endpoint accepts. No backend route changes beyond the new `GET /api/v1/printer-types`.

---

## What Does Not Change

- `POST /api/v1/printers` — unchanged; still accepts the flat `PrinterCreate` payload
- `printer_type_schemas` DB table — left as-is (JSON Schema validation layer, separate concern)
- `PrinterCreate` TypeScript interface — unchanged (flat optional fields)
- All other printer routes, `PrinterManager`, `PrinterCard` — untouched

## Scope

This design covers the **add** flow only. The edit-printer form (which also has type-specific fields) is a separate task.
