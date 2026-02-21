# Phase 6 — Order Logging and Document Generation

**Prerequisites:** Phase 5 complete and verified.
**Verify before P7:** WhatsApp group logging works, Excel append works, PDF generation works.

## Steps (execute in order, commit after each)

1. Implement `app/orders/logging_service.py` — order logging to WhatsApp group and Excel file  
   (log on order confirmation, update `whatsapp_logged_at` and `excel_logged_at`)  
   → Commit: `"orders: implement order logging to WhatsApp group and Excel file"`

2. Implement `app/reporting/excel_generator.py` — monthly Excel order log via openpyxl  
   Columns: order_number, customer, shop, items, quantities, prices, discounts, total,  
   payment_method, delivery_zone, status, confirmed_at  
   → Commit: `"reporting: implement monthly Excel order log with all columns via openpyxl"`

3. Implement `app/reporting/pdf_generator.py` — catalog PDF and order receipt PDF via ReportLab  
   → Commit: `"reporting: implement catalog PDF and order receipt generation via ReportLab"`

4. Test WhatsApp group logging, Excel file append, PDF generation end-to-end  
   → Commit: `"tests: verify order logging pipeline end-to-end"`

5. **PHASE 6 COMPLETE** Commit: `"phase-6: order logging and document generation complete"`
