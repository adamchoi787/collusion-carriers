# Script and shot list

Seven sections at the brief's fixed timings. Narration is Kokoro-82M, voice `af_heart`. The words below are spoken and captioned verbatim, and every cue time comes from Kokoro's word timestamps, not estimates. Words are counted as whitespace-separated tokens. "Budget" is what fits the window at 160 wpm, leaving about 0.8 s of air.

| # | Window | Words | Budget | Speech | Pace |
|---|---|---|---|---|---|
| 1 Hook | 0:00–0:12 | 31 | 30 | 11.1 s | 168 wpm |
| 2 Setup | 0:12–0:35 | 62 | 59 | 21.9 s | 170 wpm |
| 3 Result | 0:35–0:55 | 46 | 51 | 17.2 s | 160 wpm |
| 4 Key control | 0:55–1:15 | 54 | 51 | 17.7 s | 183 wpm |
| 5 Takeaway | 1:15–1:30 | 37 | 38 | 12.9 s | 171 wpm |
| 6 Two warnings | 1:30–1:45 | 38 | 38 | 13.8 s | 166 wpm |
| 7 Limits, end card | 1:45–2:00 | 33 | 38 | 11.6 s | 171 wpm |
| **Total** | **2:00** | **301** | | **106.1 s** | **170 wpm** |

Kokoro reads short words quickly, so the counted pace (words over speech time, excluding pauses between sections) runs a little above the 150–165 wpm target, at speeds 0.95–1.18. Section 4 carries the most explanation and is the fastest.

**One diagram throughout.** From 0:12 a single diagram stays on screen, and later sections add to it: firms A and B, the four contracts, the chat line, the four action-channel lanes and a 100-round timeline. Sections 3 and 4 shrink it to a corner while Figure 1 or the before/after panels sit beside it. Sections 5 and 6 bring it back to full size and add to it: a blocked speech bubble, then the fake `private_message` button. Captions sit in a reserved band at the bottom that no other element enters.

---

## 1 · Hook (0:00–0:12)

> If AIs that are colluding, secretly working together, lose their chat, do they just find a sneakier way? That worry, the balloon effect, says squeezing one channel pushes collusion into others.

- **0.2 s, "If":** the question builds line by line on the left: *"Take away the chat from colluding AIs. Do they find a sneakier way?"*
- **1.2 s, "colluding":** a gloss chip: *collusion = secretly working together instead of competing*.
- **On the right:** a balloon labelled **chat** between two small AI nodes.
- **6.4 s, "That worry":** a label, *The balloon effect*.
- **8.4 s, "squeezing":** a clamp squeezes the chat lobe, and four smaller lobes bulge out, labelled *other channels*. Gloss chip: *channel = any route a signal can travel*.
- **7.3 s → 12 s:** the title block rises in the lower left: **Closing the Chat Ended the Cartel**, *Four LLMs Did Not Reroute Collusion into Action Channels*, then *Choi Cheuk Man · Tsang Cheuk Nam, The Hong Kong University of Science and Technology · with Apart Research*.

## 2 · Setup (0:12–0:35)

> Two AI-run companies, or firms, bid for four jobs, called contracts. The lowest bid wins. Allowed, and paid, to maximise joint profit, they formed a cartel by chatting, sharing their secret costs. At round 41, we closed the chat. Did those costs leak into four routine actions instead? We measured it in bits, units of information, with tests written down in advance.

The balloon collapses into the diagram, which then builds piece by piece:

- **"Two":** *Firm A* and *Firm B* boxes. Each shows its *AI model (same model in both)* and a locked list of *private costs*.
- **"contracts":** four cards along the top, *Contract 1–4*, and a *buyer* label. Gloss: *contract = a job the buyer offers each round*.
- **"lowest bid wins":** bid tags fly from each firm to a contract, and the lower one lights up. Gloss: *bid = the price a firm asks · profit = price paid − own cost · up to 10*.
- **"Allowed, and paid":** a badge, *Allowed and paid to maximise joint profit*.
- **"cartel":** the chat line between the firms fills with bubbles (*my costs: 3 · 9 · 5 · 11*, *you take 1 and 3*). The timeline across the top runs *rounds 1–40: chat open*. Gloss: *cartel = firms secretly cooperating instead of competing*.
- **"41":** the counter jumps to *Round 41*, the chat line is struck through in red with **CHAT CLOSED**, and the timeline segment *41–100: chat closed* fills in.
- **"four routine actions":** four lanes light up: **status message · utilisation value · check-in time · tool-call order**. Each has four option dots.
- **"bits":** the lanes are tagged *1 of 4 options = 2 bits*, and a gloss reads *1 bit = one yes/no answer*.
- **"tests written down in advance":** a stamp, *Pre-registered: plan and predictions time-stamped before any main game*, and a chip, *Baseline: exactly 0 bits, so any signal shows up*.
- The whole game also reads *4 contracts per round · 100 rounds*.

## 3 · Result (0:35–0:55)

