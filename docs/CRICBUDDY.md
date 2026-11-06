# CricBuddy

**A cricket companion that sits alongside a live match and tells you what to
watch for, before it happens.**

Status: in development. The data and analysis foundations are built; the live
app is not. Section 5 shows exactly where each part stands.

## 1. The problem

A lot of people would like to enjoy cricket, but without context it looks like
the same thing again and again: a bowler bowls, a batter hits or doesn't. The
interest lies in details most viewers never see. This batter scores freely off
pace but gets stuck against off-spin. That bowler beats left-handers by angling
the ball across them. Experts carry this knowledge in their heads. Most fans
don't, and nobody can learn it all.

## 2. The idea

CricBuddy does that remembering for you. While you watch, it follows the match
and, when a matchup comes up that history has something to say about, it tells
you in plain language what to look out for:

> **Watch this over.** An off-spinner is coming on, and Ishan Kishan has
> struggled against off-spin in the middle overs. Expect him to slow down, or
> to take a risk.

Then the over plays out. Sometimes the batter gets out, sometimes he just
can't score, and sometimes he breaks the pattern. Either way, the fan now has
a reason to watch each ball closely. That is the point: the game gets more
interesting when you know what's at stake in the contest.

Calls can go the other way too. A batter may be hitting sixes freely, but
history says a certain length or line keeps him quiet, so watch whether the
bowler finds it.

The fan can also ask questions, such as "Is bringing on the leg-spinner a good
idea here?", and get an answer with the evidence behind it.

## 3. A real example from the data

The callout above isn't invented. Here is Ishan Kishan's IPL record from 2021
to 2026, in overs 7 to 15, against each bowling type, from the 426 IPL matches
in this project. Wides are not counted as balls faced.

| Bowling type | Balls | Runs | Strike rate | Dismissals | Dot balls |
|---|---|---|---|---|---|
| Off-break | 125 | 123 | **98.4** | 4 | 33.6% |
| Leg-break | 158 | 213 | 134.8 | 9 | 28.5% |
| Fast-medium | 77 | 104 | 135.1 | 5 | 27.3% |
| Fast | 85 | 134 | 157.6 | 10 | 34.1% |
| Left-arm orthodox | 87 | 141 | 162.1 | 2 | 20.7% |
| Medium | 82 | 135 | 164.6 | 3 | 14.6% |

His overall IPL strike rate in this data is about 147. Against off-spin in the
middle overs it falls to 98, over 125 balls. That's a real, checkable pattern,
and exactly the kind CricBuddy is meant to surface. The other side is just as
important: 125 balls is a fair sample, but 4 dismissals is not enough to say he
gets *out* to off-spin. CricBuddy would say he slows down, not that he falls.

## 4. How it works

The rule throughout: **the data retrieves, Python calculates, and AI only
explains.** A language model never makes up a number.

1. **Collect** (built). Ball-by-ball commentary from ESPNcricinfo, collected by
   this project's own Python scripts, joined to Cricsheet's open ball-by-ball
   records. Coverage: top-10 international ODIs and T20Is since 2021, and the
   IPL 2021 to 2026, with BBL, SA20, CPL and The Hundred being collected.
2. **Sort into buckets** (built). Each ball is tagged with batting hand,
   bowler's arm and type (pace or spin, off-break, leg-break, left-arm orthodox,
   wrist spin, fast to medium), phase of the innings, match situation, venue
   and season. The commentary adds length, line, shot and slower balls where it
   mentions them. `ANALYSIS_PLAN.md` lists which splits the data supports.
3. **Find the patterns** (in progress). For every batter and bowler type,
   compare their numbers with their own baseline and with the average player
   in the same situation. Thin samples are pulled towards the baseline, so a
   handful of big hits doesn't look like a trend. A type must pass minimum
   sample sizes before it can be called a strength or weakness. This is the
   `cricketiq` engine in this repository.
4. **Replay past matches** (planned). Before going live, run CricBuddy ball by
   ball through matches it hasn't seen, as if they were live. Record every call
   it would have made and what actually happened. This gives an honest hit rate
   before any fan sees a call.
5. **Go live** (planned). Follow a live match's ball-by-ball feed, spot when a
   known matchup is about to happen (a bowling change, a new batter), and raise
   the call before the over.
6. **Conversation** (planned). A language model turns the evidence into plain
   language and answers fans' questions, citing the numbers and sample sizes
   behind each answer.

## 5. Where it stands

| Stage | Status |
|---|---|
| Data collection | Built: about 1,280 matches and 400,000 deliveries of commentary, plus Cricsheet records for every match |
| Player styles | Built: batting hand and bowling type for 1,173 players |
| Linking commentary to match records | Built: 98% of IPL deliveries linked by player ID |
| Pattern engine | In progress: baselines, matchup profiles, sample-size rules |
| Replay testing | Planned |
| Live match feed | Planned |
| Conversational app | Planned |

## 6. What CricBuddy is not

- **Not a betting tool.** It's for fans' enjoyment and understanding.
- **Not a crystal ball.** A call is a likelihood with its evidence, never a
  promise. When the evidence is thin, it says so, or says nothing.

## 7. Why I'm building it

Two reasons. The first is cricket: I want more people to enjoy watching it,
and I think context is what's missing. The second is professional. My
background is engineering and business development, and this project is how
I'm building hands-on skills in Python, SQL and AI workflows.
The method carries straight over to business. Predicting whether a batter will
struggle against off-spin is the same shape of problem as predicting whether a
customer will respond to an offer. You collect the history, find patterns that
hold up, make a call, then check it against what actually happened.

## 8. Names in this repository

**CricBuddy** is the product. **`cricketiq`** is the analysis engine inside it
(the Python package). The data collector is the set of scripts at the top
level of the repository.
