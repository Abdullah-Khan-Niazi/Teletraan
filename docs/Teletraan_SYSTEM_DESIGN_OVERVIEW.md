# TELETRAAN — WhatsApp Intelligent Order & Operations Bot
### Full System Design Document | Pakistan Medicine Distribution Sector

---

## EXECUTIVE SUMMARY

TELETRAAN is a production-grade WhatsApp automation system for medicine distributors in Pakistan, built on Meta Cloud API + Python + Supabase. It handles retailer order management (Channel A) and your own software sales funnel (Channel B) — both fully automated. For a single distributor handling 1,000–2,000 orders/month, total running cost lands between **PKR 4,500–8,500/month** depending on AI provider chosen. The system is architected as multi-tenant from day one — adding a new distributor requires only a new SIM assignment and environment config, with zero structural changes.

---

## DELIVERABLE 1 — FEASIBILITY ANALYSIS

### Technical Resources Required

- **WhatsApp Business API** — Meta Cloud API (free API; pay per message after 1,000 free conversations/month)
- **AI Layer** — Gemini 1.5 Flash (recommended) or OpenAI GPT-4o-mini + Whisper
- **Hosting** — Railway or Render (free tier sufficient for single distributor; ~500MB RAM Python process)
- **Database** — Supabase free tier (500MB DB, 2GB bandwidth — sufficient for 1–2 distributors)
- **Payment** — JazzCash Merchant API or EasyPaisa Business API
- **Voice Pipeline** — WhatsApp sends voice as `.ogg` audio; must be decoded and sent to STT API
- **Webhook Server** — Always-on Python server (FastAPI/Flask) to receive WhatsApp webhook events

### Solo Developer Viability

- **Viable: YES** — with GitHub Copilot Pro assistance
- Estimated build time: **8–14 weeks** for full feature set (single distributor deployment)
- Risk: Voice pipeline (Urdu `.ogg` decoding + STT) is the hardest component — allocate 2–3 weeks
- Supabase multi-tenant schema design is straightforward if done correctly from start
- Channel B (sales bot) can be built after Channel A is stable — 2–3 additional weeks

### Automated Distributor Management Feasibility

- **Fully feasible** for routine operations (reminders, payment links, notifications)
- WhatsApp Business API supports scheduled/triggered messages via API calls — not broadcasts
- Must use **individual message sends** (not broadcast) to avoid policy violations
- Automated CRM state machine in Supabase tracks each distributor's subscription lifecycle

### Hybrid AI vs Full AI Recommendation

| Scenario | Recommendation |
|---|---|
| Text processing (orders, menus) | Full AI — Gemini Flash handles Roman Urdu/Urdu well |
| Voice transcription (Urdu) | Full AI — Gemini 1.5 Flash Audio OR OpenAI Whisper |
| Distributor management comms | Rule-based templates — no AI needed for reminders |
| Sales funnel (Channel B) | Full AI — conversational handling |
| Inventory sync | Rule-based Python script — no AI needed |
| Order logging | Rule-based — structured data extraction |

**Recommendation: Hybrid architecture** — AI for NLU/NLG, rule-based for all structured operations

### Risk Assessment

| Risk | Level | Mitigation |
|---|---|---|
| WhatsApp number ban (policy violation) | HIGH | Never use broadcast; use API-triggered individual messages only; warm up new numbers gradually |
| Meta Cloud API message cost overrun | MEDIUM | Set spending alerts; 1,000 free business-initiated conversations/month — stay within for distributors |
| Gemini/OpenAI API quota limits | LOW | Implement retry logic; per-distributor rate limiting |
| JazzCash API integration complexity | MEDIUM | JazzCash merchant API is underdocumented — EasyPaisa is slightly easier |
| Supabase free tier limits | LOW | 1–2 distributors easily within free tier; upgrade at 3+ |
| Urdu voice accuracy | MEDIUM | Gemini 1.5 Flash Audio shows strong Urdu performance; fallback to text if confidence low |
| Saraiki/Punjabi voice | HIGH | Deprioritize — no reliable STT model for Saraiki at production quality currently |

### Scalability Roadmap

- **1 distributor** — Supabase free + Railway free tier — near-zero infra cost
- **2–5 distributors** — Railway Hobby Plan (PKR ~2,800/month) + Supabase free still holds
- **10+ distributors** — Supabase Pro (~PKR 8,400/month) + Railway scale plan
- **Architecture already multi-tenant** — no code restructuring needed to add distributors

---

## DELIVERABLE 2 — COST ANALYSIS TABLE

### One-Time Development Cost

| Item | Cost (PKR) |
|---|---|
| Your development fee (self-employed) | 30,000 – 40,000 |
| Meta Business verification (one-time) | 0 (free) |
| JazzCash/EasyPaisa merchant account setup | 0 – 2,000 (documentation costs) |
| **Total One-Time** | **30,000 – 42,000** |

### Monthly Running Cost Per Distributor (1,000–2,000 orders/month)

> Assumptions: ~3 WhatsApp messages per order exchange avg, ~15% of customers use voice, text-heavy system

| Item | Option A: Gemini Only | Option B: OpenAI Only | Option C: Hybrid (Gemini Text + Whisper Voice) | Recommendation |
|---|---|---|---|---|
| **AI — Text Processing** | Gemini 1.5 Flash ~PKR 500–900 | GPT-4o-mini ~PKR 900–1,600 | Gemini Flash ~PKR 500–900 | Gemini |
| **AI — Voice (STT)** | Gemini Audio included in above | Whisper API ~PKR 300–600 | Whisper ~PKR 300–600 | Gemini (bundled) |
| **WhatsApp API Messages** | ~PKR 800–1,500 (service convos mostly free; business-initiated cost applies) | Same | Same | Same for all |
| **Hosting — Railway Hobby** | PKR 2,800/month (shared across distributors) | Same | Same | Railway |
| **Database — Supabase** | Free tier (1 distributor) | Free | Free | Free tier |
| **SIM Card + Data** | PKR 500–800/month | Same | Same | Jazz/Zong unlimited data SIM |
| **Payment Gateway Fee** | 1.5–2% per transaction (on your subscription fee collection) | Same | Same | JazzCash |
| **TOTAL (est.)** | **PKR 4,600–6,000** | **PKR 5,000–7,500** | **PKR 4,600–6,300** | **Option A or C** |

### API Cost Comparison — Cheapest vs Best Quality

| Criteria | Gemini 1.5 Flash | GPT-4o-mini | OpenAI Whisper | Recommendation |
|---|---|---|---|---|
| Urdu text understanding | Excellent | Very Good | N/A | Gemini |
| Urdu voice recognition | Very Good (Flash Audio) | N/A | Good | Gemini Flash Audio |
| Roman Urdu handling | Excellent | Good | N/A | Gemini |
| Cost per 1M tokens | ~$0.075 input / $0.30 output | ~$0.15 input / $0.60 output | $0.006/min audio | Gemini cheapest |
| API reliability | High | Very High | Very High | Tie |
| Urdu-specific training data | Stronger (Google data) | Good | Fair | Gemini |
| **Overall Winner** | ✅ Best value | ❌ 2x cost | Use only if needed | **Gemini 1.5 Flash** |

