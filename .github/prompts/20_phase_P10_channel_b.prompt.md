# Phase 10 — Channel B: Sales Bot

**Prerequisites:** Phase 9 complete and verified.
**Verify before P11:** Full Channel B flow tested — first message through payment through distributor created and onboarding sequence started.

## Steps (execute in order, commit after each)

1. Implement `app/channels/channel_b/service_registry.py` — dynamic service registry from DB with handler routing  
   (load services from `service_registry` table, cache with TTL, route to correct sales flow handler)  
   → Commit: `"channel-b: implement dynamic service registry from DB with handler routing"`

2. Implement `app/channels/channel_b/sales_flow.py` — full prospect qualification through demo booking and payment  
   Stages: greeting → qualification (business type, retailer count, city) → service presentation →  
   demo booking → proposal → payment link generation → payment confirmation  
   → Commit: `"channel-b: implement full prospect qualification through demo booking and payment"`

3. Implement `app/channels/channel_b/onboarding_flow.py` — post-payment distributor onboarding automation  
   Steps: create distributor record → run `onboarding_service` sequence → assign Channel A phone number →  
   send welcome kit → catalog upload instructions → test order setup  
   → Commit: `"channel-b: implement post-payment distributor onboarding automation"`

4. Implement `app/channels/channel_b/handler.py` — sales channel handler with owner command processing  
   Owner commands: "list prospects", "qualify [number]", "close [prospect_id]", "lost [prospect_id] [reason]"  
   → Commit: `"channel-b: implement sales channel handler with owner command processing"`

5. Seed `service_registry` table with TELETRAAN service entry (via migration 027 or script)  
   → Commit: `"db: seed service_registry with Teletraan service entry"`

6. Test full Channel B flow end-to-end: first message → qualification → service presented →  
   payment link → payment confirmed → distributor record created → onboarding started  
   → Commit: `"tests: integration test Channel B from first message to distributor creation"`

7. **PHASE 10 COMPLETE** Commit: `"phase-10: Channel B sales bot complete and integration tested"`
