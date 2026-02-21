# TELETRAAN Order Context Schema — sessions.pending_order_draft (JSONB)

**This is the COMPLETE specification** of what must be stored in
`sessions.pending_order_draft` (JSONB) for every order in progress.
Every field is REQUIRED unless marked optional.
The context must be sufficient to **fully reconstruct the order conversation state
after a complete process restart**. Update on every state transition — never leave stale.

---

## Top-Level Fields

| Field | Type | Note |
|---|---|---|
| `order_context_version` | string | `"1.0"` — schema version for forward compatibility |
| `session_order_id` | string (UUID) | Temporary ID for draft before DB write — generate on first item add |
| `flow_step` | string | ENUM: `item_collection` \| `item_confirmation` \| `bill_preview` \| `discount_request` \| `final_confirmation` \| `complete` |
| `initiated_at` | ISO8601 timestamp | When customer started this order |
| `last_modified_at` | ISO8601 timestamp | Update on every change |
| `total_messages_in_order` | integer | Count of messages exchanged — for analytics |

---

## items (array) — All items added to the order

Each item in the array:

| Field | Type | Note |
|---|---|---|
| `line_id` | string (UUID) | Unique per line item — for edit/remove targeting |
| `catalog_id` | string (UUID) or null | null if unlisted item |
| `medicine_name_raw` | string | **Exactly** what the customer typed/said — preserved for audit |
| `medicine_name_matched` | string | Name after fuzzy matching to catalog |
| `medicine_name_display` | string | Name shown to customer in bill |
| `generic_name` | string or null | |
| `brand_name` | string or null | |
| `strength` | string or null | e.g., `500mg` |
| `form` | string or null | e.g., `tablet`, `syrup` |
| `unit` | string | e.g., `strip`, `box`, `carton` |
| `quantity_requested` | integer | |
| `price_per_unit_paisas` | integer | Price snapshot at time of addition |
| `line_subtotal_paisas` | integer | quantity × price — before discounts |
| `discount_applied_paisas` | integer | default `0` |
| `bonus_units` | integer | default `0` |
| `line_total_paisas` | integer | After discount |
| `is_out_of_stock` | boolean | |
| `stock_available_at_add` | integer or null | Stock qty at time of addition |
| `is_unlisted` | boolean | True if not in catalog |
| `is_confirmed_by_customer` | boolean | Customer explicitly confirmed this item match |
| `input_method` | string | ENUM: `text` \| `voice` \| `button_selection` |
| `voice_transcription` | string or null | Original voice transcription if input_method=voice |
| `fuzzy_match_score` | float or null | RapidFuzz score — null if exact match or unlisted |
| `fuzzy_alternatives_shown` | array of strings or null | Other options shown during match |
| `added_at` | ISO8601 timestamp | |
| `discount_request` | object or null | See below |

### item.discount_request (object or null)
| Field | Type | Note |
|---|---|---|
| `request_type` | string | ENUM: `bonus_units` \| `percentage` \| `flat_amount` |
| `requested_value` | string | e.g., `'2+1'`, `'10%'`, `'PKR 50'` |
| `status` | string | ENUM: `pending` \| `approved` \| `rejected` \| `auto_applied` |

---

## order_level_discount_request (object or null)
| Field | Type | Note |
|---|---|---|
| `request_text` | string | Exactly what customer said |
| `status` | string | ENUM: `pending` \| `approved` \| `rejected` |

---

## pricing_snapshot (object)
| Field | Type | Note |
|---|---|---|
| `subtotal_paisas` | integer | |
| `item_discounts_paisas` | integer | |
| `order_discount_paisas` | integer | default `0` |
| `auto_applied_discounts` | array | List of auto-applied rule IDs and amounts |
| `delivery_charges_paisas` | integer | default `0` |
| `total_paisas` | integer | |
| `calculated_at` | ISO8601 timestamp | |

---

## delivery (object)
| Field | Type | Note |
|---|---|---|
| `address` | string or null | Copied from customer profile, can be overridden |
| `zone_id` | string (UUID) or null | |
| `zone_name` | string or null | |
| `estimated_delivery_hours` | integer or null | |
| `delivery_day_display` | string or null | e.g., `'Kal ya parson'` in customer's language |
| `address_confirmed` | boolean | default `false` |

---

## ambiguity_resolution (object)
| Field | Type | Note |
|---|---|---|
| `pending_clarifications` | array | See below |
| `all_resolved` | boolean | |

### pending_clarifications item
| Field | Type | Note |
|---|---|---|
| `line_id` | string | Which line item needs clarification |
| `ambiguity_type` | string | ENUM: `multiple_matches` \| `quantity_unclear` \| `unit_unclear` \| `strength_unclear` |
| `options_presented` | array of strings | |
| `resolved` | boolean | default `false` |

---

## voice_order_context (object or null) — when order initiated via voice
| Field | Type | Note |
|---|---|---|
| `original_transcription` | string | Full raw transcription of voice order |
| `items_extracted_count` | integer | |
| `transcription_confirmed_by_customer` | boolean | |
| `audio_duration_seconds` | float | |
| `ai_confidence` | string | ENUM: `high` \| `medium` \| `low` |

---

## quick_reorder_source (object or null) — if this is a reorder
| Field | Type | Note |
|---|---|---|
| `source_order_id` | string (UUID) | |
| `source_order_number` | string | |
| `items_changed` | boolean | Did customer modify items from source order |

---

## Remaining Top-Level Fields
| Field | Type | Note |
|---|---|---|
| `customer_notes` | string or null | Free-text notes customer added |
| `bill_shown_at` | ISO8601 timestamp or null | When bill preview was shown |
| `bill_shown_count` | integer | default `0` — detect loops |
| `confirmation_requested_at` | ISO8601 timestamp or null | |
| `order_cancelled` | boolean | default `false` |
| `cancellation_reason` | string or null | |
| `ai_context_summary` | string or null | AI-generated 2-sentence summary — injected to save tokens on long orders |

---

## Update Rules
1. Update `last_modified_at` on every field change
2. Update `pricing_snapshot` whenever any item is added, removed, or modified
3. **Never delete items** from the items array — set a `cancelled` flag instead (for audit)
4. Append to `voice_order_context` only — never overwrite
5. Persist context to DB (`session update`) on every state transition — not just at end
6. When order is confirmed and written to orders table, clear `pending_order_draft` to `{}`
7. Generate `ai_context_summary` when items count exceeds 8 — reduces token usage

---

## Pydantic Model Location
`app/db/models/order_context.py` — Pydantic v2 model matching this exact schema.
`app/orders/context_manager.py` — All CRUD operations on this context.