---

## DELIVERABLE 3 — TECHNOLOGY COMPARISON TABLE

### No-Code vs Custom Python Code

| Criteria | No-Code (Twilio, WATI, Respond.io) | Custom Python Code |
|---|---|---|
| Setup speed | Fast (days) | Slower (weeks) |
| Monthly cost | PKR 8,000–25,000+ per distributor | PKR 500–1,500 AI cost only |
| Urdu voice support | None or basic | Full control via Gemini/Whisper |
| Multi-tenant control | Locked to vendor structure | Full control |
| Custom discount/bonus logic | Not possible | Fully custom |
| Inventory sync automation | Limited/impossible | Full Python control |
| WhatsApp interactive buttons | Supported | Supported via Meta API |
| Vendor lock-in risk | HIGH | None |
| Scalability | Costs explode at scale | Costs grow linearly and cheaply |
| **Verdict** | ❌ Not viable for this use case | ✅ Only viable path |

### Open-Source LLMs vs Gemini/GPT-4o — Urdu Voice Trade-offs

| Criteria | Mistral / LLaMA (self-hosted) | Gemini 1.5 Flash | GPT-4o / Whisper |
|---|---|---|---|
| Urdu text quality | Fair (LLaMA 3.1 improved) | Excellent | Very Good |
| Urdu STT (voice) | Very Poor — no production-ready Urdu STT open-source | Very Good | Good (Whisper) |
| Roman Urdu | Poor — no fine-tuning for Roman Urdu | Excellent | Good |
| Hosting cost (self-hosted) | PKR 15,000–40,000+/month GPU server | API only — no hosting | API only |
| Reliability | You manage uptime | Google manages | OpenAI manages |
| Setup complexity | Extremely HIGH — not viable solo | Low | Low |
| Pakistan latency | High if GPU abroad | Low (Google CDN) | Medium |
| **Verdict for TELETRAAN** | ❌ Not viable — no Urdu STT, high infra cost | ✅ **Recommended** | ✅ Backup option |

---

## DELIVERABLE 4 — SYSTEM ARCHITECTURE DIAGRAM

```
╔══════════════════════════════════════════════════════════════════════════════════╗
║                          TELETRAAN — SYSTEM TOPOLOGY                            ║
╚══════════════════════════════════════════════════════════════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━━ CHANNEL A: ORDER CHANNEL ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  [Retailer/Chemist]
       │
       │  Text / Voice / Roman Urdu / Urdu / English
       ▼
  [WhatsApp App]
       │
       │  Webhook POST (message event)
       ▼
  ┌─────────────────────────────────────────────────┐
  │          META CLOUD API (WhatsApp)              │
  │   Distributor SIM Number: +92-XXX-XXXXXXX       │
  └─────────────────────────────────────────────────┘
       │
       │  Webhook → HTTPS
       ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │              TELETRAAN BOT SERVER (Railway/Render)              │
  │                                                                 │
  │  ┌─────────────────┐    ┌──────────────────┐                   │
  │  │  Message Router │───▶│  Session Manager │                   │
  │  └─────────────────┘    └──────────────────┘                   │
  │          │                      │                              │
  │          ▼                      ▼                              │
  │  ┌──────────────┐    ┌────────────────────┐                    │
  │  │ Voice Handler│    │  Text/NLU Handler  │                    │
  │  │  (.ogg→STT)  │    │  (Gemini Flash)    │                    │
  │  └──────────────┘    └────────────────────┘                    │
  │          │                      │                              │
  │          └──────────┬───────────┘                              │
  │                     ▼                                          │
  │          ┌────────────────────┐                                │
  │          │  Order Processor   │                                │
  │          │  - Catalog lookup  │                                │
  │          │  - Fuzzy match     │                                │
  │          │  - Discount logic  │                                │
  │          │  - Bill calculator │                                │
  │          └────────────────────┘                                │
  │                     │                                          │
  │          ┌──────────▼──────────┐                               │
  │          │  Response Builder   │                               │
  │          │  - Buttons/Menus    │                               │
  │          │  - Urdu/Eng/Roman   │                               │
  │          └─────────────────────┘                               │
  └─────────────────────────────────────────────────────────────────┘
       │                    │                    │
       ▼                    ▼                    ▼
  [Gemini API]       [Supabase DB]        [Meta Cloud API]
  (Text + STT)    (Orders, Customers,    (Send reply back
                  Inventory, Sessions)    to WhatsApp)
                        │
                        ▼
              ┌──────────────────┐
              │  Order Logger    │
              ├──────────────────┤
              │ • WhatsApp Group │
              │ • Excel File     │
              └──────────────────┘


━━━━━━━━━━━━━━━━━━━━━━━ CHANNEL B: SALES CHANNEL ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  [Prospect/New Distributor]
       │
       ▼
  [WhatsApp — Owner Number]
       │
       ▼
  ┌────────────────────────────────────────────┐
  │    TELETRAAN SALES BOT (same server)       │
  │                                            │
  │  ┌──────────────────────────────────────┐  │
  │  │  Service Registry Config             │  │
  │  │  (Teletraan, Future Service B, C...) │  │
  │  └──────────────────────────────────────┘  │
  │              │                             │
  │              ▼                             │
  │  ┌──────────────────────────────────────┐  │
  │  │  Sales Flow Engine                   │  │
  │  │  Qualify → Demo → Proposal →         │  │
  │  │  Payment → Onboard                   │  │
  │  └──────────────────────────────────────┘  │
  └────────────────────────────────────────────┘
       │                     │
       ▼                     ▼
  [JazzCash/EasyPaisa   [Supabase CRM]
   Payment Link]        (Prospect → Distributor)
       │
       ▼
  [Trigger Onboarding Sequence → Distributor Mgmt Module]


━━━━━━━━━━━━━━━━━━━━ DISTRIBUTOR MANAGEMENT MODULE ━━━━━━━━━━━━━━━━━━━━━━━━━━━

  [Supabase Scheduler / Cron Jobs]
       │
       ├──▶ Payment Due? → Send JazzCash link to Distributor WhatsApp
       ├──▶ 7/3/1 day before expiry → Escalating reminder messages
       ├──▶ Deployment update? → Notify all active distributors
       ├──▶ Support ticket received? → Queue for Owner review
       └──▶ Fee confirmed? → Extend subscription in DB automatically


━━━━━━━━━━━━━━━━━━━━━━━━ SUPABASE MULTI-TENANT SCHEMA ━━━━━━━━━━━━━━━━━━━━━━━━

  ┌─────────────────────────────────────────────────────┐
  │                  SUPABASE DATABASE                  │
  ├─────────────────┬───────────────────────────────────┤
  │  distributors   │  id, name, whatsapp_num, plan,    │
  │                 │  subscription_end, status          │
  ├─────────────────┼───────────────────────────────────┤
  │  customers      │  id, distributor_id (FK),          │
  │  (per tenant)   │  name, shop, address, lang_pref    │
  ├─────────────────┼───────────────────────────────────┤
  │  orders         │  id, distributor_id, customer_id, │
  │                 │  items_json, discount, status,     │
  │                 │  created_at                        │
  ├─────────────────┼───────────────────────────────────┤
  │  catalog        │  id, distributor_id, medicine_name │
  │                 │  price, stock_qty, unit            │
  ├─────────────────┼───────────────────────────────────┤
  │  sessions       │  whatsapp_num, distributor_id,    │
  │                 │  state, context_json, updated_at   │
  ├─────────────────┼───────────────────────────────────┤
  │  payments       │  id, distributor_id, amount,      │
  │                 │  method, status, confirmed_at      │
  └─────────────────┴───────────────────────────────────┘
```

