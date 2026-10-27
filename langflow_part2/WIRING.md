# Wire the Part 2 flow in Langflow

This guide builds the Part 2 attendee-list flow by hand: 16 components and 21 connections. It takes about 30–45 minutes.

## Before you start

- Langflow runs at <http://localhost:7860>. Claude Code starts it with `langflow_part2/serve.sh`, or you can run that command yourself in a terminal.
- You do not need an account (auto-login).
- The keys come from `.env`. Langflow already shows `GROQ_API_KEY` and `OPENROUTER_API_KEY`.

## How the editor works

- The **left sidebar** lists the components. Type a name in **Search**. Our components are in the category **Event Ai**.
- **Drag** a component onto the canvas.
- **Inputs are on the left** of a component, and **outputs are on the right**. To connect, drag from an output dot to an input dot. The colours show the data type, and only matching types connect.
- **Some outputs have a menu.** When a component has more than one output, click the output name and select the one you need, for example **Language Model** or **Structured Response**.
- **Settings:** click a component to open its settings panel. Some settings are under **advanced** (the "Show advanced" or "Controls" view).
- **Tool Mode:** a switch in the menu of a component (the "..." at the top of the box). With Tool Mode on, the output becomes **Toolset**.

## Step 1: Create the flow

1. Click **Create first flow** (or **New Flow**), then **Blank Flow**.
2. Click the flow name at the top. Rename it to exactly **`Event AI Part 2 Attendee list`**. The run command finds the flow by this name.

## Step 2: Add the components

A suggested layout, from left to right:

| Column | Components |
| --- | --- |
| 1 | Chat Input, Load Event |
| 2 | Load RSVP Emails, Language Model (Groq), Language Model (OpenRouter) |
| 3 | Extract RSVPs, Check Records |
| 4 | Loop, Type Convert |
| 5 | Agent, CRM Lookup, Invitee Lookup, Company Search |
| 6 | Apply Decisions, Write Outputs, Chat Output |

| # | Component | Sidebar | Settings |
| --- | --- | --- | --- |
| 1 | Chat Input | Input & Output | none |
| 2 | Load Event | Event Ai | **Source**: `seed` (`google` needs the demo account) |
| 3 | Load RSVP Emails | Event Ai | none |
| 4 | Language Model, rename it "Groq" | Models & Agents | See the note below the table. |
| 5 | Language Model, rename it "OpenRouter" | Models & Agents | See the note below the table. |
| 6 | Extract RSVPs | Event Ai | none |
| 7 | Check Records | Event Ai | none |
| 8 | Loop | Flow Control | none |
| 9 | Type Convert | Processing | **Output Type**: `Message` |
| 10 | Agent | Models & Agents | See step 4. |
| 11 | CRM Lookup | Event Ai | **Tool Mode on** |
| 12 | Invitee Lookup | Event Ai | **Tool Mode on** |
| 13 | Company Search | Event Ai | **Tool Mode on** |
| 14 | Apply Decisions | Event Ai | none |
| 17 | Agent Decision | Event Ai | none (added on 27 Oct: it closes the loop) |
| 15 | Write Outputs | Event Ai | none (it writes to `outputs/`) |
| 16 | Chat Output | Input & Output | none |

**The two models (components 4 and 5).** In this Langflow version the model dropdown is not enough:
- It lists only a few paid OpenRouter models, with no search.
- Groq is not in it at all.

So both components use the override fields, which you open with **Parameters** above the box.

| Setting | Groq (4) | OpenRouter (5) |
| --- | --- | --- |
| **Language Model** (dropdown) | any listed model (a placeholder) | any listed model (a placeholder) |
| **Provider Override** | `Groq` | empty, or `OpenRouter` |
| **Model Name Override** | `openai/gpt-oss-120b` | `nvidia/nemotron-3.5-super-vl:free` |
| **Temperature** | `0` | `0` |

Both overrides were tested on 27 Oct. The override replaces the placeholder, so the placeholder model is never called.

## Step 3: Connect the components

Click the output name first, where the step says so.

