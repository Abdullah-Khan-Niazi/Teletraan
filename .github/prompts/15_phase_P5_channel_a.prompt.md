# Phase 5 — Channel A: All Customer Flows

**Prerequisites:** Phase 4 complete and verified.
**Verify before P6:** All Channel A flows tested end-to-end (onboarding, ordering, voice, complaint, profile, language switch, quick reorder, credit check).

## Steps (execute in order, commit after each)

1. Implement `app/inventory/fuzzy_matcher.py` — RapidFuzz medicine matching, multi-field scoring, ranking  
   (match on medicine_name, generic_name, brand_name, search_keywords)  
   → Commit: `"inventory: implement RapidFuzz medicine matching with multi-field scoring and ranking"`

2. Implement `app/inventory/catalog_service.py` — catalog CRUD, TTL cache management, category operations  
   → Commit: `"inventory: implement catalog CRUD, cache management, and category operations"`

3. Implement `app/channels/channel_a/onboarding.py` — full customer registration flow  
   (name, shop_name, address, city, language preference, voice support)  
   → Commit: `"channel-a: implement full customer registration flow with validation and voice support"`

4. Implement `app/orders/billing_service.py` — discount rules engine, bonus units calculation, delivery charges  
   → Commit: `"orders: implement billing with discount rules, bonus units, and delivery charges"`

5. Integrate billing service with order context manager — update pricing_snapshot on every change  
   → Commit: `"orders: integrate billing service with order context manager"`

6. Implement `app/channels/channel_a/order_flow.py` — complete order flow  
   (item collection → fuzzy match → ambiguity resolution → voice support → bill preview → discount requests → confirmation)  
   → Commit: `"channel-a: implement complete order flow from item collection to confirmation"`

7. Implement `app/orders/order_service.py` — order CRUD, status management, history tracking  
   → Commit: `"orders: implement order CRUD with status management and history tracking"`

8. Implement `app/channels/channel_a/catalog_flow.py` — catalog browse, search, pagination, document send  
   → Commit: `"channel-a: implement catalog browse, search, pagination, and document send"`

9. Implement `app/channels/channel_a/complaint_flow.py` — complaint submission with categories, photos, ticket generation  
   → Commit: `"channel-a: implement complaint submission with categories, photos, and ticket generation"`

10. Implement `app/channels/channel_a/profile_flow.py` — profile view and field-level edit flows  
    → Commit: `"channel-a: implement profile view and field-level edit flows"`

11. Implement `app/channels/channel_a/inquiry_flow.py` — medicine questions, order status, help  
    → Commit: `"channel-a: implement inquiry handler for medicine questions, order status, and help"`

12. Implement `app/channels/channel_a/handler.py` — main handler dispatching to all flows based on state and intent  
    → Commit: `"channel-a: implement main handler dispatching to all flows based on state and intent"`

13. Implement business hours enforcement, credit limit check, human handoff flows  
    → Commit: `"channel-a: add business hours enforcement, credit limit check, and human handoff"`

14. Test all Channel A flows end-to-end with real WhatsApp messages  
    → Commit: `"tests: integration tests for all Channel A conversation flows"`

15. **PHASE 5 COMPLETE** Commit: `"phase-5: all Channel A customer flows complete and integration tested"`