---

## DELIVERABLE 5 — STEP-BY-STEP IMPLEMENTATION GUIDE

### 1. Environment & Dependency Setup
- Install Python 3.11+, create virtual environment
- Install: `fastapi`, `uvicorn`, `httpx`, `supabase-py`, `python-dotenv`, `pydub`, `openpyxl`, `rapidfuzz`
- Set up `.env` file with all API keys, never hardcode credentials
- Use GitHub for version control; connect to Railway/Render via GitHub for auto-deploy

### 2. WhatsApp Business API — Multi-Number Setup Strategy
- Create Meta Business Account → verify business (individual developer account accepted)
- Add WhatsApp Business product in Meta Developer Console
- For each distributor: register a new phone number under the same Meta App (one App, multiple numbers supported)
- Each number gets its own Phone Number ID — stored in Supabase `distributors` table
- Webhook is a single endpoint — route incoming messages by `phone_number_id` field in payload to correct distributor context
- Use permanent SIMs (Jazz/Zong) with unlimited internet packages — avoid SIM expiry

### 3. AI API Setup — Gemini 1.5 Flash (Recommended)
- Create Google Cloud project → enable Gemini API → get API key
- Use `google-generativeai` Python SDK
- For voice: WhatsApp sends voice as `.ogg` (Opus codec) — use `pydub` + `ffmpeg` to convert to `.wav` or send raw audio bytes to Gemini Audio API
- Gemini 1.5 Flash supports audio input directly — pass base64 audio with MIME type `audio/ogg`
- System prompt per distributor loaded from Supabase (distributor name, catalog summary, language preference)
- Maintain conversation history per session (last 10 turns stored in `sessions` table context_json)

### 4. Supabase Schema Design — Multi-Tenant
- All tables include `distributor_id` foreign key — this is the tenant isolation mechanism
- Row Level Security (RLS) policies in Supabase ensure each query is scoped to correct distributor
- `sessions` table uses composite key: `(whatsapp_number, distributor_id)` — a customer could exist across multiple distributors
- Catalog table populated by distributor during onboarding — CSV import script (Python) reads their Excel and upserts to Supabase
- Indexes on `distributor_id`, `customer whatsapp_number`, `order created_at` for query performance

### 5. Distributor Management Module Design
- A Python `scheduler.py` process (APScheduler library) runs alongside the bot server
- Checks Supabase daily for: subscriptions expiring in 7, 3, 1 days → fires WhatsApp API messages to distributor number
- On payment confirmation (webhook from JazzCash/EasyPaisa or manual confirmation): updates `subscription_end` in Supabase, sends confirmation message
- Support ticket flow: distributor sends "support" keyword → bot captures issue description → inserts to `support_tickets` table → sends you a WhatsApp notification

### 6. Payment Integration Setup — JazzCash vs EasyPaisa
- **Recommended: JazzCash Merchant API** — more documented, wider distributor adoption
- Register as JazzCash merchant (visit Jazz franchise or apply online — requires CNIC + business details)
- JazzCash API generates a payment link or USSD push — send this link via WhatsApp to distributor
- On payment: JazzCash sends webhook → bot updates Supabase subscription record
- **Fallback**: Distributor sends screenshot of bank transfer → bot stores it → you manually confirm → bot auto-extends subscription on your confirmation reply
- EasyPaisa Business API is alternative — similar process, slightly less documentation available

### 7. Channel B — Sales Bot Flow Design
- Separate routing: if incoming WhatsApp number matches owner number in config → route to sales bot handler
- Service registry: a JSON config in Supabase (or flat file) listing all services with descriptions, pricing, demo video links
- Gemini handles the conversational sales flow — system prompt instructs it to qualify, pitch, and collect details
- Collected prospect data → inserted to `prospects` table → on payment → moved to `distributors` table → triggers onboarding sequence

### 8. Multi-Language Support Implementation
- Detect language from first message: Gemini classifies as Urdu / English / Roman Urdu
- Store preference in `customers.lang_pref` column
- All bot response templates exist in three language versions — Gemini generates response in detected/preferred language
- Mid-conversation switch: customer types "English mein baat karo" → update session language preference → confirm switch → continue in new language
- Roman Urdu: no special handling needed — Gemini handles it natively as text

### 9. Voice Processing Pipeline
- WhatsApp sends voice message → webhook receives media ID
- Step 1: Call Meta API to get media download URL using media ID
- Step 2: Download `.ogg` audio file to temp memory (do not save to disk permanently)
- Step 3: Send audio bytes directly to Gemini 1.5 Flash Audio endpoint with prompt: "Transcribe this medicine order in the original language"
- Step 4: Get transcription → pass to same NLU pipeline as text messages
- Step 5: Reply with text confirmation of what was understood — ask customer to confirm
- Confidence fallback: if transcription seems garbled → ask customer to type or re-record

### 10. Interactive Buttons and Menu Flows
- Meta Cloud API supports `interactive` message type with `button` (up to 3 buttons) and `list` (up to 10 items) types
- Main menu: 3 buttons → [Order Karo] [Catalog Dekho] [Complaint / Inquiry]
- Medicine search result: list of up to 10 matched items with select option
- Order confirmation: 2 buttons → [Confirm Order ✅] [Edit Order ✏️]
- All button interactions return `button_reply` or `list_reply` in webhook — route accordingly
- For more than 10 options (large catalog): use paginated list messages (show 10 at a time with Next/Prev buttons)

### 11. Order Logging — WhatsApp Group + Excel
- **WhatsApp Group**: Each distributor has a dedicated WhatsApp group (distributor + their staff). Bot is added to group via same number. On order confirmation → bot sends formatted order summary to group
- **Excel File**: Use `openpyxl` to append order row to an `.xlsx` file stored in Supabase Storage (or emailed to distributor daily via a simple email API like Resend/SendGrid)
- Order log columns: Order ID | Date-Time | Customer Name | Shop Name | Items | Qty | Discount | Total | Status

### 12. Inventory Sync Automation Script Design
- Distributor maintains their stock in a simple Excel sheet (or their existing software exports CSV)
- Python script (APScheduler — every 2 hours) reads the file from a shared Google Drive link or Supabase Storage upload
- Script compares catalog stock quantities → updates `catalog.stock_qty` in Supabase
- Bot checks stock at order time: if qty = 0 → informs customer "Abhi stock nahi hai, order phir bhi place ho sakta hai — distributor restock karega"
- Level 2 inventory (real-time): **defer to after stable deployment** — Excel sync is sufficient for current scale

