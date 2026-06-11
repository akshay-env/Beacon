# Beacon — Website Layout (Functional Flow)

## Pages Overview

| # | Page | Purpose |
|---|---|---|
| 1 | **Home** | Search entry point — the first thing users see and do |
| 2 | **Search Results** | Ranked list of matching problem cards |
| 3 | **Card Detail** | Full view of a single problem card |
| 4 | **Card Editor** | Create or edit a problem card |
| 5 | **Chat** | RAG conversation grounded in selected cards |
| 6 | **Users** | Employee directory — manage people |

---

## Page 1 — Home

This is the landing page. The dominant element is a **search bar** — front and center, impossible to miss. The user's first action should always be obvious: *type your problem here*.

**What's on the page:**

- **Search bar** — text input with a submit button. This is the primary action.
- **Tag filter chips** — a row of clickable tags (populated from existing cards) that users can toggle to narrow their search before or alongside the text query.
- **"Create a Card" button** — secondary action, always accessible. Takes users to the Card Editor.
- **Navigation** — links to Users page and a system status indicator (green dot = healthy, red = something's down).
- **Recent cards** — a short list (5-10) of the most recently created cards below the search bar, so users can browse even without searching.

**What happens:**
- User types a problem and hits search → goes to **Search Results**
- User clicks a tag chip → filters the recent cards list, and pre-selects that tag for when they do search
- User clicks "Create a Card" → goes to **Card Editor**
- User clicks a recent card → goes to **Card Detail**

---

## Page 2 — Search Results

Shows the ranked results from the semantic search. Each result is a card summary — not the full card, just enough to decide if it's relevant.

**What's on the page:**

- **Search bar** (persisted from Home, pre-filled with the query) — so users can refine without going back.
- **Active tag filters** — showing which tags are applied, removable.
- **Result count** — "Found 7 results for 'DNS resolution failing'"
- **Result list** — each result shows:
  - Card title
  - First 2-3 lines of the problem description (truncated)
  - Tags
  - Similarity score (e.g., "92% match")
  - Creator name (if any)
  - Date created
- **Select checkboxes** — each result has a checkbox. Users can select 1 or more cards.
- **"Chat about selected" button** — appears once at least 1 card is selected. Takes the selected card IDs to the **Chat** page.

**What happens:**
- User clicks a card title → goes to **Card Detail**
- User selects 2-3 cards via checkboxes → clicks "Chat about selected" → goes to **Chat** with those cards as context
- User modifies the search query → results refresh in place
- User toggles a tag filter → results refresh

---

## Page 3 — Card Detail

The full, detailed view of a single problem card. Everything the author documented.

**What's on the page:**

- **Title** — the card's name
- **Problem Description** — full text, could be multiple paragraphs
- **Solution** — full text, may contain steps, code snippets, etc.
- **Outcome** — what happened after the solution was applied (if provided)
- **Tags** — displayed as clickable elements (clicking one takes you to Search Results filtered by that tag)
- **Creator info section:**
  - Creator name
  - Department
  - Contact options (email, Slack, phone — whatever they've listed)
  - A clear "Contact this person" call-to-action (e.g., opens email client, copies Slack handle)
  - If no creator → show "No creator linked" with no contact options
- **Card metadata** — created date, last updated date
- **Actions:**
  - "Edit" button → goes to **Card Editor** pre-filled with this card's data
  - "Delete" button → confirmation prompt, then deletes and returns to Home
  - "Chat about this card" button → goes to **Chat** with this single card pre-selected

**What happens:**
- User reads the solution and it answers their question → done
- User wants more detail → clicks "Chat about this card" → goes to **Chat**
- User wants to talk to the person who solved it → uses the contact info
- User clicks a tag → goes to **Search Results** filtered by that tag
- User clicks "Edit" → goes to **Card Editor**

---

## Page 4 — Card Editor

A form for creating a new card or editing an existing one. Same page, different mode.

**What's on the page (form fields):**

- **Title** — text input (required)
- **Problem Description** — large text area (required). Placeholder: "Describe the problem you encountered..."
- **Solution** — large text area (required). Placeholder: "How did you solve it?"
- **Outcome** — text area (optional). Placeholder: "What happened after applying the solution?"
- **Tags** — tag input where user can type and add tags. Shows existing tags as suggestions while typing (autocomplete from tags already in the database).
- **Created By** — dropdown of existing users (optional). If creating your own card, select yourself. Can be left empty.
- **Submit button** — "Create Card" or "Save Changes" depending on mode
- **Cancel button** — goes back to previous page without saving

**What happens:**
- On submit (create mode) → card is created, embedding is auto-generated, user is redirected to the new **Card Detail** page
- On submit (edit mode) → card is updated, embedding re-generates if content changed, user is redirected back to **Card Detail**
- Validation errors → shown inline next to the field (e.g., "Title is required")

---

## Page 5 — Chat

The RAG chat interface. The user arrives here with 1 or more cards pre-selected as context. They ask questions and the LLM answers grounded in those cards.

**What's on the page:**

- **Selected cards sidebar/header** — shows which cards are being used as context:
  - Each card shows its title
  - An "×" button to remove a card from context
  - An "Add more cards" button that opens a mini search to find and add more cards
- **Chat area** — scrollable message thread:
  - User messages on one side
  - Assistant messages on the other
  - Messages stream in token-by-token (not all at once)
  - Assistant messages may reference cards by number (e.g., "According to Card 1...")
- **Message input** — text input at the bottom with a send button
- **"New conversation" button** — clears the chat history, keeps the selected cards

**What happens:**
- User types a question → message appears in thread → assistant response streams in
- User asks a follow-up → history is maintained, response references prior context
- User removes a card from the sidebar → that card's content is no longer in context for future messages
- User clicks "Add more cards" → mini search modal, select cards, add to sidebar
- User clicks a card title in the sidebar → opens **Card Detail** in a new tab (so the chat isn't lost)

---

## Page 6 — Users

Employee directory. A simple management page.

**What's on the page:**

- **User list** — table or list of all users showing:
  - Name
  - Email
  - Department
  - Number of cards they've created
- **Search/filter bar** — filter the user list by name or department
- **"Add User" button** → opens a form (inline or modal):
  - Name (required)
  - Email (required)
  - Department (optional)
  - Contact info fields — Slack, phone, or any key-value pair
- **Each user row** has:
  - "Edit" action → edit their info inline or in a modal
  - "Delete" action → confirmation prompt
  - Clicking the name → shows that user's detail with all their linked cards listed

---

## User Flow Summary

The primary journey — someone has a problem and needs an answer:

```
Home (search bar)
  ↓ type problem, hit search
Search Results (ranked cards)
  ↓ find a relevant card
  ├─→ Card Detail (read the solution → done!)
  │     ↓ need more info?
  │     ├─→ Chat (ask follow-up questions about this card)
  │     └─→ Contact Creator (reach out to the person)
  └─→ Select multiple cards → Chat (ask questions across cards)
```

The secondary journey — someone solved a problem and wants to document it:

```
Home → "Create a Card" → Card Editor → fill in fields → submit → Card Detail
```

The admin journey:

```
Home → Users → manage employees (add, edit, delete)
```