| # | From (output) | To (input) |
| --- | --- | --- |
| 1 | Chat Input · **Chat Message** | Load Event · **Event ID** |
| 2 | Load Event · **Event** | Load RSVP Emails · **Event** |
| 3 | Load Event · **Event** | Check Records · **Event** |
| 4 | *(removed on 27 Oct, see below)* | |
| 5 | Load RSVP Emails · **Emails** | Extract RSVPs · **Emails** |
| 6 | Load RSVP Emails · **Emails** | Check Records · **Emails** |
| 7 | Groq · **Language Model** (select this output) | Extract RSVPs · **Primary model** |
| 8 | OpenRouter · **Language Model** (select this output) | Extract RSVPs · **Fallback model** |
| 9 | OpenRouter · **Language Model** | Agent · **Language Model** |
| 10 | Extract RSVPs · **Extractions** | Check Records · **Extractions** |
| 11 | Check Records · **Review queue** | Loop · **Inputs** |
| 12 | Loop · **Item** | Type Convert · **Input** |
| 13 | Type Convert · **Message Output** | Agent · **Input** |
| 14 | CRM Lookup · **Toolset** | Agent · **Tools** |
| 15 | Invitee Lookup · **Toolset** | Agent · **Tools** |
| 16 | Company Search · **Toolset** | Agent · **Tools** |
| 17 | Agent · **Structured Response** (select this output) | Agent Decision · **Structured Response** |
| 22 | Agent Decision · **Decision** | Loop · the **looping** dot on the Item output |
| 18 | Loop · **Done** | Apply Decisions · **Decisions** |
| 19 | Check Records · **Checked records** | Apply Decisions · **Checked records** |
| 20 | Apply Decisions · **Final records** | Write Outputs · **Final records** |
| 21 | Write Outputs · **Summary** | Chat Output · **Inputs** |

**Why there is no connection 4.** Langflow's Loop runs its body as a separate graph. That graph includes every component that the body depends on, back to the start of the flow.

At first, Invitee Lookup had an Event input from Load Event, and this broke the run:
- The Loop re-ran Load Event and the Chat Input for each flagged record.
- On these re-runs the Chat Input had no text, so Load Event failed on an empty event ID.

Now Load Event keeps the event in memory for the run, and Invitee Lookup reads it there. The rule: **a component inside the loop body (the Agent, its tools and its model) must have no input from before the Loop.**

**Why the Agent Decision box.** The Loop collects the **first** output of the last box in its body. For the Agent, that is its text Response, not the Structured Response, even when only the Structured Response is connected (found on 27 Oct: the first full run lost all 5 decisions). Agent Decision has one output, so the Loop collects the decision. The Agent also runs once for each record, not twice.

Connections 17 and 22 close the loop. The Agent decides one flag at a time. Its decision goes back into the Loop, and the Loop then sends the next flagged record. When every record is done, **Done** passes all the decisions on.

## Step 4: Set up the Agent

1. **Agent Instructions:** paste this text:

   ```text
   You resolve one flag on one attendee record of a company event.
   First call the CRM lookup tool with the attendee's email address. Use the invitee lookup tool for an invitation
   question, and the company search tool for a company question. Make at most 3 tool calls.

   Then decide the flag:
   - use_value: replace the field with a value that a tool result or a source email shows. Copy the value exactly.
   - keep: the current value is correct.
   - human_review: the evidence does not settle the flag, or a person must decide (for example a substitute guest).
   Never invent a value. Give the source of the value (for example crm.csv#C007) and one sentence as the reason.
   ```

   The same text is `AGENT_INSTRUCTIONS` in `eventai/agent/review.py`.

2. **Advanced settings:**

   | Setting | Value | Why |
   | --- | --- | --- |
   | Max Iterations | `4` | At most 3 lookups, then the decision. |
   | Number of Chat History Messages | `0` | Each record starts with no memory of the last one. |
   | Current Date | off | Not needed. |
   | Calculator | off | Not needed. |

3. **Output Schema** (advanced, **Open table**): add 6 rows. Each row has the type `str`, and **As List** is off.

   | Name | Description |
   | --- | --- |
   | `attendee_id` | the record ID, for example A06 |
   | `flag` | the flag you decide, exactly as given |
   | `action` | use_value, keep or human_review |
   | `value` | the new value for use_value, copied from the evidence; empty otherwise |
   | `source` | where the value comes from, for example crm.csv#C007 |
   | `reason` | one sentence |

4. At the Agent's output, select **Structured Response** (connection 17).

## Step 5: Run it

1. Click **Playground** (top right).
2. Type `partnersummit2026` and press Enter.
3. Each component turns green when it finishes.
4. The run takes about 1–3 minutes: 13 extraction calls on Groq, then about 5–15 agent calls on OpenRouter.
5. The answer shows the summary: the emails, the attendees, the flags, the resolutions, the capacity and the invitees with no reply.

If a component turns red, click it to see the error, and tell Claude Code. Claude Code can read your flow through the Langflow API, check each connection against this guide, run the flow, score it, and find its Langfuse trace.

## The free limits

- **OpenRouter:** 50 free requests a day. One run uses about 5–15, plus a fallback call when Groq gives a rate limit.
- **Groq:** 8,000 tokens a minute. When Groq gives a rate limit, the run slows down. Extract RSVPs then uses the OpenRouter fallback for that email.