### 13. Deployment on Railway/Render
- Connect GitHub repo to Railway → auto-deploy on push to `main` branch
- Environment variables set in Railway dashboard (not in code)
- Railway free tier: 500 hours/month — sufficient for single distributor (use Render free tier as backup — always-on)
- **Render free tier recommended for start**: always-on web service, 512MB RAM, no sleep (with paid $7/month — but even free works for low traffic)
- Configure WhatsApp webhook URL to point to Railway/Render public URL
- Set up health check endpoint so Railway/Render keeps service alive

### 14. Testing Procedures
- **Unit testing**: Test each module independently — catalog lookup, fuzzy match, bill calculator, session state machine
- **Conversation flow testing**: Use Meta's WhatsApp API test numbers to simulate customer messages without real SIM
- **Voice testing**: Record sample Urdu voice orders → run through pipeline → verify transcription accuracy
- **Multi-tenant isolation testing**: Create 2 test distributors → verify customer data never leaks across tenants
- **Load testing**: Simulate 50 concurrent webhook requests → verify bot handles without timeout
- **Payment flow testing**: JazzCash sandbox environment available — test full payment → confirmation → subscription update cycle
- **WhatsApp button testing**: Test all interactive button flows — confirm each state transition works correctly

---

## DELIVERABLE 6 — COMPLETE SYSTEM SIMULATION (Roman Urdu)

---

### CHANNEL A — SIM 1: First-Time Customer Onboarding (Text)

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  CHANNEL A | Naya Customer | Text
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[USER]: Hello order karna hai

[BOT]:  Assalam o Alaikum! 👋
        Al-Shifa Distributors mein khush aamdeed.
        Main aapka order assistant hoon — TELETRAAN.

        Pehli baar aa rahe hain? Chaliye account
        bana lete hain sirf 1 minute mein!

        Aapka naam kya hai?

[USER]: Rizwan Ahmed

[BOT]:  Shukriya Rizwan bhai! 😊
        Aapki dukaan ka naam?

[USER]: Rizwan Medical Store

[BOT]:  Aur dukaan ka pata? (Gali, Mohalla, Sheher)

[USER]: Main Bazar, Dukaan 14, Gujranwala

[BOT]:  Aur aapka WhatsApp number?
        (Ye number hi save ho jayega — change karna
        ho to baad mein bhi ho sakta hai)

[USER]: 0312-1234567

[BOT]:  ✅ Shukriya! Aapka account ban gaya:

        👤 Naam: Rizwan Ahmed
        🏪 Dukaan: Rizwan Medical Store
        📍 Pata: Main Bazar, Dukaan 14, Gujranwala
        📞 Number: 0312-1234567

        Kya ye details theek hain?

        ┌─────────────┐  ┌─────────────┐
        │  ✅ Haan    │  │  ✏️ Edit    │
        └─────────────┘  └─────────────┘

[USER]: [Haan button press]

[BOT]:  Zabardast! Ab aap order kar sakte hain 🎉

        Kya karna chahte hain?

        ┌─────────────┐  ┌─────────────┐  ┌──────────────┐
        │ 📦 Order   │  │ 📋 Catalog  │  │ 📞 Complaint │
        └─────────────┘  └─────────────┘  └──────────────┘
```

---

### CHANNEL A — Voice Order Flow

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  CHANNEL A | Purana Customer | Voice Input
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[USER]: 🎤 [Voice Message — 12 sec]
        (Urdu mein): "Bhai mujhe paracetamol 500mg
        ke 5 strips chahiye, augmentin 625 ke 2 boxes,
        aur ORS ka ek carton. Jaldi dena please."

[BOT]:  🎧 Shukriya! Maine sun liya. Ye mujhe
        samajh aaya:

        ─────────────────────────────────
        1. Paracetamol 500mg — 5 strips
        2. Augmentin 625mg — 2 boxes
        3. ORS Sachet — 1 carton
        ─────────────────────────────────

        Kya ye order bilkul theek hai?

        ┌────────────────┐  ┌─────────────┐
        │ ✅ Theek Hai   │  │ ✏️ Edit    │
        └────────────────┘  └─────────────┘

[USER]: [Theek Hai button press]

[BOT]:  📋 BILL ESTIMATE:

        ─────────────────────────────────────────
        Item                  Qty    Price
        ─────────────────────────────────────────
        Paracetamol 500mg     5 str  PKR 175
        Augmentin 625mg       2 box  PKR 960
        ORS Sachet Carton     1 ctn  PKR 850
        ─────────────────────────────────────────
        TOTAL                        PKR 1,985
        ─────────────────────────────────────────

        Koi discount ya bonus chaahiye?
        (e.g., "5+1 Paracetamol pe")

        ┌──────────────────┐  ┌──────────────────┐
        │ 💰 Discount Maango│  │ ✅ Seedha Confirm│
        └──────────────────┘  └──────────────────┘
```

---

### CHANNEL A — Discount/Bonus Request

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  CHANNEL A | Discount Flow
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[USER]: [Discount Maango button]

[BOT]:  Zaroor! Kaunsi cheez pe discount/bonus
        chahiye? Likhein:
        (e.g., "Augmentin pe 10+1" ya "5% chhoot chahiye")

[USER]: Augmentin pe 2+1 karo bhai purana rishta hai

[BOT]:  😄 Rizwan bhai, aapki request distributor
        ko bhej di gai hai:

        📝 Bonus Request:
        Augmentin 625mg — 2+1 bonus manga hai

        Ye distributor approve karte hain to order
        mein update ho jata hai. Abhi ke liye
        order confirm karna chahenge?

        ┌─────────────────────┐  ┌──────────────────┐
        │ ✅ Haan, Confirm Karo│  │ ⏳ Pehle Batao   │
        └─────────────────────┘  └──────────────────┘

[USER]: [Haan, Confirm Karo]

[BOT]:  ✅ ORDER CONFIRMED!

        📦 Order #2847 — Rizwan Medical Store
        📅 18 Feb 2025 | 3:42 PM

        ITEMS:
        • Paracetamol 500mg × 5 strips
        • Augmentin 625mg × 2 boxes
          (2+1 bonus request: pending approval)
        • ORS Sachet × 1 carton

        💰 Total: PKR 1,985

        🚚 Delivery: Aaj ya kal delivery hogi.
        Koi sawaal ho to message karein!

        Shukriya Al-Shifa se order karne ka 🙏
