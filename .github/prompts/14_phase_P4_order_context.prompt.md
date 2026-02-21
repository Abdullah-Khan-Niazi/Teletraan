# Phase 4 — Order Context and Session Management

**Prerequisites:** Phase 3 complete and verified.
**Verify before P5:** Process restart mid-order recovers seamlessly; both FSMs fully tested.

## Steps (execute in order, commit after each)

1. Implement `app/db/models/order_context.py` — Pydantic v2 model matching **exact** order context schema  
   See `07_order_context_schema.prompt.md` for every field  
   → Commit: `"db: add OrderContext Pydantic model matching full order context schema"`

2. Implement `app/orders/context_manager.py` — all 16 functions fully implemented (no stubs)  
   See `10_modules_and_features.prompt.md` → M35 for complete function list  
   → Commit: `"orders: implement complete order context manager with all CRUD operations"`

3. Implement `app/channels/channel_a/state_machine.py` — all states and transition validation  
   States: `idle` → `onboarding` → `main_menu` → `order_flow` → `catalog_browse` →  
   `complaint_flow` → `profile_flow` → `inquiry_flow` → `handoff` → session expiry  
   → Commit: `"channels: implement Channel A FSM with all states and transition validation"`

4. Implement `app/channels/channel_b/state_machine.py` — sales qualification and onboarding FSM  
   States: `idle` → `greeting` → `qualification` → `service_selection` → `demo_booking` →  
   `proposal` → `payment_pending` → `onboarding` → `converted`  
   → Commit: `"channels: implement Channel B FSM for sales qualification and onboarding"`

5. Implement session expiry logic — warn at 50 min, auto-expire at 60 min with notification  
   → Commit: `"sessions: add expiry warning at 50min and auto-expire at 60min with notification"`

6. Implement universal interrupt handling — cancel/menu from any state  
   → Commit: `"sessions: add universal interrupt handling for cancel and main-menu commands"`

7. Test process restart mid-order — kill server, restart, send next message, verify continuation  
   → Commit: `"tests: verify order context survives process restart via session persistence"`

8. Write unit tests for both FSMs and order context manager  
   → Commit: `"tests: add comprehensive state machine and order context unit tests"`

9. **PHASE 4 COMPLETE** Commit: `"phase-4: order context persistence and session FSMs complete, restart-safe"`
