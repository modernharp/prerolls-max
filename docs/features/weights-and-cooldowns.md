# How often and no repeats

## How often an intro plays

Every intro has a **How often** setting from 1 to 10. 5 is normal, 1 is rarely and 10 is often. Press the pencil on a video on **Intro Videos** to change it. It only matters when intros are picked **at random**: random schedules, random rules and random playlist steps.

Prerolls Max still spreads intros out fairly. Think of a bag of tickets where each intro has as many tickets as its setting. An intro set to 10 plays exactly twice as often as one set to 5, and every intro gets its turn before the bag refills. If every intro has the same setting, each one plays once before any plays again.

## Don't repeat within a number of hours

A **collection** or a **rule** can say "don't play the same intro again within 12 hours" (or any number of hours). An intro that played more recently than that is left out, as long as another one can play. If every intro in the collection played recently, the one that played longest ago goes first, so something always plays.

This uses your [play history](play-history.md), so plays on every server count. If play history is turned off, intros can repeat.

## Where these work

| | Plex | Jellyfin | Emby |
|---|---|---|---|
| How often | Yes. An intro set higher is listed more than once in Plex's intro list. | Yes, for every play | Yes, for every play |
| No repeats | Each time Prerolls Max updates Plex's list: when a schedule changes, and every 5 minutes | Yes, for every play | Yes, for every play |

Plex picks from its list by itself, which is why Prerolls Max writes a favourite intro into it more than once. A very long list is cut down to fit Plex's limit, keeping the balance between intros as close as it can.