```

---

### CHANNEL A — Medicine Misspelling / Fuzzy Match

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  CHANNEL A | Ghalat Spelling / Fuzzy Match
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[USER]: mujhe amxcillin chahiye 500mg

[BOT]:  Maine "amxcillin" dhundha — kya aap ye
        mein se koi muraad rakhte hain? 🤔

        ┌────────────────────────────────────┐
        │ 1. Amoxicillin 500mg Capsule       │
        │ 2. Amoxicillin + Clavulanate 625mg │
        │ 3. Ampicillin 500mg                │
        │ 4. Kuch aur dhundna hai            │
        └────────────────────────────────────┘

[USER]: pehla wala

[BOT]:  ✅ Amoxicillin 500mg Capsule — kitne
        chahiye?

[USER]: 3 strips

[BOT]:  Note ho gaya! ✍️
        Amoxicillin 500mg × 3 strips (PKR 210)

        Aur kuch add karna hai?

        ┌─────────────┐  ┌────────────────────┐
        │ ➕ Aur Dana │  │ ✅ Order Complete   │
        └─────────────┘  └────────────────────┘
```

---

### CHANNEL A — Out of Stock Scenario

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  CHANNEL A | Out of Stock
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[USER]: Cefixime 200mg ke 10 boxes

[BOT]:  ⚠️ Cefixime 200mg — abhi stock mein
        sirf 4 boxes hain.

        Kya karna chahenge?

        ┌───────────────────┐  ┌──────────────────┐
        │ 📦 4 Hi Le Lo    │  │ 📋 Poora Order   │
        │                   │  │ Place Karo (baki │
        │                   │  │ baad mein milega)│
        └───────────────────┘  └──────────────────┘

[USER]: [Poora Order Place Karo]

[BOT]:  ✅ Theek hai! Aapka order mein Cefixime
        200mg × 10 boxes note ho gaya.

        📌 4 boxes aaj jayenge.
        Baaki 6 boxes — restock hote hi delivery
        hogi. Distributor inform ho gaya hai.

        Koi aur medicine?
```

---

### CHANNEL A — Unrecognized Medicine Request

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  CHANNEL A | Catalog Mein Nahi
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[USER]: Molnupiravir 200mg chahiye

[BOT]:  😕 Molnupiravir abhi hamare catalog mein
        nahi hai.

        Kya main aapki ye request distributor ko
        bhejun? Agar woh source kar sakein to
        aapko inform kar diya jayega.

        ┌──────────────────┐  ┌─────────────┐
        │ ✅ Haan Bhejo    │  │ ❌ Rehne Do │
        └──────────────────┘  └─────────────┘

[USER]: [Haan Bhejo]

[BOT]:  ✅ Request bhaij di! Distributor review
        karenge aur 24-48 ghante mein update
        milega aapko. Shukriya! 🙏
```

---

### CHANNEL A — Language Switch Mid-Conversation

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  CHANNEL A | Zabaan Badalna
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[USER]: Bhai English mein baat karo samajh nahi ata

[BOT]:  Sure! I'll switch to English right away.

        Your language has been updated to English.
        All future messages will be in English.

        What would you like to do?

        ┌──────────────┐  ┌───────────────┐  ┌───────────────┐
        │ 📦 Order    │  │ 📋 Catalog    │  │ 📞 Complaint  │
        └──────────────┘  └───────────────┘  └───────────────┘
```

---

### CHANNEL A — Profile Update Flow

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  CHANNEL A | Profile Update
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[USER]: mera address change ho gaya hai

[BOT]:  Zaroor update karte hain! Naya pata
        likhein please:

[USER]: Shop 22, Anarkali Bazaar, Lahore

[BOT]:  Aapka naya pata:
        📍 Shop 22, Anarkali Bazaar, Lahore

        Confirm karte hain?

        ┌──────────────┐  ┌──────────────┐
        │ ✅ Haan      │  │ ✏️ Dobara    │
        └──────────────┘  └──────────────┘

[USER]: [Haan]

[BOT]:  ✅ Address update ho gaya! Agla order
        naye pate pe jayega. 📍
```

---

### CHANNEL A — Complaint Submission Flow

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  CHANNEL A | Complaint
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[USER]: [📞 Complaint button press]

[BOT]:  Main sun raha hoon. Kya masla hai?

        ┌─────────────────┐  ┌──────────────────┐
        │ 📦 Wrong Item   │  │ ⏰ Late Delivery  │
        └─────────────────┘  └──────────────────┘
        ┌─────────────────┐  ┌──────────────────┐
        │ 💊 Kharab Maal  │  │ 📝 Aur Masla     │
        └─────────────────┘  └──────────────────┘

[USER]: [Wrong Item]

[BOT]:  Kaunse order ka masla hai?
        Order number ya date batain:

[USER]: Order 2847 — Augmentin ki jagah kuch aur aa gaya

[BOT]:  Shukria report karne ka. Aapki complaint
        darj ho gayi:

        🎫 Ticket #C-109
        📦 Order: #2847
        ⚠️ Masla: Wrong item received
        📅 18 Feb 2025

        Distributor 24 ghante mein contact karega.
        Apna ticket number save kar lein. 🙏
```

---

### ORDER LOG FORMAT (Har Confirmed Order ke Baad WhatsApp Group + Excel)

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ORDER LOG — WhatsApp Group Message Format
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📦 *NAYA ORDER — #2847*
━━━━━━━━━━━━━━━━━━━━━━
📅 Tarikh: 18 Feb 2025 | 3:42 PM
👤 Customer: Rizwan Ahmed
🏪 Dukaan: Rizwan Medical Store
📍 Pata: Main Bazar, Dukaan 14, Gujranwala
📞 Number: 0312-1234567
━━━━━━━━━━━━━━━━━━━━━━
ITEMS:
• Paracetamol 500mg × 5 strips — PKR 175
• Augmentin 625mg × 2 boxes   — PKR 960
  ↳ 2+1 Bonus Request: PENDING
• ORS Sachet × 1 carton       — PKR 850
━━━━━━━━━━━━━━━━━━━━━━
💰 TOTAL: PKR 1,985
📊 Status: CONFIRMED — Awaiting Dispatch
━━━━━━━━━━━━━━━━━━━━━━

Excel Row Format:
| #2847 | 18-Feb-25 | 15:42 | Rizwan Ahmed | Rizwan Medical | Gujranwala | Paracetamol 500mg×5, Augmentin 625mg×2(+1 req), ORS×1ctn | 1985 | CONFIRMED |
```

---

### CHANNEL B — Prospect Inquiry → Demo → Payment

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  CHANNEL B | Naya Prospect (Owner Number)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[USER]: Hello bhai kisi ne bataya ap ka WhatsApp
        order system bahut acha hai distributors
        ke liye

[BOT]:  Wa alaikum assalam! 😊 Shukriya!
        Main TELETRAAN — ek smart WhatsApp order
        system for medicine distributors.

        Aap bhi apne business ke liye chahte hain?

        Pehle bataiye — aap kya karte hain?

        ┌─────────────────┐  ┌─────────────────┐
        │ 💊 Distributor  │  │ 🏪 Retailer/    │
        │                 │  │    Chemist      │
        └─────────────────┘  └─────────────────┘
        ┌─────────────────────────────────────────┐
        │ 🏢 Kuch Aur Business Hai                │
        └─────────────────────────────────────────┘

[USER]: [💊 Distributor]