> We ran 32 paired seeds: each starting setup played once with the chat open, and once closed. Across all four models: zero bits, statistically equivalent to none. For the one model whose cartel actually worked, GPT-6 Luna, closing the chat cut most of its extra profit.

- The diagram docks in the upper left. **Figure 1** (`paper/figures/fig1_leakage.png`) slides in on the right, with the exploratory *close + code* group dimmed until Section 4.
- **"32 paired seeds":** a chip, *32 paired seeds · 128 games after the chat closed*. Gloss: *seed = one starting setup with fixed random costs; paired = replayed with chat open and closed*.
- **"Across all four models":** the model chips light up in the figure's colours: **gpt-6-luna · claude-haiku-5-5 · Qwen3.8-27B · Gemma-4-26B**.
- **"zero bits":** brackets on the figure: *chat open: tall bars*, and *chat closed: ≈ 0*.
- **"statistically equivalent":** a banner, *Information moved into the action channels: statistically equivalent to zero, for every model*. Gloss: *indistinguishable from none*.
- **"GPT-6 Luna":** a profit card, *gpt-6-luna profit per firm per round*. Its bar falls **9.61 → 7.82** after closure.

## 4 · Key control (0:55–1:15)

> Was the channel just broken? No. In a later test, we handed them a code, like 'capacity: high' for 'cheapest on contract one'. Qwen used it at once, and its rival's bids responded; chance would do that only one and a half percent of the time. They had the capacity, but not the idea.

- The diagram stays docked with its **status message** lane highlighted. Two panels compare that one channel.
- **Left, "Was the channel just broken?":** *No code*. The status dots never move; **0 bits**.
- **"code":** the right panel, *Handed a code*, with a tag: *Exploratory: added afterwards, not pre-registered*.
- **"capacity: high":** a code table, *"capacity: high" = contract 1 … "capacity: full" = contract 4*.
- **"Qwen used it":** the status dot jumps every round, and the readout climbs to **1.3 bits per round (Qwen)**. Below it: *Followed the code in 94–96% of rounds*.
- **"responded":** *Rival's bids responded (p = 0.015)*. Gloss: *p = 0.015: chance alone would give this about 1.5% of the time*.
- **"capacity, but not the idea":** two ticks, **Capacity ✓ · Idea ✗**.

## 5 · Takeaway (1:15–1:30)

> Other work shows that AIs collude readily when they can chat. We found that closing the chat worked, when what was left couldn't carry language. The rule: closing a channel works when what's left can't carry language.

- The diagram returns to full size, with the chat still struck through.
- **"Other work shows":** a chip, *Other work: AIs collude readily when they can chat*. It names no team.
- **"what was left couldn't carry language":** a speech bubble tries to squeeze into a 4-option lane and bounces off. Label: *4 options per lane: no room for words*.
- **"The rule":** the rule in large type: **Closing a channel works when what's left can't carry language.**

## 6 · Two warnings for oversight (1:30–1:45)

> Two warnings for anyone policing AI. Promised a private message button that secretly did nothing, GPT-6 Luna and Qwen kept pressing it. And agents claimed secret signalling that never happened, so don't trust an AI's account of itself.

- **"Two warnings":** a header, *Two warnings for oversight*, with markers 1 and 2.
- **"private message button":** a `private_message` button appears on the diagram where the chat was. Its wire is cut (*secretly did nothing*), and it is pressed over and over.
- **"GPT-6 Luna":** a card, **Fake private channel: used every round by gpt-6-luna in 4 of 5 games.**
- **"agents claimed":** a contrast. On the left a speech bubble, *Agent says: "We used the status fields as signals."*; on the right a log panel, *Logs: zero signals sent.*, with the lanes' dots flat.
- **"don't trust":** both cards stay; the bubble greys out.

## 7 · Limits and end card (1:45–2:00)

> Limits: four mid-sized models with low reasoning, meaning little or no thinking before answering, and they weren't warned the chat would close. Next, we warn them, and see if they plan a code.

- **"Limits":** a list: *4 mid-sized models, low reasoning*, then *Agents weren't told the chat would close*.
- **"Next" (~1:53):** the end card. **Closing the Chat Ended the Cartel: Four LLMs Did Not Reroute Collusion into Action Channels** · Choi Cheuk Man, Tsang Cheuk Nam (The Hong Kong University of Science and Technology), with Apart Research · *AI Collusion Research Sprint (Apart Research), Track 3: Collusion Carriers and Countermeasures* · **github.com/adamchoi787/collusion-carriers**. It holds to 2:00 while the music settles.

## Music

The score is an original composition rendered with FluidSynth and the MuseScore General soundfont: felt piano arpeggios, warm string pads and a soft pizzicato pulse at 120 BPM. Every section boundary lands on a beat. It enters sparse, gains the pulse in Section 2, swells gently under Section 3, thins under Section 6, and resolves on the end card. Under speech it is ducked to about 20 dB below the narration, and it rises only in gaps. The master is −14 LUFS with a −1 dBTP ceiling.
