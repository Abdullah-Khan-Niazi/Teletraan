# TELETRAAN — Conversation Flows

## Overview

TELETRAAN operates two distinct conversation channels, each with its own
finite state machine (FSM) that governs the conversation flow.

- **Channel A** — Retailer order management (distributor's WhatsApp number)
- **Channel B** — Software sales funnel (owner's WhatsApp number)

---

## Channel A — Order Management FSM

Channel A handles existing retailer customers placing medicine orders,
checking order status, filing complaints, and browsing the catalog.

### State Diagram

```
                    ┌─────────┐
                    │  IDLE   │ ◄── session created / reset
                    └────┬────┘
                         │ incoming message
                         ▼
                ┌────────────────────┐
                │  INTENT DETECTION  │
                │  (AI-powered NLU)  │
                └───┬──┬──┬──┬──┬───┘
                    │  │  │  │  │
         ┌──────────┘  │  │  │  └──────────────┐
         ▼             │  │  │                  ▼
    ┌─────────┐        │  │  │          ┌──────────────┐
    │ NEW     │        │  │  │          │  COMPLAINT   │
    │ ORDER   │        │  │  │          │  FLOW        │
    └────┬────┘        │  │  │          └──────┬───────┘
         │             │  │  │                 │
         ▼             │  │  │                 ▼
    ┌─────────────┐    │  │  │          ┌──────────────┐
    │ ITEM INPUT  │    │  │  │          │  COMPLAINT   │
    │ (text/voice)│    │  │  │          │  DESCRIPTION │
    └────┬────────┘    │  │  │          └──────┬───────┘
         │             │  │  │                 │
         ▼             │  │  │                 ▼
    ┌─────────────┐    │  │  │          ┌──────────────┐
    │ FUZZY MATCH │    │  │  │          │  COMPLAINT   │
    │ CONFIRMATION│    │  │  │          │  SUBMITTED   │
    └────┬────────┘    │  │  │          └──────────────┘
         │             │  │  │
         ▼             │  │  │
    ┌─────────────┐    │  │  └─────────────────┐
    │ ORDER REVIEW│    │  │                    ▼
    │ (add/edit)  │    │  │            ┌──────────────┐
    └────┬────────┘    │  │            │  CATALOG     │
         │             │  │            │  BROWSING    │
         ▼             │  │            └──────┬───────┘
    ┌─────────────┐    │  │                   │
    │ PAYMENT     │    │  └───────┐           ▼
    │ SELECTION   │    │          │     ┌──────────────┐
    └────┬────────┘    │          ▼     │  CATALOG     │
         │             │    ┌─────────┐ │  RESULTS     │
         ▼             │    │ ORDER   │ └──────────────┘
    ┌─────────────┐    │    │ STATUS  │
    │ PAYMENT     │    │    │ CHECK   │
    │ PROCESSING  │    │    └─────────┘
    └────┬────────┘    │
         │             ▼
         ▼       ┌──────────┐
    ┌─────────┐  │ REORDER  │
    │ ORDER   │  │ (quick)  │
    │ COMPLETE│  └────┬─────┘
    └─────────┘       │
         │            ▼
         └────► IDLE ◄┘
```

### Key States

| State | Description | Transitions |
|---|---|---|
| `idle` | Waiting for customer message | → intent detection |
| `new_order` | Order initiated | → item_input |
| `item_input` | Receiving order items (text or voice) | → fuzzy_match / order_review |
| `fuzzy_match_confirmation` | Confirming ambiguous medicine matches | → item_input / order_review |
| `order_review` | Showing order summary, customer can edit | → payment_selection / item_input |
| `payment_selection` | Choosing payment method | → payment_processing |
| `payment_processing` | Waiting for payment confirmation | → order_complete |
| `order_complete` | Order confirmed, receipt sent | → idle |
| `catalog_browsing` | Browsing medicine catalog | → catalog_results / idle |
| `order_status_check` | Checking existing order status | → idle |
| `complaint_description` | Describing a complaint | → complaint_submitted |
| `complaint_submitted` | Complaint recorded | → idle |
| `quick_reorder` | Reordering from previous order | → order_review |

### Voice Order Flow

```
Customer sends voice message
          │
          ▼
    ┌─────────────┐
    │ TRANSCRIBE  │  (OpenAI Whisper / STT provider)
    │ AUDIO       │
    └────┬────────┘
         │
         ▼
    ┌─────────────┐
    │ NLU EXTRACT │  (AI extracts items + quantities)
    │ ORDER ITEMS │
    └────┬────────┘
         │
         ▼
    ┌─────────────┐
    │ FUZZY MATCH │  (match against distributor catalog)
    │ TO CATALOG  │
    └────┬────────┘
         │
         ▼
    Order Review (same as text flow)
```

---

## Channel B — Sales Funnel FSM

Channel B handles incoming inquiries to the owner's WhatsApp number,
qualifying prospects for the TELETRAAN software service.

### State Diagram

```
                    ┌─────────┐
                    │  IDLE   │ ◄── session created
                    └────┬────┘
                         │ first message
                         ▼
                ┌────────────────────┐
                │  GREETING +        │
                │  QUALIFICATION     │
                └────────┬───────────┘
                         │
                         ▼
                ┌────────────────────┐
                │  NEEDS ASSESSMENT  │  ← AI-driven conversation
                │  (ask about biz)   │
                └────────┬───────────┘
                         │
              ┌──────────┴──────────┐
              │                     │
              ▼                     ▼
        ┌───────────┐        ┌───────────┐
        │ QUALIFIED │        │    NOT    │
        │ (hot lead)│        │ QUALIFIED │
        └─────┬─────┘        └─────┬─────┘
              │                     │
              ▼                     ▼
        ┌───────────┐        ┌───────────┐
        │ SERVICE   │        │ THANK YOU │
        │ SHOWCASE  │        │ + EXIT    │
        └─────┬─────┘        └───────────┘
              │
              ▼
        ┌───────────┐
        │ PRICING + │
        │ DEMO OFFER│
        └─────┬─────┘
              │
              ▼
        ┌───────────┐
        │ FOLLOW UP │  ← scheduled reminder
        └─────┬─────┘
              │
              ▼
        ┌───────────┐
        │ CONVERTED │  ← becomes a distributor
        │ or LOST   │
        └───────────┘
```

### Key States

| State | Description | Transitions |
|---|---|---|
| `idle` | Waiting for first message | → greeting |
| `greeting` | Welcome + initial qualification questions | → needs_assessment |
| `needs_assessment` | AI asks about their distribution business | → qualified / not_qualified |
| `qualified` | Prospect meets criteria | → service_showcase |
| `not_qualified` | Does not meet criteria | → thank_you |
| `service_showcase` | Show TELETRAAN features and benefits | → pricing |
| `pricing` | Present pricing and offer demo | → follow_up |
| `follow_up` | Scheduled follow-up reminders | → converted / lost |

### Qualification Criteria

A prospect is qualified if they:
1. Are a medicine distributor in Pakistan
2. Have at least 10 active retailer customers
3. Currently take orders via WhatsApp manually
4. Express interest in automation

---

## Common Features (Both Channels)

### Session Expiry

Sessions expire after 30 minutes of inactivity. The scheduler runs
`cleanup_jobs.run_session_cleanup()` every 6 hours to remove expired sessions.

When a session expires:
1. If order was in progress: draft saved, customer notified
2. Session state reset to `idle`
3. Next message creates a fresh session

### Human Handoff

Any channel can trigger human handoff:
- Customer requests human operator
- AI confidence too low (< 30%)
- Sensitive topic detected (pricing disputes, complaints)

When handoff activates:
1. Session `handoff_mode` set to `true`
2. Distributor notified via WhatsApp
3. All subsequent messages forwarded to distributor
4. Distributor can release handoff via admin

### Language Support

TELETRAAN supports three language modes:
- **Roman Urdu** (default) — Urdu written in Latin script
- **Urdu** — Native Urdu script
- **English** — Full English

Language is auto-detected from the first few messages and stored in the session.

### Interrupt Handling

At any point, a customer can interrupt the current flow:
- "Cancel" → abort current operation, return to idle
- "Help" → show available commands
- "Status" → show latest order status (even mid-order)
- "Complaint" → switch to complaint flow