[BOT]:  Acha! Kaunse sheher mein hain aur
        roughly kitne retailers ko deliver karte
        hain?

[USER]: Lahore mein hoon, around 200-300 retailers
        hain

[BOT]:  Wah — solid customer base! 💪
        TELETRAAN bilkul aapke liye bana hai.

        Kya dekhna chahenge?

        ┌───────────────────┐  ┌──────────────────┐
        │ 🎬 Demo Video    │  │ 💰 Pricing Dekho │
        └───────────────────┘  └──────────────────┘
        ┌──────────────────────────────────────────┐
        │ 📞 Live Demo Call Book Karo              │
        └──────────────────────────────────────────┘

[USER]: [🎬 Demo Video]

[BOT]:  Ye raha hamara demo video:
        🎬 [video link ya YouTube link]

        Isme dikhaya gaya hai:
        ✅ Order kaise aata hai WhatsApp pe
        ✅ Catalog search + voice ordering
        ✅ Auto order log WhatsApp group + Excel
        ✅ Aap ki taraf se zero manual kaam

        Pricing bhi dekhna chahenge?

[USER]: Haan

[BOT]:  💰 TELETRAAN PRICING:

        ┌─────────────────────────────────────┐
        │ Setup Fee (One-time): PKR 30,000    │
        │ Monthly Running:      PKR 8,000     │
        │                                     │
        │ Includes:                           │
        │ • Dedicated WhatsApp number         │
        │ • Full bot setup & customization    │
        │ • Unlimited orders                  │
        │ • Support & updates                 │
        └─────────────────────────────────────┘

        Live demo call book karein?

        ┌──────────────────────────────┐
        │ 📅 Demo Call Book Karo       │
        └──────────────────────────────┘

[USER]: [Demo Call Book Karo]

[BOT]:  Konsa waqt suit karta hai?

        ┌───────────────┐  ┌──────────────────┐
        │ Kal Subah 10  │  │ Kal Dopahar 2 PM │
        └───────────────┘  └──────────────────┘
        ┌───────────────────────────────────────┐
        │ Parson Subah 11 AM                    │
        └───────────────────────────────────────┘

[USER]: [Kal Subah 10]

[BOT]:  ✅ Demo booked!

        📅 19 Feb 2025 | 10:00 AM
        📞 Main khud call karunga aapko

        Aapka naam aur number confirm karein:

[USER]: Ahmad Raza — 0321-9876543

[BOT]:  ✅ Note ho gaya!
        Ahmad Raza bhai — kal 10 baje milte hain.
        Koi sawaal ho to yahan message karein. 🙏
```

---

### CHANNEL B — Future Service Inquiry (Non-Teletraan)

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  CHANNEL B | Future Service Routing
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[USER]: Bhai apke paas koi HR ya attendance
        system bhi hai? Mujhe staff ka record
        chahiye

[BOT]:  Abhi ye service available nahi — lekin
        soon launch hone wali hai! 🚀

        Kya main aapko waitlist mein add kar dun?
        Launch pe pehle inform karenge.

        ┌──────────────────┐  ┌──────────────────┐
        │ ✅ Waitlist      │  │ ❌ Rehne Do      │
        │    Mein Daalo    │  │                  │
        └──────────────────┘  └──────────────────┘

[USER]: [Waitlist Mein Daalo]

[BOT]:  ✅ Note ho gaya! Aapko launch pe sabse
        pehle bataya jayega. Shukriya! 🙏
```

---

### DISTRIBUTOR MANAGEMENT — Payment Reminder Sequence

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  DISTRIBUTOR MGMT | Payment Reminder Sequence
  (Automatic — Distributor ke WhatsApp pe)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

— 7 DAYS BEFORE EXPIRY —

[BOT → DISTRIBUTOR]:
  Assalam o Alaikum Ahmad bhai! 😊
  TELETRAAN service ki yaad dahaani:

  📅 Aapki subscription 7 din mein expire
     ho rahi hai (25 Feb 2025)
  💰 Amount: PKR 8,000

  Abhi renew karein — uninterrupted service:
  💳 [JazzCash Payment Link]

  Shukriya! 🙏

— 3 DAYS BEFORE EXPIRY —

[BOT → DISTRIBUTOR]:
  Ahmad bhai — sirf 3 din bache hain! ⚠️

  📅 Expiry: 25 Feb 2025
  💰 Renewal: PKR 8,000

  Abhi renew karein:
  💳 [JazzCash Payment Link]

  Koi masla ho to reply karein.

— 1 DAY BEFORE EXPIRY —

[BOT → DISTRIBUTOR]:
  ⚠️ ZARURI: Kal service band ho sakti hai!

  Ahmad bhai, kal 25 Feb ko subscription
  expire ho rahi hai.

  Abhi renew karein — kal bhi orders aate
  rahein:
  💳 [JazzCash Payment Link]

  Help chahiye? Reply karein.

— EXPIRY DAY (NO PAYMENT RECEIVED) —

[BOT → DISTRIBUTOR]:
  😔 Ahmad bhai, aaj se TELETRAAN service
  temporarily suspend ho gayi hai.

  Customers ko orders dene mein mushkil
  hogi.

  Abhi renew karein:
  💳 [JazzCash Payment Link]

  Payment hote hi service turant restore
  ho jati hai. 🔄

— ON PAYMENT RECEIVED —

[BOT → DISTRIBUTOR]:
  ✅ JazaakAllah Ahmad bhai!

  PKR 8,000 payment confirm ho gayi.
  TELETRAAN service extend ho gayi:

  📅 Nayi expiry: 25 March 2025
  🟢 Service: ACTIVE

  Koi sawaal: yahan reply karein. 🙏
```

---

### DISTRIBUTOR MANAGEMENT — Onboarding Appointment Booking

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  DISTRIBUTOR MGMT | Onboarding Flow
  (After Channel B payment confirmation)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[BOT → NEW DISTRIBUTOR]:
  Assalam o Alaikum Ahmad bhai! 🎉
  TELETRAAN mein khush aamdeed!

  Aapki payment confirm ho gayi — ab setup
  shuru karte hain.

  Setup call book karte hain — konsa waqt?

  ┌────────────────┐  ┌──────────────────┐
  │ Kal 10:00 AM  │  │ Kal 2:00 PM      │
  └────────────────┘  └──────────────────┘
  ┌──────────────────────────────────────────┐
  │ Parson Subah 11:00 AM                    │
  └──────────────────────────────────────────┘

[DISTRIBUTOR]: [Kal 10:00 AM]

[BOT]:  ✅ Setup call booked!

        📅 19 Feb 2025 | 10:00 AM

        Call se pehle ye ready rakhein:
        📋 Medicines list (Excel/PDF)
        💰 Prices list
        📞 WhatsApp number for bot

        Main khud call karunga. Milte hain! 🙏
```

---

