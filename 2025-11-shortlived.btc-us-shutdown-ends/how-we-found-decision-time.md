The best-supported answer is that the shutdown ended when Trump signed H.R. 5371 at 10:24 p.m. Eastern Standard Time on Wednesday, November 12, 2025, which is:

2025‑11‑13T03:24:00Z (UTC)

So for your CLI, you’d want:

--decision-time "2025-11-13T03:24:00Z"

This is safely inside your metric window [2025‑11‑07T00:00:00Z, 2025‑11‑14T00:00:00Z].

⸻

How I got there (mapping to your step‑by‑step spec)

Step 1 – Identify the law that ended the lapse
The shutdown was ended by:

H.R. 5371 – “Continuing Appropriations, Agriculture, Legislative Branch, Military Construction and Veterans Affairs, and Extensions Act, 2026.”

Congress.gov and related legislative tracking clearly identify this as the continuing resolution/appropriations act that passed the Senate on November 10 and the House on November 12 and was then signed by the president, ending the shutdown.  ￼

The White House / presidency archive confirms that on Wednesday, November 12, 2025, the president signed H.R. 5371 into law.  ￼

So the law is unambiguous; the only real issue is the time of signing.

⸻

Step 2 – Get the signing/enactment time
Official sources (White House press note, Congress.gov, USCIS, etc.) give the date but not the clock time.  ￼

Per your spec, when that happens we fall back to a major wire report (AP / Reuters / Bloomberg) that gives a time, or, if they do not give an exact time, to widely corroborated media reporting.

Here is what different sources say:
	•	AP / Reuters / Bloomberg
	•	AP and Reuters describe the bill being signed “Wednesday night” and mention a scheduled 9:45 p.m. ET signing in the White House schedule, but do not give a precise “signed at HH:MM” timestamp.  ￼
	•	Washington Examiner (newsletter)
	•	Reports that “At 10:15 last night … President Donald Trump signed H.R. 5371”, in a Daily on Defense newsletter dated November 13, clearly referring to the evening of November 12.  ￼
	•	Multiple independent outlets (local TV, newspapers, trade press, blogs)
	•	A whole cluster of outlets state that Trump signed the bill at 10:24 p.m. ET / EST in an Oval Office ceremony, e.g.:
	•	The 2025 shutdown Wikipedia article: “The bill was later signed by president Donald Trump on 10:24 PM EST that same day.”  ￼
	•	Local US TV / news sites (via a shared national story): “Trump signed the measure into law at 10:24 p.m. ET in an Oval Office ceremony.”  ￼
	•	Waterways Journal (trade outlet): “President Donald Trump signed the stopgap measure to reopen the government at 10:24 p.m. Wednesday in the Oval Office…”  ￼
	•	A market/finance recap: “President Donald Trump … signed the bill into law at 10:24 PM EST, officially ending the fiscal crisis.”  ￼
	•	Social/local coverage (e.g. West Virginia Daily News Facebook post) also uses 10:24 PM ET.  ￼

So we have:
	•	One relatively mainstream newsletter with 10:15 (Washington Examiner).
	•	Many independent outlets converging on 10:24 p.m. ET/EST, apparently all drawing from the same underlying pool / network reporting.
	•	Major wires confirming evening of Nov 12 and a scheduled 9:45 p.m. ET signing but not giving the final completed time.

Given that:
	•	The 10:24 p.m. ET time is:
	•	More widely and consistently reported across many outlets, and
	•	Matches the kind of precise time you’d expect from a pool report or network desk note,
	•	While the 10:15 time appears only in a single newsletter and could easily be a rounded/approximate time,

the best, most defensible choice (for a precise timestamp) is:

10:24 p.m. Eastern Standard Time (EST) on November 12, 2025.

In mid‑November the U.S. has already switched back to standard time, so ET = EST = UTC‑5. That gives:
	•	Local time: 2025‑11‑12 22:24 EST
	•	UTC: 22:24 + 5 hours = 2025‑11‑13 03:24:00Z

⸻

Step 3 – Cross‑check OPM Government Operating Status
You also asked to cross‑check OPM:
	•	The OPM “Current Status” page, as of now, shows “Status: Open” for Friday, November 14, 2025, posted at 10:03 AM that day.  ￼
	•	OPM doesn’t show, on that page, the earlier shutdown vs open messages for November 12–13; those are in the “Status Archives,” which are not in the content we can see here.
	•	OPM’s own shutdown contingency guidance says that employees are expected to return to work on the next scheduled duty day after the President signs a funding bill resolving the lapse, and that they learn this via OPM.gov and the media.  ￼

Putting that together:
	•	The legal end of the funding lapse occurs at the moment of presidential signature on H.R. 5371.
	•	Agencies reopen operationally at the start of the next business day (Thursday, November 13, local time), which is consistent with OPM status flipping back to “Open” for that date and for November 14.
	•	Because OPM does not give a precise “effective at HH:MM” time for reopening (it gives a date, occasionally with a posting timestamp), your own rule kicks in:

“If OPM only gives a date with no time, just use the precise signing/enactment time you found in Step 2, confirming the date matches.”

That condition is exactly met here. So the later‑of‑two‑times rule is never triggered, and we stay with the signing time.

⸻

Final decision time (what you likely need)

On your spec:
	•	Event: “earliest moment when funding is restored and agencies are re‑opening”
	•	Decision time must be inside: [2025‑11‑07T00:00:00Z, 2025‑11‑14T00:00:00Z]

The best supported timestamp is:

2025-11-13T03:24:00Z

So in your CLI:

--decision-time "2025-11-13T03:24:00Z"


⸻

If you wanted to double‑check this yourself

If you had to justify this rigorously or re‑derive it:
	1.	Confirm the law on Congress.gov
	•	Search for H.R. 5371 (119th Congress) and confirm its short title and that it’s the bill that passed on November 10 (Senate) and 12 (House) and was presented to/signature by the president.  ￼
	2.	Confirm that it ended the shutdown
	•	Use general coverage / analyses (e.g. Verisk, DLA Piper, EMS trade sites) that explicitly say that signing H.R. 5371 reopened the government and ended the longest shutdown in history.  ￼
	3.	Pin down the time
	•	Collect all mentions of “10:24 p.m. ET/EST” for the signing: local stations, trade papers, and explanatory pieces.  ￼
	•	Compare against the Washington Examiner’s 10:15 and major-wire descriptions that it was a late‑night Oval Office ceremony.  ￼
	•	Prefer the consensus precise time (10:24 p.m.) over the lone 10:15 mention.
	4.	Convert time zone
	•	Treat “p.m. ET / EST” in November as UTC‑5, yielding 03:24:00Z on 2025‑11‑13.
	5.	Check OPM for sanity
	•	Ensure that within a day of that time, the OPM “Current Status” and agency guidance show reopening and “Open” status, which they do.  ￼

⸻

Handy reading (if you want to go deeper)

⸻

If you tell me which exact market / dataset this feeds into, I can sanity‑check any edge‑case rule (for example: what you’d do if some source later revises the time by a few minutes).