### DISTRIBUTOR MANAGEMENT — New Deployment Notification

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  DISTRIBUTOR MGMT | Update Notification
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[BOT → DISTRIBUTOR]:
  🚀 TELETRAAN UPDATE — v1.3 Live!

  Ahmad bhai, aapke bot mein naye features
  add ho gaye hain:

  ✨ Kya naya hai:
  • Saraiki voice support (beta)
  • Order history: customers dekh sakte hain
    apne pichle 5 orders
  • Catalog PDF auto-generate on request

  Koi masla aaye to yahan batayein.
  Shukriya! 💚
```

---

## DELIVERABLE 7 — FEATURES & ARCHITECTURE LIST

### MODULE 1 — CORE ORDER ENGINE (Channel A)

**Must-Have (Launch se pehle zaroori)**
- Multi-input message handler (text, voice, mixed messages)
- Session state machine (per-customer conversation state tracking)
- Customer registration and profile management (first-time onboarding)
- Medicine catalog lookup with fuzzy name matching (RapidFuzz)
- Interactive WhatsApp button and list menus (Meta API interactive messages)
- Order builder (add, remove, modify items before confirmation)
- Bill calculator with line-item breakdown
- Discount/bonus request capture and flagging to distributor
- Order confirmation flow with final summary
- Order logging to WhatsApp group and Excel file
- Multi-language support (Urdu, English, Roman Urdu)
- Language switch mid-conversation

**Nice-to-Have (Post-launch additions)**
- Catalog PDF/image generation and sending on request
- Order history view for returning customers (last 5 orders)
- Saved order templates (customer's frequent order as quick reorder)
- Estimated delivery time display

---

### MODULE 2 — VOICE PROCESSING PIPELINE

**Must-Have**
- WhatsApp voice message (.ogg) download via Meta API
- Audio conversion (pydub + ffmpeg) to compatible format
- Gemini 1.5 Flash Audio transcription (primary)
- Transcription confirmation step shown to customer before processing
- Fallback prompt if transcription confidence is low (ask to retype)

**Nice-to-Have**
- Saraiki/Punjabi basic detection (deprioritized — no production-quality STT available)
- Auto-language detection from voice input

---

### MODULE 3 — AI/NLU LAYER

**Must-Have**
- Gemini 1.5 Flash as primary LLM (text + voice)
- Per-distributor system prompt (loaded from Supabase)
- Conversation context management (last 10 turns stored in session)
- Intent classification (order, inquiry, complaint, profile update, language switch)
- Entity extraction (medicine name, quantity, unit, discount type)
- Roman Urdu normalization before entity extraction

**Nice-to-Have**
- Confidence scoring per extraction (flag low-confidence items for confirmation)
- Ambiguity resolution (bot asks clarifying question automatically)

---

### MODULE 4 — INVENTORY MANAGEMENT

**Must-Have (Level 1)**
- Catalog lookup — is medicine in distributor's list?
- Stock quantity check from Supabase catalog table
- Out-of-stock messaging with partial fulfillment option
- Unlisted medicine request capture and flagging

**Nice-to-Have (Level 2 — Defer post-launch)**
- Automated inventory sync from distributor's Excel via shared Google Drive link (APScheduler, every 2 hours)
- Real-time stock deduction on order confirmation
- Low-stock alert to distributor

---

### MODULE 5 — CUSTOMER MANAGEMENT

**Must-Have**
- Customer registration (name, shop, address, phone)
- Profile retrieval on returning customer WhatsApp number match
- Profile update flow (address, name, phone)
- Language preference storage and application
- Per-distributor customer isolation (multi-tenant)

**Nice-to-Have**
- Customer order frequency analytics (most ordered items)
- Customer credit/payment status flag (if distributor maintains credit accounts)

---

### MODULE 6 — COMPLAINT & INQUIRY HANDLING

**Must-Have**
- Complaint submission flow (categorized: wrong item, late delivery, damaged goods, other)
- Complaint ticket generation with ID
- Complaint logging to Supabase
- Distributor notification on new complaint (WhatsApp group or direct message)

**Nice-to-Have**
- Complaint status tracking (customer can query ticket status)
- Complaint resolution confirmation to customer

---

### MODULE 7 — ORDER LOGGING & REPORTING

**Must-Have**
- Confirmed order sent to designated WhatsApp group (formatted summary)
- Excel file append via openpyxl (Order ID, date, customer, items, total, status)
- Excel file stored in Supabase Storage or emailed daily to distributor

**Nice-to-Have**
- Daily/weekly summary report auto-generated and sent to distributor WhatsApp
- Monthly revenue total report

---

### MODULE 8 — MULTI-TENANT ARCHITECTURE

**Must-Have**
- Supabase schema with `distributor_id` FK on all tables
- Row Level Security (RLS) policies for data isolation
- Webhook message routing by `phone_number_id` to correct distributor context
- Per-distributor system prompt and catalog
- Per-distributor environment config (stored in Supabase `distributors` table)

---

### MODULE 9 — DISTRIBUTOR MANAGEMENT (Automated)

**Must-Have**
- Subscription lifecycle state machine (active, expiring, suspended, cancelled)
- Automated payment reminders (7 days, 3 days, 1 day, expiry day)
- JazzCash/EasyPaisa payment link generation and sending
- Payment webhook handler — auto-extend subscription on confirmation
- Manual payment fallback (screenshot confirmation → manual trigger → auto-extend)
- Service suspension and reactivation flow
- Support ticket capture from distributor
- Deployment/update notification broadcast to all active distributors

**Nice-to-Have**
- Distributor self-service: check their own subscription status via bot command
- Escalating support ticket routing to you with priority tagging

---

### MODULE 10 — CHANNEL B SALES BOT

**Must-Have**
- Prospect greeting and business type qualification
- Service presentation (Teletraan + future services via service registry config)
- Demo video/catalog sending on request
- Lead detail collection (name, city, business size)
- Demo call booking with time slot selection
- Onboarding payment link generation
- Post-payment: trigger distributor onboarding sequence automatically
- Prospect and lead data storage in Supabase CRM table

**Nice-to-Have**
- Future service waitlist capture
- Automated follow-up if prospect doesn't respond within 48 hours
- Conversion tracking (inquiry → demo booked → paid)

---

### MODULE 11 — PAYMENT INTEGRATION

**Must-Have**
- JazzCash Merchant API integration (payment link generation)
- Payment webhook handler (confirm received → update Supabase)
- Manual bank transfer fallback flow
- Payment record logging (amount, method, timestamp, distributor)

**Nice-to-Have**
- EasyPaisa Business API as secondary payment option
- Automated payment receipt PDF generation and sending

---

### MODULE 12 — WEBHOOK SERVER & API LAYER

**Must-Have**
- FastAPI server (Python) as primary webhook handler
- Meta Cloud API webhook verification (GET challenge handling)
- POST handler for incoming messages (text, voice, interactive replies, status updates)
- Outbound message sending (text, interactive buttons/lists, media, documents)
- Rate limiting per distributor (prevent runaway API costs)
- Error handling and retry logic for failed API calls
- Health check endpoint (for Railway/Render uptime monitoring)

---

### MODULE 13 — SCHEDULER & AUTOMATION

**Must-Have**
- APScheduler (Python) running alongside FastAPI server
- Daily subscription expiry check job
- Payment reminder dispatch jobs (triggered by expiry date proximity)
- Inventory sync job (if Level 2 enabled — post-launch)

---

### MODULE 14 — ADMIN DASHBOARD (Lightweight)

**Must-Have**
- Supabase Table Editor as basic admin view (no custom dashboard needed at 1-distributor stage)
- View all distributors, subscription status, payment history
- View all orders (filterable by distributor, date, status)

**Nice-to-Have**
- Simple web dashboard (Streamlit or basic HTML page) with distributor overview cards
- One-click subscription extension from dashboard

---

### TECHNOLOGY STACK (Recommended Versions)

| Component | Technology | Version |
|---|---|---|
| Language | Python | 3.11+ |
| Web Framework | FastAPI | 0.110+ |
| ASGI Server | Uvicorn | 0.29+ |
| AI — Text + Voice | Gemini 1.5 Flash | API (google-generativeai 0.5+) |
| WhatsApp API | Meta Cloud API | v19.0+ |
| Database | Supabase (PostgreSQL) | Free tier |
| Supabase Client | supabase-py | 2.x |
| Fuzzy Matching | RapidFuzz | 3.x |
| Audio Processing | pydub + ffmpeg | Latest |
| Excel Generation | openpyxl | 3.x |
| Scheduler | APScheduler | 3.x |
| HTTP Client | httpx | 0.27+ |
| Hosting | Render (Free → Paid) | — |
| Payment | JazzCash Merchant API | Latest |
| Version Control | GitHub | — |
| AI Assist | GitHub Copilot Pro | — |

---

### Future Channel B Service Portfolio (Suggestions)

- **Pharmacy POS Bot** — sales recording via WhatsApp for small chemists without POS systems
- **HR/Attendance Bot** — staff check-in/check-out via WhatsApp for small businesses
- **Wholesale Price List Bot** — auto-updated price list distribution for any wholesale sector
- **Supplier Order Bot** — distributors ordering FROM their suppliers (reverse of Channel A)
- **Cold Chain Alert Bot** — temperature monitoring integration for pharma cold storage
- **Delivery Rider Bot** — delivery status updates and proof-of-delivery via WhatsApp

---

## DELIVERABLE 8 — SYSTEM NAME & BRANDING RATIONALE

**TELETRAAN** is the clear winner for this system. Teletraan-1 in Transformers lore was the Autobots' central intelligence — it managed all operations, communications, logistics, and data. This maps precisely to what this system does: managing orders, distributor operations, inventory coordination, and automated communications. It is tech-forward and memorable without being generic like "OrderBot" or "MedBot," and it has no existing trademark conflicts in the Pakistan software market.

Among the alternatives, CPO (C-3PO reference) feels too playful for a B2B distribution context. Otto and Elita sound like product names for European markets. R2 is too short and doesn't project intelligence. Cogman is obscure. TELETRAAN has the right balance of technical credibility and distinctiveness — a distributor hearing this name for the first time will remember it.

**Domain purchase: Not required at this stage.** You are delivering a WhatsApp-based service with no web-facing customer portal. A domain becomes relevant only when you build a marketing website or web dashboard. When you do, `teletraan.pk` or `teletraanbot.pk` should be registered — both are likely available and cost approximately PKR 2,500–4,000/year through PKNIC.

**Railway vs Render vs Netlify/Vercel:** Netlify and Vercel are designed exclusively for frontend/static sites and serverless functions — they cannot host a persistent Python webhook server that needs to be always-on. Railway and Render both support Python backend processes. Render's free tier offers always-on service (with limitations) and is the better starting point. Railway's Hobby plan at ~$5/month offers more reliability and faster cold starts once you need paid hosting. Both are vastly superior to Netlify/Vercel for this use case.

**Tagline suggestion:** *"Aapka Distributor, Hamara Kaam"* — speaks directly to the core value proposition in the target market's language, positioning TELETRAAN as the operational backbone that handles distributor work automatically.

**Market positioning:** Pakistan's medicine distribution sector is almost entirely managed through WhatsApp manually — salesmen forward order images, process them by hand, and call retailers constantly. TELETRAAN is not competing with enterprise ERP software; it is replacing the manual WhatsApp chaos that every distributor currently endures. This is a pain point they already feel every day, which means the sales pitch requires zero education about the problem — only about the solution.

---

## ACTION ITEMS CHECKLIST

### Immediate (Week 1)
- [ ] Create Meta Developer account and register Business App
- [ ] Get a Jazz/Zong SIM with unlimited data — activate WhatsApp Business on it
- [ ] Register Google Cloud account — enable Gemini API — save API key
- [ ] Create Supabase project — set up initial schema (distributors, customers, orders, catalog, sessions tables)
- [ ] Create Railway/Render account — connect GitHub repo
- [ ] Set up GitHub repo with project structure and Copilot Pro active

### Development (Week 2–4)
- [ ] Build FastAPI webhook server — handle Meta webhook verification
- [ ] Implement message router — route by phone_number_id to distributor context
- [ ] Build session state machine (Supabase-backed)
- [ ] Implement customer registration flow (text)
- [ ] Implement catalog lookup + RapidFuzz fuzzy matching
- [ ] Build interactive button/list menu flows
- [ ] Build order builder, bill calculator, discount capture
- [ ] Build order confirmation + WhatsApp group logging + Excel logging

### Week 5–7
- [ ] Implement voice pipeline (ogg download → Gemini Audio → transcription → NLU)
- [ ] Implement multi-language handling (detect + switch + persist preference)
- [ ] Build complaint submission flow
- [ ] Build profile update flow
- [ ] Build out-of-stock and unlisted medicine flows

### Week 8–10
- [ ] Build distributor management module (subscription state machine)
- [ ] Implement APScheduler for payment reminders
- [ ] Integrate JazzCash Merchant API (payment link + webhook confirmation)
- [ ] Build Channel B sales bot (service registry, qualification, demo booking, payment trigger)
- [ ] Build automated onboarding sequence triggered post-payment

### Pre-Launch
- [ ] Apply for JazzCash Merchant account (allow 2–4 weeks processing time — start this early)
- [ ] Test all conversation flows with real WhatsApp numbers
- [ ] Test voice pipeline with actual Urdu voice recordings
- [ ] Test multi-tenant isolation with 2 dummy distributors
- [ ] Test payment flow end-to-end in JazzCash sandbox
- [ ] Deploy to Render/Railway — verify webhook URL is live and accessible
- [ ] Update Meta App webhook URL to production endpoint
- [ ] Onboard first distributor — live testing with real retailers

### Ongoing
- [ ] Monitor Gemini API usage monthly — set billing alerts
- [ ] Monitor WhatsApp API conversation counts — stay within free tier limits
- [ ] Review support ticket queue weekly
- [ ] Upgrade Supabase/Railway plans as distributor count grows past 2
- [ ] Defer Level 2 inventory sync until post-stable-launch
- [ ] Deprioritize Saraiki/Punjabi voice — revisit when production-quality STT becomes available